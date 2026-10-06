from __future__ import annotations

import logging
from pathlib import Path

import av

from app import db, settings, wrike
from app.config import MAX_DURATION_SEC
from app.extract import extract_proposals
from app.notify import notify_failed, notify_ready

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
        if MAX_DURATION_SEC > 0 and duration is not None and duration > MAX_DURATION_SEC:
            raise RuntimeError(f"Optagelsen er {duration:.0f} s — grænsen er {MAX_DURATION_SEC:.0f} s")
        if duration is not None:
            db.update_capture(capture_id, duration_sec=round(duration, 2))

        transcript = transcribe_if_needed(capture)
        if not transcript:
            transcript = "(ingen tale genkendt)"
        proposals = _proposals_from_transcript(transcript)
        db.replace_proposals(capture_id, proposals)
        db.update_capture(capture_id, status="ready", transcript=transcript, error_message=None)
        logger.info("Capture %s klar med %s forslag", capture_id, len(proposals))
        if proposals[0]["title"] == "Ingen tale genkendt":
            pending = [item for item in db.list_proposals(capture_id) if item.get("status") == "pending"]
            for item in pending:
                db.update_proposal(item["id"], status="discarded")
            db.update_capture(capture_id, error_message="Ingen tale genkendt — intet sendt til Wrike.")
            notify_failed("Ingen tale genkendt")
            return
        try:
            send_capture_to_wrike(capture_id)
        except Exception:
            return
    except Exception as exc:
        logger.exception("Behandling af %s fejlede", capture_id)
        db.update_capture(capture_id, status="error", error_message=str(exc))
        notify_failed(str(exc))


def transcribe_if_needed(capture: dict) -> str:
    existing = (capture.get("transcript") or "").strip()
    if existing:
        return existing
    from app.transcribe import transcribe_file

    return transcribe_file(Path(capture["audio_path"]))


def send_capture_to_wrike(capture_id: str) -> dict:
    capture = db.get_capture(capture_id)
    if not capture:
        raise ValueError("Optagelsen findes ikke")
    pending = [item for item in db.list_proposals(capture_id) if item.get("status") == "pending"]
    if not pending:
        raise ValueError("Der er intet at sende til Wrike")
    try:
        task = send_proposal_to_wrike(pending[0]["id"])
        db.update_capture(capture_id, error_message=None)
        return task
    except Exception as exc:
        logger.exception("Wrike-oprettelse af %s fejlede", capture_id)
        db.update_capture(capture_id, error_message=str(exc))
        notify_failed(pending[0]["title"])
        raise


def send_proposal_to_wrike(proposal_id: str) -> dict:
    proposal = db.get_proposal(proposal_id)
    if not proposal:
        raise ValueError("Forslaget findes ikke")
    capture = db.get_capture(proposal["capture_id"])
    folder_id = settings.wrike_folder_id()
    if not folder_id:
        raise wrike.WrikeError("Vælg en Wrike-mappe i administrationen.")
    assignee_id, assignee_name = settings.wrike_assignee()
    if not assignee_id:
        raise wrike.WrikeError("Vælg en ansvarlig i administrationen.")
    description = task_description(
        proposal.get("note") or "",
        (capture or {}).get("transcript") or "",
    )
    task = wrike.create_task(
        title=proposal["title"],
        description=description,
        folder_id=folder_id,
        importance=settings.wrike_importance(),
        responsible_id=assignee_id,
        responsible_name=assignee_name,
    )
    db.update_proposal(
        proposal_id,
        status="sent",
        wrike_task_id=task["id"],
        wrike_url=task.get("url") or None,
    )
    notify_ready(proposal["title"])
    return task


def retry_capture_job(capture_id: str) -> None:
    capture = db.get_capture(capture_id)
    if not capture:
        return
    transcript = (capture.get("transcript") or "").strip()
    pending = [item for item in db.list_proposals(capture_id) if item.get("status") == "pending"]
    if transcript and pending:
        try:
            send_capture_to_wrike(capture_id)
            db.update_capture(capture_id, status="ready")
        except Exception:
            db.update_capture(capture_id, status="ready")
        return
    process_capture(capture_id)


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


def task_description(note: str, transcript: str) -> str:
    note = (note or "").strip()
    transcript = (transcript or "").strip()
    if note and transcript and note != transcript:
        return f"{note}\n\n{transcript}"
    return note or transcript
