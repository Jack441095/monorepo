import random
import unittest


class _FakeMarkov:
    def get_rhythm_probs(self, _ctx, _temp):
        return {0.25: 1.0}


class RhythmSinglePassTests(unittest.TestCase):
    def test_single_pass_samples_directly_from_distribution(self):
        from audiogen_core.config import CONFIG
        from ai.markov.melody.note_generator import NoteGenerator

        ng = NoteGenerator(markov_models=_FakeMarkov(), motif_manager=None, phrase_planner=None, rng=random.Random(0))

        old_single_pass = getattr(CONFIG.composition, "melody_rhythm_single_pass_enabled", False)
        try:
            CONFIG.composition.melody_rhythm_single_pass_enabled = True
            ng._rhythm_distribution = lambda *args, **kwargs: {0.5: 1.0}
            ng._bias_rhythm = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("legacy path should be bypassed"))

            picked = ng._select_rhythm([], 1.0, 0.0, 4.0, None)
            self.assertEqual(float(picked), 0.5)
        finally:
            CONFIG.composition.melody_rhythm_single_pass_enabled = old_single_pass

    def test_single_pass_keeps_distribution_early_exit_value(self):
        from audiogen_core.config import CONFIG
        from ai.markov.melody.note_generator import NoteGenerator

        ng = NoteGenerator(markov_models=_FakeMarkov(), motif_manager=None, phrase_planner=None, rng=random.Random(0))

        old_single_pass = getattr(CONFIG.composition, "melody_rhythm_single_pass_enabled", False)
        try:
            CONFIG.composition.melody_rhythm_single_pass_enabled = True
            ng._rhythm_distribution = lambda *args, **kwargs: 0.0

            picked = ng._select_rhythm([], 1.0, 0.0, 4.0, None)
            self.assertEqual(float(picked), 0.0)
        finally:
            CONFIG.composition.melody_rhythm_single_pass_enabled = old_single_pass


if __name__ == "__main__":
    unittest.main()
