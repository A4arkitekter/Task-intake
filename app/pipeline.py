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
        proposals = _proposals_from_transcript(transcript)
        db.replace_proposals(capture_id, proposals)
        db.update_capture(capture_id, status="ready", transcript=transcript, error_message=None)
        logger.info("Capture %s klar med %s forslag", capture_id, len(proposals))
    except Exception as exc:
        logger.exception("Behandling af %s fejlede", capture_id)
        db.update_capture(capture_id, status="error", error_message=str(exc))


def rewrite_capture(capture_id: str) -> dict:
    capture = db.get_capture(capture_id)
    if not capture:
        raise ValueError("Optagelsen findes ikke")
    transcript = (capture.get("transcript") or "").strip()
    if capture.get("status") != "ready" or not transcript:
        raise ValueError("Optagelsen er ikke klar til ny overskrift")
    proposals = _proposals_from_transcript(transcript)
    db.replace_pending_proposals(capture_id, proposals)
    logger.info("Capture %s fik ny overskrift: %s", capture_id, proposals[0]["title"])
    capture = db.get_capture(capture_id)
    assert capture is not None
    capture["proposals"] = db.list_proposals(capture_id)
    return capture


def _proposals_from_transcript(transcript: str) -> list[dict[str, str]]:
    if transcript == "(ingen tale genkendt)":
        return [
            {
                "title": "Ingen tale genkendt",
                "note": "Optagelsen var tom eller for stille. Smid væk eller optag igen.",
            }
        ]
    proposals = extract_proposals(transcript)[:1]
    if proposals:
        return proposals
    return [{"title": "Ny idé", "note": transcript}]
