"""Draw-cause tagging, on hand-made game records (no Forge build needed)."""
import unittest

from cedh_sim import draws

ROLES = {"Island": ["land"], "Tundra": ["land"], "Sol Ring": ["fast"], "Mox Opal": ["fast"],
         "Underground Sea": ["land"], "Rhystic Study": ["draw"], "Imperial Seal": ["tutor"],
         "Ragavan, Nimble Pilferer": [], "Counterspell": ["interaction"]}


def game(hand, board, winner=None):
    return {"game": 1, "winner": winner, "how": "round cap (draw)",
            "stats": {"A": {"end_hand": hand, "battlefield": board, "countered": []},
                      "B": {"end_hand": ["Counterspell"], "battlefield": ["Island"], "countered": []}}}


class DrawCauseTest(unittest.TestCase):
    def test_win_is_not_a_draw(self):
        self.assertIsNone(draws.cause(game([], [], winner="A"), ROLES))

    def test_held_combo_is_a_mistake(self):
        c = draws.cause(game(["Thassa's Oracle", "Demonic Consultation"], ["Island"]), ROLES)
        self.assertEqual(c["kind"], "AI mistake")

    def test_oracle_already_in_play_is_not_a_held_win(self):
        c = draws.cause(game(["Demonic Consultation"], ["Thassa's Oracle", "Island"]), ROLES)
        self.assertEqual(c["kind"], "natural")

    def test_threats_with_mana_to_spare_is_a_mistake(self):
        board = ["Island", "Tundra", "Underground Sea", "Sol Ring", "Mox Opal"]
        c = draws.cause(game(["Rhystic Study", "Imperial Seal", "Ragavan, Nimble Pilferer"], board), ROLES)
        self.assertEqual(c["kind"], "AI mistake")

    def test_holding_answers_is_natural(self):
        board = ["Island", "Tundra", "Underground Sea", "Sol Ring", "Mox Opal"]
        c = draws.cause(game(["Counterspell", "Counterspell", "Pact of Negation"], board), ROLES)
        self.assertEqual(c["kind"], "natural")

    def test_lock_piece_is_named(self):
        c = draws.cause(game([], ["Drannith Magistrate", "Island"]), ROLES)
        self.assertIn("Drannith Magistrate", " ".join(c["why"]))


if __name__ == "__main__":
    unittest.main()


class RangesTest(unittest.TestCase):
    def test_missing_games_group_into_runs(self):
        from cedh_sim.engine import _ranges
        self.assertEqual(_ranges([45, 31, 32, 33, 40, 41]), [(31, 3), (40, 2), (45, 1)])
        self.assertEqual(_ranges([]), [])
