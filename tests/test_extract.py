import unittest

from app.extract import extract_proposals


class ExtractTests(unittest.TestCase):
    def test_single_idea(self):
        cards = extract_proposals("Husk at ringe til Martin om kontrakten.")
        self.assertEqual(len(cards), 1)
        blob = (cards[0]["title"] + " " + cards[0]["note"]).lower()
        self.assertIn("martin", blob)

    def test_splits_on_og_saa(self):
        cards = extract_proposals(
            "Jeg skal booke lokale til tirsdag. Og så købe ind til middagen."
        )
        self.assertGreaterEqual(len(cards), 2)

    def test_empty(self):
        self.assertEqual(extract_proposals("   "), [])


if __name__ == "__main__":
    unittest.main()
