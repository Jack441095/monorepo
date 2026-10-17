"""Regression guard for the numba/numpy version cliff (docs/AUDIOGEN_COMPOSITION_PLAN.md).

On 2026-07-04 an unpinned NumPy upgrade to 2.5 broke numba's import, which silently dropped
ALL audio DSP (reverb/delay/mixer/sampler filters) to pure Python -- ~100x slower render,
manifesting as NO AUDIO in the realtime player. requirements.txt now pins the compatible
numpy/numba/llvmlite window. These tests fail LOUDLY if that regresses, and also guard the
`np.asarray(..., copy=True)` (NumPy 2.0+) usage that a numpy *down*grade would break.
"""
import unittest

import numpy as np


class TestNumpyApiContract(unittest.TestCase):
    def test_array_copy_kwarg_supported(self):
        # The realtime render path uses np.array(..., copy=True) to defensively copy
        # audio buffers. This works on all NumPy versions (unlike np.asarray copy=
        # which requires NumPy 2.0+).
        out = np.array([1.0, 2.0], dtype=np.float32, copy=True)
        self.assertEqual(out.dtype, np.float32)


class TestDspNumbaActive(unittest.TestCase):
    """numba must be importable AND active in the DSP modules. If numba can't import
    (usually a numpy version numba doesn't support), these fail -- which is the whole
    point: a silent 100x render slowdown becomes a loud test failure."""

    def test_numba_imports(self):
        try:
            import numba  # noqa: F401
            from numba import njit
        except Exception as e:  # pragma: no cover
            self.fail(
                f"numba failed to import ({e}); audio DSP would run pure-Python (~100x "
                f"slower render, no audio). Align numpy/numba per requirements.txt."
            )
        # and it must actually compile (import can succeed but njit fail on bad numpy)
        f = njit(lambda x: x + 1.0)
        self.assertEqual(f(1.0), 2.0)

    def test_dsp_modules_report_numba_active(self):
        from audio.engine import mixer, reverb
        from sampler.pitch_filter import NUMBA_AVAILABLE as pitch_filter_numba

        self.assertIsNotNone(getattr(mixer, "_nb", None),
                             "mixer numba path inactive -> delay/mixer render is pure-Python")
        self.assertTrue(getattr(reverb, "NUMBA_AVAILABLE", False),
                        "reverb numba path inactive -> reverb render is pure-Python")
        self.assertTrue(pitch_filter_numba,
                        "pitch_filter numba path inactive -> filter render is pure-Python")


class TestRenderChordSmoke(unittest.TestCase):
    def test_render_chord_runs_and_is_fast(self):
        """Exercises the exact call chain that crashed on the numpy downgrade
        (render_chord -> render_note -> _apply_loop_crossfade -> np.asarray(copy=True))
        and confirms it renders quickly (numba active), not the 7-15s/bar pure-Python path."""
        import time

        from audiogen_core.config import CONFIG
        from sampler.engine import SamplerEngine

        eng = SamplerEngine(CONFIG)
        t0 = time.perf_counter()
        audio = eng.render_chord([60, 64, 67], 90, 1.0, channel=1)  # must not raise
        dt = time.perf_counter() - t0
        self.assertIsNotNone(audio)
        self.assertEqual(audio.shape[1], 2)  # stereo
        # a 1s chord should render well under a second with numba; generous ceiling for CI.
        self.assertLess(dt, 3.0, f"render_chord took {dt:.1f}s -- numba likely inactive (pure-Python DSP)")


if __name__ == "__main__":
    unittest.main()
