from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, time as clock_time
from typing import Any

from app import db
from app.config import APP_URL, REMIND_AT, REMIND_CHECK_SECONDS, REMIND_TO

logger = logging.getLogger(__name__)

STATE_KEY = "remind_last_sent_date"
DEFAULT_TIME = clock_time(8, 30)
# Fejler Outlook, skal der prøves igen — men ikke hvert femte minut hele dagen.
RETRY_AFTER_SEC = 3600.0

_last_failure = 0.0


def _enabled() -> bool:
    return os.getenv("REMIND_ENABLED", "1").lower() not in {"0", "false", "no"}


def remind_time() -> clock_time:
    try:
        hour, minute = (int(part) for part in REMIND_AT.split(":", 1))
        return clock_time(hour, minute)
    except (ValueError, TypeError):
        logger.warning("REMIND_AT='%s' kunne ikke læses. Bruger %s", REMIND_AT, DEFAULT_TIME)
        return DEFAULT_TIME


def age_text(created_at: str, now: datetime) -> str:
    try:
        created = datetime.fromisoformat(created_at)
    except (TypeError, ValueError):
        return "ukendt alder"
    if created.tzinfo is None:
        created = created.replace(tzinfo=now.tzinfo)
    days = (now - created).days
    if days <= 0:
        return "i dag"
    if days == 1:
        return "i går"
    return f"{days} dage"


def describe(item: dict[str, Any], now: datetime) -> str:
    age = age_text(item.get("created_at") or "", now)
    if item.get("status") == "error":
        reason = (item.get("error_message") or "ukendt fejl").strip()
        return f"Optagelse der fejlede: {reason} ({age})"
    title = (item.get("title") or "Uden overskrift").strip()
    return f"{title} ({age})"


def build_message(items: list[dict[str, Any]], now: datetime) -> tuple[str, str]:
    count = len(items)
    noun = "idé" if count == 1 else "idéer"
    subject = f"{count} {noun} venter i din idé-indbakke"

    adjective = "usorteret" if count == 1 else "usorterede"
    lines = [f"Der ligger {count} {adjective} {noun} i indbakken."]
    # Items kommer ældste først. Alderen er kun værd at nævne, når den bør genere dig.
    oldest = age_text(items[0].get("created_at") or "", now)
    if count > 1 and oldest != "i dag":
        lines.append(f"Den ældste er fra {oldest}.")
    lines.append("")
    lines.extend(f"  - {describe(item, now)}" for item in items)
    lines.extend(
        [
            "",
            f"Åbn indbakken: {APP_URL}",
            "",
            "Denne besked gentages hver dag, indtil indbakken er tom.",
        ]
    )
    return subject, "\n".join(lines)


def send_email(subject: str, body: str, *, send: bool = True) -> bool:
    """Send gennem din kørende Outlook, så der ikke skal gemmes en adgangskode nogen steder.

    Med send=False gemmes en kladde i stedet. Så kan hele kæden prøves af uden at
    sende noget — nyttigt, fordi "der kom ingen fejl" ikke er det samme som at det virker.
    """
    try:
        import pythoncom
        import win32com.client
    except ImportError as exc:
        logger.warning("Kan ikke sende oversigten: pywin32 mangler (%s)", exc)
        return False

    # Outlook tilgås via COM, og det skal sættes op i den tråd der bruger det.
    pythoncom.CoInitialize()
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        mail = outlook.CreateItem(0)
        mail.To = REMIND_TO
        mail.Subject = subject
        mail.Body = body
        if send:
            mail.Send()
        else:
            mail.Save()
        return True
    except Exception as exc:
        logger.warning("Outlook kunne ikke %s oversigten: %s", "sende" if send else "gemme", exc)
        return False
    finally:
        pythoncom.CoUninitialize()


def send_now(*, now: datetime | None = None) -> bool:
    """Send oversigten uden at spørge om klokken. Returnerer False hvis intet venter."""
    now = now or datetime.now().astimezone()
    items = db.list_waiting()
    if not items:
        logger.info("Ingen oversigt sendt: indbakken er tom")
        return False
    subject, body = build_message(items, now)
    if not send_email(subject, body):
        return False
    logger.info("Sendte oversigt til %s: %s", REMIND_TO, subject)
    return True


def is_due(now: datetime, last_sent: str | None) -> bool:
    if last_sent == now.date().isoformat():
        return False
    return now.time() >= remind_time()


def send_reminder_if_due(now: datetime | None = None) -> bool:
    global _last_failure
    if not _enabled():
        return False
    now = now or datetime.now().astimezone()
    if not is_due(now, db.get_state(STATE_KEY)):
        return False
    if _last_failure and time.monotonic() - _last_failure < RETRY_AFTER_SEC:
        return False

    items = db.list_waiting()
    if not items:
        # En tom indbakke må ikke markere dagen som sendt. I morgen er en ny chance.
        return False

    subject, body = build_message(items, now)
    if not send_email(subject, body):
        _last_failure = time.monotonic()
        return False

    _last_failure = 0.0
    db.set_state(STATE_KEY, now.date().isoformat())
    logger.info("Sendte daglig oversigt til %s: %s", REMIND_TO, subject)
    return True


class Reminder:
    """Tjekker med jævne mellemrum om dagens oversigt mangler at blive sendt."""

    def __init__(self, interval: float = REMIND_CHECK_SECONDS) -> None:
        self.interval = interval
        self._stop = threading.Event()

    def run(self) -> None:
        # Første tjek sker med det samme. Var maskinen slukket klokken 08:30,
        # skal dagen ikke bare være tabt.
        while not self._stop.is_set():
            try:
                send_reminder_if_due()
            except Exception:
                logger.exception("Den daglige oversigt fejlede")
            self._stop.wait(self.interval)

    def stop(self) -> None:
        self._stop.set()


def start() -> Reminder | None:
    if not _enabled():
        logger.info("Daglig oversigt er slået fra")
        return None
    reminder = Reminder()
    threading.Thread(target=reminder.run, daemon=True, name="daily-reminder").start()
    logger.info("Daglig oversigt sendes til %s omkring %s", REMIND_TO, REMIND_AT)
    return reminder
