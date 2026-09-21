import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tools import install_autostart, service_supervisor


class SupervisorTests(unittest.TestCase):
    def test_pythonw_supervisor_uses_console_python_for_the_server(self):
        with (
            patch.object(service_supervisor.sys, "executable", r"C:\app\.venv\Scripts\pythonw.exe"),
            patch.object(Path, "is_file", return_value=True),
        ):
            self.assertTrue(service_supervisor.console_python().endswith("python.exe"))

    def test_unexpected_app_failure_is_restarted(self):
        lock = MagicMock()
        with (
            patch.object(service_supervisor, "acquire_lock", return_value=lock),
            patch.object(service_supervisor, "log"),
            patch.object(service_supervisor, "run_child", side_effect=[1, 0]) as run,
            patch.object(service_supervisor.time, "sleep") as sleep,
        ):
            self.assertEqual(service_supervisor.supervise(), 0)
        self.assertEqual(run.call_count, 2)
        sleep.assert_called_once_with(service_supervisor.RESTART_DELAY_SECONDS)
        lock.close.assert_called_once()

    def test_update_exit_runs_updater_and_restarts_app(self):
        lock = MagicMock()
        with (
            patch.object(service_supervisor, "acquire_lock", return_value=lock),
            patch.object(service_supervisor, "log"),
            patch.object(service_supervisor, "run_child", side_effect=[42, 0, 0]) as run,
            patch.object(service_supervisor, "write_update_result") as result,
        ):
            self.assertEqual(service_supervisor.supervise(), 0)
        self.assertEqual(run.call_count, 3)
        result.assert_called_once_with(True, "updated")


class AutostartTests(unittest.TestCase):
    def test_scheduled_task_targets_pythonw_supervisor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pythonw = root / ".venv" / "Scripts" / "pythonw.exe"
            supervisor = root / "tools" / "service_supervisor.py"
            pythonw.parent.mkdir(parents=True)
            supervisor.parent.mkdir(parents=True)
            pythonw.write_bytes(b"")
            supervisor.write_text("# supervisor", encoding="utf-8")
            success = MagicMock(returncode=0, stdout="", stderr="")
            with patch.object(install_autostart.subprocess, "run", return_value=success) as run:
                method = install_autostart.register(root)
        self.assertEqual(method, "task")
        create = run.call_args_list[0].args[0]
        self.assertIn("schtasks.exe", create)
        self.assertIn("ONLOGON", create)
        self.assertTrue(any("pythonw.exe" in value for value in create))
        self.assertTrue(any("service_supervisor.py" in value for value in create))


if __name__ == "__main__":
    unittest.main()
