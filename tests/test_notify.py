import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["NOTIFY"] = "0"
os.environ["WATCH_ENABLED"] = "0"

from app import activity, notify
from app.rewrite import MAX_CONTEXT, MAX_TRANSCRIPT_CHARS, context_size, fit_transcript


class AutoOpenTests(unittest.TestCase):
    def setUp(self):
        activity.reset()
        os.environ["AUTO_OPEN"] = "1"

    def tearDown(self):
        os.environ["AUTO_OPEN"] = "0"
        activity.reset()

    def test_opens_when_nobody_is_looking(self):
        with patch("app.notify.webbrowser.open") as opener:
            notify.open_inbox_if_unattended()
        opener.assert_called_once()

    def test_stays_quiet_when_a_tab_already_shows_the_inbox(self):
        activity.mark_inbox_seen()
        with patch("app.notify.webbrowser.open") as opener:
            notify.open_inbox_if_unattended()
        opener.assert_not_called()

    def test_skipping_the_window_is_logged(self):
        activity.mark_inbox_seen()
        with self.assertLogs("app.notify", level="INFO") as logs:
            notify.open_inbox_if_unattended()
        self.assertTrue(any("Sprang vindue over" in line for line in logs.output))

    def test_a_burst_of_synced_files_opens_one_window(self):
        with patch("app.notify.webbrowser.open") as opener:
            for _ in range(5):
                notify.open_inbox_if_unattended()
        self.assertEqual(opener.call_count, 1)

    def test_env_can_turn_it_off(self):
        os.environ["AUTO_OPEN"] = "0"
        with patch("app.notify.webbrowser.open") as opener:
            notify.open_inbox_if_unattended()
        opener.assert_not_called()

    def test_a_broken_browser_does_not_break_the_pipeline(self):
        with patch("app.notify.webbrowser.open", side_effect=OSError("ingen browser")):
            notify.open_inbox_if_unattended()


class ContextSizeTests(unittest.TestCase):
    def test_a_short_idea_uses_the_small_window(self):
        self.assertEqual(context_size("Husk at ringe til Jens"), 2048)

    def test_a_long_recording_gets_room_for_the_whole_transcript(self):
        # Ti minutters tale ville blive afkortet lydløst i et 2048-vindue.
        self.assertGreater(context_size("ord " * 4000), 4096)

    def test_the_window_stops_where_the_graphics_card_does(self):
        self.assertEqual(context_size("ord " * 200_000), MAX_CONTEXT)


class FitTranscriptTests(unittest.TestCase):
    def test_normal_length_is_untouched(self):
        text = "Husk at ringe til Jens om lageret."
        self.assertEqual(fit_transcript(text), text)

    def test_an_enormous_transcript_keeps_its_ending(self):
        # Det vigtigste i en lang indtaling siges ofte allersidst.
        text = "start " + "midte " * 10_000 + "FRISTEN ER DEN FJORTENDE NOVEMBER"
        fitted = fit_transcript(text)
        self.assertLessEqual(len(fitted), MAX_TRANSCRIPT_CHARS + 40)
        self.assertIn("FRISTEN ER DEN FJORTENDE NOVEMBER", fitted)
        self.assertTrue(fitted.startswith("start"))
        self.assertIn("midten er udeladt", fitted)


class LimitTests(unittest.TestCase):
    def test_there_is_no_duration_limit_by_default(self):
        from app.config import MAX_DURATION_SEC

        self.assertEqual(MAX_DURATION_SEC, 0.0)


if __name__ == "__main__":
    unittest.main()
