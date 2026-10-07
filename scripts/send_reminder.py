r"""Send fejlmailen nu, uden at vente til i morgen.

Bruges til at kontrollere, at mailen faktisk lander — ikke bare at der ikke kom en fejl.

Kør med:  .\.venv\Scripts\python.exe scripts\send_reminder.py
Tørkørsel: .\.venv\Scripts\python.exe scripts\send_reminder.py --draft
    Lægger den i Outlooks kladder i stedet, så du kan se den før du sender.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db, remind
from app.config import REMIND_TO


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    db.init()

    failed = db.list_failed()
    print(f"FEJL        {len(failed)} ting")
    if not failed:
        print("Ingen fejl. Der sendes ingen mail.")
        return 0

    now = datetime.now().astimezone()
    subject, body = remind.build_message(failed, now)
    print(f"TIL         {REMIND_TO}")
    print(f"EMNE        {subject}")
    print("-" * 60)
    print(body)
    print("-" * 60)

    send = "--draft" not in sys.argv
    if remind.send_email(subject, body, send=send):
        print("SENDT       ja. Se efter den i Outlook." if send else "KLADDE      gemt i Outlook.")
        return 0
    print("RESULTAT    mislykkedes. Se advarslen ovenfor.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
