from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import threading
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app import db
from app.auth import require_user
from app.config import (
    AUDIO_DIR,
    ICON_DIR,
    MAX_AUDIO_BYTES,
    MAX_RECORD_SECONDS,
    APP_PASSWORD,
    SECRET_KEY,
    STATIC_DIR,
    WHISPER_WARMUP,
    ensure_dirs,
    mail_settings,
)
from app.icons import ensure_icons
from app.mailer import compose
from app.pipeline import audio_duration_sec, process_capture
from app.transcribe import status as whisper_status, warm_up

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_dirs()
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    ensure_icons()
    db.init()
    if WHISPER_WARMUP:
        threading.Thread(target=warm_up, daemon=True, name="whisper-warmup").start()
    yield


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
        "mail": mail_settings(),
        **whisper_status(),
    }


@app.get("/api/me")
def me(request: Request) -> dict:
    return {"authenticated": bool(request.session.get("user")), "mail": mail_settings()}


@app.post("/api/login")
def login(request: Request, payload: dict) -> dict:
    password = str(payload.get("password") or "")
    if password != APP_PASSWORD:
        raise HTTPException(status_code=401, detail="Forkert adgangskode")
    request.session["user"] = True
    return {"ok": True}


@app.post("/api/logout")
def logout(request: Request) -> dict:
    request.session.clear()
    return {"ok": True}


@app.get("/api/inbox")
def inbox(_: None = Depends(require_user)) -> dict:
    return {"captures": db.list_inbox(), "mail": mail_settings(), **whisper_status()}


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
    data = await audio.read()
    if not data:
        raise HTTPException(status_code=400, detail="Tom optagelse")
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=400, detail="Optagelsen er for stor")

    mime = audio.content_type or "audio/webm"
    suffix = _suffix_for_mime(mime, audio.filename)
    capture_id = db.new_id()
    dest = AUDIO_DIR / f"{capture_id}{suffix}"
    dest.write_bytes(data)

    duration = audio_duration_sec(dest)
    if duration is not None and duration > MAX_RECORD_SECONDS + 15:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Optagelsen er længere end ét minut")

    capture = db.create_capture(
        capture_id=capture_id,
        source=source or "pwa",
        audio_path=str(dest),
        audio_mime=mime,
        duration_sec=round(duration, 2) if duration is not None else None,
    )

    background.add_task(process_capture, capture["id"])
    return {"id": capture["id"], "status": "processing"}


@app.post("/api/captures/{capture_id}/discard")
def discard_capture(capture_id: str, _: None = Depends(require_user)) -> dict:
    capture = db.get_capture(capture_id)
    if not capture:
        raise HTTPException(status_code=404, detail="Optagelsen findes ikke")
    db.discard_pending_for_capture(capture_id)
    return {"ok": True}


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
