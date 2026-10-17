import random
import unittest


class _FakeRhythmMarkov:
    def __init__(self, probs):
        self._probs = dict(probs)

    def get_rhythm_probs(self, _ctx, _temp):
        return dict(self._probs)


class _FakeMarkovSet:
    rhythm_order = 4
    interval_order = 3

    def __init__(self):
        self.rhythm = _FakeRhythmMarkov({0.25: 0.34, 0.5: 0.33, 1.0: 0.33})

    def get_rhythm_probs(self, ctx, temp):
        return self.rhythm.get_rhythm_probs(ctx, temp)

    def get_interval_probs(self, _ctx, _temp):
        # Favor small intervals so joint rerank should favor short durations.
        return {-1: 0.1, 0: 0.35, 1: 0.35, 2: 0.1, 3: 0.1}


class MarkovPhaseBFeaturesTests(unittest.TestCase):
    def test_breath_rhythm_bias_favors_longer_on_high_breath_bar(self):
        from audiogen_core.config import CONFIG
        from ai.markov.melody.note_generator import NoteGenerator
        from ai.markov.melody.phrase_planner import PhrasePlanner

        mk = _FakeMarkovSet()
        ng = NoteGenerator(markov_models=mk, motif_manager=None, phrase_planner=PhrasePlanner(), rng=random.Random(0))
        breath = [0.0, 0.0, 0.0, 1.0]

        old_on = getattr(CONFIG.composition, "melody_breath_rhythm_bias_enabled", False)
        old_st = getattr(CONFIG.composition, "melody_breath_rhythm_bias_strength", 0.65)
        try:
            CONFIG.composition.melody_breath_rhythm_bias_enabled = True
            CONFIG.composition.melody_breath_rhythm_bias_strength = 1.0

            def frac_one_at_bar3():
                picks = []
                for _ in range(300):
                    picks.append(
                        ng._select_rhythm(
                            [],
                            1.0,
                            12.0,
                            4.0,
                            None,
                            breath_window_by_bar=breath,
                        )
                    )
                return sum(1 for p in picks if abs(float(p) - 1.0) < 1e-9) / len(picks)

            def frac_one_at_bar0():
                picks = []
                for _ in range(300):
                    picks.append(
                        ng._select_rhythm(
                            [],
                            1.0,
                            0.0,
                            4.0,
                            None,
                            breath_window_by_bar=breath,
                        )
                    )
                return sum(1 for p in picks if abs(float(p) - 1.0) < 1e-9) / len(picks)

            self.assertGreater(frac_one_at_bar3(), frac_one_at_bar0() + 0.05)
        finally:
            CONFIG.composition.melody_breath_rhythm_bias_enabled = old_on
            CONFIG.composition.melody_breath_rhythm_bias_strength = old_st

    def test_duration_interval_compat_prefers_short_dur_when_intervals_small(self):
        """Joint rerank uses this score: short IOIs should beat long when P(|iv|<=1) is high."""
        from ai.markov.melody.note_generator import NoteGenerator

        ip = {-1: 0.1, 0: 0.35, 1: 0.35, 2: 0.1, 3: 0.1}
        c_short = NoteGenerator._duration_interval_compat(ip, 0.25)
        c_long = NoteGenerator._duration_interval_compat(ip, 1.0)
        self.assertGreater(c_short, c_long)


class RestSafeTrainingTests(unittest.TestCase):
    def test_voiced_only_intervals_skip_rests(self):
        mel = [(0, 0.25), (-1, 0.5), (3, 1.0), (4, 0.5)]
        voiced = [int(d) for d, _ in mel if isinstance(d, int) and int(d) >= 0]
        self.assertEqual(voiced, [0, 3, 4])
        intervals = [voiced[j + 1] - voiced[j] for j in range(len(voiced) - 1)]
        self.assertEqual(intervals, [3, 1])


if __name__ == "__main__":
    unittest.main()
