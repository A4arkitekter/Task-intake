import os
import unittest
from unittest.mock import patch

from app import update as program_update
from tools import apply_and_restart


class UpdateHandoffTests(unittest.TestCase):
    def test_spawn_handoff_passes_wait_pid_and_detaches(self):
        with patch.object(program_update.subprocess, "Popen") as popen:
            self.assertTrue(program_update.spawn_update_handoff(wait_pid=4321))
        args, kwargs = popen.call_args
        command = args[0]
        self.assertEqual(command[0], program_update.sys.executable)
        self.assertTrue(str(command[1]).endswith("apply_and_restart.py"))
        self.assertEqual(kwargs["env"]["INTAKE_WAIT_PID"], "4321")
        self.assertTrue(kwargs["creationflags"] & getattr(program_update.subprocess, "DETACHED_PROCESS", 0))

    def test_handoff_exits_zero_when_spawn_succeeds(self):
        exits = []

        def fake_exit(code):
            exits.append(code)
            raise SystemExit(code)

        with (
            patch.object(program_update, "spawn_update_handoff", return_value=True),
            patch.object(program_update.os, "_exit", side_effect=fake_exit),
        ):
            with self.assertRaises(SystemExit):
                program_update.handoff_and_exit()
        self.assertEqual(exits, [0])

    def test_handoff_falls_back_to_exit_42_when_spawn_fails(self):
        exits = []

        def fake_exit(code):
            exits.append(code)
            raise SystemExit(code)

        with (
            patch.object(program_update, "spawn_update_handoff", return_value=False),
            patch.object(program_update.os, "_exit", side_effect=fake_exit),
        ):
            with self.assertRaises(SystemExit):
                program_update.handoff_and_exit()
        self.assertEqual(exits, [program_update.UPDATE_RESTART_EXIT_CODE])


class ApplyAndRestartTests(unittest.TestCase):
    def test_waits_for_pid_then_applies_and_starts_supervisor(self):
        with (
            patch.dict(os.environ, {"INTAKE_WAIT_PID": "1234"}),
            patch.object(apply_and_restart, "wait_for_pid") as wait_pid,
            patch.object(apply_and_restart, "wait_for_supervisor_lock") as wait_lock,
            patch.object(
                apply_and_restart,
                "apply_package",
                return_value={"changed": True, "version": "abc123"},
            ),
            patch.object(apply_and_restart, "start_supervisor") as start,
            patch.object(apply_and_restart, "write_update_result") as result,
            patch.object(apply_and_restart, "log"),
        ):
            self.assertEqual(apply_and_restart.main(), 0)
        wait_pid.assert_called_once_with(1234)
        wait_lock.assert_called_once()
        start.assert_called_once()
        result.assert_called_once_with(True, "updated")

    def test_starts_supervisor_even_when_apply_fails(self):
        with (
            patch.dict(os.environ, {"INTAKE_WAIT_PID": ""}),
            patch.object(apply_and_restart, "wait_for_pid") as wait_pid,
            patch.object(apply_and_restart, "wait_for_supervisor_lock"),
            patch.object(apply_and_restart, "apply_package", side_effect=RuntimeError("nas nede")),
            patch.object(apply_and_restart, "start_supervisor") as start,
            patch.object(apply_and_restart, "write_update_result") as result,
            patch.object(apply_and_restart, "log"),
        ):
            self.assertEqual(apply_and_restart.main(), 1)
        wait_pid.assert_not_called()
        start.assert_called_once()
        result.assert_called_once_with(False, "update_failed")


class PublisherHandoffContractTests(unittest.TestCase):
    def test_publisher_and_git_check_require_handoff_script(self):
        from tools import publish_update

        self.assertIn("tools/apply_and_restart.py", publish_update.REQUIRED_FILES)
        script = (program_update.ROOT / "Test-GitContents.ps1").read_text(encoding="utf-8")
        self.assertIn("tools/apply_and_restart.py", script)
        self.assertTrue((program_update.ROOT / "tools" / "apply_and_restart.py").is_file())


if __name__ == "__main__":
    unittest.main()
