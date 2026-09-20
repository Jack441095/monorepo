import unittest


class _FakeMarkov:
    def __init__(self, probs):
        self._probs = dict(probs)

    def get_rhythm_probs(self, _ctx, _temp):
        return dict(self._probs)


class MelodyPositionConditioningTests(unittest.TestCase):
    def test_position_conditioning_prefers_bar_end_landing(self):
        from audiogen_core.config import CONFIG
        from ai.markov.melody.note_generator import NoteGenerator

        # Fake rhythm distribution.
        mk = _FakeMarkov({0.25: 0.5, 0.5: 0.25, 1.0: 0.25})
        ng = NoteGenerator(markov_models=mk, motif_manager=None, phrase_planner=None)

        old_on = getattr(CONFIG.composition, "melody_position_conditioning_enabled", False)
        old_st = getattr(CONFIG.composition, "melody_position_conditioning_strength", 0.75)
        try:
            # current_beat is 3.75 -> to_bar_end = 0.25.
            def _sample(enabled: bool) -> float:
                CONFIG.composition.melody_position_conditioning_enabled = bool(enabled)
                CONFIG.composition.melody_position_conditioning_strength = 1.0
                picks = []
                for _ in range(250):
                    picks.append(
                        ng._select_rhythm(
                            rhythm_context=[],
                            temperature=1.0,
                            current_beat=3.75,
                            beats_per_bar=4.0,
                            emotion=None,
                            plan=None,
                            phrase_pos=0.9,
                            current_chord=None,
                            phrase_end_beat=8.0,
                            last_interval=0,
                        )
                    )
                return sum(1 for p in picks if abs(float(p) - 0.25) < 1e-9) / len(picks)

            base = _sample(False)
            improved = _sample(True)
            self.assertGreater(improved, base + 0.03)
        finally:
            CONFIG.composition.melody_position_conditioning_enabled = old_on
            CONFIG.composition.melody_position_conditioning_strength = old_st


if __name__ == "__main__":
    unittest.main()

