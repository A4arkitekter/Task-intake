from __future__ import annotations

import logging
import threading
from pathlib import Path

from app.config import MODEL_DIR, WHISPER_COMPUTE_TYPE, WHISPER_DEVICE, WHISPER_LANGUAGE, WHISPER_MODEL

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_model = None
_status = "idle"
_error: str | None = None


def status() -> dict[str, str | None]:
    return {"whisper": _status, "error": _error}


def warm_up() -> None:
    try:
        _load_model()
    except Exception:
        logger.exception("Kunne ikke indlæse Whisper")


def _load_model():
    global _model, _status, _error
    with _lock:
        if _model is not None:
            return _model
        _status = "loading"
        try:
            from faster_whisper import WhisperModel

            logger.info("Indlæser Whisper-model %s (%s/%s)", WHISPER_MODEL, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE)
            _model = WhisperModel(
                WHISPER_MODEL,
                device=WHISPER_DEVICE,
                compute_type=WHISPER_COMPUTE_TYPE,
                download_root=str(MODEL_DIR),
            )
            _status = "ready"
            _error = None
            logger.info("Whisper er klar")
            return _model
        except Exception as exc:
            _status = "error"
            _error = str(exc)
            raise


def transcribe_file(path: Path) -> str:
    model = _load_model()
    with _lock:
        segments, _info = model.transcribe(
            str(path),
            language=WHISPER_LANGUAGE,
            vad_filter=True,
            beam_size=1,
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
    return text
