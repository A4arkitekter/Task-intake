import hashlib
import json
import shutil
import subprocess
import tempfile
import time
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def make_update_fixture(tmp_path, corrupt_descriptor=False, with_obsolete=False):
    install = tmp_path / "installeret program"
    source = tmp_path / "netværkskilde"
    package_root = tmp_path / "pakke"
    install.mkdir()
    source.mkdir()
    package_root.mkdir()

    shutil.copy2(ROOT / "Update-Intake.ps1", install / "Update-Intake.ps1")
    (install / "Test-InstallState.ps1").write_text("param([switch]$Quiet)\nexit 0\n", encoding="utf-8")
    (install / "app.py").write_text("gammel\n", encoding="utf-8")
    (install / ".env").write_text("APP_PASSWORD=hemmelig\n", encoding="utf-8")
    (install / "runtime").mkdir()
    (install / "runtime" / "bevar.txt").write_text("runtime\n", encoding="utf-8")
    (install / "data").mkdir()
    (install / "data" / "bevar.txt").write_text("data\n", encoding="utf-8")
    if with_obsolete:
        (install / "gammel-programfil.py").write_text("udgaaet\n", encoding="utf-8")
        (install / ".update-state.json").write_text(
            json.dumps({
                "schema": 1,
                "version": "previous",
                "files": ["app.py", "gammel-programfil.py"],
            }),
            encoding="utf-8",
        )

    new_app = package_root / "app.py"
    new_app.write_text("ny version\n", encoding="utf-8")
    app_bytes = new_app.read_bytes()
    manifest = {
        "schema": 1,
        "version": "abc123def456",
        "files": [{
            "path": "app.py",
            "size": len(app_bytes),
            "sha256": hashlib.sha256(app_bytes).hexdigest(),
        }],
    }
    (package_root / "_update-manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    package = source / "intake-update-abc123def456.zip"
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in package_root.iterdir():
            archive.write(path, path.name)
    package_bytes = package.read_bytes()
    descriptor_hash = hashlib.sha256(package_bytes).hexdigest()
    if corrupt_descriptor:
        descriptor_hash = "0" * 64
    (source / "latest.json").write_text(
        json.dumps({
            "schema": 1,
            "version": "abc123def456",
            "package": package.name,
            "size": len(package_bytes),
            "sha256": descriptor_hash,
        }),
        encoding="utf-8",
    )
    return install, source


def run_updater(install, source):
    return subprocess.run(
        [
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(install / "Update-Intake.ps1"),
            "-Source", str(source),
        ],
        cwd=install,
        capture_output=True,
        text=True,
        timeout=60,
    )


def check_updater(install, source):
    result = subprocess.run(
        [
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(install / "Update-Intake.ps1"),
            "-Source", str(source), "-CheckOnly",
        ],
        cwd=install,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    payload = json.loads([line for line in result.stdout.splitlines() if line.strip()][-1])
    return result, payload


class UpdaterTests(unittest.TestCase):
    def test_check_only_reports_version_without_changing_program(self):
        with tempfile.TemporaryDirectory() as tmp:
            install, source = make_update_fixture(Path(tmp))

            result, payload = check_updater(install, source)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["updateAvailable"])
            self.assertEqual(payload["latestVersion"], "abc123def456")
            self.assertEqual((install / "app.py").read_text(encoding="utf-8"), "gammel\n")

            self.assertEqual(run_updater(install, source).returncode, 0)
            _result, current_payload = check_updater(install, source)
            self.assertFalse(current_payload["updateAvailable"])

    def test_updater_replaces_program_and_preserves_local_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            install, source = make_update_fixture(Path(tmp))

            result = run_updater(install, source)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((install / "app.py").read_text(encoding="utf-8"), "ny version\n")
            self.assertEqual((install / ".env").read_text(encoding="utf-8"), "APP_PASSWORD=hemmelig\n")
            self.assertEqual((install / "runtime" / "bevar.txt").read_text(encoding="utf-8"), "runtime\n")
            self.assertEqual((install / "data" / "bevar.txt").read_text(encoding="utf-8"), "data\n")
            state = json.loads((install / ".update-state.json").read_text(encoding="utf-8-sig"))
            self.assertEqual(state["version"], "abc123def456")
            self.assertIn("SETUP.bat skal ikke koeres", result.stdout)

    def test_updater_rejects_corrupt_package_without_touching_program(self):
        with tempfile.TemporaryDirectory() as tmp:
            install, source = make_update_fixture(Path(tmp), corrupt_descriptor=True)

            result = run_updater(install, source)

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((install / "app.py").read_text(encoding="utf-8"), "gammel\n")
            self.assertIn("forkert checksum", result.stdout)

    def test_updater_removes_files_that_disappeared_from_new_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            install, source = make_update_fixture(Path(tmp), with_obsolete=True)

            result = run_updater(install, source)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse((install / "gammel-programfil.py").exists())

    def test_automatic_update_abandons_unreachable_smb_source_quickly(self):
        with tempfile.TemporaryDirectory() as tmp:
            install, _ = make_update_fixture(Path(tmp))
            started = time.monotonic()
            result = subprocess.run(
                [
                    "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-File", str(install / "Update-Intake.ps1"),
                    "-Source", r"\\192.0.2.1\missing", "-Automatic",
                ],
                cwd=install,
                capture_output=True,
                text=True,
                timeout=10,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertLess(time.monotonic() - started, 7)
            self.assertEqual((install / "app.py").read_text(encoding="utf-8"), "gammel\n")
            self.assertIn("installerede version bruges videre", result.stdout)

    def test_publisher_creates_verified_feed_and_bootstrap_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            developer = Path(tmp) / "udvikler"
            destination = Path(tmp) / "central opdatering"
            developer.mkdir()
            destination.mkdir()
            for name in ("Publish-Update.ps1", "OPDATER.bat", "Update-Intake.ps1"):
                shutil.copy2(ROOT / name, developer / name)
            (developer / "Test-GitContents.ps1").write_text("exit 0\n", encoding="utf-8")
            (developer / "app.py").write_text("print('version')\n", encoding="utf-8")

            subprocess.run(["git", "init", "-q"], cwd=developer, check=True)
            subprocess.run(["git", "config", "user.name", "Updater test"], cwd=developer, check=True)
            subprocess.run(["git", "config", "user.email", "updater@example.invalid"], cwd=developer, check=True)
            subprocess.run(["git", "add", "."], cwd=developer, check=True)
            subprocess.run(["git", "commit", "-qm", "Test version"], cwd=developer, check=True)

            result = subprocess.run(
                [
                    "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-File", str(developer / "Publish-Update.ps1"),
                    "-Destination", str(destination),
                ],
                cwd=developer,
                capture_output=True,
                text=True,
                timeout=60,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            latest = json.loads((destination / "latest.json").read_text(encoding="utf-8-sig"))
            package = destination / latest["package"]
            self.assertEqual(package.stat().st_size, latest["size"])
            self.assertEqual(hashlib.sha256(package.read_bytes()).hexdigest(), latest["sha256"])
            self.assertTrue((destination / "OPDATER.bat").is_file())
            self.assertTrue((destination / "Update-Intake.ps1").is_file())
            with zipfile.ZipFile(package) as archive:
                names = set(archive.namelist())
            self.assertIn("_update-manifest.json", names)
            self.assertIn("app.py", names)


if __name__ == "__main__":
    unittest.main()
