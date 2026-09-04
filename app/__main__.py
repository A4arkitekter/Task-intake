"""Kør med: python -m app"""

import uvicorn

from app.config import ensure_dirs


def main() -> None:
    ensure_dirs()
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
