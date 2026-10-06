from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

API_BASE = os.getenv("WRIKE_API_BASE", "https://www.wrike.com/api/v4").rstrip("/")
_HEALTH_TTL_SEC = 30.0
_health_cache: dict[str, Any] = {"at": 0.0, "value": None}


class WrikeError(RuntimeError):
    pass


def client_id() -> str:
    return (os.getenv("WRIKE_CLIENT_ID") or "").strip()


def client_secret() -> str:
    return (os.getenv("WRIKE_CLIENT_SECRET") or os.getenv("WRIKE_SECRET_KEY") or "").strip()


def token() -> str:
    return (os.getenv("WRIKE_TOKEN") or "").strip()


def token_is_set() -> bool:
    return bool(token())


def credentials_are_set() -> bool:
    return bool(token()) or (bool(client_id()) and bool(client_secret()))


def _request(method: str, path: str, payload: dict | None = None) -> dict[str, Any]:
    secret = token()
    if not secret:
        if client_id() and client_secret():
            raise WrikeError(
                "Client ID og Secret Key er sat, men Wrike-API'et bruger et Permanent Access Token. "
                "Klik Get token på samme Wrike-side og sæt WRIKE_TOKEN i .env."
            )
        raise WrikeError("Wrike-nøgle mangler. Sæt Client ID, Secret Key og token i .env.")
    url = f"{API_BASE}{path}"
    data = None
    headers = {"Authorization": f"Bearer {secret}", "Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise WrikeError(f"Wrike svarede {exc.code}: {detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise WrikeError(f"Kunne ikke nå Wrike: {exc.reason}") from exc
    if not body:
        return {}
    try:
        parsed = json.loads(body)
    except ValueError as exc:
        raise WrikeError("Wrike sendte ugyldigt JSON") from exc
    if not isinstance(parsed, dict):
        raise WrikeError("Wrike sendte et uventet svar")
    return parsed


def health(*, force: bool = False) -> dict[str, Any]:
    now = time.monotonic()
    cached = _health_cache.get("value")
    if not force and cached and now - float(_health_cache.get("at") or 0) < _HEALTH_TTL_SEC:
        return cached
    if not token_is_set():
        if client_id() and client_secret():
            message = (
                "Client ID er sat. Klik Get token på samme Wrike-side og sæt WRIKE_TOKEN i .env."
            )
        elif client_id() or client_secret():
            message = "Udfyld både WRIKE_CLIENT_ID og WRIKE_CLIENT_SECRET i .env."
        else:
            message = "Wrike-nøgle mangler. Sæt Client ID, Secret Key og token i .env."
        value = {"ok": False, "level": "red", "message": message}
        _health_cache["at"] = now
        _health_cache["value"] = value
        return value
    try:
        _request("GET", "/contacts")
        value = {
            "ok": True,
            "level": "green",
            "message": "API er i orden.",
        }
    except WrikeError as exc:
        value = {"ok": False, "level": "red", "message": str(exc)}
    _health_cache["at"] = now
    _health_cache["value"] = value
    return value


def list_folders(*, query: str = "") -> list[dict[str, str]]:
    payload = _request("GET", "/folders")
    rows: list[dict[str, str]] = []
    needle = query.strip().casefold()
    for item in payload.get("data") or []:
        if not isinstance(item, dict):
            continue
        if item.get("deleted") or item.get("recycled"):
            continue
        folder_id = str(item.get("id") or "").strip()
        title = str(item.get("title") or "").strip() or folder_id
        if not folder_id:
            continue
        if needle and needle not in title.casefold():
            continue
        rows.append({"id": folder_id, "title": title})
    rows.sort(key=lambda row: row["title"].casefold())
    return rows


def pick_default_folder(folders: list[dict[str, str]]) -> dict[str, str] | None:
    preferred = ("indbakke", "inbox", "backlog", "opgaver", "tasks")
    for row in folders:
        title = row["title"].casefold()
        if any(word in title for word in preferred):
            return row
    return folders[0] if folders else None


def _display_name(person: dict[str, Any]) -> str:
    first = str(person.get("firstName") or "").strip()
    last = str(person.get("lastName") or "").strip()
    return " ".join(part for part in (first, last) if part)


def list_contacts(*, query: str = "") -> list[dict[str, str]]:
    payload = _request("GET", "/contacts")
    rows: list[dict[str, str]] = []
    needle = query.strip().casefold()
    for item in payload.get("data") or []:
        if not isinstance(item, dict) or item.get("deleted"):
            continue
        kind = str(item.get("type") or "Person").strip() or "Person"
        if kind.casefold() != "person":
            continue
        contact_id = str(item.get("id") or "").strip()
        if not contact_id:
            continue
        name = _display_name(item)
        email = ""
        for profile in item.get("profiles") or []:
            if isinstance(profile, dict):
                email = str(profile.get("email") or "").strip()
                if email:
                    break
        title = name or email or contact_id
        if name and email:
            title = f"{name} ({email})"
        haystack = f"{name} {email} {title}".casefold()
        if needle and needle not in haystack:
            continue
        rows.append({"id": contact_id, "title": title, "name": name or title})
    rows.sort(key=lambda row: row["title"].casefold())
    return rows


def create_task(
    *,
    title: str,
    description: str,
    folder_id: str,
    importance: str = "High",
    responsible_id: str = "",
    responsible_name: str = "",
) -> dict[str, str]:
    folder_id = folder_id.strip()
    if not folder_id:
        raise WrikeError("Vælg en Wrike-mappe i administrationen.")
    owner_id = responsible_id.strip()
    owner_name = responsible_name.strip() or owner_id
    if not owner_id:
        raise WrikeError("Vælg en ansvarlig i administrationen.")
    level = importance if importance in {"High", "Normal", "Low"} else "High"
    payload = _request(
        "POST",
        f"/folders/{urllib.parse.quote(folder_id, safe='')}/tasks",
        {
            "title": (title or "Ny idé").strip() or "Ny idé",
            "description": (description or "").strip(),
            "importance": level,
            "responsibles": [owner_id],
        },
    )
    data = payload.get("data") or []
    task = data[0] if data and isinstance(data[0], dict) else {}
    task_id = str(task.get("id") or "").strip()
    permalink = str(task.get("permalink") or "").strip()
    if not task_id:
        raise WrikeError("Wrike oprettede opgaven, men svarede uden id.")
    logger.info("Wrike-opgave %s (%s) tildelt %s", task_id, level, owner_name)
    return {"id": task_id, "url": permalink, "importance": level, "assignee": owner_name}
