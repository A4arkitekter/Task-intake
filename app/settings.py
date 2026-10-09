from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from app.config import DATA_DIR, INBOX_DIR

SETTINGS_PATH = DATA_DIR / "admin-settings.json"
IMPORTANCE_CHOICES = ("High", "Normal", "Low")
_lock = threading.Lock()

_DEFAULTS = {
    "inbox_dir": "",
    "remind_to": "",
    "wrike_folder_id": "",
    "wrike_folder_name": "",
    "wrike_importance": "High",
    "wrike_assignee_id": "",
    "wrike_assignee_name": "",
}


def _defaults() -> dict:
    data = dict(_DEFAULTS)
    data["inbox_dir"] = str(INBOX_DIR)
    return data


def load() -> dict:
    with _lock:
        data = _defaults()
        if SETTINGS_PATH.is_file():
            try:
                raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8-sig"))
                if isinstance(raw, dict):
                    data.update({key: raw[key] for key in _DEFAULTS if key in raw})
            except (OSError, ValueError):
                pass
        importance = str(data.get("wrike_importance") or "High").strip().title()
        data["wrike_importance"] = importance if importance in IMPORTANCE_CHOICES else "High"
        inbox = str(data.get("inbox_dir") or "").strip().strip('"')
        data["inbox_dir"] = inbox or str(INBOX_DIR)
        data["wrike_folder_id"] = str(data.get("wrike_folder_id") or "").strip() or (
            os.getenv("WRIKE_FOLDER_ID") or ""
        ).strip()
        data["wrike_folder_name"] = str(data.get("wrike_folder_name") or "").strip()
        data["wrike_assignee_id"] = str(data.get("wrike_assignee_id") or "").strip()
        data["wrike_assignee_name"] = str(data.get("wrike_assignee_name") or "").strip()
        remind_to = str(data.get("remind_to") or "").strip()
        data["remind_to"] = remind_to or (os.getenv("REMIND_TO") or os.getenv("MAIL_CC") or "").strip()
        return data


def save(updates: dict) -> dict:
    data = load()
    if "inbox_dir" in updates:
        inbox = str(updates.get("inbox_dir") or "").strip().strip('"')
        if not inbox:
            raise ValueError("Stien til optagelser må ikke være tom")
        data["inbox_dir"] = inbox
    if "wrike_folder_id" in updates:
        data["wrike_folder_id"] = str(updates.get("wrike_folder_id") or "").strip()
    if "wrike_folder_name" in updates:
        data["wrike_folder_name"] = str(updates.get("wrike_folder_name") or "").strip()
    if "wrike_importance" in updates:
        importance = str(updates.get("wrike_importance") or "High").strip().title()
        if importance not in IMPORTANCE_CHOICES:
            raise ValueError("Prioritet skal være High, Normal eller Low")
        data["wrike_importance"] = importance
    if "wrike_assignee_id" in updates:
        data["wrike_assignee_id"] = str(updates.get("wrike_assignee_id") or "").strip()
    if "wrike_assignee_name" in updates:
        data["wrike_assignee_name"] = str(updates.get("wrike_assignee_name") or "").strip()
    if "remind_to" in updates:
        mail = str(updates.get("remind_to") or "").strip()
        if mail and "@" not in mail:
            raise ValueError("Skriv en gyldig arbejdmail, for eksempel navn@a4.dk")
        data["remind_to"] = mail
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def inbox_dir() -> Path:
    return Path(load()["inbox_dir"])


def wrike_folder_id() -> str:
    return load()["wrike_folder_id"]


def wrike_importance() -> str:
    return load()["wrike_importance"]


def wrike_assignee() -> tuple[str, str]:
    data = load()
    return data["wrike_assignee_id"], data["wrike_assignee_name"]
