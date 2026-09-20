import logging
import unittest

import numpy as np

from sampler.sample_loader import SampleLoader


def _db_to_linear(db: float) -> float:
    return 10.0 ** (float(db) / 20.0)


class SampleLoaderDcTests(unittest.TestCase):
    def _build_loader(self, **normalizer):
        return SampleLoader(
            sample_rate=1000,
            logger=logging.getLogger("test"),
            librosa_module=None,
            pre_gain_db=0.0,
            post_gain_db=0.0,
            db_to_linear=_db_to_linear,
            normalizer_config=normalizer,
        )

    def test_finalize_loaded_audio_reduces_dc_when_enabled(self):
        loader = self._build_loader(
            sample_dc_block_enabled=True,
            sample_dc_block_cutoff_hz=20.0,
            sample_dc_block_min_mean_abs=1e-5,
        )
        t = np.linspace(0.0, 1.0, 1000, endpoint=False, dtype=np.float32)
        mono = (0.15 + 0.05 * np.sin(2.0 * np.pi * 5.0 * t)).astype(np.float32)
        audio = np.column_stack([mono, mono]).astype(np.float32)
        before = float(np.mean(audio[:, 0]))

        out = loader.finalize_loaded_audio(audio, sr=1000)
        after = float(np.mean(out[:, 0]))

        self.assertGreater(abs(before), 0.1)
        self.assertLess(abs(after), 0.02)

    def test_finalize_loaded_audio_keeps_dc_when_disabled(self):
        loader = self._build_loader(sample_dc_block_enabled=False)
        audio = np.ones((512, 2), dtype=np.float32) * 0.12
        before = float(np.mean(audio[:, 0]))

        out = loader.finalize_loaded_audio(audio, sr=1000)
        after = float(np.mean(out[:, 0]))

        self.assertLess(abs(after - before), 0.0035)

    def test_finalize_loaded_audio_skips_when_below_threshold(self):
        loader = self._build_loader(
            sample_dc_block_enabled=True,
            sample_dc_block_cutoff_hz=20.0,
            sample_dc_block_min_mean_abs=0.01,
        )
        audio = np.ones((512, 2), dtype=np.float32) * 0.003
        before = float(np.mean(audio[:, 0]))

        out = loader.finalize_loaded_audio(audio, sr=1000)
        after = float(np.mean(out[:, 0]))

        self.assertLess(abs(after - before), 1.2e-4)


if __name__ == "__main__":
    unittest.main()
