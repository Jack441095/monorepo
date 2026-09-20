import unittest


class VoiceLeadingRerankTests(unittest.TestCase):
    def test_voiceleading_delta_prefers_smoother_strongbeat_motion(self):
        from ai.markov.melody.generator import _voiceleading_local_rerank_delta

        # Two phrases over 1 bar: one leaps on downbeat, one is stepwise.
        chord_weights = [{0: 1.0, 2: 1.0, 4: 1.0, 6: 1.0}]
        smooth = [(1, 1.0), (2, 1.0), (3, 1.0), (4, 1.0)]
        leapy = [(4, 1.0), (0, 1.0), (4, 1.0), (0, 1.0)]

        ds = _voiceleading_local_rerank_delta(
            phrase=smooth,
            start_degree=0,
            start_beat=0.0,
            beats_per_bar=4.0,
            chord_weights_per_bar=chord_weights,
            strength=1.0,
        )
        dl = _voiceleading_local_rerank_delta(
            phrase=leapy,
            start_degree=0,
            start_beat=0.0,
            beats_per_bar=4.0,
            chord_weights_per_bar=chord_weights,
            strength=1.0,
        )
        self.assertGreater(ds, dl)


if __name__ == "__main__":
    unittest.main()

