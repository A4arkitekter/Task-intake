"""Giver programmet en identitet, Windows anerkender.

Windows viser kun notifikationer fra et program, det kender. Kendskabet kommer fra en
genvej i Start-menuen, der bærer et program-id. Mangler den, tager Windows imod
notifikationen og smider den væk uden at klage — og loggen ser ud, som om alt gik godt.

Genvejen peger på indbakken, ikke på serveren. Så starter et klik ikke en ekstra
kopi af programmet oven i den, der allerede kører.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from app.config import APP_NAME, APP_URL, TOAST_AUMID

logger = logging.getLogger(__name__)


def shortcut_path() -> Path:
    programs = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    return programs / f"{APP_NAME}.lnk"


def is_registered() -> bool:
    return shortcut_path().is_file()


def register(*, force: bool = False) -> Path | None:
    """Opret genvejen i Start-menuen. Returnerer stien, eller None hvis det ikke lykkedes."""
    if os.name != "nt":
        return None
    path = shortcut_path()
    if path.is_file() and not force:
        return path

    try:
        import pythoncom
        from win32com.propsys import propsys, pscon
        from win32com.shell import shell
    except ImportError as exc:
        logger.warning("Kan ikke registrere programmet hos Windows: pywin32 mangler (%s)", exc)
        return None

    try:
        from app.icons import ensure_app_icon

        icon = ensure_app_icon()
        path.parent.mkdir(parents=True, exist_ok=True)

        link = pythoncom.CoCreateInstance(
            shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLinkW
        )
        # explorer.exe åbner adressen i din standardbrowser.
        link.SetPath(str(Path(os.environ.get("WINDIR", r"C:\Windows")) / "explorer.exe"))
        link.SetArguments(APP_URL)
        link.SetDescription("Din idé-indbakke")
        link.SetIconLocation(str(icon), 0)

        store = link.QueryInterface(propsys.IID_IPropertyStore)
        store.SetValue(pscon.PKEY_AppUserModel_ID, propsys.PROPVARIANTType(TOAST_AUMID, pythoncom.VT_LPWSTR))
        store.Commit()

        link.QueryInterface(pythoncom.IID_IPersistFile).Save(str(path), 0)
    except Exception as exc:
        logger.warning("Kunne ikke registrere programmet hos Windows: %s", exc)
        return None

    logger.info("Registrerede %s hos Windows som %s", APP_NAME, TOAST_AUMID)
    return path


def unregister() -> None:
    shortcut_path().unlink(missing_ok=True)
