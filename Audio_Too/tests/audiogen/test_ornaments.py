"""Tests for melodic ornaments (docs/AUDIOGEN_COMPOSITION_PLAN.md item 16 follow-up):
mordent / turn / slide in ai.markov.melody.embellishments. Core contract: each ornament
preserves the note's total duration, respects the 0.25-beat grid, and rejects too-short
notes."""
import random
import unittest


class TestOrnamentContract(unittest.TestCase):
    def _preserves_duration(self, seg, dur):
        self.assertIsNotNone(seg)
        self.assertAlmostEqual(sum(d for _, d in seg), dur, places=9)
        # every sub-note on/above the 0.25 grid floor
        for _, d in seg:
            self.assertGreaterEqual(d, 0.25 - 1e-9)

    def test_mordent(self):
        from ai.markov.melody.embellishments import find_mordent_opportunity

        rng = random.Random(0)
        seg = find_mordent_opportunity([(3, 1.0)], 0, rng=rng)
        self._preserves_duration(seg, 1.0)
        self.assertEqual(len(seg), 3)
        self.assertEqual(seg[0][0], 3)  # starts on principal
        self.assertEqual(seg[2][0], 3)  # returns to principal

    def test_turn(self):
        from ai.markov.melody.embellishments import find_turn_opportunity

        seg = find_turn_opportunity([(3, 2.0)], 0)
        self._preserves_duration(seg, 2.0)
        self.assertEqual(len(seg), 4)
        self.assertEqual([d for d, _ in seg], [(3 + 1) % 7, 3, (3 - 1) % 7, 3])  # upper,main,lower,main

    def test_slide(self):
        from ai.markov.melody.embellishments import find_slide_opportunity

        seg = find_slide_opportunity([(4, 1.0)], 0)
        self._preserves_duration(seg, 1.0)
        self.assertEqual([d for d, _ in seg], [(4 - 2) % 7, (4 - 1) % 7, 4])  # scalar approach up

    def test_too_short_rejected(self):
        from ai.markov.melody.embellishments import (
            find_mordent_opportunity, find_slide_opportunity, find_turn_opportunity)

        self.assertIsNone(find_mordent_opportunity([(3, 0.5)], 0))   # needs >= 0.75
        self.assertIsNone(find_slide_opportunity([(3, 0.5)], 0))     # needs >= 0.75
        self.assertIsNone(find_turn_opportunity([(3, 0.75)], 0))     # needs >= 1.0


class TestApplyPreservesTotalDuration(unittest.TestCase):
    def test_full_melody_duration_preserved(self):
        from ai.markov.melody.embellishments import apply_embellishments

        rng = random.Random(7)
        melody = [(0, 1.0), (2, 1.0), (4, 2.0), (2, 1.0), (0, 2.0), (4, 1.0)]
        bp = [0.0, 1.0, 2.0, 4.0, 5.0, 7.0]
        ct = [{0, 2, 4}, {0, 2, 4}]
        total_in = sum(d for _, d in melody)
        out = apply_embellishments(
            melody, bp, ct, 4.0,
            prob_passing=0.0, prob_neighbor=0.0, prob_appoggiatura=0.0,
            prob_mordent=0.9, prob_turn=0.9, prob_slide=0.9, rng=rng,
        )
        self.assertAlmostEqual(sum(d for _, d in out), total_in, places=9)
        self.assertGreater(len(out), len(melody))  # ornaments added notes


if __name__ == "__main__":
    unittest.main()
