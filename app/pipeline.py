from __future__ import annotations

import logging
from pathlib import Path

import av

from app import db
from app.config import MAX_DURATION_SLACK
from app.extract import extract_proposals
from app.transcribe import transcribe_file

logger = logging.getLogger(__name__)


def audio_duration_sec(path: Path) -> float | None:
    try:
        with av.open(str(path)) as container:
            if container.duration is None:
                return None
            return float(container.duration) / av.time_base
    except Exception:
        logger.exception("Kunne ikke læse varighed for %s", path)
        return None


def process_capture(capture_id: str) -> None:
    capture = db.get_capture(capture_id)
    if not capture:
        return
    path = Path(capture["audio_path"])
    try:
        duration = audio_duration_sec(path)
        if duration is not None and duration > MAX_DURATION_SLACK:
            raise RuntimeError(f"Optagelsen er {duration:.0f} s — max er 60 sekunder")
        if duration is not None:
            db.update_capture(capture_id, duration_sec=round(duration, 2))

        transcript = transcribe_file(path)
        if not transcript:
            transcript = "(ingen tale genkendt)"
        if transcript == "(ingen tale genkendt)":
            proposals = [
                {
                    "title": "Ingen tale genkendt",
                    "note": "Optagelsen var tom eller for stille. Smid væk eller optag igen.",
                }
            ]
        else:
            proposals = extract_proposals(transcript)
        db.replace_proposals(capture_id, proposals)
        db.update_capture(capture_id, status="ready", transcript=transcript, error_message=None)
        logger.info("Capture %s klar med %s forslag", capture_id, len(proposals))
    except Exception as exc:
        logger.exception("Behandling af %s fejlede", capture_id)
        db.update_capture(capture_id, status="error", error_message=str(exc))
