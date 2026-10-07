import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["WHISPER_WARMUP"] = "0"
os.environ["NOTIFY"] = "0"
os.environ["WATCH_ENABLED"] = "0"
os.environ["AUTO_OPEN"] = "0"
os.environ["REMIND_ENABLED"] = "1"
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="intake-remind-")

from app import db, remind

NOW = datetime(2026, 9, 4, 9, 0, tzinfo=timezone.utc)


def add_waiting(*, days_old: int, title: str) -> str:
    capture = db.create_capture(
        source="sync",
        audio_path="lyd.m4a",
        audio_mime="audio/mp4",
        duration_sec=5,
    )
    created = (NOW - timedelta(days=days_old)).isoformat()
    db.update_capture(capture["id"], status="ready", transcript=title, created_at=created)
    db.replace_proposals(capture["id"], [{"title": title, "note": f"{title}."}])
    return capture["id"]


def add_failed(*, days_old: int, reason: str) -> str:
    capture = db.create_capture(
        source="sync",
        audio_path="lyd.m4a",
        audio_mime="audio/mp4",
        duration_sec=5,
    )
    created = (NOW - timedelta(days=days_old)).isoformat()
    db.update_capture(capture["id"], status="error", error_message=reason, created_at=created)
    return capture["id"]


class WaitingTests(unittest.TestCase):
    def setUp(self):
        db.init()
        with db.cursor() as cur:
            cur.execute("DELETE FROM proposals")
            cur.execute("DELETE FROM captures")
            cur.execute("DELETE FROM app_state")

    def test_an_empty_inbox_has_nothing_waiting(self):
        self.assertEqual(db.list_waiting(), [])

    def test_a_card_you_have_not_sent_is_waiting(self):
        add_waiting(days_old=3, title="Møde med Tine")
        waiting = db.list_waiting()
        self.assertEqual(len(waiting), 1)
        self.assertEqual(waiting[0]["title"], "Møde med Tine")

    def test_a_failed_recording_is_waiting_too(self):
        # En fejlet optagelse er præcis det, man ikke må glemme.
        add_failed(days_old=1, reason="GPU var optaget")
        waiting = db.list_waiting()
        self.assertEqual(len(waiting), 1)
        self.assertEqual(waiting[0]["status"], "error")
        self.assertEqual(len(db.list_failed()), 1)

    def test_a_pending_idea_is_not_a_mail_failure(self):
        add_waiting(days_old=3, title="Møde med Tine")
        self.assertEqual(len(db.list_waiting()), 1)
        self.assertEqual(db.list_failed(), [])

    def test_a_recording_still_being_processed_does_not_count(self):
        db.create_capture(source="sync", audio_path="lyd.m4a", audio_mime="audio/mp4", duration_sec=5)
        self.assertEqual(db.list_waiting(), [])

    def test_the_oldest_comes_first(self):
        add_waiting(days_old=1, title="Ny")
        add_waiting(days_old=12, title="Gammel")
        self.assertEqual([item["title"] for item in db.list_waiting()], ["Gammel", "Ny"])


class MessageTests(unittest.TestCase):
    def test_one_failure_reads_naturally(self):
        items = [
            {
                "created_at": NOW.isoformat(),
                "status": "error",
                "title": "Møde med Tine",
                "error_message": "Wrike svarede 403",
            }
        ]
        subject, body = remind.build_message(items, NOW)
        self.assertEqual(subject, "1 job fejlede")
        self.assertIn("1 job med fejl", body)
        self.assertIn("Møde med Tine: Wrike svarede 403", body)

    def test_several_failures_name_the_age_of_the_oldest(self):
        items = [
            {
                "created_at": (NOW - timedelta(days=12)).isoformat(),
                "status": "error",
                "title": "Gammel",
                "error_message": "timeout",
            },
            {
                "created_at": NOW.isoformat(),
                "status": "error",
                "title": "Ny",
                "error_message": "GPU var optaget",
            },
        ]
        subject, body = remind.build_message(items, NOW)
        self.assertEqual(subject, "2 job fejlede")
        self.assertIn("Det ældste er fra 12 dage", body)
        self.assertIn("Gammel: timeout (12 dage)", body)
        self.assertIn("Ny: GPU var optaget (i dag)", body)

    def test_the_age_line_is_left_out_when_nothing_is_old(self):
        items = [
            {"created_at": NOW.isoformat(), "status": "error", "error_message": "En"},
            {"created_at": NOW.isoformat(), "status": "error", "error_message": "To"},
        ]
        _subject, body = remind.build_message(items, NOW)
        self.assertNotIn("Den ældste", body)

    def test_a_failed_recording_says_why(self):
        items = [{"created_at": NOW.isoformat(), "status": "error", "error_message": "GPU var optaget"}]
        _subject, body = remind.build_message(items, NOW)
        self.assertIn("GPU var optaget", body)

    def test_the_message_says_it_will_come_again(self):
        items = [{"created_at": NOW.isoformat(), "status": "error", "error_message": "Noget"}]
        _subject, body = remind.build_message(items, NOW)
        self.assertIn("gentages hver dag", body)


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        db.init()
        with db.cursor() as cur:
            cur.execute("DELETE FROM proposals")
            cur.execute("DELETE FROM captures")
            cur.execute("DELETE FROM app_state")
        remind._last_failure = 0.0

    def test_too_early_in_the_morning_is_not_due(self):
        early = NOW.replace(hour=6, minute=0)
        self.assertFalse(remind.is_due(early, None))

    def test_after_the_hour_it_is_due(self):
        self.assertTrue(remind.is_due(NOW, None))

    def test_it_only_goes_out_once_a_day(self):
        self.assertFalse(remind.is_due(NOW, NOW.date().isoformat()))

    def test_a_late_start_still_sends_today(self):
        # Var maskinen slukket klokken 08:30, må dagen ikke bare være tabt.
        late = NOW.replace(hour=23, minute=0)
        self.assertTrue(remind.is_due(late, None))

    def test_nothing_waiting_means_nothing_sent(self):
        with patch("app.remind.send_email") as sender:
            self.assertFalse(remind.send_reminder_if_due(NOW))
        sender.assert_not_called()

    def test_an_empty_inbox_does_not_use_up_the_day(self):
        with patch("app.remind.send_email", return_value=True):
            remind.send_reminder_if_due(NOW)
        self.assertIsNone(db.get_state(remind.STATE_KEY))

    def test_a_waiting_idea_does_not_get_a_mail(self):
        add_waiting(days_old=2, title="Møde med Tine")
        with patch("app.remind.send_email") as sender:
            self.assertFalse(remind.send_reminder_if_due(NOW))
        sender.assert_not_called()
        self.assertIsNone(db.get_state(remind.STATE_KEY))

    def test_a_failed_job_gets_sent_and_marks_the_day(self):
        add_failed(days_old=2, reason="GPU var optaget")
        with patch("app.remind.send_email", return_value=True) as sender:
            self.assertTrue(remind.send_reminder_if_due(NOW))
        sender.assert_called_once()
        self.assertEqual(db.get_state(remind.STATE_KEY), NOW.date().isoformat())

        # Samme dag igen må ikke give endnu en mail.
        with patch("app.remind.send_email", return_value=True) as sender:
            self.assertFalse(remind.send_reminder_if_due(NOW))
        sender.assert_not_called()

    def test_it_comes_again_the_next_day_while_a_failure_remains(self):
        add_failed(days_old=2, reason="GPU var optaget")
        with patch("app.remind.send_email", return_value=True):
            remind.send_reminder_if_due(NOW)
        with patch("app.remind.send_email", return_value=True) as sender:
            self.assertTrue(remind.send_reminder_if_due(NOW + timedelta(days=1)))
        sender.assert_called_once()

    def test_a_failed_send_does_not_mark_the_day(self):
        add_failed(days_old=2, reason="GPU var optaget")
        with patch("app.remind.send_email", return_value=False):
            self.assertFalse(remind.send_reminder_if_due(NOW))
        self.assertIsNone(db.get_state(remind.STATE_KEY))

    def test_env_can_turn_it_off(self):
        add_failed(days_old=2, reason="GPU var optaget")
        os.environ["REMIND_ENABLED"] = "0"
        try:
            with patch("app.remind.send_email") as sender:
                self.assertFalse(remind.send_reminder_if_due(NOW))
            sender.assert_not_called()
        finally:
            os.environ["REMIND_ENABLED"] = "1"


class AgeTests(unittest.TestCase):
    def test_today(self):
        self.assertEqual(remind.age_text(NOW.isoformat(), NOW), "i dag")

    def test_yesterday(self):
        self.assertEqual(remind.age_text((NOW - timedelta(days=1)).isoformat(), NOW), "i går")

    def test_a_long_forgotten_idea(self):
        self.assertEqual(remind.age_text((NOW - timedelta(days=21)).isoformat(), NOW), "21 dage")

    def test_nonsense_does_not_crash_the_reminder(self):
        self.assertEqual(remind.age_text("ikke en dato", NOW), "ukendt alder")


if __name__ == "__main__":
    unittest.main()
