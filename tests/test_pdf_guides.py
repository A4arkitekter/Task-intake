import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PdfGuideTests(unittest.TestCase):
    def test_pdf_guides_are_current_and_valid(self):
        try:
            from pypdf import PdfReader
        except ImportError:
            self.skipTest("pypdf mangler. Kør: pip install -r requirements-dev.txt")

        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "generate_guides_pdf.py"), "--validate-only"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            {path.name for path in ROOT.glob("*.pdf")},
            {"INSTALLATIONSVEJLEDNING.pdf", "BRUGERVEJLEDNING.pdf"},
        )
        install = " ".join(
            (page.extract_text() or "") for page in PdfReader(ROOT / "INSTALLATIONSVEJLEDNING.pdf").pages
        )
        self.assertIn("Førstegangsinstallation", install)
        self.assertIn("arbejdmail", install)
        self.assertIn("ASRRecordings", install)
        self.assertIn("RecUp", install)
        self.assertIn("Opdatér og genstart", install)
        self.assertIn(r"\\a4diskstation4\A4software\task-intake", install)

        daily = " ".join(
            (page.extract_text() or "") for page in PdfReader(ROOT / "BRUGERVEJLEDNING.pdf").pages
        )
        self.assertIn("høj prioritet", daily)
        self.assertIn("Åbn i Outlook", daily)
        self.assertIn("ASR Voice Recorder", daily)
        self.assertIn("RecUp", daily)


if __name__ == "__main__":
    unittest.main()
