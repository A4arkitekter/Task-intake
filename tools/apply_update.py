"""Kontrollér eller installer en verificeret Task-intake-opdatering."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path(r"\\a4diskstation4\A4software\task-intake\updates")
STATE_PATH = ROOT / ".update-state.json"
PROTECTED = {
    ".env", "install-state.json", "setup-log.txt", "systemtjek.txt",
    "fejlrapport.zip", "update-source.txt", ".update-state.json",
    ".browser-update-result.json",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def safe_relative(value: str) -> PurePosixPath:
    normalized = value.replace("\\", "/").lstrip("/")
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or ".." in path.parts:
        raise RuntimeError(f"Ugyldig filsti i opdateringen: {value}")
    if normalized in PROTECTED or path.parts[0] in {".git", ".venv", "runtime"}:
        raise RuntimeError(f"Beskyttet fil i opdateringen: {value}")
    if path.parts[0] == "data" and normalized != "data/.gitkeep":
        raise RuntimeError(f"Beskyttet datafil i opdateringen: {value}")
    return path


def target_path(relative: PurePosixPath) -> Path:
    target = (ROOT / Path(*relative.parts)).resolve()
    root = ROOT.resolve()
    if target != root and root not in target.parents:
        raise RuntimeError(f"Filstien forlader programmappen: {relative}")
    return target


def load_latest(source: Path) -> dict:
    latest_path = source / "latest.json"
    if not latest_path.is_file():
        raise RuntimeError(f"Opdateringsmappen mangler latest.json: {source}")
    latest = read_json(latest_path)
    if latest.get("schema") != 1 or not latest.get("version") or not latest.get("package"):
        raise RuntimeError("Opdateringsbeskrivelsen har et ukendt format")
    return latest


def current_state() -> dict | None:
    return read_json(STATE_PATH) if STATE_PATH.is_file() else None


def check(source: Path) -> dict:
    latest = load_latest(source)
    current = current_state()
    current_version = (current or {}).get("version")
    return {
        "ok": True,
        "updateAvailable": current_version != latest["version"],
        "currentVersion": current_version,
        "latestVersion": latest["version"],
    }


def verify_package(source: Path, latest: dict, extract_root: Path) -> list[tuple[PurePosixPath, Path, Path]]:
    package = source / str(latest["package"])
    if not package.is_file():
        raise RuntimeError(f"Opdateringspakken mangler: {package}")
    if package.stat().st_size != int(latest["size"]):
        raise RuntimeError("Opdateringspakken har forkert størrelse")
    if sha256(package) != str(latest["sha256"]).lower():
        raise RuntimeError("Opdateringspakken har forkert checksum")

    with ZipFile(package) as archive:
        for member in archive.infolist():
            member_path = PurePosixPath(member.filename)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise RuntimeError(f"Usikker sti i ZIP: {member.filename}")
        archive.extractall(extract_root)

    manifest_path = extract_root / "_update-manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("Pakken mangler sit interne manifest")
    manifest = read_json(manifest_path)
    if manifest.get("version") != latest["version"]:
        raise RuntimeError("Pakkens version matcher ikke latest.json")
    entries = manifest.get("files") or []
    if not entries:
        raise RuntimeError("Pakken indeholder ingen programfiler")

    verified = []
    for entry in entries:
        relative = safe_relative(str(entry["path"]))
        package_file = extract_root / Path(*relative.parts)
        if not package_file.is_file():
            raise RuntimeError(f"En fil fra manifestet mangler: {relative}")
        if (
            package_file.stat().st_size != int(entry["size"])
            or sha256(package_file) != str(entry["sha256"]).lower()
        ):
            raise RuntimeError(f"En fil i pakken er beskadiget: {relative}")
        verified.append((relative, package_file, target_path(relative)))
    return verified


def apply(source: Path) -> dict:
    if (ROOT / ".git").is_dir():
        raise RuntimeError("Dette er en udviklingsmappe med Git. Opdater den med Git i stedet")
    latest = load_latest(source)
    current = current_state()
    if (current or {}).get("version") == latest["version"]:
        return {"changed": False, "version": latest["version"], "recovery": None}

    with tempfile.TemporaryDirectory(prefix="intake-update-") as temp:
        temp_root = Path(temp)
        extract_root = temp_root / "package"
        rollback_root = temp_root / "rollback"
        extract_root.mkdir()
        rollback_root.mkdir()
        verified = verify_package(source, latest, extract_root)

        new_paths = {relative.as_posix() for relative, _package_file, _target in verified}
        obsolete = []
        for old in (current or {}).get("files", []):
            relative = safe_relative(str(old))
            if relative.as_posix() not in new_paths:
                obsolete.append((relative, target_path(relative)))

        recovery_dir = ROOT / "data" / "update-backups"
        recovery_dir.mkdir(parents=True, exist_ok=True)
        old_version = (current or {}).get("version", "ukendt")
        recovery = recovery_dir / f"pre-{latest['version']}-fra-{old_version}.zip"
        with ZipFile(recovery, "w") as archive:
            if STATE_PATH.is_file():
                archive.write(STATE_PATH, ".update-state.json")
            for relative, _package_file, destination in verified:
                if destination.is_file():
                    archive.write(destination, relative.as_posix())
            for relative, destination in obsolete:
                if destination.is_file():
                    archive.write(destination, relative.as_posix())

        changed: list[tuple[Path, Path | None]] = []
        try:
            for relative, package_file, destination in verified:
                backup = None
                if destination.is_file():
                    backup = rollback_root / Path(*relative.parts)
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(destination, backup)
                destination.parent.mkdir(parents=True, exist_ok=True)
                changed.append((destination, backup))
                shutil.copy2(package_file, destination)

            for relative, destination in obsolete:
                if destination.is_file():
                    backup = rollback_root / Path(*relative.parts)
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(destination, backup)
                    changed.append((destination, backup))
                    destination.unlink()

            new_state = {
                "schema": 1,
                "version": latest["version"],
                "updatedUtc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "files": [relative.as_posix() for relative, _package_file, _target in verified],
            }
            state_temp = ROOT / ".update-state.new.json"
            state_temp.write_text(json.dumps(new_state, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(state_temp, STATE_PATH)
        except Exception:
            for destination, backup in reversed(changed):
                if backup and backup.is_file():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup, destination)
                else:
                    destination.unlink(missing_ok=True)
            raise

    return {"changed": True, "version": latest["version"], "recovery": str(recovery)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    try:
        if args.check_only:
            print(json.dumps(check(args.source), ensure_ascii=False))
        else:
            result = apply(args.source)
            if result["changed"]:
                print(f"Programmet er opdateret til {result['version']}.")
                print(f"Recovery: {result['recovery']}")
            else:
                print(f"Programmet er allerede opdateret ({result['version']}).")
        return 0
    except Exception as exc:
        if args.check_only:
            print(json.dumps({"ok": False, "updateAvailable": False, "error": str(exc)}, ensure_ascii=False))
            return 0
        print(f"FEJL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
