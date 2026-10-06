import os
import tempfile
import unittest
from pathlib import Path

os.environ["WHISPER_WARMUP"] = "0"
os.environ["NOTIFY"] = "0"
os.environ["WATCH_ENABLED"] = "0"
os.environ["AUTO_OPEN"] = "0"
os.environ["LLM_ENABLED"] = "0"
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="intake-settings-")

from app import settings


class SettingsTests(unittest.TestCase):
    def setUp(self):
        if settings.SETTINGS_PATH.is_file():
            settings.SETTINGS_PATH.unlink()

    def test_default_importance_is_high(self):
        data = settings.load()
        self.assertEqual(data["wrike_importance"], "High")
        self.assertEqual(data["wrike_folder_id"], "")

    def test_folder_and_priority_persist_outside_env(self):
        saved = settings.save(
            {
                "wrike_folder_id": "IEAAA",
                "wrike_folder_name": "Indbakke",
                "wrike_importance": "Low",
                "inbox_dir": str(Path(os.environ["DATA_DIR"]) / "optagelser"),
            }
        )
        self.assertEqual(saved["wrike_importance"], "Low")
        again = settings.load()
        self.assertEqual(again["wrike_folder_name"], "Indbakke")
        self.assertEqual(again["inbox_dir"], saved["inbox_dir"])

    def test_invalid_importance_is_rejected(self):
        with self.assertRaises(ValueError):
            settings.save({"wrike_importance": "Urgent"})

    def test_env_folder_id_is_used_until_browser_saves_one(self):
        os.environ["WRIKE_FOLDER_ID"] = "ENVFOLDER"
        try:
            self.assertEqual(settings.load()["wrike_folder_id"], "ENVFOLDER")
            settings.save({"wrike_folder_id": "UIFOLDER", "wrike_folder_name": "Backlog"})
            self.assertEqual(settings.load()["wrike_folder_id"], "UIFOLDER")
        finally:
            os.environ.pop("WRIKE_FOLDER_ID", None)
