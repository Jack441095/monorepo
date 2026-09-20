"""Spatial effects module for automated mixdown system.

Implements:
  1. Schroeder-Moorer Reverb — Fast minimum-phase reverb using cascaded biquads
     and low-pass feedback comb filters implemented with scipy.signal.lfilter.
  2. Stereo/Ping-Pong Delay — Feedback delay lines, optionally synced to tempo.
"""

from __future__ import annotations

import numpy as np
from . import native as _native

try:
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

# The Schroeder comb/allpass filters are feedback DELAY LINES (a tap at n-d), not
# high-order IIRs. Implementing them as scipy.lfilter with a length-d denominator
# is O(N*d) per filter -- profiling showed this reverb at ~63% of a whole AutoMix
# render (a delay of ~1500 samples => a 1500-order lfilter over the full signal).
# These O(N) delay-line kernels compute the identical recurrence; numba-JIT'd like
# the dynamics.py envelope loops, with a numpy-friendly pure-Python fallback.
try:  # pragma: no cover
    import numba as _nb  # type: ignore[import]
except Exception:  # pragma: no cover
    _nb = None


def _lbcf_comb_py(x, d, g, damping):
    """Low-pass feedback comb: y[n] = x[n-d] + g*((1-damping)*y[n-d] + damping*y[n-d-1]).
    Identical recurrence to lfilter(b, a, x) with a[d]=-g(1-damping), a[d+1]=-g*damping, b[d]=1."""
    n = x.shape[0]
    y = np.zeros(n, dtype=np.float64)
    g1 = g * (1.0 - damping)
    g2 = g * damping
    for i in range(n):
        acc = 0.0
        if i >= d:
            acc = x[i - d] + g1 * y[i - d]
            if i >= d + 1:
                acc += g2 * y[i - d - 1]
        y[i] = acc
    return y


def _allpass_py(x, d, g):
    """All-pass: y[n] = -g*x[n] + x[n-d] + g*y[n-d]. Identical recurrence to
    lfilter(b, a, x) with a[d]=-g, b[0]=-g, b[d]=1."""
    n = x.shape[0]
    y = np.zeros(n, dtype=np.float64)
    for i in range(n):
        acc = -g * x[i]
        if i >= d:
            acc += x[i - d] + g * y[i - d]
        y[i] = acc
    return y


def _lbcf_comb(x, d: int, g: float, damping: float) -> np.ndarray:
    try:
        from .native import native_lbcf_comb_filter, is_reverb_available
        if is_reverb_available():
            return native_lbcf_comb_filter(x, d, g, damping)
    except Exception:
        pass
    if _nb is not None:
        return _lbcf_comb_py_nb(x, d, g, damping)
    return _lbcf_comb_py(x, d, g, damping)


def _allpass(x, d: int, g: float) -> np.ndarray:
    try:
        from .native import native_allpass_filter, is_reverb_available
        if is_reverb_available():
            return native_allpass_filter(x, d, g)
    except Exception:
        pass
    if _nb is not None:
        return _allpass_py_nb(x, d, g)
    return _allpass_py(x, d, g)


if _nb is not None:  # pragma: no cover
    _lbcf_comb_py_nb = _nb.njit(cache=True)(_lbcf_comb_py)
    _allpass_py_nb = _nb.njit(cache=True)(_allpass_py)


class Reverb:
    """Schroeder-Moorer algorithmic reverb using LBCF and All-Pass filters."""

    def __init__(
        self,
        sample_rate: int = 44100,
        pre_delay_ms: float = 20.0,
        room_size: float = 0.5,      # Scales delay line lengths
        decay_time: float = 1.5,      # RT60 decay time in seconds
        damping: float = 0.3,         # High frequency damping
        wet_dry: float = 0.15,        # 0.0 (fully dry) to 1.0 (fully wet)
    ):
        self.sample_rate = sample_rate
        self.pre_delay_ms = pre_delay_ms
        self.room_size = room_size
        self.decay_time = decay_time
        self.damping = damping
        self.wet_dry = wet_dry

    def apply(
        self,
        left: np.ndarray | list[float],
        right: np.ndarray | list[float] | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Apply reverb to mono or stereo signals.

        Returns (stereo_l, stereo_r) pair.
        """
        x_l = np.asarray(left, dtype=np.float64)
        if right is None:
            x_r = x_l.copy()
        else:
            x_r = np.asarray(right, dtype=np.float64)

        if len(x_l) == 0:
            return x_l, x_r

        fs = float(self.sample_rate)
        pre_samples = int(fs * (self.pre_delay_ms / 1000.0))

        if _native is not None:
            try:
                if getattr(_native, "is_reverb_full_available", lambda: False)():
                    return _native.native_schroeder_reverb(
                        x_l, x_r, pre_samples, self.room_size, self.decay_time,
                        self.damping, self.wet_dry, fs
                    )
            except Exception:
                pass

        # 1. Pre-delay
        if pre_samples > 0:
            x_l_delayed = np.pad(x_l, (pre_samples, 0))[:-pre_samples]
            x_r_delayed = np.pad(x_r, (pre_samples, 0))[:-pre_samples]
        else:
            x_l_delayed = x_l
            x_r_delayed = x_r

        # Mix to mono for reverb input
        mono_input = 0.5 * (x_l_delayed + x_r_delayed)

        # 2. Schroeder-Moorer Structure
        # Prime delay numbers scaled by room size
        scale = 0.5 + self.room_size * 1.5
        comb_delays = [int(1116 * scale), int(1188 * scale), int(1277 * scale), int(1356 * scale)]
        ap_delays = [int(225 * scale), int(341 * scale)]

        # Decay gain (g) from RT60
        # RT60 is time for level to drop by 60 dB (10^-3 amplitude)
        # For a delay line of D samples, feedback gain g is:
        # g = 10 ** (-3 * D / (decay_time * fs))
        combs_out = np.zeros_like(mono_input)

        # Low-pass feedback comb filters (LBCF) run in parallel. O(N) delay-line
        # kernels -- NOT lfilter with a length-d denominator (that was O(N*d)).
        for d in comb_delays:
            if d >= len(mono_input):
                continue
            g = 10.0 ** (-3.0 * d / (max(0.1, self.decay_time) * fs))
            combs_out += _lbcf_comb(mono_input, d, g, self.damping)

        # Divide by number of combs to prevent clipping
        combs_out = combs_out / 4.0

        # All-pass filters run in series
        ap_out = combs_out
        for d in ap_delays:
            if d >= len(ap_out):
                continue
            g_ap = 0.7
            ap_out = _allpass(ap_out, d, g_ap)

        # 3. Create Stereo Spread (different delay offsets for left and right)
        # Delay left by 23ms, right by 29ms to create spatial width
        delay_l = int(fs * 0.023)
        delay_r = int(fs * 0.029)

        wet_l = np.pad(ap_out, (delay_l, 0))[:-delay_l] if delay_l < len(ap_out) else ap_out
        wet_r = np.pad(ap_out, (delay_r, 0))[:-delay_r] if delay_r < len(ap_out) else ap_out

        # 4. Wet/Dry Blend
        out_l = (1.0 - self.wet_dry) * x_l + self.wet_dry * wet_l
        out_r = (1.0 - self.wet_dry) * x_r + self.wet_dry * wet_r

        return out_l, out_r


class Delay:
    """Stereo delay with feedback and ping-pong routing."""

    def __init__(
        self,
        sample_rate: int = 44100,
        delay_time_ms: float = 250.0,
        feedback: float = 0.3,
        ping_pong: bool = False,
        wet_dry: float = 0.2,
        bpm: float | None = None,
        sync_division: float | None = None,  # e.g., 0.25 for quarter note
    ):
        self.sample_rate = sample_rate
        self.delay_time_ms = delay_time_ms
        self.feedback = max(0.0, min(feedback, 0.95))
        self.ping_pong = ping_pong
        self.wet_dry = wet_dry
        self.bpm = bpm
        self.sync_division = sync_division

    def apply(
        self,
        left: np.ndarray | list[float],
        right: np.ndarray | list[float] | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Apply delay to mono or stereo signals."""
        x_l = np.asarray(left, dtype=np.float64)
        if right is None:
            x_r = x_l.copy()
        else:
            x_r = np.asarray(right, dtype=np.float64)

        if len(x_l) == 0:
            return x_l, x_r

        fs = float(self.sample_rate)

        # 1. Determine delay time in samples
        if self.bpm is not None and self.sync_division is not None:
            # Quarter note duration in seconds = 60 / BPM
            beat_duration = 60.0 / self.bpm
            delay_seconds = beat_duration * self.sync_division * 4.0  # sync_division is fraction of a bar
            delay_samples = int(fs * delay_seconds)
        else:
            delay_samples = int(fs * (self.delay_time_ms / 1000.0))

        delay_samples = max(1, min(delay_samples, len(x_l) // 2))

        # 2. Delay Buffer Processing
        n = len(x_l)
        wet_l = np.zeros(n)
        wet_r = np.zeros(n)

        # Process block-by-block of size delay_samples to keep feedback vectorized
        d = delay_samples
        fb = self.feedback

        if self.ping_pong:
            # Ping-Pong: Left delay feeds back to Right, and Right delay to Left
            for start in range(0, n, d):
                end = min(start + d, n)
                chunk_len = end - start
                
                # Feedback contribution from previous block
                if start >= d:
                    wet_l[start:end] = x_l[start:end] + fb * wet_r[start-d : start-d + chunk_len]
                    wet_r[start:end] = x_r[start:end] + fb * wet_l[start-d : start-d + chunk_len]
                else:
                    wet_l[start:end] = x_l[start:end]
                    wet_r[start:end] = x_r[start:end]
            
            # Shift wet signals by delay_samples
            wet_l_shifted = np.pad(wet_l, (d, 0))[:-d]
            wet_r_shifted = np.pad(wet_r, (d, 0))[:-d]
        else:
            # Standard Stereo Delay
            for start in range(0, n, d):
                end = min(start + d, n)
                chunk_len = end - start
                
                if start >= d:
                    wet_l[start:end] = x_l[start:end] + fb * wet_l[start-d : start-d + chunk_len]
                    wet_r[start:end] = x_r[start:end] + fb * wet_r[start-d : start-d + chunk_len]
                else:
                    wet_l[start:end] = x_l[start:end]
                    wet_r[start:end] = x_r[start:end]
            
            wet_l_shifted = np.pad(wet_l, (d, 0))[:-d]
            wet_r_shifted = np.pad(wet_r, (d, 0))[:-d]

        # 3. Wet/Dry Blend
        out_l = (1.0 - self.wet_dry) * x_l + self.wet_dry * wet_l_shifted
        out_r = (1.0 - self.wet_dry) * x_r + self.wet_dry * wet_r_shifted

        return out_l, out_r
