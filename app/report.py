from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime, timezone

from app.config import DATA_DIR, ROOT

_SECRET_LINE = re.compile(
    r"(?im)^(\s*(?:APP_PASSWORD|SECRET_KEY|WRIKE_TOKEN|WRIKE_CLIENT_ID|WRIKE_CLIENT_SECRET|WRIKE_SECRET_KEY)\s*=\s*).+$"
)


def _sanitize(text: str) -> str:
    return _SECRET_LINE.sub(r"\1[SKJULT]", text)


def _add_text(archive: zipfile.ZipFile, name: str, text: str) -> None:
    archive.writestr(name, _sanitize(text).encode("utf-8"))


def build_error_report() -> bytes:
    buffer = io.BytesIO()
    created = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    info = "\n".join(
        [
            "Indtagelse - fejlrapport",
            f"Oprettet: {created}",
            f"Projektmappe: {ROOT}",
            "",
            "Rapporten indeholder kun tekstlogs og installationsstatus.",
            "Den indeholder ikke .env, tokens, runtime, lydfiler eller databasen.",
            "",
        ]
    )
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        _add_text(archive, "rapportinfo.txt", info)
        for name in ("setup-log.txt", "systemtjek.txt", "install-state.json", "start-log.txt"):
            path = ROOT / name
            if path.is_file():
                _add_text(archive, name, path.read_text(encoding="utf-8", errors="replace"))
        app_log = DATA_DIR / "logs" / "app.log"
        if app_log.is_file():
            _add_text(archive, "app.log", app_log.read_text(encoding="utf-8", errors="replace"))
    return buffer.getvalue()
