import os
import tempfile
import time
import unittest
from pathlib import Path

os.environ["LLM_ENABLED"] = "0"
os.environ["NOTIFY"] = "0"
os.environ["WATCH_ENABLED"] = "0"
os.environ["AUTO_OPEN"] = "0"
os.environ["WHISPER_WARMUP"] = "0"
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="intake-watch-"))

from app import db
from app.watch import FolderWatcher, capture_id_for, iso_from_mtime


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="intake-sync-"))
        self.processed: list[str] = []
        self.watcher = FolderWatcher(
            self.folder,
            archive=False,
            on_capture=self.processed.append,
        )

    def write(self, name: str, payload: bytes = b"lyd") -> Path:
        path = self.folder / name
        path.write_bytes(payload)
        return path

    def test_needs_two_stable_scans(self):
        self.write("idea.m4a")
        self.assertEqual(self.watcher.scan_once(), [])
        self.assertEqual(len(self.watcher.scan_once()), 1)

    def test_growing_file_is_not_ingested(self):
        path = self.write("idea.m4a", b"a")
        self.assertEqual(self.watcher.scan_once(), [])
        path.write_bytes(b"aa")
        self.assertEqual(self.watcher.scan_once(), [])
        path.write_bytes(b"aaa")
        self.assertEqual(self.watcher.scan_once(), [])
        # Først når filen ligger stille to runder i træk, må den hentes ind.
        self.assertEqual(len(self.watcher.scan_once()), 1)

    def test_empty_file_is_skipped(self):
        self.write("tom.m4a", b"")
        self.assertEqual(self.watcher.scan_once(), [])
        self.assertEqual(self.watcher.scan_once(), [])

    def test_non_audio_is_ignored(self):
        self.write("noter.txt")
        self.write("billede.jpg")
        self.assertEqual(self.watcher.scan_once(), [])
        self.assertEqual(self.watcher.scan_once(), [])
        self.assertEqual(self.processed, [])

    def test_no_duplicate_on_repeated_scans(self):
        self.write("idea.m4a")
        self.watcher.scan_once()
        ingested = self.watcher.scan_once()
        self.assertEqual(len(ingested), 1)
        self.assertEqual(self.watcher.scan_once(), [])
        self.assertEqual(self.watcher.scan_once(), [])
        self.assertEqual(len(self.processed), 1)

    def test_fresh_watcher_skips_already_known_file(self):
        self.write("idea.m4a")
        self.watcher.scan_once()
        capture_id = self.watcher.scan_once()[0]
        again = FolderWatcher(self.folder, archive=False, on_capture=self.processed.append)
        again.scan_once()
        self.assertEqual(again.scan_once(), [])
        self.assertIsNotNone(db.get_capture(capture_id))

    def test_created_at_comes_from_file_time(self):
        path = self.write("idea.m4a")
        long_ago = time.time() - 7200
        os.utime(path, (long_ago, long_ago))
        self.watcher.scan_once()
        capture_id = self.watcher.scan_once()[0]
        capture = db.get_capture(capture_id)
        assert capture is not None
        self.assertEqual(capture["created_at"], iso_from_mtime(path.stat().st_mtime))
        self.assertEqual(capture["source"], "sync")

    def test_audio_is_copied_into_data_dir(self):
        self.write("idea.m4a", b"noget-lyd")
        self.watcher.scan_once()
        capture_id = self.watcher.scan_once()[0]
        capture = db.get_capture(capture_id)
        assert capture is not None
        copied = Path(capture["audio_path"])
        self.assertTrue(copied.is_file())
        self.assertEqual(copied.read_bytes(), b"noget-lyd")
        self.assertEqual(copied.suffix, ".m4a")

    def test_too_big_is_skipped(self):
        small = FolderWatcher(self.folder, archive=False, max_bytes=4, on_capture=self.processed.append)
        self.write("stor.m4a", b"meget mere end fire bytes")
        small.scan_once()
        self.assertEqual(small.scan_once(), [])

    def test_archive_moves_the_source_file(self):
        watcher = FolderWatcher(self.folder, archive=True, on_capture=self.processed.append)
        path = self.write("idea.m4a")
        watcher.scan_once()
        watcher.scan_once()
        self.assertFalse(path.exists())
        self.assertTrue((self.folder / "behandlet" / "idea.m4a").is_file())

    def test_archive_dir_can_live_outside_the_watched_folder(self):
        outside = Path(tempfile.mkdtemp(prefix="intake-arkiv-"))
        watcher = FolderWatcher(
            self.folder,
            archive=True,
            archive_dir=outside,
            on_capture=self.processed.append,
        )
        path = self.write("idea.m4a")
        watcher.scan_once()
        watcher.scan_once()
        self.assertFalse(path.exists())
        self.assertFalse((self.folder / "behandlet").exists())
        self.assertTrue((outside / "idea.m4a").is_file())

    def test_archive_folder_is_not_rescanned(self):
        watcher = FolderWatcher(self.folder, archive=True, on_capture=self.processed.append)
        self.write("idea.m4a")
        watcher.scan_once()
        watcher.scan_once()
        self.assertEqual(watcher.scan_once(), [])
        self.assertEqual(len(self.processed), 1)

    def test_capture_id_is_stable_and_distinct(self):
        first = capture_id_for("idea.m4a", 10, 123)
        self.assertEqual(first, capture_id_for("idea.m4a", 10, 123))
        self.assertNotEqual(first, capture_id_for("idea.m4a", 11, 123))
        self.assertNotEqual(first, capture_id_for("anden.m4a", 10, 123))

    def test_missing_folder_is_harmless(self):
        watcher = FolderWatcher(self.folder / "findes-ikke", archive=False)
        self.assertEqual(watcher.scan_once(), [])


if __name__ == "__main__":
    unittest.main()
