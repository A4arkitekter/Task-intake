import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ["WHISPER_WARMUP"] = "0"
os.environ["NOTIFY"] = "0"
os.environ["WATCH_ENABLED"] = "0"
os.environ["AUTO_OPEN"] = "0"
os.environ["LLM_ENABLED"] = "0"
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="intake-pipe-")

from app import db, settings
from app.pipeline import process_capture, retry_capture_job, task_description


class PipelineWrikeTests(unittest.TestCase):
    def setUp(self):
        db.init()
        with db.cursor() as cur:
            cur.execute("DELETE FROM proposals")
            cur.execute("DELETE FROM captures")
        settings.save(
            {
                "wrike_folder_id": "FOLDER1",
                "wrike_folder_name": "Indbakke",
                "wrike_importance": "High",
                "wrike_assignee_id": "KU123",
                "wrike_assignee_name": "Erik Petersen",
            }
        )

    def test_process_capture_creates_wrike_task(self):
        audio = Path(os.environ["DATA_DIR"]) / "ide.m4a"
        audio.write_bytes(b"lyd")
        capture = db.create_capture(
            source="sync",
            audio_path=str(audio),
            audio_mime="audio/mp4",
            duration_sec=2,
        )
        with (
            patch("app.pipeline.audio_duration_sec", return_value=2.0),
            patch("app.pipeline.transcribe_if_needed", return_value="Ring til Martin om kontrakten."),
            patch("app.pipeline.extract_proposals", return_value=[{"title": "Ring til Martin", "note": "Om kontrakten."}]),
            patch(
                "app.wrike.create_task",
                return_value={"id": "T1", "url": "https://www.wrike.com/open.htm?id=1", "importance": "High"},
            ) as creator,
        ):
            process_capture(capture["id"])
        creator.assert_called_once()
        self.assertEqual(creator.call_args.kwargs["importance"], "High")
        self.assertIn("Om kontrakten.", creator.call_args.kwargs["description"])
        self.assertIn("Ring til Martin om kontrakten.", creator.call_args.kwargs["description"])
        sent = db.list_proposals(capture["id"])[0]
        self.assertEqual(sent["status"], "sent")
        self.assertEqual(sent["wrike_task_id"], "T1")
        again = db.get_capture(capture["id"])
        self.assertEqual(again["status"], "ready")
        self.assertIsNone(again["error_message"])

    def test_retry_does_not_transcribe_again_when_text_exists(self):
        capture = db.create_capture(
            source="sync",
            audio_path="missing.m4a",
            audio_mime="audio/mp4",
            duration_sec=2,
        )
        db.update_capture(
            capture["id"],
            status="ready",
            transcript="Ring til Martin",
            error_message="Wrike nede",
        )
        db.replace_proposals(capture["id"], [{"title": "Ring til Martin", "note": "Om kontrakten."}])
        with (
            patch("app.pipeline.transcribe_if_needed") as transcribe,
            patch(
                "app.wrike.create_task",
                return_value={"id": "T2", "url": "https://www.wrike.com/open.htm?id=2", "importance": "High"},
            ),
        ):
            retry_capture_job(capture["id"])
        transcribe.assert_not_called()
        sent = db.list_proposals(capture["id"])[0]
        self.assertEqual(sent["wrike_task_id"], "T2")

    def test_wrike_description_includes_note_and_transcript(self):
        text = task_description("Om kontrakten.", "Ring til Martin om kontrakten.")
        self.assertIn("Om kontrakten.", text)
        self.assertIn("Ring til Martin om kontrakten.", text)
