from __future__ import annotations

import logging
import time

from app import db, settings, wrike
from app.rewrite import status as rewrite_status
from app.transcribe import status as whisper_status

logger = logging.getLogger(__name__)

_INBOX_HEALTH_TTL_SEC = 45.0
_inbox_health_cache: dict = {"at": 0.0, "path": "", "value": None}


def _lamp(level: str, message: str, *, ok: bool | None = None) -> dict:
    return {"level": level, "ok": True if ok is None else ok, "message": message}


def inbox_health(*, force: bool = False) -> dict:
    """Må ikke scanne OneDrive på hvert poll — stat() på skyfiler kan fryse siden i 20 sekunder."""
    path = settings.inbox_dir()
    now = time.monotonic()
    cached = _inbox_health_cache.get("value")
    if (
        not force
        and cached
        and _inbox_health_cache.get("path") == str(path)
        and now - float(_inbox_health_cache.get("at") or 0) < _INBOX_HEALTH_TTL_SEC
    ):
        return cached
    if not path.exists():
        value = _lamp("red", f"Mappen findes ikke: {path}", ok=False)
    elif not path.is_dir():
        value = _lamp("red", "Stien er ikke en mappe.", ok=False)
    else:
        value = _lamp("green", f"Overvåger {path}")
    _inbox_health_cache["at"] = now
    _inbox_health_cache["path"] = str(path)
    _inbox_health_cache["value"] = value
    return value


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


def ensure_default_assignee(data: dict) -> dict:
    if not wrike.token_is_set():
        return data
    identity = wrike.token_identity()
    if not identity:
        return data
    if (
        data.get("wrike_assignee_id") == identity["id"]
        and data.get("wrike_assignee_name") == identity["name"]
    ):
        return data
    return settings.save(
        {
            "wrike_assignee_id": identity["id"],
            "wrike_assignee_name": identity["name"],
        }
    )


def ensure_default_folder(data: dict) -> dict:
    if data.get("wrike_folder_id") or not wrike.credentials_are_set():
        return data
    if not wrike.token_identity():
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
    return ensure_default_folder(ensure_default_assignee(settings.load()))


def payload() -> dict:
    data = public_settings()
    identity = wrike.token_identity() if wrike.token_is_set() else None
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
            "wrike_token_owner": str((identity or {}).get("label") or ""),
            "wrike_token_owner_id": str((identity or {}).get("id") or ""),
            "wrike_keys_ready": wrike.credentials_complete(),
            "remind_to": data.get("remind_to") or "",
        },
        "health": {
            "wrike": wrike.health(),
            "inbox": inbox_health(),
            "behandling": processing_health(),
        },
        "jobs": db.list_catalog(days=30),
        "waiting": len(db.list_waiting()),
    }


def pulse() -> dict:
    return {
        "ok": True,
        "health": {
            "wrike": wrike.health(),
            "inbox": inbox_health(),
            "behandling": processing_health(),
        },
        "jobs": db.list_catalog(days=30, transcripts=False),
        "waiting": len(db.list_waiting()),
    }
