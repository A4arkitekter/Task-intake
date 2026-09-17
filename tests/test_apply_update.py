import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

from tools import apply_update


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_feed(source: Path, version: str, files: dict[str, bytes]) -> None:
    stage = source / "stage"
    entries = []
    for name, content in files.items():
        path = stage / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        entries.append({"path": name, "size": len(content), "sha256": digest(path)})
    manifest = {"schema": 1, "version": version, "commit": version, "files": entries}
    (stage / "_update-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    package = source / f"intake-update-{version}.zip"
    with ZipFile(package, "w", ZIP_DEFLATED) as archive:
        for path in stage.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(stage).as_posix())
    latest = {
        "schema": 1,
        "version": version,
        "package": package.name,
        "size": package.stat().st_size,
        "sha256": digest(package),
    }
    (source / "latest.json").write_text(json.dumps(latest), encoding="utf-8")


class ApplyUpdateTests(unittest.TestCase):
    def test_update_preserves_local_files_and_removes_obsolete_program_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            install = base / "install"
            source = base / "feed"
            install.mkdir()
            source.mkdir()
            (install / "app").mkdir()
            (install / "app" / "value.txt").write_text("old", encoding="utf-8")
            (install / "obsolete.txt").write_text("remove", encoding="utf-8")
            (install / ".env").write_text("SECRET=keep", encoding="utf-8")
            state = {
                "schema": 1,
                "version": "old",
                "files": ["app/value.txt", "obsolete.txt"],
            }
            state_path = install / ".update-state.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            make_feed(source, "new", {"app/value.txt": b"new", "new.txt": b"added"})

            with (
                patch.object(apply_update, "ROOT", install),
                patch.object(apply_update, "STATE_PATH", state_path),
            ):
                self.assertTrue(apply_update.check(source)["updateAvailable"])
                result = apply_update.apply(source)
                self.assertFalse(apply_update.check(source)["updateAvailable"])

            self.assertTrue(result["changed"])
            self.assertEqual((install / "app" / "value.txt").read_text(), "new")
            self.assertEqual((install / "new.txt").read_text(), "added")
            self.assertFalse((install / "obsolete.txt").exists())
            self.assertEqual((install / ".env").read_text(), "SECRET=keep")
            self.assertTrue(Path(str(result["recovery"])).is_file())

    def test_corrupt_package_is_rejected_before_installation_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            install = base / "install"
            source = base / "feed"
            install.mkdir()
            source.mkdir()
            state_path = install / ".update-state.json"
            state_path.write_text(json.dumps({"schema": 1, "version": "old", "files": []}))
            make_feed(source, "new", {"new.txt": b"added"})
            package = source / "intake-update-new.zip"
            package.write_bytes(package.read_bytes() + b"corrupt")

            with (
                patch.object(apply_update, "ROOT", install),
                patch.object(apply_update, "STATE_PATH", state_path),
            ):
                with self.assertRaisesRegex(RuntimeError, "størrelse"):
                    apply_update.apply(source)
            self.assertFalse((install / "new.txt").exists())


if __name__ == "__main__":
    unittest.main()
