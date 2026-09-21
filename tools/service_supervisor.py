"""Hold den installerede Task-intake-service kørende uden PowerShell."""
from __future__ import annotations

import json
import msvcrt
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
LOG_PATH = DATA_DIR / "logs" / "supervisor.log"
LOCK_PATH = DATA_DIR / "service-supervisor.lock"
UPDATE_RESULT_PATH = ROOT / ".browser-update-result.json"
RESTART_EXIT_CODE = 42
RESTART_DELAY_SECONDS = 10


def log(message: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as stream:
        stream.write(f"{datetime.now().isoformat(timespec='seconds')} {message}\n")


def acquire_lock():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    stream = LOCK_PATH.open("a+b")
    if stream.tell() == 0:
        stream.write(b"0")
        stream.flush()
    stream.seek(0)
    try:
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        stream.close()
        return None
    return stream


def write_update_result(ok: bool, code: str) -> None:
    payload = {
        "ok": ok,
        "code": code,
        "completedUtc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    UPDATE_RESULT_PATH.write_text(json.dumps(payload), encoding="utf-8")


def run_child(arguments: list[str]) -> int:
    env = os.environ.copy()
    env["OPEN_BROWSER"] = "0"
    return subprocess.run(
        arguments,
        cwd=ROOT,
        env=env,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    ).returncode


def supervise() -> int:
    lock = acquire_lock()
    if lock is None:
        log("En supervisor kører allerede; denne instans stopper.")
        return 0

    log(f"Supervisor startet pid={os.getpid()}")
    try:
        while True:
            exit_code = run_child([sys.executable, "-m", "app"])
            if exit_code == 0:
                log("Appen blev stoppet normalt; supervisor stopper.")
                return 0
            if exit_code == RESTART_EXIT_CODE:
                log("Browseren bad om opdatering.")
                update_code = run_child([sys.executable, str(ROOT / "tools" / "apply_update.py")])
                if update_code == 0:
                    write_update_result(True, "updated")
                    log("Opdatering gennemført; appen genstartes.")
                    continue
                write_update_result(False, "update_failed")
                log(f"Opdatering fejlede med kode {update_code}; installeret version genstartes.")
                time.sleep(RESTART_DELAY_SECONDS)
                continue
            log(f"Appen stoppede uventet med kode {exit_code}; genstarter om {RESTART_DELAY_SECONDS} s.")
            time.sleep(RESTART_DELAY_SECONDS)
    finally:
        lock.close()


if __name__ == "__main__":
    raise SystemExit(supervise())
