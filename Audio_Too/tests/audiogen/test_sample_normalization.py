import unittest

import numpy as np

from sampler.utils import normalize_audio


class SampleNormalizationTests(unittest.TestCase):
    def test_rms_normalization_ignores_long_silence(self):
        # Same "active" tone, but one sample has lots of silence appended.
        sr = 44100
        t = np.linspace(0, 1, sr, endpoint=False)
        tone = 0.2 * np.sin(2 * np.pi * 220 * t).astype(np.float32)
        a = np.column_stack([tone, tone])
        b = np.concatenate([a, np.zeros((sr * 3, 2), dtype=np.float32)], axis=0)  # +3s silence

        na = normalize_audio(a, target_db=-12.0, mode="rms", prevent_clipping=True, sample_rate=sr)
        nb = normalize_audio(b, target_db=-12.0, mode="rms", prevent_clipping=True, sample_rate=sr)

        # Measure RMS over the first second (active part)
        ra = float(np.sqrt(np.mean(na[:sr] ** 2)))
        rb = float(np.sqrt(np.mean(nb[:sr] ** 2)))
        self.assertAlmostEqual(ra, rb, places=3)

    def test_loudness_normalization_stable_for_sparse_transient(self):
        sr = 44100
        # One short transient + mostly silence
        x = np.zeros((sr, 2), dtype=np.float32)
        x[100:200, 0] = 0.5
        x[100:200, 1] = 0.5

        y = normalize_audio(x, target_db=-18.0, mode="loudness", prevent_clipping=True, sample_rate=sr)

        # Should not explode in gain; peak should remain bounded by clipping protection.
        self.assertLessEqual(float(np.max(np.abs(y))), 0.95 + 1e-6)


if __name__ == "__main__":
    unittest.main()

