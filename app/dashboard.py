from __future__ import annotations

import logging

from app import db, settings, wrike
from app.rewrite import status as rewrite_status
from app.transcribe import status as whisper_status

logger = logging.getLogger(__name__)


def _lamp(level: str, message: str, *, ok: bool | None = None) -> dict:
    return {"level": level, "ok": True if ok is None else ok, "message": message}


def inbox_health() -> dict:
    path = settings.inbox_dir()
    if not path.exists():
        return _lamp("red", f"Mappen findes ikke: {path}", ok=False)
    if not path.is_dir():
        return _lamp("red", "Stien er ikke en mappe.", ok=False)
    try:
        probe = path / ".intake-write-check"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError:
        return _lamp("red", f"Mappen kan ikke skrives: {path}", ok=False)
    from app.watch import AUDIO_SUFFIXES

    audio = 0
    empty = 0
    try:
        for item in path.iterdir():
            if not item.is_file() or item.suffix.lower() not in AUDIO_SUFFIXES:
                continue
            audio += 1
            try:
                if item.stat().st_size <= 0:
                    empty += 1
            except OSError:
                empty += 1
    except OSError:
        return _lamp("yellow", f"Mappen kan ikke læses: {path}", ok=False)
    if audio and empty == audio:
        return _lamp(
            "yellow",
            "Kun tomme pladsholdere. Hold mappen lokal i OneDrive, ellers springes filerne over.",
            ok=False,
        )
    return _lamp("green", f"Overvåger {path}")


def whisper_health() -> dict:
    data = whisper_status()
    state = str(data.get("whisper") or "idle")
    error = str(data.get("error") or "").strip()
    model = str(data.get("whisper_model") or "")
    if state == "error":
        return _lamp("red", error or "Whisper kunne ikke starte.", ok=False)
    if state == "loading":
        return _lamp("yellow", "Whisper indlæses første gang.", ok=False)
    extra = f" ({model})" if model else ""
    return _lamp("green", f"Whisper er klar{extra}.")


def ollama_health() -> dict:
    data = rewrite_status()
    state = str(data.get("rewrite") or "idle")
    error = str(data.get("rewrite_error") or "").strip()
    model = str(data.get("rewrite_model") or "")
    if state == "error":
        return _lamp("red", error or "Ollama svarede ikke.", ok=False)
    if state == "unavailable":
        return _lamp(
            "yellow",
            f"Ollama kører ikke. Overskrifter bruger rå tekst, indtil {model or 'modellen'} er i gang.",
            ok=False,
        )
    extra = f" ({model})" if model else ""
    return _lamp("green", f"Ollama er klar{extra}.")


def processing_health() -> dict:
    whisper = whisper_health()
    ollama = ollama_health()
    rank = {"green": 0, "yellow": 1, "red": 2}
    level = whisper["level"] if rank.get(whisper["level"], 0) >= rank.get(ollama["level"], 0) else ollama["level"]
    parts = []
    for lamp in (whisper, ollama):
        text = str(lamp.get("message") or "").strip()
        if text and text not in parts:
            parts.append(text)
    return _lamp(level, " ".join(parts) or "Behandling ukendt", ok=bool(whisper.get("ok") and ollama.get("ok")))


def ensure_default_folder(data: dict) -> dict:
    if data.get("wrike_folder_id") or not wrike.credentials_are_set():
        return data
    try:
        folders = wrike.list_folders()
    except wrike.WrikeError as exc:
        logger.info("Kunne ikke vælge standardmappe i Wrike: %s", exc)
        return data
    picked = wrike.pick_default_folder(folders)
    if not picked:
        return data
    saved = settings.save(
        {
            "wrike_folder_id": picked["id"],
            "wrike_folder_name": picked["title"],
        }
    )
    saved["wrike_folder_defaulted"] = True
    return saved


def public_settings() -> dict:
    return ensure_default_folder(settings.load())


def payload(*, jobs: int = 40) -> dict:
    data = public_settings()
    return {
        "ok": True,
        "settings": {
            "inbox_dir": data["inbox_dir"],
            "wrike_folder_id": data["wrike_folder_id"],
            "wrike_folder_name": data["wrike_folder_name"],
            "wrike_importance": data["wrike_importance"],
            "wrike_folder_defaulted": bool(data.get("wrike_folder_defaulted")),
            "wrike_assignee_id": data["wrike_assignee_id"],
            "wrike_assignee_name": data["wrike_assignee_name"],
        },
        "health": {
            "wrike": wrike.health(),
            "inbox": inbox_health(),
            "behandling": processing_health(),
        },
        "jobs": db.list_jobs(limit=jobs),
        "waiting": len(db.list_waiting()),
    }
