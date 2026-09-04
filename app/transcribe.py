from __future__ import annotations

import gc
import logging
import os
import sys
import threading
import time
from pathlib import Path

from app.config import (
    MODEL_DIR,
    WHISPER_COMPUTE_TYPE,
    WHISPER_DEVICE,
    WHISPER_IDLE_UNLOAD_SEC,
    WHISPER_LANGUAGE,
    WHISPER_MODEL,
)

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_model = None
_status = "idle"
_error: str | None = None
_device: str | None = None
_last_used = 0.0


def status() -> dict[str, str | None]:
    return {
        "whisper": _status,
        "whisper_model": WHISPER_MODEL,
        "whisper_device": _device,
        "error": _error,
    }


def warm_up() -> None:
    try:
        _load_model()
    except Exception:
        logger.exception("Kunne ikke indlæse Whisper")


def _add_cuda_dll_dirs() -> None:
    """CTranslate2 slår cublas64_12.dll op ad navn, så pip-pakkernes DLL-mapper skal ligge i PATH."""
    if os.name != "nt":
        return
    nvidia = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
    folders = [str(nvidia / name / "bin") for name in ("cublas", "cudnn", "cuda_nvrtc")]
    found = [folder for folder in folders if Path(folder).is_dir()]
    if not found:
        logger.warning("Fandt ingen NVIDIA-DLL-mapper i %s", nvidia)
        return
    os.environ["PATH"] = os.pathsep.join([*found, os.environ.get("PATH", "")])


def _build(device: str, compute_type: str):
    from faster_whisper import WhisperModel

    logger.info("Indlæser Whisper-model %s (%s/%s)", WHISPER_MODEL, device, compute_type)
    model = WhisperModel(
        WHISPER_MODEL,
        device=device,
        compute_type=compute_type,
        download_root=str(MODEL_DIR),
    )
    _smoke_test(model)
    return model


def _smoke_test(model) -> None:
    """Optaget eller manglende GPU viser sig først ved første kodning, ikke når modellen bygges."""
    import numpy as np

    segments, _info = model.transcribe(
        np.zeros(16000, dtype=np.float32),
        language=WHISPER_LANGUAGE,
        vad_filter=False,
        beam_size=1,
    )
    list(segments)


def _load_model():
    global _model, _status, _error, _device, _last_used
    with _lock:
        if _model is not None:
            _last_used = time.monotonic()
            return _model
        _status = "loading"

        attempts = [(WHISPER_DEVICE, WHISPER_COMPUTE_TYPE)]
        if WHISPER_DEVICE == "cuda":
            _add_cuda_dll_dirs()
            # Er GPU'en optaget af andet arbejde, er en langsom transskription
            # stadig uendeligt bedre end en tabt idé.
            attempts.append(("cpu", "int8"))

        last_error: Exception | None = None
        for device, compute_type in attempts:
            try:
                _model = _build(device, compute_type)
            except Exception as exc:
                last_error = exc
                logger.warning("Whisper på %s/%s virker ikke: %s", device, compute_type, exc)
                continue
            _status = "ready"
            _error = None
            _device = device
            _last_used = time.monotonic()
            logger.info("Whisper er klar på %s", device)
            return _model

        _status = "error"
        _error = str(last_error)
        assert last_error is not None
        raise last_error


def release() -> str | None:
    """Giv GPU-hukommelsen fra sig. Returnerer den enhed, der blev frigivet."""
    global _model, _status, _device
    with _lock:
        if _model is None:
            return None
        freed = _device
        _model = None
        _status = "idle"
        _device = None
    gc.collect()
    return freed


def release_if_idle() -> bool:
    if WHISPER_IDLE_UNLOAD_SEC <= 0:
        return False
    with _lock:
        if _model is None:
            return False
        if time.monotonic() - _last_used < WHISPER_IDLE_UNLOAD_SEC:
            return False
    freed = release()
    if freed:
        logger.info("Frigav Whisper fra %s efter tomgang", freed)
    return bool(freed)


def transcribe_file(path: Path) -> str:
    try:
        return _transcribe(path)
    except Exception as exc:
        # Løb GPU'en tør, fordi du selv brugte den, skal idéen ikke gå tabt. Vi smider
        # modellen væk og henter den igen — næste forsøg ender på CPU, hvis kortet er optaget.
        logger.warning("Transskription fejlede (%s). Frigiver modellen og prøver igen.", exc)
        release()
        return _transcribe(path)


def _transcribe(path: Path) -> str:
    global _last_used
    model = _load_model()
    with _lock:
        segments, _info = model.transcribe(
            str(path),
            language=WHISPER_LANGUAGE,
            vad_filter=True,
            beam_size=1,
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        _last_used = time.monotonic()
    return text


class IdleReleaser:
    """Holder øje med om modellen har stået ubrugt, og giver så hukommelsen tilbage."""

    def __init__(self, interval: float = 30.0) -> None:
        self.interval = interval
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.is_set():
            self._stop.wait(self.interval)
            if self._stop.is_set():
                return
            try:
                release_if_idle()
            except Exception:
                logger.exception("Kunne ikke frigive Whisper")

    def stop(self) -> None:
        self._stop.set()


def start_idle_releaser() -> IdleReleaser | None:
    if WHISPER_IDLE_UNLOAD_SEC <= 0:
        return None
    releaser = IdleReleaser()
    threading.Thread(target=releaser.run, daemon=True, name="whisper-idle").start()
    return releaser
