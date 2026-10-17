"""LUFS analyzer + loudness-target convergence (docs/AUDIOGEN_COMPOSITION_PLAN.md,
auto-mixer work 2026-07-05).

Nothing computed real LUFS before this (composition/song_rerank_model.py reads an
"integrated_lufs" dict key that nothing ever populated, always defaulting to -18.0).
audio/engine/lufs.py is a from-scratch ITU-R BS.1770-4 implementation; these tests pin its
core correctness (relative level math is exact regardless of the absolute calibration
constant) plus the master-bus target-trim control loop that uses it to converge real
generated audio toward -14 LUFS.
"""
import unittest

import numpy as np


def _sine(amp, freq, seconds, sr):
    t = np.arange(int(seconds * sr)) / sr
    mono = amp * np.sin(2 * np.pi * freq * t)
    return np.stack([mono, mono], axis=1).astype(np.float32)


class TestIntegratedLufs(unittest.TestCase):
    def test_halving_amplitude_drops_exactly_6db(self):
        """The core relative-level property: -6.0206dB is exact regardless of the absolute
        BS.1770 calibration constant, so this doesn't depend on memorizing a reference value."""
        from audio.engine.lufs import integrated_lufs

        sr = 44100
        full = _sine(0.5, 1000.0, 2.0, sr)
        half = _sine(0.25, 1000.0, 2.0, sr)
        l_full = integrated_lufs(full, sr)
        l_half = integrated_lufs(half, sr)
        self.assertAlmostEqual(l_half - l_full, -6.0206, places=2)

    def test_silence_is_negative_infinity(self):
        from audio.engine.lufs import integrated_lufs

        silence = np.zeros((44100, 2), dtype=np.float32)
        self.assertEqual(integrated_lufs(silence, 44100), -np.inf)

    def test_absolute_gate_excludes_near_silent_tail(self):
        """A loud section followed by a near-silent tail should read close to the loud
        section's level, not be dragged down by the gated-out quiet tail."""
        from audio.engine.lufs import integrated_lufs

        sr = 44100
        loud = _sine(0.3, 1000.0, 3.0, sr)
        quiet = _sine(1e-6, 1000.0, 3.0, sr)
        combined = np.concatenate([loud, quiet], axis=0)
        l_loud_only = integrated_lufs(loud, sr)
        l_combined = integrated_lufs(combined, sr)
        self.assertAlmostEqual(l_combined, l_loud_only, delta=0.5)


class TestRollingKWeightedLoudness(unittest.TestCase):
    def test_converges_to_integrated_value_for_steady_signal(self):
        from audio.engine.lufs import RollingKWeightedLoudness, integrated_lufs

        sr = 44100
        sig = _sine(0.3, 1000.0, 4.0, sr)
        target = integrated_lufs(sig, sr)

        roller = RollingKWeightedLoudness(sr, ema_alpha=0.3)
        block = 4410
        last = None
        for i in range(0, len(sig), block):
            last = roller.process(sig[i:i + block])
        self.assertAlmostEqual(last, target, delta=0.2)

    def test_reset_clears_state(self):
        from audio.engine.lufs import RollingKWeightedLoudness

        roller = RollingKWeightedLoudness(44100)
        roller.process(_sine(0.3, 1000.0, 1.0, 44100))
        self.assertTrue(roller._warm)
        roller.reset()
        self.assertFalse(roller._warm)


class TestMasterBusLoudnessTarget(unittest.TestCase):
    """Guards the specific bug found and fixed 2026-07-05: the target-trim correction is
    measured fresh from the RAW signal every block (not accumulated), so a clamp smaller
    than the actual gap to target never fully converges -- it applies the same small
    correction forever. These tests pin that a large persistent gap DOES fully close."""

    def _make_bus(self, target_db=-14.0, max_change_db=24.0):
        from audio.engine.master_bus import MasterBus, MasterBusSettings

        settings = MasterBusSettings(
            target_enabled=True, target_rms_db=target_db,
            target_max_change_db=max_change_db, target_ema_alpha=0.3,
        )
        mb = MasterBus(44100, settings)
        mb.master_target_use_k_weighting = True
        return mb

    def test_large_gap_converges_with_sufficient_clamp(self):
        from audio.engine.lufs import integrated_lufs

        mb = self._make_bus(target_db=-14.0, max_change_db=24.0)
        quiet = _sine(0.01, 300.0, 4.0, 44100)  # ~-35 LUFS-ish, matches the measured regression
        out = None
        for _ in range(8):
            out = mb.process(quiet.copy())
        self.assertAlmostEqual(integrated_lufs(out, 44100), -14.0, delta=3.0)

    def test_insufficient_clamp_does_not_converge(self):
        """Regression guard for the exact bug: a clamp much smaller than the gap should NOT
        reach target even after many blocks (confirms the mechanism is memoryless, so
        anyone re-lowering the clamp will see this test fail as an early warning)."""
        from audio.engine.lufs import integrated_lufs

        mb = self._make_bus(target_db=-14.0, max_change_db=1.5)
        quiet = _sine(0.01, 300.0, 4.0, 44100)
        out = None
        for _ in range(20):
            out = mb.process(quiet.copy())
        final_lufs = integrated_lufs(out, 44100)
        self.assertLess(final_lufs, -20.0, "small clamp should not fully close a large gap")

    def test_no_clipping_after_convergence(self):
        mb = self._make_bus()
        quiet = _sine(0.01, 300.0, 4.0, 44100)
        out = None
        for _ in range(10):
            out = mb.process(quiet.copy())
        self.assertLessEqual(float(np.max(np.abs(out))), 1.0 + 1e-6)


class TestKWeightingPerformance(unittest.TestCase):
    """Regression guard for the exact bug found 2026-07-05: a pure-Python per-sample biquad
    loop measured ~220ms of overhead per 4s bar (~7x realtime overhead) -- the same class of
    "100x slower pure-Python DSP" pitfall this project already hit once with numba/numpy
    (see docs/AUDIOGEN_COMPOSITION_PLAN.md). Fixed via scipy.signal.lfilter (vectorized C
    loop): overhead dropped to ~10ms. This fails loudly if the fast path regresses."""

    def test_k_weighting_is_vectorized_not_pure_python_loop(self):
        import time

        from audio.engine.lufs import apply_k_weighting

        sr = 44100
        n = int(sr * 4.0)
        rng = np.random.default_rng(0)
        mono = (rng.random(n).astype(np.float64) - 0.5) * 0.3

        t0 = time.perf_counter()
        apply_k_weighting(mono, sr)
        dt = time.perf_counter() - t0
        self.assertLess(
            dt, 0.05,
            f"K-weighting a 4s block took {dt*1000:.1f}ms -- should be a few ms via "
            f"scipy.signal.lfilter, not ~50ms+ (pure-Python per-sample loop regression)",
        )


class TestConfigDefaults(unittest.TestCase):
    def test_target_is_minus_14_lufs_k_weighted(self):
        from audiogen_core.config import CONFIG

        self.assertEqual(CONFIG.audio.master_target_rms_db, -14.0)
        self.assertTrue(CONFIG.audio.master_target_use_k_weighting)
        self.assertTrue(CONFIG.audio.master_target_enabled)
        self.assertGreaterEqual(CONFIG.audio.master_target_max_change_db, 20.0)


if __name__ == "__main__":
    unittest.main()
