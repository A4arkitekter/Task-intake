import os
import tempfile
import unittest

os.environ["WHISPER_WARMUP"] = "0"
os.environ["APP_PASSWORD"] = "test-pass"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["MAIL_TO"] = "wrike@wrike.com"
os.environ["MAIL_CC"] = "ep@a4.dk"
os.environ["MAIL_MARKER"] = "*PODIOWRIKETASKDELETE*"
os.environ["LLM_ENABLED"] = "0"
os.environ["NOTIFY"] = "0"
os.environ["WATCH_ENABLED"] = "0"
os.environ["AUTO_OPEN"] = "0"
os.environ["REMIND_ENABLED"] = "0"

_tmp = tempfile.mkdtemp(prefix="intake-test-")
os.environ["DATA_DIR"] = _tmp

from fastapi.testclient import TestClient

from app import activity
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
        padded = self.client.post("/api/login", json={"password": "  test-pass  "})
        self.assertEqual(padded.status_code, 200)
        inbox = self.client.get("/api/inbox")
        self.assertEqual(inbox.status_code, 200)
        self.assertIsInstance(inbox.json()["captures"], list)

    def test_a_hidden_tab_does_not_count_as_watching(self):
        # En skjult baggrundsfane henter stadig listen. Talte den som en seer, ville
        # indbakken aldrig åbne sig selv — og det var netop fejlen.
        self.client.post("/api/login", json={"password": "test-pass"})
        activity.reset()
        self.client.get("/api/inbox?visible=0")
        self.assertEqual(activity.seconds_since_inbox_seen(), float("inf"))
        self.client.get("/api/inbox?visible=1")
        self.assertLess(activity.seconds_since_inbox_seen(), 5)

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

    def test_rewrite_updates_pending_card(self):
        from unittest.mock import patch

        from app import db

        self.client.post("/api/login", json={"password": "test-pass"})
        capture = db.create_capture(
            source="pwa",
            audio_path="missing.webm",
            audio_mime="audio/webm",
            duration_sec=3,
        )
        db.update_capture(
            capture["id"],
            status="ready",
            transcript="Jeg har en idé, der handler om, at vi fremover os, skal sortere vores affald i købnet",
        )
        db.replace_proposals(
            capture["id"],
            [{"title": "Jeg har en idé, der handler om", "note": "rå tekst"}],
        )
        with patch(
            "app.extract.rewrite_idea",
            return_value={
                "title": "Fremtidig affaldssortering i køkkenet",
                "note": "Vi skal fremover sortere vores affald i køkkenet.",
            },
        ):
            response = self.client.post(f"/api/captures/{capture['id']}/rewrite")
        self.assertEqual(response.status_code, 200, response.text)
        pending = [p for p in response.json()["proposals"] if p["status"] == "pending"]
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["title"], "Fremtidig affaldssortering i køkkenet")
        self.assertIn("køkkenet", pending[0]["note"])

    def test_inbox_collapses_extra_proposals(self):
        from app import db

        self.client.post("/api/login", json={"password": "test-pass"})
        capture = db.create_capture(
            source="pwa",
            audio_path="missing.webm",
            audio_mime="audio/webm",
            duration_sec=3,
        )
        transcript = (
            "Jeg har en IDTA 4US. Vi skal fremover have dashboards til alle mulige ting."
        )
        db.update_capture(capture["id"], status="ready", transcript=transcript)
        db.replace_proposals(
            capture["id"],
            [
                {"title": "Jeg har en IDTA 4US", "note": "Jeg har en IDTA 4US."},
                {
                    "title": "Vi skal fremover have dashboards til alle",
                    "note": "Vi skal fremover have dashboards til alle mulige ting.",
                },
            ],
        )
        inbox = self.client.get("/api/inbox")
        self.assertEqual(inbox.status_code, 200)
        self.assertEqual(len(inbox.json()["captures"]), 1)
        pending = [
            p
            for p in inbox.json()["captures"][0]["proposals"]
            if p["status"] == "pending"
        ]
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["title"], "Jeg har en IDTA 4US")

    def test_retry_reruns_a_failed_capture(self):
        from pathlib import Path
        from unittest.mock import patch

        from app import db

        self.client.post("/api/login", json={"password": "test-pass"})
        audio = Path(_tmp) / "fejlet.m4a"
        audio.write_bytes(b"lyden ligger stadig paa disken")
        capture = db.create_capture(
            source="sync",
            audio_path=str(audio),
            audio_mime="audio/mp4",
            duration_sec=5,
        )
        db.update_capture(capture["id"], status="error", error_message="GPU var optaget")

        with patch("app.main.process_capture") as worker:
            response = self.client.post(f"/api/captures/{capture['id']}/retry")

        self.assertEqual(response.status_code, 200, response.text)
        worker.assert_called_once_with(capture["id"])
        again = db.get_capture(capture["id"])
        self.assertEqual(again["status"], "processing")
        self.assertIsNone(again["error_message"])

    def test_retry_is_refused_when_nothing_failed(self):
        from app import db

        self.client.post("/api/login", json={"password": "test-pass"})
        capture = db.create_capture(
            source="pwa",
            audio_path="missing.webm",
            audio_mime="audio/webm",
            duration_sec=1,
        )
        db.update_capture(capture["id"], status="ready", transcript="noget")
        response = self.client.post(f"/api/captures/{capture['id']}/retry")
        self.assertEqual(response.status_code, 409)

    def test_retry_is_refused_when_the_audio_is_gone(self):
        from app import db

        self.client.post("/api/login", json={"password": "test-pass"})
        capture = db.create_capture(
            source="sync",
            audio_path="findes-ikke.m4a",
            audio_mime="audio/mp4",
            duration_sec=1,
        )
        db.update_capture(capture["id"], status="error", error_message="fejl")
        response = self.client.post(f"/api/captures/{capture['id']}/retry")
        self.assertEqual(response.status_code, 409)

    def test_manifest(self):
        response = self.client.get("/manifest.webmanifest")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Ny ide", response.text)

    def test_health_exposes_instance_id(self):
        from app import update as program_update

        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["instance_id"], program_update.SERVER_INSTANCE_ID)
        self.assertEqual(data["update_action_token"], program_update.UPDATE_ACTION_TOKEN)


class UpdateApiTests(unittest.TestCase):
    def setUp(self):
        from app import db
        from app import update as program_update

        self.client = TestClient(app)
        program_update.update_shutdown_requested.clear()
        with db.cursor() as cur:
            cur.execute("UPDATE captures SET status = 'ready' WHERE status = 'processing'")

    def tearDown(self):
        from app import update as program_update

        program_update.update_shutdown_requested.clear()

    def test_browser_update_status_is_exposed(self):
        from unittest.mock import patch

        fake = {
            "ok": True,
            "supported": True,
            "update_available": True,
            "latest_version": "abc123",
        }
        with patch("app.update.check_update_status", return_value=fake):
            response = self.client.get("/api/update/status")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["update"]["update_available"])

    def test_browser_update_request_stops_server_only_when_no_job_is_active(self):
        from unittest.mock import patch

        from app import update as program_update

        fake = {
            "ok": True,
            "supported": True,
            "update_available": True,
            "latest_version": "abc123",
        }
        stopped = []
        with patch("app.update.check_update_status", return_value=fake), patch(
            "app.update.request_program_update_shutdown",
            side_effect=lambda: stopped.append(True),
        ):
            response = self.client.post(
                "/api/update/apply",
                headers={"X-Update-Token": program_update.UPDATE_ACTION_TOKEN},
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["restarting"])
        self.assertEqual(stopped, [True])

    def test_browser_update_is_rejected_during_processing(self):
        from unittest.mock import patch

        from app import db
        from app import update as program_update

        db.create_capture(
            source="pwa",
            audio_path="busy.webm",
            audio_mime="audio/webm",
            duration_sec=1,
        )
        fake = {"ok": True, "supported": True, "update_available": True}
        with patch("app.update.check_update_status", return_value=fake):
            response = self.client.post(
                "/api/update/apply",
                headers={"X-Update-Token": program_update.UPDATE_ACTION_TOKEN},
            )
        self.assertEqual(response.status_code, 409)
        self.assertIn("optagelse", response.json()["error"])

    def test_browser_update_is_rejected_without_token(self):
        response = self.client.post("/api/update/apply")
        self.assertEqual(response.status_code, 403)

    def test_developer_git_checkout_hides_updates(self):
        from unittest.mock import patch

        from app.update import check_update_status

        with patch("app.update.is_developer_checkout", return_value=True):
            status = check_update_status()
        self.assertFalse(status["supported"])
        self.assertFalse(status["update_available"])


if __name__ == "__main__":
    unittest.main()
