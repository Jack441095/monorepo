import random
import unittest


class PostProcessorStrongBeatAnchorTests(unittest.TestCase):
    def test_strong_beats_snap_to_stable_chord_members(self):
        from ai.markov.melody.post_processor import PostProcessor

        post = PostProcessor(rng=random.Random(0))
        melody = [
            (1, 1.0),  # bar 1 downbeat, non-chord
            (2, 1.0),  # weak beat, chord tone
            (6, 1.0),  # strong beat at beat 2, non-stable extension-like tone
            (4, 1.0),  # weak beat, chord tone
        ]
        beat_positions = [0.0, 1.0, 2.0, 3.0]
        chord_tones_per_bar = [{0, 2, 4, 6}]
        chord_weights_per_bar = [{0: 1.0, 2: 0.9, 4: 0.8, 6: 0.6}]

        out = post.enforce_chord_tones(
            melody,
            chord_tones_per_bar,
            4.0,
            beat_positions,
            probability=0.0,
            chord_weights_per_bar=chord_weights_per_bar,
        )

        self.assertEqual(out[0][0], 0)
        self.assertEqual(out[1][0], 2)
        self.assertIn(out[2][0], {0, 2, 4})
        self.assertEqual(out[3][0], 4)


if __name__ == "__main__":
    unittest.main()
