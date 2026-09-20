import random
import unittest
from types import SimpleNamespace


class _UniformIntervalMarkov:
    use_chord_conditioned = False

    def get_interval_probs(self, _ctx, _temp):
        return {i: 1.0 for i in (-6, -5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5, 6)}


class IntervalDurationCouplingTests(unittest.TestCase):
    def test_short_then_long_duration_bias_interval_width(self):
        from ai.markov.melody.note_generator import NoteGenerator
        from ai.markov.melody.phrase_planner import PhrasePlanner
        from audiogen_core.config import CONFIG

        planner = PhrasePlanner()
        ng = NoteGenerator(
            markov_models=_UniformIntervalMarkov(),
            motif_manager=None,
            phrase_planner=planner,
            rng=random.Random(42),
            stepwise_boost_base=1.0,
            chord_tone_multiplier=1.0,
            downbeat_chord_multiplier=1.0,
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

        old_on = getattr(CONFIG.composition, "melody_interval_duration_coupling_enabled", False)
        old_st = getattr(CONFIG.composition, "melody_interval_duration_coupling_strength", 0.65)
        try:
            CONFIG.composition.melody_interval_duration_coupling_strength = 1.0

            def mean_abs(melody, enabled: bool) -> float:
                CONFIG.composition.melody_interval_duration_coupling_enabled = bool(enabled)
                xs = []
                for _ in range(400):
                    iv = ng._select_interval(
                        [],
                        3,
                        melody,
                        1.0,
                        plan,
                        None,
                        0,
                        0.3,
                        None,
                        None,
                        None,
                        None,
                        4.0,
                        64,
                        None,
                        1.0,
                    )
                    xs.append(abs(int(iv)))
                return sum(xs) / len(xs)

            short_off = mean_abs([(3, 0.25)], False)
            short_on = mean_abs([(3, 0.25)], True)
            long_off = mean_abs([(3, 2.0)], False)
            long_on = mean_abs([(3, 2.0)], True)

            self.assertLess(short_on, short_off - 0.05)
            self.assertGreater(long_on, long_off + 0.05)
        finally:
            CONFIG.composition.melody_interval_duration_coupling_enabled = old_on
            CONFIG.composition.melody_interval_duration_coupling_strength = old_st


if __name__ == "__main__":
    unittest.main()
