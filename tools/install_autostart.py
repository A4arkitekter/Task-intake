"""Registrér Task-intake ved login og start supervisoren uden PowerShell."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


TASK_NAME = "Task-intake"
RUN_KEY = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_FILE_NAME = "Task-intake.cmd"


def log(root: Path, message: str) -> None:
    with (root / "autostart-log.txt").open("a", encoding="utf-8") as stream:
        stream.write(f"{datetime.now().isoformat(timespec='seconds')} {message}\n")


def command_paths(root: Path) -> tuple[Path, Path, str]:
    pythonw = root / ".venv" / "Scripts" / "pythonw.exe"
    supervisor = root / "tools" / "service_supervisor.py"
    if not pythonw.is_file():
        raise RuntimeError(f"Python-miljøet mangler: {pythonw}")
    if not supervisor.is_file():
        raise RuntimeError(f"Supervisoren mangler: {supervisor}")
    command = f'"{pythonw}" "{supervisor}"'
    return pythonw, supervisor, command


def startup_directory() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    return Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def write_startup_launcher(root: Path, command: str) -> Path:
    """Installér en synlig og vedvarende login-launcher uafhængigt af registreringsdatabasen."""
    startup = startup_directory()
    startup.mkdir(parents=True, exist_ok=True)
    launcher = startup / STARTUP_FILE_NAME
    contents = (
        "@echo off\r\n"
        f'cd /d "{root}"\r\n'
        f'start "" /b {command}\r\n'
        "exit /b 0\r\n"
    )
    temporary = launcher.with_suffix(".tmp")
    temporary.write_text(contents, encoding="utf-8")
    temporary.replace(launcher)
    return launcher


def register(root: Path) -> str:
    root = root.resolve()
    if (root / ".git").is_dir():
        raise RuntimeError("Autostart må ikke sættes fra Git-udviklingsmappen")
    _pythonw, _supervisor, command = command_paths(root)
    launcher = write_startup_launcher(root, command)

    task = subprocess.run(
        [
            "schtasks.exe", "/Create", "/TN", TASK_NAME, "/SC", "ONLOGON",
            "/TR", command, "/RL", "LIMITED", "/F",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if task.returncode == 0:
        subprocess.run(
            ["reg.exe", "delete", RUN_KEY, "/v", TASK_NAME, "/f"],
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        log(root, f"Autostart registreret som planlagt opgave og i Startup: {launcher}")
        return "task+startup"

    fallback = subprocess.run(
        ["reg.exe", "add", RUN_KEY, "/v", TASK_NAME, "/t", "REG_SZ", "/d", command, "/f"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if fallback.returncode:
        detail = fallback.stderr.strip() or task.stderr.strip() or "ukendt fejl"
        raise RuntimeError(f"Autostart kunne ikke registreres: {detail}")
    log(root, f"Planlagt opgave fejlede; autostart registreret i HKCU Run og Startup: {launcher}")
    return "registry+startup"


def start_now(root: Path) -> int:
    pythonw, supervisor, _command = command_paths(root)
    process = subprocess.Popen(
        [str(pythonw), str(supervisor)],
        cwd=root,
        close_fds=True,
        creationflags=(
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        ),
    )
    log(root, f"Supervisor startet manuelt pid={process.pid}.")
    return process.pid


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--start-now", action="store_true")
    args = parser.parse_args()
    try:
        method = register(args.root)
        print(f"Autostart registreret via {method}.")
        if args.start_now:
            print(f"Supervisor startet med PID {start_now(args.root)}.")
        return 0
    except Exception as exc:
        print(f"FEJL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
