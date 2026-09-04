"""Kør med: python -m app"""

import uvicorn

from app.config import DEV_RELOAD, ensure_dirs


def main() -> None:
    ensure_dirs()
    # reload spawner en ekstra proces og hører ikke hjemme i autostart. Sæt DEV_RELOAD=1 under udvikling.
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=DEV_RELOAD)


if __name__ == "__main__":
    main()
