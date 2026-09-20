"""Auto-mixer / mastering-chain work (docs/AUDIOGEN_COMPOSITION_PLAN.md, 2026-07-04).

Covers three additions:
  1. Per-emotion auto-mix bias (data/auto_mix_profiles.py) -- subtle reverb/EQ variation
     derived from existing emotion knobs (brightness/tempo/density), never the frozen
     "everything sounds identical" behavior this session started with.
  2. The previously dead `emotion_auto_mix_enabled` / mastering-chain config flags are now
     load-bearing (soft-clip, loudness target, stereo width).
  3. Master-bus stereo width DSP stage.
"""
import unittest

import numpy as np


class TestAutoMixBias(unittest.TestCase):
    def test_bias_is_subtle(self):
        from data.auto_mix_profiles import auto_mix_bias_for_emotion
        from data.music_data import EMOTIONS

        for e in EMOTIONS:
            b = auto_mix_bias_for_emotion(e)
            self.assertLessEqual(abs(b.reverb_wet_delta), 0.08 + 1e-9)
            self.assertLessEqual(abs(b.eq_low_shelf_delta_db), 1.2 + 1e-9)
            self.assertLessEqual(abs(b.eq_high_shelf_delta_db), 1.2 + 1e-9)

    def test_bright_emotion_gets_high_shelf_lift(self):
        from data.auto_mix_profiles import auto_mix_bias_for_emotion
        from data.music_data import EMOTION_BY_NAME

        bright = auto_mix_bias_for_emotion(EMOTION_BY_NAME["excitement"])
        dark = auto_mix_bias_for_emotion(EMOTION_BY_NAME["grief"])
        self.assertGreater(bright.eq_high_shelf_delta_db, dark.eq_high_shelf_delta_db)

    def test_varies_across_emotions(self):
        """The whole point: this must NOT be a constant (that would repeat the frozen-key bug
        in a new location)."""
        from data.auto_mix_profiles import auto_mix_bias_for_emotion
        from data.music_data import EMOTIONS

        deltas = {round(auto_mix_bias_for_emotion(e).reverb_wet_delta, 4) for e in EMOTIONS}
        self.assertGreater(len(deltas), 5)

    def test_missing_attrs_default_safely(self):
        import types

        from data.auto_mix_profiles import auto_mix_bias_for_emotion

        bare = types.SimpleNamespace(name="nonexistent_emotion")
        b = auto_mix_bias_for_emotion(bare)
        self.assertEqual(b.reverb_wet_delta, b.reverb_wet_delta)  # no NaN/crash


class TestMasterBusStereoWidth(unittest.TestCase):
    def _make_bus(self):
        from audio.engine.master_bus import MasterBus, MasterBusSettings

        return MasterBus(44100, MasterBusSettings())

    def test_unity_width_is_default_and_inert(self):
        mb = self._make_bus()
        self.assertFalse(mb.master_stereo_width_enabled)
        self.assertEqual(mb.master_stereo_width, 1.0)

    def test_width_changes_output_when_enabled(self):
        mb = self._make_bus()
        rng = np.random.default_rng(0)
        dry = (rng.random((256, 2)).astype(np.float32) - 0.5) * 0.3

        mb.master_stereo_width_enabled = False
        out_off = mb.process(dry.copy())

        mb2 = self._make_bus()
        mb2.master_stereo_width_enabled = True
        mb2.master_stereo_width = 1.5
        out_on = mb2.process(dry.copy())

        self.assertFalse(np.allclose(out_off, out_on))
        self.assertFalse(np.any(np.isnan(out_on)))

    def test_width_preserves_mono_content(self):
        """Mid-only (L==R) content should be unchanged by width (side is zero)."""
        mb = self._make_bus()
        mb.master_stereo_width_enabled = True
        mb.master_stereo_width = 1.8
        mono = np.full((256, 2), 0.1, dtype=np.float32)
        out = mb.process(mono)
        self.assertTrue(np.allclose(out[:, 0], out[:, 1], atol=1e-5))


class TestMasteringChainDefaults(unittest.TestCase):
    def test_previously_dormant_flags_now_enabled(self):
        from audiogen_core.config import CONFIG

        self.assertTrue(CONFIG.audio.master_soft_clip)
        self.assertTrue(CONFIG.audio.master_target_enabled)
        self.assertTrue(CONFIG.audio.emotion_auto_mix_enabled)

    def test_stereo_width_ships_disabled(self):
        from audiogen_core.config import CONFIG

        self.assertFalse(CONFIG.audio.master_stereo_width_enabled)


if __name__ == "__main__":
    unittest.main()
