import random
import unittest


class MotifTransformGrammarTests(unittest.TestCase):
    def test_fragment_variant_truncates_and_shortens_rhythm(self) -> None:
        from composition.motif_transform import transform_motif_for_slot

        iv, rh, name = transform_motif_for_slot(
            intervals=[0, 1, -1, 2],
            rhythms=[0.5, 0.5, 0.5, 0.5],
            role="a_prime",
            section_variant="fragment",
            slot_variant="fragment",
            slot_index=0,
            total_slots=2,
            strength=1.0,
            rng=random.Random(7),
        )
        self.assertLessEqual(len(iv), 3)
        self.assertEqual(len(iv), len(rh))
        self.assertTrue(any(float(r) < 0.5 for r in rh))
        self.assertIn("truncate", str(name))

    def test_statement_variant_keeps_identity_at_low_strength(self) -> None:
        from composition.motif_transform import transform_motif_for_slot

        src_iv = [0, 1, 0, -1]
        src_rh = [0.5, 0.5, 1.0, 0.5]
        iv, rh, name = transform_motif_for_slot(
            intervals=list(src_iv),
            rhythms=list(src_rh),
            role="b",
            section_variant="statement",
            slot_variant="statement",
            slot_index=0,
            total_slots=1,
            strength=0.0,
            rng=random.Random(123),
        )
        self.assertEqual(iv, src_iv)
        self.assertEqual(rh, src_rh)
        self.assertEqual(str(name), "identity")


if __name__ == "__main__":
    unittest.main()

