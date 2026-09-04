"""Copy Whisper, Ollama and GPU wheels to the NAS runtime share. One-off helper."""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(r"C:\Dev\Task-intake")
NAS_ROOT = Path(r"\\a4diskstation4\A4software\task-intake")
NAS_RUNTIME = NAS_ROOT / "runtime"
NAS_UPDATES = NAS_ROOT / "updates"

WHISPER_SRC = Path.home() / ".cache/huggingface/hub/models--Systran--faster-whisper-large-v3"
WHISPER_DST = NAS_RUNTIME / "models--Systran--faster-whisper-large-v3"
OLLAMA_SRC = Path.home() / ".ollama/models"
QWEN_MANIFEST = OLLAMA_SRC / "manifests/registry.ollama.ai/library/qwen2.5/14b"
QWEN_BLOBS = [
    "sha256-2049f5674b1e92b4464e5729975c9689fcfbf0b0e4443ccf10b5339f370f9a54",
    "sha256-66b9ea09bd5b7099cbb4fc820f31b575c0366fa439b08245566692c6784e281e",
    "sha256-eb4402837c7829a690fa845de4d7f3fd842c2adee476d5341da8a46ea9255175",
    "sha256-832dd9e00a68dd83b3c3fb9f5588dad7dcf337a0db50f7d9483f310cd292e92e",
    "sha256-db59b814cab753a51167db007fa6b6e0095f678ff24c9f7284753b75b34c6df3",
]
OLLAMA_SETUP_URL = "https://github.com/ollama/ollama/releases/latest/download/OllamaSetup.exe"


def log(message: str) -> None:
    print(message, flush=True)


def folder_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def robocopy(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "robocopy",
            str(src),
            str(dst),
            "/E",
            "/R:3",
            "/W:5",
            "/MT:8",
            "/NFL",
            "/NDL",
            "/NJH",
            "/NJS",
        ],
        capture_output=True,
        text=True,
    )
    # Robocopy: 0-7 = success with various copy/extra/mismatch flags.
    if result.returncode >= 8:
        raise SystemExit(
            f"robocopy fejlede ({result.returncode}): {result.stdout}\n{result.stderr}"
        )
    log(f"  robocopy {src.name} -> OK (kode {result.returncode})")


def main() -> None:
    os.chdir(ROOT)
    try:
        with socket.create_connection(("a4diskstation4", 445), timeout=4):
            pass
    except OSError as exc:
        raise SystemExit(f"NAS svarer ikke på port 445: {exc}") from exc
    if not NAS_ROOT.parent.is_dir():
        raise SystemExit(r"NAS-andelen \\a4diskstation4\A4software findes ikke.")
    if not WHISPER_SRC.is_dir() or folder_size(WHISPER_SRC) < 2_000_000_000:
        raise SystemExit(f"Whisper large-v3 mangler eller er for lille: {WHISPER_SRC}")
    if not QWEN_MANIFEST.is_file():
        raise SystemExit(f"qwen2.5:14b-manifest mangler: {QWEN_MANIFEST}")
    for name in QWEN_BLOBS:
        blob = OLLAMA_SRC / "blobs" / name
        if not blob.is_file():
            raise SystemExit(f"Ollama-blob mangler: {blob}")

    NAS_ROOT.mkdir(parents=True, exist_ok=True)
    NAS_RUNTIME.mkdir(parents=True, exist_ok=True)
    NAS_UPDATES.mkdir(parents=True, exist_ok=True)

    log(f"1/5 Whisper large-v3 ({folder_size(WHISPER_SRC) / (1024**3):.2f} GB) -> NAS")
    robocopy(WHISPER_SRC, WHISPER_DST)

    log("2/5 qwen2.5:14b (~9 GB) -> NAS")
    man_dst = NAS_RUNTIME / "ollama-models/manifests/registry.ollama.ai/library/qwen2.5/14b"
    man_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(QWEN_MANIFEST, man_dst)
    blob_dst = NAS_RUNTIME / "ollama-models/blobs"
    blob_dst.mkdir(parents=True, exist_ok=True)
    for name in QWEN_BLOBS:
        src = OLLAMA_SRC / "blobs" / name
        dst = blob_dst / name
        log(f"  blob {name[-12:]} ({src.stat().st_size / (1024**3):.2f} GB)")
        if dst.is_file() and dst.stat().st_size == src.stat().st_size:
            log("    findes allerede, springer over")
            continue
        shutil.copy2(src, dst)

    setup_dst = NAS_RUNTIME / "OllamaSetup.exe"
    log("3/5 OllamaSetup.exe")
    if setup_dst.is_file() and setup_dst.stat().st_size > 1_000_000:
        log(f"  findes allerede ({setup_dst.stat().st_size} bytes)")
    else:
        log(f"  henter {OLLAMA_SETUP_URL}")
        urllib.request.urlretrieve(OLLAMA_SETUP_URL, setup_dst)
        log(f"  {setup_dst.stat().st_size} bytes")

    log("4/5 GPU-hjul -> runtime/gpu")
    wheel_dir = NAS_RUNTIME / "gpu"
    wheel_dir.mkdir(parents=True, exist_ok=True)
    pip = ROOT / ".venv" / "Scripts" / "pip.exe"
    try:
        subprocess.run(
            [
                str(pip),
                "download",
                "--disable-pip-version-check",
                "-d",
                str(wheel_dir),
                "nvidia-cublas-cu12",
                "nvidia-cudnn-cu12>=9,<10",
            ],
            check=True,
            cwd=str(ROOT),
        )
    except subprocess.CalledProcessError as exc:
        log(f"  ADVARSEL pip download fejlede ({exc}). Fortsætter uden GPU-hjul.")

    log("5/5 runtime-manifest.json")
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "New-RuntimeManifest.ps1"),
            "-RuntimePath",
            str(NAS_RUNTIME),
        ],
        check=True,
        cwd=str(ROOT),
    )

    manifest = NAS_RUNTIME / "runtime-manifest.json"
    if not manifest.is_file():
        raise SystemExit("runtime-manifest.json blev ikke skrevet på NAS.")
    log(f"Færdig. NAS runtime: {folder_size(NAS_RUNTIME) / (1024**3):.2f} GB")
    log(f"Kontrolfil: {manifest}")
    log(f"Updates-mappe: {NAS_UPDATES} (tom indtil UDGIV OPDATERING.bat)")


if __name__ == "__main__":
    main()
