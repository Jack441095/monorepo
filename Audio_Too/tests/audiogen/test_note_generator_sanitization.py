import random
import unittest
from types import SimpleNamespace


class _UniformIntervalMarkov:
    use_chord_conditioned = False

    def get_interval_probs(self, _ctx, _temp):
        return {i: 1.0 for i in (-2, -1, 0, 1, 2)}


class NoteGeneratorSanitizationTests(unittest.TestCase):
    def test_zero_emotion_intensity_does_not_crash_interval_selection(self):
        from ai.markov.melody.note_generator import NoteGenerator
        from ai.markov.melody.phrase_planner import PhrasePlanner

        ng = NoteGenerator(
            markov_models=_UniformIntervalMarkov(),
            motif_manager=None,
            phrase_planner=PhrasePlanner(),
            rng=random.Random(0),
            stepwise_boost_base=1.0,
            chord_tone_multiplier=1.0,
            downbeat_chord_multiplier=1.0,
            emotion_intensity=0.0,
        )
        plan = SimpleNamespace(
            contour="neutral",
            cadence_zone_start=0.75,
            climax_position=0.67,
            target_climax=None,
            entry_degree=None,
            pre_cadence_degree=None,
            phrase_type="",
        )
        emotion = SimpleNamespace(name="sad", scale_intervals=[0, 2, 4, 5, 7, 9, 11])

        interval = ng._select_interval(
            [],
            3,
            [(3, 1.0)],
            1.0,
            plan,
            emotion,
            0,
            0.3,
            None,
            None,
            None,
            None,
            4.0,
            16,
            None,
            1.0,
        )

        self.assertIn(int(interval), {-2, -1, 0, 1, 2})


if __name__ == "__main__":
    unittest.main()
