import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["WHISPER_WARMUP"] = "0"
os.environ["NOTIFY"] = "0"
os.environ["WATCH_ENABLED"] = "0"
os.environ["AUTO_OPEN"] = "0"

from app import transcribe


class ReleaseTests(unittest.TestCase):
    def tearDown(self):
        transcribe._model = None
        transcribe._device = None
        transcribe._last_used = 0.0

    def test_release_hands_the_memory_back(self):
        transcribe._model = object()
        transcribe._device = "cuda"
        self.assertEqual(transcribe.release(), "cuda")
        self.assertIsNone(transcribe._model)

    def test_release_on_an_unloaded_model_is_harmless(self):
        self.assertIsNone(transcribe.release())

    def test_a_model_in_use_is_kept(self):
        transcribe._model = object()
        transcribe._device = "cuda"
        transcribe._last_used = time.monotonic()
        self.assertFalse(transcribe.release_if_idle())
        self.assertIsNotNone(transcribe._model)

    def test_an_idle_model_gives_the_card_back(self):
        transcribe._model = object()
        transcribe._device = "cuda"
        transcribe._last_used = time.monotonic() - transcribe.WHISPER_IDLE_UNLOAD_SEC - 1
        self.assertTrue(transcribe.release_if_idle())
        self.assertIsNone(transcribe._model)


class RuntimeFallbackTests(unittest.TestCase):
    def test_a_failed_transcription_is_retried_before_giving_up(self):
        # Bruger du selv GPU'en, naar en ide lander, maa idéen ikke gaa tabt.
        calls: list[Path] = []

        def flaky(path: Path) -> str:
            calls.append(path)
            if len(calls) == 1:
                raise RuntimeError("CUDA failed with error out of memory")
            return "reddet tekst"

        with patch("app.transcribe._transcribe", side_effect=flaky):
            result = transcribe.transcribe_file(Path("ide.m4a"))

        self.assertEqual(result, "reddet tekst")
        self.assertEqual(len(calls), 2)

    def test_a_hopeless_file_still_raises(self):
        with patch("app.transcribe._transcribe", side_effect=RuntimeError("filen er i stykker")):
            with self.assertRaises(RuntimeError):
                transcribe.transcribe_file(Path("i-stykker.m4a"))


if __name__ == "__main__":
    unittest.main()
