import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from tools import publish_update


class PublishUpdateTests(unittest.TestCase):
    def test_package_and_feed_are_verified(self):
        commit = "a" * 40
        files = ["README.md", "OPDATER.bat", "Update-Intake.ps1"]
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp)
            with (
                patch.object(publish_update, "validate_repository", return_value=files),
                patch.object(publish_update, "git", return_value=commit),
            ):
                latest = publish_update.publish(destination)

            package = destination / str(latest["package"])
            self.assertTrue(package.is_file())
            self.assertEqual(hashlib.sha256(package.read_bytes()).hexdigest(), latest["sha256"])
            self.assertEqual(
                json.loads((destination / "latest.json").read_text(encoding="utf-8"))["version"],
                commit[:12],
            )
            with ZipFile(package) as archive:
                self.assertIn("_update-manifest.json", archive.namelist())
                manifest = json.loads(archive.read("_update-manifest.json"))
            self.assertEqual(manifest["commit"], commit)
            self.assertEqual({item["path"] for item in manifest["files"]}, set(files))

    def test_dirty_tree_is_refused(self):
        with patch.object(publish_update, "git", return_value=" M README.md"):
            with self.assertRaisesRegex(RuntimeError, "Commit"):
                publish_update.validate_repository()


if __name__ == "__main__":
    unittest.main()
