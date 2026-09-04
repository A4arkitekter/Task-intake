from __future__ import annotations

import json
import logging
import os
import re
import threading
from typing import Any

import httpx

from app.config import LLM_BASE_URL, LLM_MODEL, LLM_TIMEOUT_SEC

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


def _complete(transcript: str) -> str:
    payload = {
        "model": LLM_MODEL,
        "stream": False,
        "format": "json",
        "keep_alive": "1h",
        "options": {"temperature": 0.1, "num_predict": 200, "num_ctx": 2048},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": transcript},
        ],
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
