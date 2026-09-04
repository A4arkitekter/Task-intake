r"""Prøve: låner programmet GPU'en og giver den ordentligt fra sig igen?

Transskriberer den samme fil to gange med en frigivelse imellem. Anden runde skal
koste et par sekunder ekstra på at hente modellen frem, og hukommelsen skal være
tilbage på udgangspunktet til slut.

Kør med:  .\.venv\Scripts\python.exe scripts\probe_gpu_cycle.py [sti-til-lydfil]
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import transcribe

DEFAULT_AUDIO = Path(__file__).resolve().parent.parent / "data" / "behandlet"


def vram() -> int:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            check=True,
        )
        return int(out.stdout.strip().splitlines()[0])
    except Exception:
        return -1


def pick_audio() -> Path | None:
    if len(sys.argv) > 1:
        candidate = Path(sys.argv[1])
        return candidate if candidate.is_file() else None
    if DEFAULT_AUDIO.is_dir():
        return next((item for item in sorted(DEFAULT_AUDIO.iterdir()) if item.is_file()), None)
    return None


def run(audio: Path, label: str) -> None:
    started = time.time()
    text = transcribe.transcribe_file(audio)
    print(f"{label:12} {time.time() - started:5.1f} s, VRAM {vram()} MiB")
    print(f"{'':12} {text[:80]}")


def main() -> int:
    audio = pick_audio()
    if audio is None:
        print("Fandt ingen lydfil at prøve med. Angiv en sti som argument.")
        return 1

    print(f"LYDFIL       {audio.name}")
    print(f"START        VRAM {vram()} MiB")

    run(audio, "FOERSTE")
    freed = transcribe.release()
    print(f"FRIGIVET     {freed}, VRAM {vram()} MiB")

    run(audio, "EFTER RELOAD")
    transcribe.release()
    print(f"SLUT         VRAM {vram()} MiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
