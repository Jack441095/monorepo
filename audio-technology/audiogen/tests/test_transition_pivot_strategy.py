import unittest


class TransitionPivotStrategyTests(unittest.TestCase):
    def test_extracts_pedal_strategy_when_bass_holds(self) -> None:
        from composition.transition_handoff import extract_last_bar_harmonic_context

        events = [
            # Bar 0
            (1, 0, 90, 0.0, 4.0, [60, 64, 67]),
            (0, 48, 80, 0.0, 4.0, [48]),
            # Bar 1
            (1, 0, 90, 4.0, 4.0, [60, 65, 67]),
            (0, 48, 80, 4.0, 4.0, [48]),
        ]
        ctx = extract_last_bar_harmonic_context(events, total_bars=2, beats_per_bar=4.0)
        self.assertIsNotNone(ctx)
        self.assertEqual(str((ctx or {}).get("handoff_pivot_strategy", "")), "pedal")

    def test_extracts_dominant_pivot_for_fifth_bass_motion(self) -> None:
        from composition.transition_handoff import extract_last_bar_harmonic_context

        events = [
            # Bar 0: C harmony / bass C
            (1, 0, 90, 0.0, 4.0, [60, 64, 67]),
            (0, 48, 80, 0.0, 4.0, [48]),
            # Bar 1: A-like harmony / bass G (P5 up from C)
            (1, 0, 90, 4.0, 4.0, [57, 61, 64]),
            (0, 55, 80, 4.0, 4.0, [55]),
        ]
        ctx = extract_last_bar_harmonic_context(events, total_bars=2, beats_per_bar=4.0)
        self.assertIsNotNone(ctx)
        self.assertEqual(str((ctx or {}).get("handoff_pivot_strategy", "")), "dominant_pivot")


if __name__ == "__main__":
    unittest.main()

