"""Tests for per-song arranged-form variety (docs/AUDIOGEN_COMPOSITION_PLAN.md item 2):
data/arrangement_forms.select_arranged_form / arranged_form_weights."""
import unittest


class TestFormWeights(unittest.TestCase):
    def test_weights_normalized_and_cover_pool(self):
        from data.arrangement_forms import _AUTO_FORM_POOL, arranged_form_weights

        w = arranged_form_weights("joy")
        self.assertEqual(set(w.keys()), set(_AUTO_FORM_POOL))
        self.assertAlmostEqual(sum(w.values()), 1.0, places=6)
        # floor keeps every form reachable
        self.assertTrue(all(v > 0.0 for v in w.values()))

    def test_energetic_emotion_prefers_energetic_forms(self):
        from data.arrangement_forms import arranged_form_weights

        w = arranged_form_weights("excitement")
        # high-energy forms should out-weight the slow ballad
        self.assertGreater(w["anthem"] + w["wave"] + w["pop_ext"], w["ballad"] * 3)

    def test_calm_emotion_prefers_calm_forms(self):
        from data.arrangement_forms import arranged_form_weights

        w = arranged_form_weights("grief")
        # ballad (slow, emotional) should dominate for grief
        self.assertEqual(max(w, key=w.get), "ballad")


class TestFormSelection(unittest.TestCase):
    def test_seeded_selection_is_deterministic(self):
        from data.arrangement_forms import select_arranged_form

        a = select_arranged_form("excitement", seed=123)
        b = select_arranged_form("excitement", seed=123)
        self.assertEqual(a, b)

    def test_selection_varies_across_seeds(self):
        from data.arrangement_forms import select_arranged_form

        picks = {select_arranged_form("excitement", seed=s) for s in range(40)}
        # a real variety improvement: more than one structure appears
        self.assertGreater(len(picks), 1)

    def test_avoid_downweights_repeat(self):
        from data.arrangement_forms import select_arranged_form

        # over many seeds, avoiding a form should reduce (not forbid) its share
        base = [select_arranged_form("excitement", seed=s) for s in range(200)]
        avoided = [select_arranged_form("excitement", seed=s, avoid="anthem") for s in range(200)]
        self.assertLess(avoided.count("anthem"), base.count("anthem"))

    def test_returned_form_is_in_pool(self):
        from data.arrangement_forms import _AUTO_FORM_POOL, select_arranged_form

        for emo in ("joy", "grief", "neutral", "anger"):
            self.assertIn(select_arranged_form(emo, seed=1), _AUTO_FORM_POOL)


if __name__ == "__main__":
    unittest.main()
