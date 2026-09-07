from __future__ import annotations

import logging
from email.message import EmailMessage
from urllib.parse import quote

from app.config import MAIL_CC, MAIL_MARKER, MAIL_TO

logger = logging.getLogger(__name__)
OL_IMPORTANCE_HIGH = 2


def compose(*, title: str, note: str, transcript: str, open_outlook: bool = False) -> dict[str, str | bool]:
    subject = (title or "").strip() or "Ny idé"
    body = build_body(note=note, transcript=transcript)
    opened = open_outlook_draft(to=MAIL_TO, cc=MAIL_CC, subject=subject, body=body) if open_outlook else False
    return {
        "to": MAIL_TO,
        "cc": MAIL_CC,
        "subject": subject,
        "body": body,
        "importance": "high",
        "outlook": opened,
        "mailto": mailto_url(to=MAIL_TO, cc=MAIL_CC, subject=subject, body=body),
        "eml": build_eml(to=MAIL_TO, cc=MAIL_CC, subject=subject, body=body),
    }


def build_body(*, note: str, transcript: str) -> str:
    chunks: list[str] = []
    note_text = (note or "").strip()
    transcript_text = (transcript or "").strip()
    if note_text:
        chunks.append(note_text)
    if transcript_text and transcript_text not in note_text:
        chunks.append("Transskription:")
        chunks.append(transcript_text)
    marker = (MAIL_MARKER or "").strip()
    if marker:
        chunks.append(marker)
    return "\n\n".join(chunks).strip() + "\n"


def mailto_url(*, to: str, cc: str, subject: str, body: str) -> str:
    query = [
        f"subject={quote(subject, safe='')}",
        f"body={quote(body.replace('\n', '\r\n'), safe='')}",
    ]
    if cc.strip():
        query.insert(0, f"cc={quote(cc.strip(), safe='')}")
    return f"mailto:{to.strip()}?" + "&".join(query)


def build_eml(*, to: str, cc: str, subject: str, body: str) -> str:
    message = EmailMessage()
    message["To"] = to
    if cc.strip():
        message["Cc"] = cc.strip()
    message["Subject"] = subject
    message["Importance"] = "high"
    message["X-Priority"] = "1"
    message["Priority"] = "urgent"
    message.set_content(body)
    return message.as_string()


def open_outlook_draft(*, to: str, cc: str, subject: str, body: str) -> bool:
    """Opret en synlig Outlook-kladde med høj prioritet. mailto: kan ikke sætte prioritet."""
    try:
        import pythoncom
        import win32com.client
    except ImportError as exc:
        logger.warning("Outlook-kladde springes over: pywin32 mangler (%s)", exc)
        return False

    pythoncom.CoInitialize()
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        mail = outlook.CreateItem(0)
        mail.To = to
        mail.CC = cc
        mail.Subject = subject
        mail.Body = body
        mail.Importance = OL_IMPORTANCE_HIGH
        mail.Display(False)
        return True
    except Exception as exc:
        logger.warning("Outlook kunne ikke åbne kladden: %s", exc)
        return False
    finally:
        pythoncom.CoUninitialize()
