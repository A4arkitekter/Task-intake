import os
import tempfile
import unittest
from unittest.mock import patch

os.environ["WHISPER_WARMUP"] = "0"
os.environ["NOTIFY"] = "0"
os.environ["WATCH_ENABLED"] = "0"
os.environ["AUTO_OPEN"] = "0"
os.environ["LLM_ENABLED"] = "0"
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="intake-wrike-")

from app import wrike


class WrikeTests(unittest.TestCase):
    def test_pick_default_prefers_inbox(self):
        folders = [
            {"id": "1", "title": "Projekter"},
            {"id": "2", "title": "Indbakke"},
            {"id": "3", "title": "Arkiv"},
        ]
        self.assertEqual(wrike.pick_default_folder(folders)["id"], "2")

    def test_list_folders_distinguishes_same_title_by_owner(self):
        wrike._folders_cache.update({"at": 0.0, "value": None})
        wrike._contacts_cache.update({"at": 0.0, "value": None})
        wrike._spaces_cache.update({"at": 0.0, "value": None})
        folders = {
            "data": [
                {"id": "ROOT", "title": "Root", "childIds": ["SPACE1", "SPACE2"]},
                {"id": "SPACE1", "title": "Personal", "childIds": ["F1"]},
                {"id": "SPACE2", "title": "Personal", "childIds": []},
                {"id": "F1", "title": "task-intake", "childIds": []},
            ]
        }
        spaces = {
            "data": [
                {
                    "id": "SPACE1",
                    "title": "Personal",
                    "accessType": "Personal",
                    "members": [{"id": "KU1", "isManager": True}],
                },
                {
                    "id": "SPACE2",
                    "title": "Personal",
                    "accessType": "Personal",
                    "members": [{"id": "KU2", "isManager": True}],
                },
            ]
        }
        contacts = {
            "data": [
                {"id": "KU1", "firstName": "Eric", "lastName": "Prescott", "type": "Person", "me": True},
                {"id": "KU2", "firstName": "Anna", "lastName": "Jensen", "type": "Person"},
            ]
        }

        def fake_request(_method, path, _payload=None):
            if path.startswith("/folders"):
                return folders
            if path.startswith("/spaces"):
                return spaces
            if path.startswith("/contacts"):
                return contacts
            raise AssertionError(path)

        with patch("app.wrike._request", side_effect=fake_request):
            self.assertEqual(wrike.list_folders(query="personal"), [])
            mine = {row["id"]: row for row in wrike.list_folders(query="personal", account_id="KU1")}
            other = {row["id"]: row for row in wrike.list_folders(query="personal", account_id="KU2")}
            nested = wrike.list_folders(query="task-intake", account_id="KU1")
        self.assertEqual(set(mine), {"SPACE1", "F1"})
        self.assertNotIn("SPACE2", mine)
        self.assertEqual(mine["SPACE1"]["subtitle"], "Din mappe")
        self.assertEqual(set(other), {"SPACE2"})
        self.assertEqual(other["SPACE2"]["subtitle"], "Din mappe")
        self.assertEqual(nested[0]["id"], "F1")
        self.assertEqual(nested[0]["subtitle"], "Din mappe")
        self.assertEqual(nested[0]["label"], "task-intake · Din mappe")

    def test_create_task_posts_to_selected_folder(self):
        payload = {"data": [{"id": "T1", "permalink": "https://www.wrike.com/open.htm?id=1"}]}
        with patch("app.wrike._request", return_value=payload) as request:
            task = wrike.create_task(
                title="Ring til Martin",
                description="Om kontrakten",
                folder_id="IEAAAAAQK4AAAAA2",
                importance="High",
                responsible_id="KU123",
                responsible_name="Erik Petersen",
            )
        request.assert_called_once()
        self.assertEqual(request.call_args.args[0], "POST")
        self.assertIn("/folders/IEAAAAAQK4AAAAA2/tasks", request.call_args.args[1])
        self.assertEqual(request.call_args.args[2]["importance"], "High")
        self.assertEqual(request.call_args.args[2]["responsibles"], ["KU123"])
        self.assertEqual(task["id"], "T1")
        self.assertEqual(task["assignee"], "Erik Petersen")
        self.assertIn("wrike.com", task["url"])

    def test_list_contacts_keeps_people_and_skips_groups(self):
        payload = {
            "data": [
                {
                    "id": "KU1",
                    "firstName": "Erik",
                    "lastName": "Petersen",
                    "type": "Person",
                    "profiles": [{"email": "ep@a4.dk"}],
                },
                {"id": "KG1", "firstName": "Team", "type": "Group"},
            ]
        }
        with patch("app.wrike._request", return_value=payload):
            people = wrike.list_contacts(query="erik")
        self.assertEqual(len(people), 1)
        self.assertEqual(people[0]["id"], "KU1")
        self.assertIn("ep@a4.dk", people[0]["title"])

    def test_missing_folder_is_a_clear_error(self):
        with self.assertRaises(wrike.WrikeError):
            wrike.create_task(
                title="X",
                description="",
                folder_id="",
                importance="High",
                responsible_id="KU123",
            )

    def test_missing_assignee_is_a_clear_error(self):
        with self.assertRaises(wrike.WrikeError):
            wrike.create_task(
                title="X",
                description="",
                folder_id="FOLDER1",
                importance="High",
            )

    def test_health_asks_for_permanent_token_when_only_client_secrets_exist(self):
        with patch.dict(
            os.environ,
            {"WRIKE_CLIENT_ID": "abc", "WRIKE_CLIENT_SECRET": "xyz", "WRIKE_TOKEN": ""},
        ):
            status = wrike.health(force=True)
        self.assertFalse(status["ok"])
        self.assertIn("Get token", status["message"])
