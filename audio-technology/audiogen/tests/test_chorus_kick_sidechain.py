import os
import tempfile
import unittest

import numpy as np

from audio.engine.chorus_kick_sidechain import (
    apply_chorus_kick_sidechain,
    clear_chorus_kick_sample_cache,
    duck_gain_from_kick,
    kick_four_four_from_one_shot,
    load_chorus_kick_one_shot_mono,
    parse_chorus_roles,
    resolve_chorus_kick_sample_path,
    should_apply_chorus_kick_sidechain,
    synthesize_kick_four_four,
)
from audio.RT_player.render_pipeline import RenderPipeline
from audiogen_core.mixer_config import ChorusKickSidechainConfig


def _test_sidechain_cfg() -> ChorusKickSidechainConfig:
    return ChorusKickSidechainConfig(
        enabled=True,
        roles=("b", "chorus", "hook", "tag"),
        beats_per_bar=4,
        kick_level_linear=0.4,
        kick_pulse_ms=12.0,
        attack_ms=1.0,
        release_ms=28.0,
        threshold_db=-32.0,
        max_depth=0.5,
        drone_channel=4,
        mixer_channel=6,
        sample_enabled=False,
        sample_path="samples/kick.wav",
        sample_max_ms=450.0,
    )


class ChorusKickSidechainTests(unittest.TestCase):
    def test_parse_chorus_roles(self):
        self.assertEqual(parse_chorus_roles("b, chorus ,hook"), {"b", "chorus", "hook"})
        self.assertEqual(parse_chorus_roles(("tag", "B")), {"tag", "b"})

    def test_should_apply_respects_role(self):
        sc = _test_sidechain_cfg()
        self.assertTrue(should_apply_chorus_kick_sidechain(arrangement_role="chorus", sidechain_cfg=sc))
        self.assertTrue(should_apply_chorus_kick_sidechain(arrangement_role="b", sidechain_cfg=sc))
        self.assertFalse(should_apply_chorus_kick_sidechain(arrangement_role="verse", sidechain_cfg=sc))
        self.assertFalse(should_apply_chorus_kick_sidechain(arrangement_role="", sidechain_cfg=sc))

    def test_should_apply_false_when_kick_and_sidechain_off(self):
        sc = _test_sidechain_cfg()
        sc.kick_enabled = False
        sc.sidechain_enabled = False
        self.assertFalse(should_apply_chorus_kick_sidechain(arrangement_role="chorus", sidechain_cfg=sc))

    def test_kick_off_does_not_write_kick_stem(self):
        sr = 2000
        n = 4000
        ch = RenderPipeline.create_channel_buffers(n)
        ch[0][:] = 0.5
        ch[4][:] = 0.7
        ch[6][:] = 0.0
        sc = _test_sidechain_cfg()
        sc.kick_enabled = False
        apply_chorus_kick_sidechain(ch, sample_rate=sr, bar_samples=n, sidechain_cfg=sc)
        self.assertLess(float(np.min(ch[0])), 0.48)
        self.assertLess(float(np.max(np.abs(ch[6]))), 1e-4)

    def test_sidechain_off_does_not_duck(self):
        sr = 2000
        n = 4000
        ch = RenderPipeline.create_channel_buffers(n)
        ch[0][:] = 0.5
        ch[4][:] = 0.7
        sc = _test_sidechain_cfg()
        sc.sidechain_enabled = False
        apply_chorus_kick_sidechain(ch, sample_rate=sr, bar_samples=n, sidechain_cfg=sc)
        self.assertGreater(float(np.min(ch[0])), 0.49)
        self.assertGreater(float(np.max(np.abs(ch[6]))), 1e-4)

    def test_kick_energy_in_each_quarter(self):
        sr = 8000
        n = int(round(4 * 60.0 / 120.0 * sr))
        k = synthesize_kick_four_four(n, sr, beats_per_bar=4, level=0.5, pulse_ms=10.0)
        self.assertEqual(k.shape, (n,))
        q = max(1, n // 4)
        for i in range(4):
            seg = k[int(i * q) : int(min(n, (i + 1) * q))]
            self.assertGreater(float(np.max(np.abs(seg))), 1e-4)

    def test_drone_channel_not_ducked(self):
        sr = 2000
        n = 4000
        ch = RenderPipeline.create_channel_buffers(n)
        ch[0][:] = 0.5
        ch[4][:] = 0.7
        apply_chorus_kick_sidechain(
            ch,
            sample_rate=sr,
            bar_samples=n,
            sidechain_cfg=_test_sidechain_cfg(),
        )
        self.assertLess(float(np.min(ch[0])), 0.48)
        self.assertGreater(float(np.min(ch[4])), 0.69)
        self.assertGreater(float(np.max(np.abs(ch[6]))), 1e-4)

    def test_load_wav_one_shot_and_four_on_floor(self):
        clear_chorus_kick_sample_cache()
        sr = 8000
        pulse = np.zeros(200, dtype=np.int16)
        pulse[:40] = 8000
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            from scipy.io import wavfile

            wavfile.write(path, sr, pulse)
            p = resolve_chorus_kick_sample_path(path)
            one = load_chorus_kick_one_shot_mono(p, sr, 500.0)
            self.assertIsNotNone(one)
            self.assertGreater(float(np.max(np.abs(np.asarray(one)))), 0.01)
            n = int(round(4 * 60.0 / 120.0 * sr))
            bar = kick_four_four_from_one_shot(one, n, beats_per_bar=4, level=0.9)
            q = max(1, n // 4)
            for i in range(4):
                seg = bar[int(i * q) : int(min(n, (i + 1) * q))]
                self.assertGreater(float(np.max(np.abs(seg))), 1e-5)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
            clear_chorus_kick_sample_cache()

    def test_duck_gain_curve_bounds(self):
        sr = 2000
        n = 2000
        k = synthesize_kick_four_four(n, sr, level=0.4)
        g = duck_gain_from_kick(
            k,
            sr,
            attack_ms=1.0,
            release_ms=35.0,
            threshold_db=-32.0,
            max_depth=0.6,
        )
        self.assertEqual(g.shape, (n,))
        self.assertTrue(np.all(g <= 1.01))
        self.assertTrue(np.all(g >= 0.05))


if __name__ == "__main__":
    unittest.main()
