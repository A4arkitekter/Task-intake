"""Opdater installationen og start supervisoren uden at afhænge af en kørende forælder."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = ROOT / "data" / "logs" / "apply-and-restart.log"
UPDATE_RESULT_PATH = ROOT / ".browser-update-result.json"
WAIT_PID_TIMEOUT_SECONDS = 60
LOCK_WAIT_TIMEOUT_SECONDS = 30


def log(message: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as stream:
        stream.write(f"{datetime.now().isoformat(timespec='seconds')} {message}\n")


def pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def wait_for_pid(pid: int, timeout: float = WAIT_PID_TIMEOUT_SECONDS) -> None:
    deadline = time.time() + timeout
    while pid_is_running(pid) and time.time() < deadline:
        time.sleep(0.2)
    if pid_is_running(pid):
        log(f"Fortsatte alligevel; proces {pid} stoppede ikke inden timeout")


def wait_for_supervisor_lock(timeout: float = LOCK_WAIT_TIMEOUT_SECONDS) -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from tools.service_supervisor import acquire_lock

    deadline = time.time() + timeout
    while time.time() < deadline:
        lock = acquire_lock()
        if lock is not None:
            lock.close()
            return
        time.sleep(0.2)
    log("Supervisor-låsen blev ikke frigivet inden timeout; fortsætter")


def apply_package() -> dict:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from tools.apply_update import DEFAULT_SOURCE, apply

    return apply(DEFAULT_SOURCE)


def write_update_result(ok: bool, code: str) -> None:
    payload = {
        "ok": ok,
        "code": code,
        "completedUtc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    UPDATE_RESULT_PATH.write_text(json.dumps(payload), encoding="utf-8")


def supervisor_command() -> list[str]:
    pythonw = ROOT / ".venv" / "Scripts" / "pythonw.exe"
    supervisor = ROOT / "tools" / "service_supervisor.py"
    python = str(pythonw) if pythonw.is_file() else sys.executable
    return [python, str(supervisor)]


def start_supervisor() -> None:
    creationflags = (
        getattr(subprocess, "CREATE_NO_WINDOW", 0)
        | getattr(subprocess, "DETACHED_PROCESS", 0)
        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    )
    subprocess.Popen(
        supervisor_command(),
        cwd=str(ROOT),
        close_fds=True,
        creationflags=creationflags,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> int:
    wait_raw = os.environ.get("INTAKE_WAIT_PID", "").strip()
    wait_pid = int(wait_raw) if wait_raw.isdigit() else 0
    log(f"Handoff startet wait_pid={wait_pid}")
    if wait_pid:
        wait_for_pid(wait_pid)
    wait_for_supervisor_lock()

    updated = False
    try:
        result = apply_package()
        updated = True
        log(f"Opdatering færdig version={result.get('version')} changed={result.get('changed')}")
        write_update_result(True, "updated")
    except Exception as exc:
        log(f"Opdatering fejlede: {exc}")
        write_update_result(False, "update_failed")

    try:
        start_supervisor()
        log("Supervisor startet")
    except Exception as exc:
        log(f"Supervisor kunne ikke startes: {exc}")
        return 1
    return 0 if updated else 1


if __name__ == "__main__":
    raise SystemExit(main())
