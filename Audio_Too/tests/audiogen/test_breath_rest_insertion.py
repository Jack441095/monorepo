import random
import unittest


class BreathRestInsertionTests(unittest.TestCase):
    def test_breath_spike_increases_rests_on_that_bar(self):
        from ai.markov.melody.post_processor import PostProcessor

        # 64 sixteenth notes = 16 beats = 4 bars; bar index 3 covers beats [12, 16).
        melody = [(0, 0.25)] * 64
        beat_positions = [float(i) * 0.25 for i in range(64)]
        breath = [0.0, 0.0, 0.0, 1.0]

        def rests_in_bar3(seq):
            return sum(
                1
                for i, (deg, _) in enumerate(seq)
                if deg == -1 and 12.0 <= beat_positions[i] < 16.0
            )

        total_base = 0
        total_biased = 0
        trials = 800
        for seed in range(trials):
            pp1 = PostProcessor(rng=random.Random(seed))
            r1 = pp1.insert_rests(melody, beat_positions, 4.0, prob=0.25)
            pp2 = PostProcessor(rng=random.Random(seed))
            r2 = pp2.insert_rests(
                melody,
                beat_positions,
                4.0,
                prob=0.25,
                breath_window_by_bar=breath,
                breath_bias_strength=1.0,
            )
            total_base += rests_in_bar3(r1)
            total_biased += rests_in_bar3(r2)

        self.assertGreater(total_biased, total_base)


if __name__ == "__main__":
    unittest.main()
