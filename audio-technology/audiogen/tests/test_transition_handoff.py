# tests/test_transition_handoff.py
# ---------------------------------------------------------------------------
# Emotion handoff harmonic context extraction.
# ---------------------------------------------------------------------------
import unittest

from composition.transition_handoff import extract_last_bar_harmonic_context


class TransitionHandoffTests(unittest.TestCase):
    def test_extracts_chord_pcs_and_bass_from_last_bar(self):
        events = [
            (0, 36, 80, 0.0, 4.0, [36]),
            (1, 0, 80, 0.0, 4.0, [60, 64, 67]),
            (0, 40, 80, 4.0, 4.0, [40]),
            (1, 0, 80, 4.0, 4.0, [64, 67, 71]),
        ]
        ctx = extract_last_bar_harmonic_context(events, total_bars=2, beats_per_bar=4.0)
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.get("previous_bass_midi"), 40)
        self.assertEqual(set(ctx["previous_chord_pcs"]), {4, 7, 11})

    def test_returns_none_when_no_overlap(self):
        events = [(2, 60, 80, 0.0, 1.0, [60])]
        self.assertIsNone(
            extract_last_bar_harmonic_context(events, total_bars=2, beats_per_bar=4.0)
        )


if __name__ == "__main__":
    unittest.main()
