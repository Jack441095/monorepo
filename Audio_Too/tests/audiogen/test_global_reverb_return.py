import unittest

import numpy as np


class GlobalReverbReturnTests(unittest.TestCase):
    def test_reverb_defaults_to_long_global_return(self):
        from audiogen_core.config import ConfigurationManager

        cfg = ConfigurationManager()
        self.assertTrue(bool(cfg.audio.reverb_enabled))
        self.assertAlmostEqual(float(cfg.audio.reverb_rt60), 20.8)
        self.assertAlmostEqual(float(cfg.audio.reverb_return_highpass_hz), 500.0)
        self.assertAlmostEqual(float(cfg.audio.reverb_return_highpass_slope_db_per_oct), 12.0)

    def test_return_highpass_removes_low_frequency_tail_energy(self):
        from audio.engine.reverb import RoomReverb

        sr = 8000
        n = sr * 2
        dc = np.ones((n, 2), dtype=np.float32) * 0.5
        wet_full = RoomReverb(sample_rate=sr, rt60=10.0, wet=1.0, highpass_hz=0.0).process(dc, wet=1.0)
        wet_hp = RoomReverb(sample_rate=sr, rt60=10.0, wet=1.0, highpass_hz=500.0).process(dc, wet=1.0)

        tail = slice(sr, None)
        rms_full = float(np.sqrt(np.mean(np.square(wet_full[tail]))))
        rms_hp = float(np.sqrt(np.mean(np.square(wet_hp[tail]))))
        self.assertLess(rms_hp, rms_full * 0.35)

    def test_audio_container_applies_reverb_highpass_config(self):
        from audio.audio_container import AudioContainer
        from audiogen_core.config import ConfigurationManager

        cfg = ConfigurationManager()
        cfg.audio.sample_rate = 8000
        cfg.audio.reverb_return_highpass_hz = 650.0
        cfg.audio.reverb_return_highpass_slope_db_per_oct = 12.0

        container = AudioContainer.create_from_config(cfg)
        self.assertAlmostEqual(float(container.reverb.highpass_hz), 650.0)
        self.assertAlmostEqual(float(container.reverb.highpass_slope_db_per_oct), 12.0)


if __name__ == "__main__":
    unittest.main()
