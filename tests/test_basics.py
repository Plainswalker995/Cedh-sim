"""Fast checks that need no Forge build: statistics and deck-list parsing."""
import unittest

from cedh_sim import stats
from cedh_sim.decks import parse_text


class StatsTest(unittest.TestCase):
    def test_wilson_contains_rate(self):
        lo, hi = stats.wilson(30, 120)
        self.assertLess(lo, 0.25)
        self.assertGreater(hi, 0.25)

    def test_paired_no_difference(self):
        diff, lo, hi = stats.paired([0, 0, 1, -1] * 25)
        self.assertEqual(diff, 0)
        self.assertLess(lo, 0)
        self.assertGreater(hi, 0)


class DeckTest(unittest.TestCase):
    def test_partner_line_and_basics(self):
        d = parse_text("Commander: Tymna the Weaver + Kraum, Ludevic's Opus\n98 Island\n", name="t")
        self.assertEqual(len(d.commanders), 2)
        self.assertEqual(d.main.get("Island"), 98)

    def test_ampersand_name_is_one_commander(self):
        d = parse_text("Commander: Raph & Mikey, Troublemakers\n99 Mountain\n", name="t")
        self.assertEqual(len(d.commanders), 1)


if __name__ == "__main__":
    unittest.main()
