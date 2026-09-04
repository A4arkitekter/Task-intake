import os
import tempfile
import unittest
from unittest.mock import patch

os.environ["LLM_ENABLED"] = "0"
os.environ["APP_PASSWORD"] = "test-pass"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["WHISPER_WARMUP"] = "0"
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="intake-extract-")

from app.extract import extract_proposals, headline
from app.rewrite import parse_card


class ExtractTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(extract_proposals("   "), [])

    def test_one_recording_is_one_card(self):
        cards = extract_proposals(
            "Jeg skal booke lokale til tirsdag. Og så købe ind til middagen."
        )
        self.assertEqual(len(cards), 1)
        self.assertIn("booke lokale", cards[0]["note"].lower())

    def test_headline_ring(self):
        self.assertEqual(
            headline("Husk at ringe til Martin om kontrakten."),
            "Ring til Martin om kontrakten",
        )

    def test_headline_book(self):
        self.assertEqual(headline("Jeg skal booke lokale til tirsdag."), "Book lokale til tirsdag")

    def test_headline_send_after_preamble(self):
        title = headline("Ja altså jeg tænkte på at vi burde sende tilbuddet til kunden")
        self.assertEqual(title, "Send tilbuddet til kunden")

    def test_headline_buy(self):
        self.assertEqual(headline("Og så købe ind til middagen"), "Køb ind til middagen")

    def test_headline_skips_idea_opener(self):
        text = (
            "Jeg har en ny idé, den nedrører A4 OS. "
            "Vi skal have nogle dashboards, både til entrepriser og sager."
        )
        self.assertEqual(len(extract_proposals(text)), 1)
        title = headline(text)
        self.assertIn("dashboard", title.lower())
        self.assertNotIn("ny idé", title.lower())

    def test_llm_card_matches_quality_example(self):
        messy = (
            "Jeg har en idé, der handler om, at vi fremover os, "
            "skal sortere vores affald i købnet"
        )
        with patch(
            "app.extract.rewrite_idea",
            return_value={
                "title": "Fremtidig affaldssortering i køkkenet",
                "note": "Vi skal fremover sortere vores affald i køkkenet.",
            },
        ):
            cards = extract_proposals(messy)
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["title"], "Fremtidig affaldssortering i køkkenet")
        self.assertEqual(cards[0]["note"], "Vi skal fremover sortere vores affald i køkkenet.")


class RewriteParseTests(unittest.TestCase):
    def test_parse_plain_json(self):
        card = parse_card(
            '{"title":"Fremtidig affaldssortering i køkkenet",'
            '"note":"Vi skal fremover sortere vores affald i køkkenet."}'
        )
        assert card is not None
        self.assertEqual(card["title"], "Fremtidig affaldssortering i køkkenet")
        self.assertTrue(card["note"].endswith("."))

    def test_parse_fenced_json(self):
        card = parse_card(
            '```json\n{"title":"Dashboards til A4 OS","note":"Vi skal have dashboards til entrepriser og sager"}\n```'
        )
        assert card is not None
        self.assertEqual(card["title"], "Dashboards til A4 OS")
        self.assertEqual(card["note"], "Vi skal have dashboards til entrepriser og sager.")

    def test_parse_garbage(self):
        self.assertIsNone(parse_card("ingen json her"))


if __name__ == "__main__":
    unittest.main()
