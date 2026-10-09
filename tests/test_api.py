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
os.environ["WRIKE_TOKEN"] = ""
os.environ["WRIKE_CLIENT_ID"] = ""
os.environ["WRIKE_CLIENT_SECRET"] = ""

_tmp = tempfile.mkdtemp(prefix="intake-test-")
os.environ["DATA_DIR"] = _tmp
os.environ["INBOX_DIR"] = str(__import__("pathlib").Path(_tmp) / "indbakke")

from unittest.mock import patch

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
        self.assertIn("Importance: high", payload["eml"])
        self.assertIn("X-Priority: 1", payload["eml"])
        self.assertFalse(payload["outlook"])


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self._outlook = patch("app.mailer.open_outlook_draft", return_value=True)
        self._outlook.start()
        from app import db

        db.init()
        with db.cursor() as cur:
            cur.execute("DELETE FROM proposals")
            cur.execute("DELETE FROM captures")

    def tearDown(self):
        self._outlook.stop()

    def test_health(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["mail"]["to"], "wrike@wrike.com")
        self.assertEqual(response.json()["mail"]["cc"], "ep@a4.dk")

    def test_inbox_opens_without_login(self):
        inbox = self.client.get("/api/inbox")
        self.assertEqual(inbox.status_code, 200)
        self.assertIsInstance(inbox.json()["captures"], list)
        me = self.client.get("/api/me")
        self.assertTrue(me.json()["authenticated"])
        self.assertEqual(self.client.post("/api/login", json={}).status_code, 200)

    def test_a_hidden_tab_does_not_count_as_watching(self):
        # En skjult baggrundsfane henter stadig listen. Talte den som en seer, ville
        # indbakken aldrig åbne sig selv — og det var netop fejlen.
        activity.reset()
        self.client.get("/api/inbox?visible=0")
        self.assertEqual(activity.seconds_since_inbox_seen(), float("inf"))
        self.client.get("/api/inbox?visible=1")
        self.assertLess(activity.seconds_since_inbox_seen(), 5)

    def test_home_is_spa(self):
        response = self.client.get("/ny-ide")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])

    def test_approve_creates_wrike_task(self):
        from unittest.mock import patch

        from app import db
        from app import settings as admin_settings

        admin_settings.save(
            {
                "wrike_folder_id": "FOLDER1",
                "wrike_folder_name": "Indbakke",
                "wrike_importance": "High",
                "wrike_assignee_id": "KU123",
                "wrike_assignee_name": "Erik Petersen",
            }
        )
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
        with patch(
            "app.wrike.create_task",
            return_value={"id": "IEAAA", "url": "https://www.wrike.com/open.htm?id=1", "importance": "High"},
        ) as creator:
            response = self.client.post(f"/api/proposals/{cards[0]['id']}/approve")
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["status"], "sent")
        self.assertEqual(data["wrike_task_id"], "IEAAA")
        self.assertIn("wrike.com", data["wrike_url"])
        creator.assert_called_once()
        self.assertEqual(creator.call_args.kwargs["folder_id"], "FOLDER1")
        self.assertEqual(creator.call_args.kwargs["importance"], "High")

    def test_admin_saves_folder_and_priority_without_env(self):
        response = self.client.patch(
            "/api/admin/settings",
            json={
                "wrike_folder_id": "ABC",
                "wrike_folder_name": "Backlog",
                "wrike_importance": "Normal",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        saved = response.json()["settings"]
        self.assertEqual(saved["wrike_folder_id"], "ABC")
        self.assertEqual(saved["wrike_importance"], "Normal")
        again = self.client.get("/api/admin")
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json()["settings"]["wrike_folder_name"], "Backlog")
        self.assertEqual(again.json()["health"]["wrike"]["level"], "red")
        self.assertIn("behandling", again.json()["health"])

    def test_admin_catalog_keeps_transcripts_for_30_days(self):
        from datetime import datetime, timedelta, timezone

        from app import db

        capture = db.create_capture(
            source="sync",
            audio_path="missing.m4a",
            audio_mime="audio/mp4",
            duration_sec=4,
        )
        db.update_capture(
            capture["id"],
            status="ready",
            transcript="Ring til Martin om kontrakten.",
        )
        db.replace_proposals(capture["id"], [{"title": "Ring til Martin", "note": "Om kontrakten."}])
        old = db.create_capture(
            source="sync",
            audio_path="old.m4a",
            audio_mime="audio/mp4",
            duration_sec=4,
        )
        db.update_capture(
            old["id"],
            created_at=(datetime.now(timezone.utc) - timedelta(days=40)).isoformat(),
            status="ready",
            transcript="Gammel idé.",
        )
        response = self.client.get("/api/admin")
        self.assertEqual(response.status_code, 200)
        jobs = response.json()["jobs"]
        ids = {item["id"] for item in jobs}
        self.assertIn(capture["id"], ids)
        self.assertNotIn(old["id"], ids)
        found = next(item for item in jobs if item["id"] == capture["id"])
        self.assertEqual(found["transcript"], "Ring til Martin om kontrakten.")
        pulse = self.client.get("/api/admin/pulse")
        self.assertEqual(pulse.status_code, 200)
        pulse_job = next(item for item in pulse.json()["jobs"] if item["id"] == capture["id"])
        self.assertEqual(pulse_job["transcript"], "")
        self.assertIn("behandling", pulse.json()["health"])

    def test_catalog_delete_removes_capture_but_keeps_wrike_task_untouched(self):
        from pathlib import Path

        from app import db
        from app.config import AUDIO_DIR

        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        audio = AUDIO_DIR / "catalog-delete.m4a"
        audio.write_bytes(b"lyd")
        capture = db.create_capture(
            source="sync",
            audio_path=str(audio),
            audio_mime="audio/mp4",
            duration_sec=2,
        )
        db.update_capture(capture["id"], status="ready", transcript="Kort test.")
        response = self.client.delete(f"/api/captures/{capture['id']}")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(db.get_capture(capture["id"]))
        self.assertFalse(audio.is_file())
        gone = self.client.get("/api/admin").json()["jobs"]
        self.assertFalse(any(item["id"] == capture["id"] for item in gone))

    def test_retry_resends_failed_wrike_job(self):
        from app import db

        capture = db.create_capture(
            source="sync",
            audio_path="missing.webm",
            audio_mime="audio/webm",
            duration_sec=3,
        )
        db.update_capture(
            capture["id"],
            status="ready",
            transcript="Ring til Martin",
            error_message="Wrike svarede 401",
        )
        db.replace_proposals(capture["id"], [{"title": "Ring til Martin", "note": "Ring til Martin."}])
        with patch("app.main.retry_capture_job") as worker:
            response = self.client.post(f"/api/captures/{capture['id']}/retry")
        self.assertEqual(response.status_code, 200, response.text)
        worker.assert_called_once_with(capture["id"])

    def test_error_report_is_a_zip_without_secrets(self):
        response = self.client.get("/api/admin/report")
        self.assertEqual(response.status_code, 200)
        self.assertIn("zip", response.headers["content-type"])
        self.assertIn("fejlrapport.zip", response.headers.get("content-disposition", ""))
        self.assertGreater(len(response.content), 20)

    def test_rewrite_updates_pending_card(self):
        from unittest.mock import patch

        from app import db

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

        audio = Path(_tmp) / "fejlet.m4a"
        audio.write_bytes(b"lyden ligger stadig paa disken")
        capture = db.create_capture(
            source="sync",
            audio_path=str(audio),
            audio_mime="audio/mp4",
            duration_sec=5,
        )
        db.update_capture(capture["id"], status="error", error_message="GPU var optaget")

        with patch("app.main.retry_capture_job") as worker:
            response = self.client.post(f"/api/captures/{capture['id']}/retry")

        self.assertEqual(response.status_code, 200, response.text)
        worker.assert_called_once_with(capture["id"])
        again = db.get_capture(capture["id"])
        self.assertEqual(again["status"], "processing")
        self.assertIsNone(again["error_message"])

    def test_retry_is_refused_when_nothing_failed(self):
        from app import db

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


class WrikeCredentialsApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_empty_wrike_keys_are_rejected(self):
        from app import wrike as wrike_mod

        with patch(
            "app.main.wrike.save_installed_credentials",
            side_effect=wrike_mod.WrikeError("Udfyld Client ID, Client secret og Get token."),
        ):
            response = self.client.post(
                "/api/admin/wrike/credentials",
                json={"client_id": "", "client_secret": "", "token": ""},
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Client ID", response.json()["detail"])

    def test_saved_wrike_keys_are_not_echoed(self):
        identity = {
            "id": "KU1",
            "name": "Anna Jensen",
            "email": "aj@a4.dk",
            "label": "Anna Jensen (aj@a4.dk)",
        }
        payload = {
            "settings": {
                "wrike_keys_ready": True,
                "wrike_token_owner": "Anna Jensen (aj@a4.dk)",
            },
            "health": {"wrike": {"ok": True, "message": "API er i orden som Anna Jensen (aj@a4.dk)."}},
        }
        with (
            patch("app.main.wrike.save_installed_credentials", return_value=identity),
            patch("app.main.admin_dashboard.ensure_default_assignee"),
            patch("app.main.admin_dashboard.payload", return_value=payload),
        ):
            response = self.client.post(
                "/api/admin/wrike/credentials",
                json={
                    "client_id": "cid-secret",
                    "client_secret": "sec-secret",
                    "token": "tok-superhemmelig",
                },
            )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        dumped = str(body)
        self.assertNotIn("tok-superhemmelig", dumped)
        self.assertNotIn("cid-secret", dumped)
        self.assertNotIn("sec-secret", dumped)
        self.assertEqual(body["owner"], "Anna Jensen (aj@a4.dk)")


if __name__ == "__main__":
    unittest.main()
