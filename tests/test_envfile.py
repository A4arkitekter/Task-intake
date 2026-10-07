import tempfile
import unittest
from pathlib import Path

from app.envfile import migrate_dotenv, parse_assignments


class EnvfileTests(unittest.TestCase):
    def test_legacy_outlook_env_gains_wrike_keys_and_drops_password(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            example = root / ".env.example"
            env_path = root / ".env"
            example.write_text(
                "SECRET_KEY=skift\n"
                "APP_PORT=7000\n"
                "WRIKE_TOKEN=\n"
                "AUTO_OPEN=0\n"
                "MAIL_CC=ep@a4.dk\n",
                encoding="utf-8",
            )
            env_path.write_text(
                "APP_PASSWORD=hemmelig\n"
                "SECRET_KEY=bevar-mig\n"
                "MAIL_TO=wrike@wrike.com\n"
                "MAIL_CC=ep@a4.dk\n"
                "AUTO_OPEN=1\n"
                "INBOX_DIR=C:\\optagelser\n",
                encoding="utf-8",
            )
            self.assertTrue(migrate_dotenv(env_path, example))
            values = parse_assignments(env_path.read_text(encoding="utf-8"))
            self.assertNotIn("APP_PASSWORD", values)
            self.assertNotIn("MAIL_TO", values)
            self.assertEqual(values["SECRET_KEY"], "bevar-mig")
            self.assertEqual(values["MAIL_CC"], "ep@a4.dk")
            self.assertEqual(values["WRIKE_TOKEN"], "")
            self.assertEqual(values["AUTO_OPEN"], "0")
            self.assertEqual(values["INBOX_DIR"], r"C:\optagelser")
            self.assertEqual(values["APP_PORT"], "7000")

    def test_second_run_does_not_rewrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            example = root / ".env.example"
            env_path = root / ".env"
            example.write_text("SECRET_KEY=x\nWRIKE_TOKEN=\n", encoding="utf-8")
            env_path.write_text("SECRET_KEY=x\nWRIKE_TOKEN=abc\nEXTRA=1\n", encoding="utf-8")
            self.assertTrue(migrate_dotenv(env_path, example))
            self.assertFalse(migrate_dotenv(env_path, example))
            self.assertEqual(parse_assignments(env_path.read_text(encoding="utf-8"))["WRIKE_TOKEN"], "abc")
