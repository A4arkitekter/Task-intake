import os
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path

os.environ["WHISPER_WARMUP"] = "0"
os.environ["NOTIFY"] = "0"
os.environ["WATCH_ENABLED"] = "0"
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="intake-report-")

from app.report import build_error_report


class ReportTests(unittest.TestCase):
    def test_report_redacts_wrike_token(self):
        from app.config import DATA_DIR, ROOT

        log_dir = DATA_DIR / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "app.log").write_text(
            "WRIKE_TOKEN=hemmelig\nWRIKE_CLIENT_SECRET=hemmelig-secret\nSECRET_KEY=andet\n",
            encoding="utf-8",
        )
        payload = build_error_report()
        with zipfile.ZipFile(BytesIO(payload)) as archive:
            names = archive.namelist()
            self.assertIn("rapportinfo.txt", names)
            text = archive.read("app.log").decode("utf-8")
        self.assertIn("[SKJULT]", text)
        self.assertNotIn("hemmelig", text)
        self.assertNotIn("hemmelig-secret", text)
        self.assertTrue((ROOT / "app" / "report.py").is_file())
