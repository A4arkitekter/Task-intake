r"""Prøve: tog Windows imod vores notifikation?

"Der kom ingen fejl" er ikke et bevis. Windows kan tage imod en notifikation fra et
program, det ikke kender, og smide den væk uden at klage. Windows fører til gengæld
selv en protokol, og den kan læses bagefter.

Vi tæller kun vores egne poster og læser ikke andre programmers notifikationer.

Kør med:  .\.venv\Scripts\python.exe scripts\probe_toast.py
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import TOAST_AUMID

WPN_DB = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Notifications" / "wpndatabase.db"


def our_notification_count() -> int:
    """Tæl de notifikationer Windows har registreret fra netop dette program."""
    if not WPN_DB.is_file():
        return -1
    copy = Path(tempfile.gettempdir()) / "indtagelse-wpn.db"
    for suffix in ("", "-wal", "-shm"):
        source = WPN_DB.with_name(WPN_DB.name + suffix)
        target = copy.with_name(copy.name + suffix)
        target.unlink(missing_ok=True)
        # Databasen skriver til en log ved siden af. Uden den ser man kun det, der blev
        # skrevet igennem for længe siden — altså netop ikke den, man lige sendte.
        if source.is_file():
            shutil.copy2(source, target)

    con = sqlite3.connect(copy)
    try:
        row = con.execute(
            """
            SELECT COUNT(*) FROM Notification n
            JOIN NotificationHandler h ON h.RecordId = n.HandlerId
            WHERE h.PrimaryId = ?
            """,
            (TOAST_AUMID,),
        ).fetchone()
    finally:
        con.close()
    return int(row[0])


def main() -> int:
    from app.notify import notify_ready

    before = our_notification_count()
    if before < 0:
        print("Fandt ikke Windows' notifikationsprotokol. Proeven kan ikke afgoeres.")
        return 1
    print(f"AFSENDER    {TOAST_AUMID}")
    print(f"FOER        {before} registrerede notifikationer")

    notify_ready("Proeve: kan du se denne notifikation?")

    # Windows skriver protokollen asynkront, saa der skal ventes paa den. Et fast
    # sekundtal gav foerst det forkerte svar "blev ikke registreret".
    deadline = time.monotonic() + 15
    after = before
    while after <= before and time.monotonic() < deadline:
        time.sleep(1)
        after = our_notification_count()

    if after > before:
        print(f"EFTER       {after}. Windows tog imod den.")
        print("SKAERM      den boer staa nede til hoejre, indtil du lukker den.")
        return 0

    print(f"EFTER       {after}. Windows registrerede ingen ny notifikation.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
