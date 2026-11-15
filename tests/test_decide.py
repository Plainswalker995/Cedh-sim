import random
import unittest

from cedh_sim import decide


class DecideTest(unittest.TestCase):
    def test_parse(self):
        e = decide.parse("T9 DECIDE counter 0 explore cmc=2.0,ready=1.0 | Kinnan, Bonder Prodigy")
        self.assertEqual(e["kind"], "counter")
        self.assertEqual(e["choice"], 0)
        self.assertEqual(e["f"], {"cmc": 2.0, "ready": 1.0})
        self.assertEqual(e["player"], "Kinnan, Bonder Prodigy")
        self.assertIsNone(decide.parse("PLAN x casts y"))

    def test_too_few_examples(self):
        m = decide.fit("go", [{"choice": 1, "f": {"prot": 1.0}, "won": 1}] * 50)
        self.assertFalse(m["ok"])

    def test_learns_the_better_option(self):
        # waiting (0) wins more when opponents hold open mana; going (1) wins more otherwise
        rng = random.Random(3)
        rows = []
        for _ in range(2000):
            open_ = rng.choice([0.0, 4.0])
            c = rng.choice([0, 1])
            p = (0.45 if c else 0.2) if open_ == 0 else (0.1 if c else 0.3)
            rows.append({"choice": c, "f": {"opp_open": open_}, "won": int(rng.random() < p)})
        m = decide.fit("go", rows)
        self.assertTrue(m["ok"])
        self.assertGreater(decide._score(m, {"opp_open": 0.0}, 1), decide._score(m, {"opp_open": 0.0}, 0))
        self.assertLess(decide._score(m, {"opp_open": 4.0}, 1), decide._score(m, {"opp_open": 4.0}, 0))
        lines = decide.properties_lines({"go": m})
        self.assertTrue(any(x.startswith("go.cw.opp_open=") for x in lines))


if __name__ == "__main__":
    unittest.main()
