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
_LIST_TTL_SEC = 60.0
_health_cache: dict[str, Any] = {"at": 0.0, "value": None}
_folders_cache: dict[str, Any] = {"at": 0.0, "value": None}
_contacts_cache: dict[str, Any] = {"at": 0.0, "value": None}
_spaces_cache: dict[str, Any] = {"at": 0.0, "value": None}
_SPACES_FIELDS = urllib.parse.quote(json.dumps(["members"]), safe="")


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
        with urllib.request.urlopen(request, timeout=12) as response:
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
        contacts = _request("GET", "/contacts")
        _contacts_cache["at"] = now
        _contacts_cache["value"] = contacts
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


def _cached_list(cache: dict[str, Any], path: str) -> dict[str, Any]:
    now = time.monotonic()
    cached = cache.get("value")
    if cached and now - float(cache.get("at") or 0) < _LIST_TTL_SEC:
        return cached
    payload = _request("GET", path)
    cache["at"] = now
    cache["value"] = payload
    return payload


def _contact_index(payload: dict[str, Any]) -> tuple[dict[str, str], str]:
    names: dict[str, str] = {}
    me_id = ""
    for item in payload.get("data") or []:
        if not isinstance(item, dict) or item.get("deleted"):
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
        names[contact_id] = name or email or contact_id
        if item.get("me"):
            me_id = contact_id
    return names, me_id


def _space_index(payload: dict[str, Any], names: dict[str, str], me_id: str) -> dict[str, dict[str, Any]]:
    spaces: dict[str, dict[str, Any]] = {}
    for item in payload.get("data") or []:
        if not isinstance(item, dict):
            continue
        space_id = str(item.get("id") or "").strip()
        if not space_id:
            continue
        members = [m for m in (item.get("members") or []) if isinstance(m, dict)]
        owner_id = ""
        for member in members:
            if member.get("isManager") or member.get("isOwner"):
                owner_id = str(member.get("id") or "").strip()
                if owner_id:
                    break
        if not owner_id and members:
            owner_id = str(members[0].get("id") or "").strip()
        member_ids = {str(member.get("id") or "").strip() for member in members}
        member_ids.discard("")
        access = str(item.get("accessType") or "").strip()
        spaces[space_id] = {
            "id": space_id,
            "title": str(item.get("title") or "").strip(),
            "access": access,
            "owner": names.get(owner_id, ""),
            "owner_id": owner_id,
            "member_ids": member_ids,
            "mine": bool(me_id and me_id in member_ids),
        }
    return spaces


def _parent_map(items: list[dict[str, Any]]) -> dict[str, str]:
    parent: dict[str, str] = {}
    for item in items:
        folder_id = str(item.get("id") or "").strip()
        if not folder_id:
            continue
        for child in item.get("childIds") or []:
            child_id = str(child or "").strip()
            if child_id and child_id not in parent:
                parent[child_id] = folder_id
    return parent


def _space_for(folder_id: str, parent: dict[str, str], spaces: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    seen: set[str] = set()
    current = folder_id
    while current and current not in seen:
        if current in spaces:
            return spaces[current]
        seen.add(current)
        current = parent.get(current, "")
    return None


def _folder_path(folder_id: str, by_id: dict[str, dict[str, Any]], parent: dict[str, str]) -> str:
    titles: list[str] = []
    seen: set[str] = set()
    current = parent.get(folder_id, "")
    while current and current not in seen:
        seen.add(current)
        node = by_id.get(current) or {}
        title = str(node.get("title") or "").strip()
        scope = str(node.get("scope") or "")
        if title and title.casefold() not in {"root", "recycle bin"} and scope != "RbFolder":
            titles.append(title)
        current = parent.get(current, "")
    titles.reverse()
    return " / ".join(titles)


def _folder_subtitle(*, title: str, path: str, space: dict[str, Any] | None) -> str:
    owner = str((space or {}).get("owner") or "").strip()
    access = str((space or {}).get("access") or "").strip()
    mine = bool((space or {}).get("mine"))
    space_title = str((space or {}).get("title") or "").strip()
    parts: list[str] = []
    if mine:
        parts.append("Din mappe")
    elif owner:
        parts.append(owner)
    elif access:
        parts.append(access)
    trail = path
    if trail and space_title and trail.casefold().startswith(space_title.casefold()):
        rest = trail[len(space_title):].lstrip(" /")
        trail = rest
    if trail and trail.casefold() != title.casefold():
        parts.append(trail)
    return " · ".join(part for part in parts if part)


def list_folders(*, query: str = "", account_id: str = "") -> list[dict[str, Any]]:
    account_id = account_id.strip()
    if not account_id:
        return []
    payload = _cached_list(_folders_cache, "/folders")
    contacts_payload = _cached_list(_contacts_cache, "/contacts")
    try:
        spaces_payload = _cached_list(_spaces_cache, f"/spaces?fields={_SPACES_FIELDS}")
    except WrikeError as exc:
        logger.info("Kunne ikke hente Wrike-spaces: %s", exc)
        spaces_payload = {"data": []}
    names, me_id = _contact_index(contacts_payload)
    spaces = _space_index(spaces_payload, names, me_id)
    items = [item for item in (payload.get("data") or []) if isinstance(item, dict)]
    by_id = {str(item.get("id") or "").strip(): item for item in items if item.get("id")}
    parent = _parent_map(items)
    rows: list[dict[str, Any]] = []
    needle = query.strip().casefold()
    for item in items:
        if item.get("deleted") or item.get("recycled"):
            continue
        folder_id = str(item.get("id") or "").strip()
        title = str(item.get("title") or "").strip() or folder_id
        scope = str(item.get("scope") or "")
        if not folder_id or scope == "RbFolder" or title.casefold() in {"root", "recycle bin"}:
            continue
        space = _space_for(folder_id, parent, spaces)
        members = (space or {}).get("member_ids") or set()
        if account_id not in members:
            continue
        path = _folder_path(folder_id, by_id, parent)
        personal = str((space or {}).get("access") or "") == "Personal"
        view = dict(space) if space else None
        if view is not None:
            view["mine"] = personal
        subtitle = _folder_subtitle(title=title, path=path, space=view)
        label = f"{title} · {subtitle}" if subtitle else title
        haystack = f"{title} {path} {subtitle} {label}".casefold()
        if needle and needle not in haystack:
            continue
        rows.append(
            {
                "id": folder_id,
                "title": title,
                "label": label,
                "subtitle": subtitle,
                "path": path,
                "mine": personal,
            }
        )
    rows.sort(key=lambda row: (not row["mine"], row["title"].casefold(), str(row.get("subtitle") or "").casefold()))
    return rows


def pick_default_folder(folders: list[dict[str, Any]]) -> dict[str, Any] | None:
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
    payload = _cached_list(_contacts_cache, "/contacts")
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
        raise WrikeError("Vælg en Wrike-konto i administrationen.")
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
