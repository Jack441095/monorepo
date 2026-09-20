"""Regression tests for runtime player audit fixes."""

import unittest

import numpy as np

from audio.RT_player.drone_manager import DroneManager
from audio.RT_player.render_pipeline import RenderPipeline
from audiogen_core.mixer_config import AUDIO_MIXER_CHANNEL_COUNT
from tests.audiogen.test_player_runtime import PlayerRuntimeTests


class TestDroneManagerIntegrity(unittest.TestCase):
    def test_get_slice_does_not_mutate_shared_loop(self):
        loop = np.ones((200, 2), dtype=np.float32) * 0.5
        ref_peak = float(np.max(loop))
        dm = DroneManager(loop, sample_rate=44100, volume=0.25)
        _ = dm.get_slice(64)
        self.assertTrue(np.allclose(loop, 0.5))
        self.assertEqual(float(np.max(loop)), ref_peak)


class TestRenderPipelineDroneMix(unittest.TestCase):
    def test_apply_drone_adds_to_existing_channel_four(self):
        bar_samples = 8
        ch_audio = {
            ch: np.zeros((bar_samples, 2), dtype=np.float32)
            for ch in range(int(AUDIO_MIXER_CHANNEL_COUNT))
        }
        ch_audio[4][:] = 0.2
        drone = np.full((bar_samples, 2), 0.1, dtype=np.float32)
        RenderPipeline.apply_drone_and_velocity(ch_audio, drone, bar_samples, 1.0)
        self.assertTrue(np.allclose(ch_audio[4], 0.3))


class TestMasterInsertBypassFlags(PlayerRuntimeTests):
    def test_master_insert_bypass_flags_do_not_recurse(self):
        player = self._make_player()
        for mode in ("normal", "balanced", "safe", "emergency"):
            player._should_bypass_master_multiband(mode)
            player._should_bypass_master_eq(mode)
            player._should_bypass_master_inserts(mode)


class TestRuntimeModeLadder(PlayerRuntimeTests):
    def test_no_emergency_when_buffer_empty_before_warmup(self):
        player = self._make_player()
        player.load_emotion(0, 60)
        player._playing = False
        player.chunks_generated = 0
        player.last_bar_render_time = 0.1
        player.max_bar_render_time = 0.1

        player._advance_runtime_mode_ladder()

        self.assertFalse(bool(getattr(player, "_emergency_active", False)))
        self.assertNotEqual(player._runtime_generation_mode(), "emergency")

    def test_emergency_can_engage_after_warmup_with_slow_render(self):
        player = self._make_player()
        player.load_emotion(0, 60)
        player._playing = True
        player.chunks_generated = 2
        player.last_bar_render_time = 20.0
        player.max_bar_render_time = 20.0
        player.buffer.clear()

        player._advance_runtime_mode_ladder()

        self.assertTrue(player._emergency_active)

    def test_section_compose_does_not_inflate_bar_render_max(self):
        player = self._make_player()
        player._record_bar_render_timing(0.5)
        player.record_section_compose_time(30.0)

        self.assertLess(player.max_bar_render_time, 2.0)
        self.assertEqual(player.last_section_compose_time, 30.0)

    def test_callback_underflow_does_not_increment_ring_underruns(self):
        player = self._make_player()
        from tests.audiogen.test_player_runtime import FakeStatus

        n0 = player.telemetry.buffer_underruns
        player._log_stream_status(FakeStatus(output_underflow=True, priming_output=False))
        self.assertGreater(player.telemetry.callback_underflows, 0)
        self.assertEqual(player.telemetry.buffer_underruns, n0)


if __name__ == "__main__":
    unittest.main()
