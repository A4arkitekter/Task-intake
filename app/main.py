from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import os
import threading
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app import db
from app import update as program_update
from app.activity import mark_inbox_seen
from app.auth import require_user
from app.config import (
    AUDIO_DIR,
    DATA_DIR,
    ICON_DIR,
    INBOX_DIR,
    MAX_AUDIO_BYTES,
    MAX_RECORD_SECONDS,
    REMIND_AT,
    REMIND_TO,
    APP_PASSWORD,
    APP_URL,
    SECRET_KEY,
    STATIC_DIR,
    WATCH_ENABLED,
    WHISPER_WARMUP,
    ensure_dirs,
    mail_settings,
)
from app.icons import ensure_icons
from app.mailer import compose
from app.notify import open_inbox_if_unattended
from app.pipeline import audio_duration_sec, process_capture, rewrite_capture
from app.remind import start as start_reminder
from app.winapp import register as register_with_windows
from app.rewrite import status as rewrite_status
from app.transcribe import start_idle_releaser, status as whisper_status, warm_up
from app.watch import start as start_watcher


def _setup_logging() -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        # Autostart kører uden konsol, så der skal være et spor at læse bagefter.
        log_dir = DATA_DIR / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                log_dir / "app.log",
                maxBytes=1_000_000,
                backupCount=3,
                encoding="utf-8",
            )
        )
    except OSError:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


_setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_dirs()
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    ensure_icons()
    # Giver programmet et navn, Windows anerkender, før den første notifikation skal vises.
    register_with_windows()
    db.init()
    if WHISPER_WARMUP:
        threading.Thread(target=warm_up, daemon=True, name="whisper-warmup").start()
    watcher = start_watcher() if WATCH_ENABLED else None
    releaser = start_idle_releaser()
    reminder = start_reminder()
    _open_inbox_if_anything_waits()
    _maybe_open_browser()
    try:
        yield
    finally:
        if watcher is not None:
            watcher.stop()
        if releaser is not None:
            releaser.stop()
        if reminder is not None:
            reminder.stop()


def _maybe_open_browser() -> None:
    flag = os.environ.get("OPEN_BROWSER", "").strip().lower()
    if flag not in {"1", "true", "yes", "on"}:
        return
    url = APP_URL if "://" in APP_URL else f"http://127.0.0.1:8000/"
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()


def _is_loopback(request: Request) -> bool:
    host = (request.client.host if request.client else "") or ""
    return host in {"127.0.0.1", "::1", "testclient"}


def _open_inbox_if_anything_waits() -> None:
    """Bagstopper ved login: en idé fra før ferien skal dukke op af sig selv."""
    try:
        waiting = db.list_waiting()
    except Exception:
        logger.exception("Kunne ikke se efter ventende idéer")
        return
    if not waiting:
        return
    logger.info("%s ting venter i indbakken", len(waiting))
    open_inbox_if_unattended()


app = FastAPI(title="Task intake", docs_url=None, redoc_url=None, lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    same_site="lax",
    https_only=False,
    max_age=60 * 60 * 24 * 30,
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "instance_id": program_update.SERVER_INSTANCE_ID,
        "update_action_token": program_update.UPDATE_ACTION_TOKEN,
        "mail": mail_settings(),
        "inbox_dir": str(INBOX_DIR),
        "watching": WATCH_ENABLED,
        "waiting": len(db.list_waiting()),
        "remind_to": REMIND_TO,
        "remind_at": REMIND_AT,
        **whisper_status(),
        **rewrite_status(),
    }


@app.get("/api/update/status")
def api_update_status() -> dict:
    return {"ok": True, "update": program_update.check_update_status()}


@app.get("/api/update/result")
def api_update_result():
    try:
        result = program_update.read_update_result()
    except (OSError, ValueError):
        return JSONResponse(
            {
                "ok": False,
                "error": "Resultatet af opdateringen kunne ikke læses. Kør SYSTEMTJEK.bat.",
            },
            status_code=500,
        )
    return {"ok": True, "result": result}


@app.post("/api/update/apply")
def api_apply_update(request: Request):
    if not _is_loopback(request):
        return JSONResponse(
            {"ok": False, "error": "Opdatering kan kun startes på denne computer."},
            status_code=403,
        )
    if request.headers.get("X-Update-Token") != program_update.UPDATE_ACTION_TOKEN:
        return JSONResponse(
            {"ok": False, "error": "Opdateringsanmodningen blev afvist."},
            status_code=403,
        )
    if program_update.update_shutdown_requested.is_set():
        return {"ok": True, "message": "Opdateringen er allerede startet."}
    if db.has_processing_capture():
        return JSONResponse(
            {
                "ok": False,
                "error": "Vent, til den igangværende optagelse er færdig, og prøv igen.",
            },
            status_code=409,
        )

    status = program_update.check_update_status(force=True)
    if not status.get("supported"):
        return JSONResponse(
            {
                "ok": False,
                "error": status.get("message") or "Denne installation kan ikke opdateres fra browseren.",
            },
            status_code=409,
        )
    if not status.get("ok"):
        return JSONResponse({"ok": False, "error": status.get("message")}, status_code=503)
    if not status.get("update_available"):
        return {"ok": True, "message": "Programmet er allerede opdateret."}

    program_update.update_shutdown_requested.set()
    logger.info("Browseropdatering accepteret version=%s", status.get("latest_version"))
    program_update.request_program_update_shutdown()
    return {
        "ok": True,
        "restarting": True,
        "message": "Opdateringen starter. Programmet genstarter automatisk.",
        "instance_id": program_update.SERVER_INSTANCE_ID,
    }


@app.get("/api/me")
def me(request: Request) -> dict:
    return {
        "authenticated": bool(request.session.get("user")),
        "mail": mail_settings(),
        # Optageren i browseren skal kende serverens grænse, ikke gætte sin egen.
        "max_record_seconds": MAX_RECORD_SECONDS,
    }


@app.post("/api/login")
def login(request: Request, payload: dict) -> dict:
    password = str(payload.get("password") or "").strip()
    if password != APP_PASSWORD:
        raise HTTPException(status_code=401, detail="Forkert adgangskode")
    request.session["user"] = True
    return {"ok": True}


@app.post("/api/logout")
def logout(request: Request) -> dict:
    request.session.clear()
    return {"ok": True}


@app.get("/api/inbox")
def inbox(visible: bool = True, _: None = Depends(require_user)) -> dict:
    # En skjult fane henter stadig data, men beviser ikke at nogen kigger. Browsere
    # struber baggrundsfaner ned til cirka ét kald i minuttet, og det så tidligere ud
    # præcis som en opmærksom seer — så åbnede indbakken sig aldrig af sig selv.
    if visible:
        mark_inbox_seen()
    return {"captures": db.list_inbox(), "mail": mail_settings(), **whisper_status(), **rewrite_status()}


@app.get("/api/captures/{capture_id}")
def get_capture(capture_id: str, _: None = Depends(require_user)) -> dict:
    capture = db.get_capture(capture_id)
    if not capture:
        raise HTTPException(status_code=404, detail="Optagelsen findes ikke")
    capture["proposals"] = db.list_proposals(capture_id)
    return capture


@app.get("/api/captures/{capture_id}/audio")
def get_audio(capture_id: str, _: None = Depends(require_user)) -> FileResponse:
    capture = db.get_capture(capture_id)
    if not capture or not capture.get("audio_path"):
        raise HTTPException(status_code=404, detail="Lydfilen findes ikke")
    path = Path(capture["audio_path"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Lydfilen findes ikke")
    mime = capture.get("audio_mime") or "application/octet-stream"
    return FileResponse(path, media_type=mime, filename=path.name)


@app.post("/api/captures")
async def upload_capture(
    background: BackgroundTasks,
    audio: UploadFile = File(...),
    source: str = Form("pwa"),
    _: None = Depends(require_user),
) -> dict:
    if program_update.update_shutdown_requested.is_set():
        raise HTTPException(
            status_code=503,
            detail="Programmet er ved at opdatere. Vent på den automatiske genstart.",
        )
    data = await audio.read()
    if not data:
        raise HTTPException(status_code=400, detail="Tom optagelse")
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Optagelsen er over {MAX_AUDIO_BYTES // (1024 * 1024)} MB",
        )

    mime = audio.content_type or "audio/webm"
    suffix = _suffix_for_mime(mime, audio.filename)
    capture_id = db.new_id()
    dest = AUDIO_DIR / f"{capture_id}{suffix}"
    dest.write_bytes(data)

    duration = audio_duration_sec(dest)
    if duration is not None and duration > MAX_RECORD_SECONDS + 15:
        dest.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail=f"Optagelsen er længere end {MAX_RECORD_SECONDS // 60} minutter",
        )

    capture = db.create_capture(
        capture_id=capture_id,
        source=source or "pwa",
        audio_path=str(dest),
        audio_mime=mime,
        duration_sec=round(duration, 2) if duration is not None else None,
    )

    background.add_task(process_capture, capture["id"])
    return {"id": capture["id"], "status": "processing"}


@app.post("/api/captures/{capture_id}/retry")
def retry_capture(capture_id: str, background: BackgroundTasks, _: None = Depends(require_user)) -> dict:
    if program_update.update_shutdown_requested.is_set():
        raise HTTPException(
            status_code=503,
            detail="Programmet er ved at opdatere. Vent på den automatiske genstart.",
        )
    capture = db.get_capture(capture_id)
    if not capture:
        raise HTTPException(status_code=404, detail="Optagelsen findes ikke")
    if capture.get("status") != "error":
        raise HTTPException(status_code=409, detail="Optagelsen fejlede ikke")
    path = Path(capture.get("audio_path") or "")
    if not path.is_file():
        raise HTTPException(status_code=409, detail="Lydfilen findes ikke længere")
    # Lyden ligger stadig på disken, så en fejl behøver ikke koste idéen.
    db.update_capture(capture_id, status="processing", error_message=None)
    background.add_task(process_capture, capture_id)
    return {"id": capture_id, "status": "processing"}


@app.post("/api/captures/{capture_id}/discard")
def discard_capture(capture_id: str, _: None = Depends(require_user)) -> dict:
    capture = db.get_capture(capture_id)
    if not capture:
        raise HTTPException(status_code=404, detail="Optagelsen findes ikke")
    db.discard_pending_for_capture(capture_id)
    return {"ok": True}


@app.post("/api/captures/{capture_id}/rewrite")
def rewrite_existing(capture_id: str, _: None = Depends(require_user)) -> dict:
    capture = db.get_capture(capture_id)
    if not capture:
        raise HTTPException(status_code=404, detail="Optagelsen findes ikke")
    try:
        return rewrite_capture(capture_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.patch("/api/proposals/{proposal_id}")
async def edit_proposal(proposal_id: str, request: Request, _: None = Depends(require_user)) -> dict:
    proposal = db.get_proposal(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Forslaget findes ikke")
    if proposal["status"] != "pending":
        raise HTTPException(status_code=409, detail="Forslaget er allerede behandlet")
    payload = await request.json()
    fields = {}
    if "title" in payload:
        title = str(payload["title"]).strip()
        if not title:
            raise HTTPException(status_code=400, detail="Titel må ikke være tom")
        fields["title"] = title
    if "note" in payload:
        fields["note"] = str(payload["note"]).strip()
    db.update_proposal(proposal_id, **fields)
    updated = db.get_proposal(proposal_id)
    assert updated is not None
    return updated


@app.post("/api/proposals/{proposal_id}/discard")
def discard_proposal(proposal_id: str, _: None = Depends(require_user)) -> dict:
    proposal = db.get_proposal(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Forslaget findes ikke")
    if proposal["status"] != "pending":
        raise HTTPException(status_code=409, detail="Forslaget er allerede behandlet")
    db.update_proposal(proposal_id, status="discarded")
    return {"ok": True}


@app.post("/api/proposals/{proposal_id}/approve")
def approve_proposal(proposal_id: str, _: None = Depends(require_user)) -> dict:
    proposal = db.get_proposal(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Forslaget findes ikke")
    if proposal["status"] != "pending":
        raise HTTPException(status_code=409, detail="Forslaget er allerede behandlet")

    payload = _compose_proposal(proposal)
    db.update_proposal(proposal_id, status="sent", wrike_task_id=None, wrike_url=None)
    updated = db.get_proposal(proposal_id)
    assert updated is not None
    return {**updated, **payload}


@app.get("/api/proposals/{proposal_id}/mail")
def proposal_mail(proposal_id: str, _: None = Depends(require_user)) -> dict:
    proposal = db.get_proposal(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Forslaget findes ikke")
    return _compose_proposal(proposal)


@app.get("/api/proposals/{proposal_id}/eml")
def proposal_eml(proposal_id: str, _: None = Depends(require_user)) -> Response:
    proposal = db.get_proposal(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Forslaget findes ikke")
    payload = _compose_proposal(proposal)
    return Response(
        content=payload["eml"].encode("utf-8"),
        media_type="message/rfc822",
        headers={"Content-Disposition": 'attachment; filename="wrike-opgave.eml"'},
    )


def _compose_proposal(proposal: dict) -> dict:
    capture = db.get_capture(proposal["capture_id"])
    return compose(
        title=proposal["title"],
        note=proposal["note"],
        transcript=(capture or {}).get("transcript") or "",
    )


def _suffix_for_mime(mime: str, filename: str | None) -> str:
    if filename and Path(filename).suffix:
        return Path(filename).suffix
    mapping = {
        "audio/webm": ".webm",
        "audio/ogg": ".ogg",
        "audio/mp4": ".m4a",
        "audio/mpeg": ".mp3",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/aac": ".aac",
    }
    base = mime.split(";")[0].strip().lower()
    return mapping.get(base, ".webm")


@app.get("/manifest.webmanifest")
def manifest() -> FileResponse:
    return FileResponse(STATIC_DIR / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/sw.js")
def service_worker() -> FileResponse:
    return FileResponse(STATIC_DIR / "sw.js", media_type="text/javascript")


@app.get("/favicon.ico")
def favicon() -> FileResponse:
    icon = ICON_DIR / "icon-192.png"
    if icon.is_file():
        return FileResponse(icon)
    raise HTTPException(status_code=404)


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse({"detail": detail}, status_code=exc.status_code)


@app.get("/{full_path:path}")
def spa(full_path: str) -> FileResponse:
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404)
    candidate = STATIC_DIR / full_path
    if full_path and candidate.is_file():
        return FileResponse(candidate)
    return FileResponse(STATIC_DIR / "index.html")
