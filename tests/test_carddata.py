"""Card data parsing and the Commander deck rules, without a Forge build."""
import unittest

from cedh_sim import banlist, carddata

SQUELCHER = """Name:Hexing Squelcher
ManaCost:1 R
Types:Creature Goblin Sorcerer
PT:2/2
Oracle:This spell can't be countered.\\nSpells you control can't be countered.
"""
FIRE_ICE = """Name:Fire
ManaCost:1 R
Types:Instant
AlternateMode:Split
Oracle:Fire deals 2 damage divided as you choose among one or two targets.
ALTERNATE
Name:Ice
ManaCost:1 U
Types:Instant
Oracle:Tap target permanent.\\nDraw a card.
"""
WILSON = "Name:Wilson\nManaCost:2 G\nTypes:Legendary Creature Bear Warrior\nPT:4/4\nOracle:Reach\\nChoose a Background\n"
GIANTS = "Name:Raised by Giants\nManaCost:5 G\nTypes:Legendary Enchantment Background\nOracle:Commander creatures you own have base power and toughness 10/10.\n"


class CardData(unittest.TestCase):
    def test_types_and_cost(self):
        c = carddata._parse(SQUELCHER)
        self.assertEqual(c["type_line"], "Creature — Goblin Sorcerer")
        self.assertEqual(c["types"], ["Creature"])
        self.assertEqual((c["mana_cost"], c["mv"], c["color_identity"]), ("{1}{R}", 2, ["R"]))

    def test_split_card(self):
        c = carddata._parse(FIRE_ICE)
        self.assertEqual((c["name"], c["mv"], c["color_identity"]), ("Fire // Ice", 4, ["U", "R"]))

    def test_odd_costs(self):
        self.assertEqual(carddata.mana_value("2/B 2/B"), 4)
        self.assertEqual(carddata.cost_symbols("UP"), "{U/P}")
        self.assertEqual(carddata.cost_symbols("WU 1"), "{W/U}{1}")
        self.assertEqual(carddata.mana_value("X U U"), 2)


class Rules(unittest.TestCase):
    def setUp(self):
        cards = {n: carddata._parse(t) for n, t in (("Hexing Squelcher", SQUELCHER), ("Wilson", WILSON),
                                                    ("Raised by Giants", GIANTS))}
        cards["Mana Crypt"] = carddata._parse("Name:Mana Crypt\nManaCost:0\nTypes:Artifact\nOracle:{T}: Add {C}{C}.\n")
        self.info = cards.get

    def test_background_pair(self):
        self.assertEqual(banlist.check(["Wilson", "Raised by Giants"], {}, self.info), [])

    def test_banned_offcolor_singleton(self):
        p = banlist.check(["Wilson", "Raised by Giants"], {"Mana Crypt": 1, "Hexing Squelcher": 2}, self.info)
        self.assertIn("Mana Crypt: banned", p)
        self.assertTrue(any("outside the commanders' colors" in x for x in p))
        self.assertTrue(any("singleton" in x for x in p))


if __name__ == "__main__":
    unittest.main()
