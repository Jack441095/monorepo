import unittest

from ai.markov.melody.note_generator._interval_helpers import canon_chord_symbol_for_interval
from ai.markov.melody.note_generator._interval_role_blend import blend_interval_probs_with_phrase_role


class CanonChordSymbolTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(canon_chord_symbol_for_interval(""), "")
        self.assertEqual(canon_chord_symbol_for_interval("   "), "")

    def test_roman_major_minor(self):
        self.assertEqual(canon_chord_symbol_for_interval("Imaj7"), "Imaj")
        self.assertEqual(canon_chord_symbol_for_interval("vi"), "vimin")
        self.assertEqual(canon_chord_symbol_for_interval("V7"), "Vdom")

    def test_dim_aug_sus(self):
        self.assertEqual(canon_chord_symbol_for_interval("ii°7"), "iidim")
        self.assertEqual(canon_chord_symbol_for_interval("I+"), "Iaug")
        self.assertEqual(canon_chord_symbol_for_interval("Vsus4"), "Vsus")


class IntervalRoleBlendTests(unittest.TestCase):
    def test_no_op_without_role_model(self):
        class M:
            pass

        probs = {1: 0.5, 2: 0.5}
        out = blend_interval_probs_with_phrase_role(
            M(), object(), None, dict(probs), [1, 2], 1.0, blend=0.5, role_enabled=True
        )
        self.assertEqual(out, probs)

    def test_blends_when_role_model_present(self):
        class M:
            def get_interval_probs_for_role(self, role, ctx, temp):
                return {1: 0.9, 2: 0.1} if role == "cadence" else {}

        class Plan:
            phrase_role = "cadence"

        probs = {1: 0.1, 2: 0.9}
        out = blend_interval_probs_with_phrase_role(
            M(), Plan(), None, dict(probs), [1, 2], 1.0, blend=0.5, role_enabled=True
        )
        self.assertAlmostEqual(sum(out.values()), 1.0, places=5)
        self.assertGreater(out[1], probs[1])


if __name__ == "__main__":
    unittest.main()
