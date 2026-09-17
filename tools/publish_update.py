"""Udgiv en verificerbar programopdatering til kollegaernes NAS-feed."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DESTINATION = Path(r"\\a4diskstation4\A4software\task-intake\updates")

REQUIRED_FILES = (
    ".env.example", ".gitignore", "SETUP.bat", "setup.ps1", "install.ps1",
    "SYSTEMTJEK.bat", "Run-SystemCheck.ps1", "check_setup.ps1",
    "START.bat", "Start-Indtagelse.ps1", "OPDATER.bat", "Update-Intake.ps1",
    "UDGIV OPDATERING.bat", "Publish-Update.ps1", "Test-GitContents.ps1",
    "Test-InstallState.ps1", "Test-RuntimeManifest.ps1", "New-RuntimeManifest.ps1",
    ".gitattributes", "install-contract.json", "runtime-contract.json",
    "requirements.txt", "requirements-lock.txt", "requirements-gpu.txt",
    "requirements-dev.txt", "tools/Install-Helpers.ps1", "tools/publish_update.py",
    "docs/source/KOLLEGA-START.md", "docs/source/INSTALLATIONSVEJLEDNING.md",
    "docs/source/BRUGERVEJLEDNING.md", "01-START-HER.md",
    "static/brand/a4-logo.svg", "INSTALLATIONSVEJLEDNING.pdf",
    "BRUGERVEJLEDNING.pdf", "tools/generate_guides_pdf.py",
)

FORBIDDEN_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(^|/)runtime/", r"(^|/)\.env$", r"(^|/)\.venv/", r"(^|/)data/audio/",
        r"(^|/)data/models/", r"(^|/)data/behandlet/", r"(^|/)data/indbakke/",
        r"(^|/)data/logs/", r"\.sqlite3", r"(^|/)install-state\.json$",
        r"(^|/)setup-log\.txt$", r"(^|/)start-log\.txt$", r"(^|/)autostart-log\.txt$",
        r"(^|/)systemtjek\.txt$", r"(^|/)fejlrapport\.zip$", r"(^|/)update-source\.txt$",
        r"(^|/)\.update-state\.json$", r"(^|/)\.browser-update-result\.json$",
        r"\.(exe|dll|bin|wav|mp3|m4a|flac|ogg|wma|mp4|webm)$",
    )
)


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, text=True, encoding="utf-8",
        errors="replace", capture_output=True,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Git-kommandoen fejlede.")
    return result.stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_repository() -> list[str]:
    if git("status", "--porcelain"):
        raise RuntimeError("Commit ændringerne, før en opdatering udgives.")

    files = [line.replace("\\", "/") for line in git("ls-files").splitlines() if line]
    visible = set(
        line.replace("\\", "/")
        for line in git("ls-files", "--cached", "--others", "--exclude-standard").splitlines()
        if line
    )
    missing = [name for name in REQUIRED_FILES if name not in visible]
    forbidden = [name for name in files if any(pattern.search(name) for pattern in FORBIDDEN_PATTERNS)]
    if missing or forbidden:
        details = []
        if missing:
            details.append("Påkrævede Git-filer mangler: " + ", ".join(missing))
        if forbidden:
            details.append("Filer hører ikke til i Git: " + ", ".join(forbidden))
        raise RuntimeError("\n".join(details))
    return files


def publish(destination: Path) -> dict[str, object]:
    files = validate_repository()
    commit = git("rev-parse", "HEAD")
    version = commit[:12]
    destination.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="intake-publish-") as temp:
        temp_root = Path(temp)
        stage = temp_root / "package"
        manifest_files = []
        for name in files:
            source = ROOT / name
            if not source.is_file():
                raise RuntimeError(f"Git-filen mangler på disken: {name}")
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            manifest_files.append(
                {"path": name, "size": target.stat().st_size, "sha256": sha256(target)}
            )

        manifest = {
            "schema": 1, "version": version, "commit": commit,
            "createdUtc": utcnow(), "files": manifest_files,
        }
        (stage / "_update-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        package_name = f"intake-update-{version}.zip"
        local_package = temp_root / package_name
        with ZipFile(local_package, "w", ZIP_DEFLATED) as archive:
            for path in sorted(stage.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(stage).as_posix())

        published = destination / package_name
        shutil.copy2(local_package, published)
        shutil.copy2(ROOT / "OPDATER.bat", destination / "OPDATER.bat")
        shutil.copy2(ROOT / "Update-Intake.ps1", destination / "Update-Intake.ps1")

        latest = {
            "schema": 1, "version": version, "package": package_name,
            "size": published.stat().st_size, "sha256": sha256(published),
            "createdUtc": utcnow(),
        }
        latest_temp = destination / f"latest-{uuid4().hex}.json"
        latest_temp.write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(latest_temp, destination / "latest.json")
        return latest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", nargs="?", type=Path, default=DEFAULT_DESTINATION)
    args = parser.parse_args()
    try:
        latest = publish(args.destination.resolve())
    except Exception as exc:
        print(f"FEJL: {exc}")
        return 1
    print(f"Opdatering {latest['version']} er udgivet til {args.destination}")
    print("Kollegainstallationer henter den ved næste start eller med knappen i indbakken.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
