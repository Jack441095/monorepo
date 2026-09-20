import unittest


class TransitionPickupWriterTests(unittest.TestCase):
    def test_verse_to_prechorus_writes_lift_pickup(self):
        from composition.melody_runtime import MelodyRuntime

        tokens = [(0, 1.0), (1, 1.0), (3, 1.0), (4, 1.0)]
        out = MelodyRuntime._apply_transition_pickup_writer(
            tokens,
            notes_per_phrase=[4],
            section_role="a",
            next_role="pre_chorus",
            strength=1.0,
        )

        self.assertIn(int(out[-1][0]), {1, 3})
        self.assertLessEqual(float(out[-1][1]), 0.5)
        self.assertGreater(float(out[-2][1]), float(tokens[-2][1]))

    def test_prechorus_to_chorus_writes_hook_approach_pickup(self):
        from composition.melody_runtime import MelodyRuntime

        tokens = [(2, 1.0), (3, 1.0), (4, 1.0), (5, 1.0)]
        out = MelodyRuntime._apply_transition_pickup_writer(
            tokens,
            notes_per_phrase=[4],
            section_role="pre_chorus",
            next_role="b",
            hook_anchor_degree=0,
            strength=1.0,
        )

        self.assertIn(int(out[-1][0]), {6, 1})
        self.assertLessEqual(float(out[-1][1]), 0.5)

    def test_non_transition_roles_are_unchanged(self):
        from composition.melody_runtime import MelodyRuntime

        tokens = [(0, 1.0), (2, 1.0), (4, 1.0), (2, 1.0)]
        out = MelodyRuntime._apply_transition_pickup_writer(
            tokens,
            notes_per_phrase=[4],
            section_role="b",
            next_role="a",
            strength=1.0,
        )

        self.assertEqual(out, tokens)


if __name__ == "__main__":
    unittest.main()
