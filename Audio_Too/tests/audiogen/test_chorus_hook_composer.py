import unittest


class ChorusHookComposerTests(unittest.TestCase):
    def test_stabilize_chorus_phrase_plan_reuses_clearer_shapes(self):
        from composition.melody_runtime import MelodyRuntime

        contours, counts = MelodyRuntime._stabilize_chorus_hook_phrase_plan(
            ["desc", "static", "asc", "desc"],
            [6, 10, 7, 9],
            section_role="b",
            strength=1.0,
        )

        self.assertEqual(contours[0], "desc")
        self.assertEqual(contours[1], "desc")
        self.assertEqual(contours[2], "arch")
        self.assertEqual(sum(counts), 32)

    def test_chorus_hook_composer_restates_opening_phrase(self):
        from composition.melody_runtime import MelodyRuntime

        tokens = [
            (0, 1.0), (2, 1.0), (4, 1.0), (2, 1.0),
            (5, 1.0), (6, 1.0), (5, 1.0), (4, 1.0),
            (1, 1.0), (3, 1.0), (5, 1.0), (3, 1.0),
            (6, 1.0), (5, 1.0), (4, 1.0), (0, 1.0),
        ]
        out = MelodyRuntime._apply_chorus_hook_composer(
            tokens,
            notes_per_phrase=[4, 4, 4, 4],
            section_role="b",
            strength=1.0,
        )

        self.assertEqual(out[4:8], out[0:4])
        self.assertEqual(out[8:12], out[0:4])
        # Final cadence note is preserved.
        self.assertEqual(out[15], tokens[15])


if __name__ == "__main__":
    unittest.main()
