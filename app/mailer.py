from __future__ import annotations

from email.message import EmailMessage
from urllib.parse import quote

from app.config import MAIL_CC, MAIL_MARKER, MAIL_TO


def compose(*, title: str, note: str, transcript: str) -> dict[str, str]:
    subject = (title or "").strip() or "Ny idé"
    body = build_body(note=note, transcript=transcript)
    return {
        "to": MAIL_TO,
        "cc": MAIL_CC,
        "subject": subject,
        "body": body,
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
    message.set_content(body)
    return message.as_string()
