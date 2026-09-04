import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UPDATE_PATH = r"\\a4diskstation4\A4software\task-intake\updates"


class RepositoryContractTests(unittest.TestCase):
    def test_git_contents_contract(self):
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ROOT / "Test-GitContents.ps1"),
            ],
            cwd=ROOT,
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_process_probe_handles_missing_python_without_terminating(self):
        command = (
            f". '{ROOT / 'tools' / 'Install-Helpers.ps1'}'; "
            "$result = Invoke-ProcessCapture 'C:\\Windows\\System32\\missing-python.exe' '--version'; "
            "if ($result.ExitCode -ne -1) { exit 1 }"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            cwd=ROOT,
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_start_batch_is_a_thin_powershell_launcher(self):
        script = (ROOT / "START.bat").read_text(encoding="utf-8-sig")
        self.assertIn("Start-Indtagelse.ps1", script)
        self.assertNotIn("for /f", script.lower())
        self.assertNotIn("netstat", script.lower())

    def test_installed_start_handles_browser_requested_update_and_restart(self):
        script = (ROOT / "Start-Indtagelse.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("Update-Intake.ps1", script)
        self.assertIn("$exitCode -ne 42", script)
        self.assertIn("Write-BrowserUpdateResult", script)
        self.assertNotIn("-Automatic", script)

        updater = (ROOT / "Update-Intake.ps1").read_text(encoding="utf-8-sig")
        self.assertIn(UPDATE_PATH, updater)
        self.assertIn("WaitOne(3000)", updater)

    def test_publisher_requires_clean_tree_and_includes_updater_bootstrap(self):
        script = (ROOT / "Publish-Update.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("git status --porcelain)", script)
        self.assertNotIn("--untracked-files=no", script)
        self.assertIn('(Join-Path $Destination "OPDATER.bat")', script)
        self.assertIn('(Join-Path $Destination "Update-Intake.ps1")', script)
        self.assertIn(UPDATE_PATH, script)
        self.assertTrue((ROOT / "UDGIV OPDATERING.bat").is_file())

    def test_system_check_tells_user_to_send_only_safe_report(self):
        script = (ROOT / "SYSTEMTJEK.bat").read_text(encoding="utf-8-sig")
        self.assertIn("Send kun fejlrapport.zip til IT", script)
        self.assertNotIn("Send systemtjek.txt", script)

    def test_setup_explains_that_local_configuration_is_preserved(self):
        script = (ROOT / "SETUP.bat").read_text(encoding="utf-8-sig")
        self.assertIn("Eksisterende runtime, .env og data bevares", script)

    def test_updater_refuses_to_run_directly_from_a_network_share(self):
        script = (ROOT / "Update-Intake.ps1").read_text(encoding="utf-8-sig")
        self.assertIn('$PSScriptRoot.StartsWith("\\\\")', script)
        self.assertIn("maa ikke koeres fra NAS'en", script)

    def test_autostart_launches_the_wrapper_not_pythonw(self):
        script = (ROOT / "scripts" / "install-autostart.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("Start-Indtagelse.ps1", script)
        self.assertIn("-NoBrowser", script)
        self.assertIn("powershell.exe", script)
        self.assertNotIn("pythonw.exe", script.lower())

    def test_inbox_exposes_update_and_restart_button(self):
        script = (ROOT / "static" / "js" / "inbox.js").read_text(encoding="utf-8")
        self.assertIn("Opdatér og genstart", script)
        self.assertIn("/api/update/apply", script)
        self.assertIn("X-Update-Token", script)

    def test_powershell_start_script_has_valid_syntax_and_safe_port_handling(self):
        script_path = ROOT / "Start-Indtagelse.ps1"
        command = (
            "$null = [scriptblock]::Create((Get-Content -LiteralPath "
            f"'{script_path}' -Raw)); exit 0"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            cwd=ROOT,
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        script = script_path.read_text(encoding="utf-8-sig")
        self.assertIn("from app.config import PORT", script)
        self.assertIn("Invoke-RestMethod", script)
        self.assertIn("Test-LocalPortInUse", script)
        self.assertIn("Programmet koerer allerede. Browseren aabnes igen.", script)


def make_start_fixture(tmp_path, port):
    project = tmp_path / "projekt med mellemrum"
    (project / ".venv" / "Scripts").mkdir(parents=True)
    (project / "runtime").mkdir()
    (project / "app").mkdir()
    shutil.copy2(ROOT / "Start-Indtagelse.ps1", project / "Start-Indtagelse.ps1")
    shutil.copy2(Path(sys.executable), project / ".venv" / "Scripts" / "python.exe")
    source_venv = Path(sys.executable).parent.parent
    pyvenv = source_venv / "pyvenv.cfg"
    if pyvenv.is_file():
        shutil.copy2(pyvenv, project / ".venv" / "pyvenv.cfg")
    else:
        (project / ".venv" / "pyvenv.cfg").write_text(
            f"home = {Path(sys.executable).parent}\ninclude-system-site-packages = false\n",
            encoding="ascii",
        )
    (project / "runtime" / "runtime-manifest.json").write_text("{}", encoding="utf-8")
    (project / "Test-InstallState.ps1").write_text(
        "param([switch]$Quiet)\nexit 0\n", encoding="ascii"
    )
    (project / "app" / "__init__.py").write_text("", encoding="ascii")
    (project / "app" / "config.py").write_text(f"PORT = {port}\n", encoding="ascii")
    (project / "app" / "main.py").write_text("# stub\n", encoding="ascii")
    (project / "app" / "__main__.py").write_text('print("FAKE APP STARTED")\n', encoding="ascii")
    return project


def run_start_fixture(project):
    return subprocess.run(
        [
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(project / "Start-Indtagelse.ps1"), "-NoBrowser",
        ],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=30,
    )


class StartFlowTests(unittest.TestCase):
    def test_start_flow_handles_project_path_with_spaces(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
        port = server.server_port
        server.server_close()
        with tempfile.TemporaryDirectory() as tmp:
            project = make_start_fixture(Path(tmp), port)
            result = run_start_fixture(project)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("FAKE APP STARTED", result.stdout)
        self.assertIn(f"http://127.0.0.1:{port}", result.stdout)

    def test_start_flow_reuses_an_existing_intake_server(self):
        class HealthHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps({"ok": True}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), HealthHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                project = make_start_fixture(Path(tmp), server.server_port)
                result = run_start_fixture(project)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Programmet koerer allerede", result.stdout)
        self.assertNotIn("FAKE APP STARTED", result.stdout)

    def test_start_flow_rejects_a_port_used_by_another_program(self):
        class OtherHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(404)
                self.end_headers()

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), OtherHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                project = make_start_fixture(Path(tmp), server.server_port)
                result = run_start_fixture(project)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("bruges af et andet program", result.stdout)
        self.assertNotIn("FAKE APP STARTED", result.stdout)

    def test_start_flow_applies_browser_update_and_restarts_server(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
        port = server.server_port
        server.server_close()
        with tempfile.TemporaryDirectory() as tmp:
            project = make_start_fixture(Path(tmp), port)
            (project / "app" / "__main__.py").write_text(
                "from pathlib import Path\n"
                "import sys\n"
                "marker = Path(__file__).resolve().parents[1] / 'update-applied.txt'\n"
                "if not marker.exists():\n"
                "    sys.exit(42)\n"
                "print('FAKE UPDATED APP STARTED')\n",
                encoding="utf-8",
            )
            (project / "Update-Intake.ps1").write_text(
                "Set-Content -LiteralPath (Join-Path $PSScriptRoot 'update-applied.txt') -Value 'ok'\n"
                "exit 0\n",
                encoding="ascii",
            )

            result = run_start_fixture(project)
            update_result = json.loads(
                (project / ".browser-update-result.json").read_text(encoding="utf-8-sig")
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("FAKE UPDATED APP STARTED", result.stdout)
        self.assertTrue(update_result["ok"])


if __name__ == "__main__":
    unittest.main()
