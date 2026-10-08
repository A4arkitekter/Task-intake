from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from app.config import ROOT

UPDATE_SCRIPT_PATH = ROOT / "tools" / "apply_update.py"
HANDOFF_SCRIPT_PATH = ROOT / "tools" / "apply_and_restart.py"
UPDATE_RESULT_PATH = ROOT / ".browser-update-result.json"
UPDATE_RESTART_EXIT_CODE = 42
UPDATE_ACTION_TOKEN = uuid.uuid4().hex
SERVER_INSTANCE_ID = uuid.uuid4().hex

update_shutdown_requested = threading.Event()
_update_status_lock = threading.Lock()
_update_status_cache: dict = {"checked_at": 0.0, "value": None}


def is_developer_checkout() -> bool:
    return (ROOT / ".git").is_dir()


def check_update_status(force: bool = False) -> dict:
    """Kontrollér den centrale version uden at blokere browseren i lang tid."""
    if is_developer_checkout():
        return {"ok": True, "supported": False, "update_available": False}
    if not UPDATE_SCRIPT_PATH.is_file():
        return {
            "ok": True,
            "supported": False,
            "update_available": False,
            "message": "Denne ældre installation skal gøres opdateringsklar af IT én gang.",
        }

    now = time.monotonic()
    with _update_status_lock:
        cached = _update_status_cache["value"]
        if not force and cached is not None and now - _update_status_cache["checked_at"] < 60:
            return dict(cached)

    command = [
        sys.executable,
        str(UPDATE_SCRIPT_PATH),
        "--check-only",
    ]
    try:
        result = subprocess.run(
            command,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=12,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        payload = json.loads(lines[-1]) if lines else {}
        value = {
            "ok": bool(payload.get("ok")),
            "supported": True,
            "update_available": bool(payload.get("updateAvailable")),
            "current_version": payload.get("currentVersion"),
            "latest_version": payload.get("latestVersion"),
        }
        if not value["ok"]:
            value["message"] = "Opdateringsdrevet kunne ikke kontrolleres. Programmet kan stadig bruges."
    except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError):
        value = {
            "ok": False,
            "supported": True,
            "update_available": False,
            "message": "Opdateringsdrevet kunne ikke kontrolleres. Programmet kan stadig bruges.",
        }

    with _update_status_lock:
        _update_status_cache["checked_at"] = time.monotonic()
        _update_status_cache["value"] = dict(value)
    return value


def read_update_result() -> dict | None:
    if not UPDATE_RESULT_PATH.is_file():
        return None
    result = json.loads(UPDATE_RESULT_PATH.read_text(encoding="utf-8-sig"))
    UPDATE_RESULT_PATH.unlink(missing_ok=True)
    return result


def spawn_update_handoff(wait_pid: int | None = None) -> bool:
    """Start opdatering i en løsrevet proces, så den overlever at serveren stopper."""
    if not HANDOFF_SCRIPT_PATH.is_file():
        return False
    env = os.environ.copy()
    env["INTAKE_WAIT_PID"] = str(os.getpid() if wait_pid is None else wait_pid)
    creationflags = (
        getattr(subprocess, "CREATE_NO_WINDOW", 0)
        | getattr(subprocess, "DETACHED_PROCESS", 0)
        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    )
    try:
        subprocess.Popen(
            [sys.executable, str(HANDOFF_SCRIPT_PATH)],
            cwd=str(ROOT),
            env=env,
            close_fds=True,
            creationflags=creationflags,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return False
    return True


def handoff_and_exit() -> None:
    if spawn_update_handoff():
        os._exit(0)
    os._exit(UPDATE_RESTART_EXIT_CODE)


def request_program_update_shutdown() -> None:
    """Afslut efter HTTP-svaret; en løsrevet proces opdaterer og starter igen."""

    def stop_later() -> None:
        time.sleep(1.0)
        handoff_and_exit()

    threading.Thread(target=stop_later, daemon=True).start()
