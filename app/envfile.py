"""Hold den installerede .env i trit med produktet uden at overskrive hemmeligheder."""
from __future__ import annotations

from pathlib import Path

OBSOLETE_KEYS = {"APP_PASSWORD", "MAIL_TO", "MAIL_MARKER"}
LEGACY_DEFAULTS = {"AUTO_OPEN": "0", "OPEN_BROWSER": "0"}


def parse_assignments(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or "=" not in raw:
            continue
        key, _, value = raw.partition("=")
        key = key.strip()
        if key.startswith("#"):
            continue
        if key:
            values[key] = value.rstrip("\r")
    return values


def render_migrated(example_text: str, existing: dict[str, str]) -> str:
    used: set[str] = set()
    lines: list[str] = []
    for raw in example_text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            lines.append(raw)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in OBSOLETE_KEYS:
            continue
        used.add(key)
        if key in existing:
            lines.append(f"{key}={existing[key]}")
        else:
            lines.append(raw)
    extras = [key for key in existing if key not in used and key not in OBSOLETE_KEYS]
    if extras:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append("# Bevaret fra denne maskine")
        for key in extras:
            lines.append(f"{key}={existing[key]}")
    return "\n".join(lines).rstrip() + "\n"


def upsert_dotenv(env_path: Path, updates: dict[str, str]) -> None:
    """Sæt navngivne nøgler i .env uden at røre andre linjer."""
    text = env_path.read_text(encoding="utf-8-sig") if env_path.is_file() else ""
    lines = text.splitlines()
    found: set[str] = set()
    out: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if stripped and not stripped.startswith("#") and "=" in raw:
            key = raw.split("=", 1)[0].strip()
            if key in updates:
                out.append(f"{key}={updates[key]}")
                found.add(key)
                continue
        out.append(raw)
    for key, value in updates.items():
        if key not in found:
            out.append(f"{key}={value}")
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def migrate_dotenv(env_path: Path, example_path: Path) -> bool:
    """Udfyld manglende nøgler og fjern forældede. Returnerer True hvis filen blev skrevet."""
    if not example_path.is_file():
        return False
    example_text = example_path.read_text(encoding="utf-8-sig")
    existing_text = env_path.read_text(encoding="utf-8-sig") if env_path.is_file() else ""
    existing = parse_assignments(existing_text)
    if "APP_PASSWORD" in existing:
        existing.update(LEGACY_DEFAULTS)
    for key in OBSOLETE_KEYS:
        existing.pop(key, None)
    migrated = render_migrated(example_text, existing)
    if env_path.is_file() and existing_text.replace("\r\n", "\n") == migrated:
        return False
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text(migrated, encoding="utf-8")
    return True
