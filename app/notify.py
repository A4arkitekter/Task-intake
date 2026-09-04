from __future__ import annotations

import logging
import os
import threading
import webbrowser

from app.activity import mark_inbox_seen, seconds_since_inbox_seen
from app.config import APP_NAME, APP_URL, AUTO_OPEN_IDLE_SEC, TOAST_AUMID

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_open_lock = threading.Lock()
_toaster = None
_broken = False


def _enabled() -> bool:
    return os.getenv("NOTIFY", "1").lower() not in {"0", "false", "no"}


def _auto_open_enabled() -> bool:
    return os.getenv("AUTO_OPEN", "1").lower() not in {"0", "false", "no"}


def open_inbox_if_unattended() -> None:
    """Åbn indbakken i browseren, men kun hvis ingen fane allerede kigger på den."""
    if not _auto_open_enabled():
        return
    with _open_lock:
        idle = seconds_since_inbox_seen()
        # En synlig fane henter selv listen. Et nyt vindue oven i den ville stjæle fokus.
        # En skjult fane tæller ikke — den så tidligere ud som en opmærksom seer.
        if idle <= AUTO_OPEN_IDLE_SEC:
            logger.info("Sprang vindue over: indbakken blev set for %.0f s siden", idle)
            return
        # Vi tæller som en kigger med det samme, så en byge af synkede filer kun giver ét vindue.
        mark_inbox_seen()
    try:
        webbrowser.open(APP_URL)
        logger.info("Åbnede indbakken i browseren")
    except Exception as exc:
        logger.info("Kunne ikke åbne browseren: %s", exc)


def notify_ready(headline: str) -> None:
    """Vis en Windows-notifikation med den nye overskrift. Må aldrig kaste."""
    if not _enabled():
        logger.info("Sprang notifikation over: NOTIFY er slået fra")
        return
    toaster = _get_toaster()
    if toaster is None:
        return
    try:
        from windows_toasts import Toast, ToastButton, ToastScenario

        toast = Toast()
        toast.text_fields = ["Ny idé i indbakken", headline]
        # En almindelig notifikation forsvinder efter fem sekunder. Som påmindelse
        # bliver den stående, indtil du selv gør noget ved den — og så er den svær
        # at overse, også hvis du lige var ude af rummet.
        toast.scenario = ToastScenario.Reminder
        toast.AddAction(ToastButton("Åbn indbakken", "open"))
        toast.on_activated = lambda _: webbrowser.open(APP_URL)
        toaster.show_toast(toast)
        # Uden en kvittering her kan en notifikation, der aldrig blev vist, gemme sig
        # i loggen som "ingen fejl". Det skete.
        logger.info("Viste notifikation: %s", headline)
    except Exception as exc:
        _disable(f"kunne ikke vise notifikation: {exc}")


def _get_toaster():
    global _toaster, _broken
    with _lock:
        if _broken:
            return None
        if _toaster is not None:
            return _toaster
        try:
            from windows_toasts import InteractableWindowsToaster

            from app.winapp import register

            # Uden en registreret identitet tager Windows imod notifikationen og
            # smider den væk i stilhed. Genvejen er det, der gør programmet kendt.
            register()
            _toaster = InteractableWindowsToaster(APP_NAME, TOAST_AUMID)
            return _toaster
        except Exception as exc:
            _broken = True
            logger.info("Notifikationer er slået fra: %s", exc)
            return None


def _disable(reason: str) -> None:
    global _broken
    with _lock:
        _broken = True
    logger.info("Notifikationer er slået fra: %s", reason)
