from __future__ import annotations

import json
import logging
import os
import re
import threading
from typing import Any

import httpx

from app.config import LLM_BASE_URL, LLM_KEEP_ALIVE, LLM_MODEL, LLM_TIMEOUT_SEC

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Du retter en dansk talegenkendelse og laver én opgave.

Svar KUN med JSON: {"title":"...","note":"..."}

Regler for title:
- Kort overskrift, max 70 tegn
- Som en opgave i Wrike: konkret, uden fyld
- ALDRIG start med "Jeg har en idé" og ALDRIG en afkortet rå transskript

Regler for note:
- 1-2 sætninger der gengiver det, personen faktisk sagde, på korrekt dansk
- Ret kun indlysende talegenkendelsesfejl ud fra sammenhæng
- Fjern fyldord og indledninger
- Opfind IKKE extra mål, kategorier, metoder eller facts

Eksempel:
Tekst: Jeg har en idé, der handler om, at vi fremover os, skal sortere vores affald i købnet
Svar: {"title":"Fremtidig affaldssortering i køkkenet","note":"Vi skal fremover sortere vores affald i køkkenet."}
"""

LONG_NOTE_PROMPT = """\
Teksten er en lang indtaling. Note skal derfor være et referat på 3-10 sætninger.
Bevar alle konkrete punkter, navne, tal og datoer. Udelad intet, du ikke selv ville
kunne gætte. Title skal stadig være én kort overskrift for hele indtalingen.
"""

# Over denne længde er en note på to sætninger et tab af information, ikke en oprydning.
LONG_INPUT_CHARS = 800

# Ollamas KV-cache vokser med num_ctx — omkring 0,2 MB per token for en 14b-model.
# Et 12 GB kort, der også holder Whisper, kan ikke bære mere end dette.
MAX_CONTEXT = 8192
# Det der er plads til i MAX_CONTEXT, når systemprompt og svar er trukket fra.
MAX_TRANSCRIPT_CHARS = 20_000

_lock = threading.Lock()
_status = "idle"
_error: str | None = None
FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def status() -> dict[str, str | None]:
    return {"rewrite": _status, "rewrite_model": LLM_MODEL, "rewrite_error": _error}


def _enabled() -> bool:
    return os.getenv("LLM_ENABLED", "1").lower() not in {"0", "false", "no"}


def rewrite_idea(transcript: str) -> dict[str, str] | None:
    text = (transcript or "").strip()
    if not text or not _enabled():
        return None
    if not _ensure_ready():
        return None
    try:
        raw = _complete(text)
        card = parse_card(raw)
        if card:
            logger.info("LLM-kort: %s", card["title"])
        return card
    except Exception as exc:
        logger.exception("LLM-omskrivning fejlede")
        _set_status("error", str(exc))
        return None


def parse_card(raw: str) -> dict[str, str] | None:
    text = FENCE.sub("", (raw or "").strip()).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data: Any = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    title = str(data.get("title") or "").strip()
    note = str(data.get("note") or "").strip()
    if not title or not note:
        return None
    if not note.endswith((".", "!", "?")):
        note += "."
    return {"title": title[:80].rstrip(" .,;:"), "note": note}


def _ensure_ready() -> bool:
    global _status, _error
    if not _enabled():
        _set_status("disabled", None)
        return False
    with _lock:
        if _status == "ready":
            return True
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{LLM_BASE_URL}/api/tags")
                response.raise_for_status()
                names = [item.get("name") for item in response.json().get("models") or []]
            if LLM_MODEL not in names and f"{LLM_MODEL}:latest" not in names:
                _status = "unavailable"
                _error = f"Ollama-modellen {LLM_MODEL} er ikke installeret"
                logger.warning("%s", _error)
                return False
            _status = "ready"
            _error = None
            return True
        except Exception as exc:
            _status = "unavailable"
            _error = str(exc)
            logger.warning("Ollama er ikke klar: %s", exc)
            return False


def context_size(transcript: str) -> int:
    """Ollama afkorter prompten lydløst ved num_ctx, så en lang indtaling ville miste slutningen."""
    tokens = (len(SYSTEM_PROMPT) + len(LONG_NOTE_PROMPT) + len(transcript)) // 3
    needed = tokens + 1024
    for size in (2048, 4096, MAX_CONTEXT):
        if needed <= size:
            return size
    return MAX_CONTEXT


def fit_transcript(transcript: str) -> str:
    """Er teksten længere end vinduet, forkortes den synligt i stedet for lydløst.

    Begyndelsen og slutningen beholdes, fordi det vigtigste i en indtaling ofte
    siges allersidst.
    """
    if len(transcript) <= MAX_TRANSCRIPT_CHARS:
        return transcript
    head = MAX_TRANSCRIPT_CHARS * 2 // 3
    tail = MAX_TRANSCRIPT_CHARS - head
    logger.warning(
        "Transskriptionen er %s tegn. Midten udelades, så slutningen ikke falder ud.",
        len(transcript),
    )
    return f"{transcript[:head]}\n[... midten er udeladt ...]\n{transcript[-tail:]}"


def _complete(raw_transcript: str) -> str:
    transcript = fit_transcript(raw_transcript)
    long_input = len(transcript) > LONG_INPUT_CHARS
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if long_input:
        messages.append({"role": "system", "content": LONG_NOTE_PROMPT})
    messages.append({"role": "user", "content": transcript})
    payload = {
        "model": LLM_MODEL,
        "stream": False,
        "format": "json",
        "keep_alive": LLM_KEEP_ALIVE,
        "options": {
            "temperature": 0.1,
            "num_predict": 900 if long_input else 200,
            "num_ctx": context_size(transcript),
        },
        "messages": messages,
    }
    with httpx.Client(timeout=LLM_TIMEOUT_SEC) as client:
        response = client.post(f"{LLM_BASE_URL}/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()
    return str((data.get("message") or {}).get("content") or "")


def _set_status(value: str, error: str | None) -> None:
    global _status, _error
    with _lock:
        _status = value
        _error = error
