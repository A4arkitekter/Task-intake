import os
import tempfile
import unittest

os.environ["WHISPER_WARMUP"] = "0"
os.environ["APP_PASSWORD"] = "test-pass"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["MAIL_TO"] = "wrike@wrike.com"
os.environ["MAIL_CC"] = "ep@a4.dk"
os.environ["MAIL_MARKER"] = "*PODIOWRIKETASKDELETE*"

_tmp = tempfile.mkdtemp(prefix="intake-test-")
os.environ["DATA_DIR"] = _tmp

from fastapi.testclient import TestClient

from app.mailer import build_body, compose, mailto_url
from app.main import app


class MailerTests(unittest.TestCase):
    def test_body_contains_marker_and_transcript(self):
        body = build_body(note="Ring til Martin.", transcript="Husk at ringe til Martin om kontrakten.")
        self.assertIn("Ring til Martin.", body)
        self.assertIn("Husk at ringe til Martin om kontrakten.", body)
        self.assertIn("*PODIOWRIKETASKDELETE*", body)
        self.assertTrue(body.strip().endswith("*PODIOWRIKETASKDELETE*"))

    def test_body_skips_duplicate_transcript(self):
        body = build_body(note="Samme tekst", transcript="Samme tekst")
        self.assertEqual(body.count("Samme tekst"), 1)

    def test_mailto_fields(self):
        url = mailto_url(
            to="wrike@wrike.com",
            cc="ep@a4.dk",
            subject="Ringe til Martin",
            body="Detalje\n\n*PODIOWRIKETASKDELETE*\n",
        )
        self.assertTrue(url.startswith("mailto:wrike@wrike.com?"))
        self.assertIn("cc=ep%40a4.dk", url)
        self.assertIn("subject=Ringe%20til%20Martin", url)
        self.assertIn("PODIOWRIKETASKDELETE", url)

    def test_compose_eml(self):
        payload = compose(title="Ringe til Martin", note="Note her.", transcript="Fuld tekst.")
        self.assertEqual(payload["to"], "wrike@wrike.com")
        self.assertEqual(payload["cc"], "ep@a4.dk")
        self.assertIn("To: wrike@wrike.com", payload["eml"])
        self.assertIn("Cc: ep@a4.dk", payload["eml"])
        self.assertIn("Subject: Ringe til Martin", payload["eml"])
        self.assertIn("*PODIOWRIKETASKDELETE*", payload["eml"])


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["mail"]["to"], "wrike@wrike.com")
        self.assertEqual(response.json()["mail"]["cc"], "ep@a4.dk")

    def test_login_and_inbox(self):
        denied = self.client.get("/api/inbox")
        self.assertEqual(denied.status_code, 401)
        bad = self.client.post("/api/login", json={"password": "forkert"})
        self.assertEqual(bad.status_code, 401)
        ok = self.client.post("/api/login", json={"password": "test-pass"})
        self.assertEqual(ok.status_code, 200)
        inbox = self.client.get("/api/inbox")
        self.assertEqual(inbox.status_code, 200)
        self.assertEqual(inbox.json()["captures"], [])

    def test_home_is_spa(self):
        response = self.client.get("/ny-ide")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])

    def test_approve_returns_mailto(self):
        from app import db

        self.client.post("/api/login", json={"password": "test-pass"})
        capture = db.create_capture(
            source="pwa",
            audio_path="missing.webm",
            audio_mime="audio/webm",
            duration_sec=3,
        )
        db.update_capture(capture["id"], status="ready", transcript="Ring til Martin om kontrakten.")
        cards = db.replace_proposals(
            capture["id"],
            [{"title": "Ring til Martin", "note": "Ring til Martin om kontrakten."}],
        )
        response = self.client.post(f"/api/proposals/{cards[0]['id']}/approve")
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["status"], "sent")
        self.assertTrue(data["mailto"].startswith("mailto:wrike@wrike.com?"))
        self.assertIn("cc=ep%40a4.dk", data["mailto"])
        self.assertIn("*PODIOWRIKETASKDELETE*", data["body"])
        eml = self.client.get(f"/api/proposals/{cards[0]['id']}/eml")
        self.assertEqual(eml.status_code, 200)
        self.assertIn(b"wrike@wrike.com", eml.content)
        self.assertIn(b"ep@a4.dk", eml.content)
        self.assertIn(b"PODIOWRIKETASKDELETE", eml.content)

    def test_manifest(self):
        response = self.client.get("/manifest.webmanifest")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Ny ide", response.text)


if __name__ == "__main__":
    unittest.main()
