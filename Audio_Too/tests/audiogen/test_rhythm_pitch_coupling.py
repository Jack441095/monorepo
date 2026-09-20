import unittest


class _FakeMarkov:
    def __init__(self, probs):
        self._probs = dict(probs)

    def get_rhythm_probs(self, _ctx, _temp):
        return dict(self._probs)


class RhythmPitchCouplingTests(unittest.TestCase):
    def test_large_interval_prefers_longer_durations(self):
        from audiogen_core.config import CONFIG
        from ai.markov.melody.note_generator import NoteGenerator

        mk = _FakeMarkov({0.25: 0.33, 0.5: 0.33, 1.0: 0.34})
        ng = NoteGenerator(markov_models=mk, motif_manager=None, phrase_planner=None)

        old_on = getattr(CONFIG.composition, "melody_rhythm_pitch_coupling_enabled", False)
        old_st = getattr(CONFIG.composition, "melody_rhythm_pitch_coupling_strength", 0.65)
        try:
            CONFIG.composition.melody_rhythm_pitch_coupling_enabled = True
            CONFIG.composition.melody_rhythm_pitch_coupling_strength = 1.0

            # Large last interval should bias toward 1.0 over 0.25.
            picks = []
            for _ in range(200):
                picks.append(
                    ng._select_rhythm(
                        rhythm_context=[],
                        temperature=1.0,
                        current_beat=1.0,
                        beats_per_bar=4.0,
                        emotion=None,
                        plan=None,
                        phrase_pos=0.5,
                        current_chord=None,
                        phrase_end_beat=None,
                        last_interval=5,
                    )
                )
            frac_long = sum(1 for p in picks if abs(float(p) - 1.0) < 1e-9) / len(picks)
            frac_short = sum(1 for p in picks if abs(float(p) - 0.25) < 1e-9) / len(picks)
            self.assertGreater(frac_long, frac_short)
        finally:
            CONFIG.composition.melody_rhythm_pitch_coupling_enabled = old_on
            CONFIG.composition.melody_rhythm_pitch_coupling_strength = old_st


if __name__ == "__main__":
    unittest.main()

