"""Dynamics processor module for automated mixdown system.

Implements:
  1. Compressor — Feed-forward compressor with soft/hard knee, RMS/Peak detection,
     and sidechain high-pass filter option.
  2. Limiter — Brickwall look-ahead limiter with optional true-peak (4x oversampled) detection.
  3. Gate — Noise gate with adjustable threshold, attack, hold, release, and range.
All processing runs offline using numpy and scipy.
"""

from __future__ import annotations

import math
import numpy as np
import scipy.signal as sig

try:
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

# Optional JIT acceleration for the per-sample envelope-follower loops below
# (Compressor/Limiter/Gate). Each has a state-dependent attack/release
# coefficient switch per sample, so it can't be expressed as a fixed-
# coefficient scipy.signal.lfilter -- a plain Python for-loop is the only
# numpy-only option, and it is the dominant cost of every render (the
# closed-loop gain solve in mix_renderer.py invokes the limiter alone
# 8-10+ times per render). Same optional-numba/pure-Python-fallback pattern
# already used in studio/audiogen/audiogen/audio/engine/mixer.py. No
# fastmath here (unlike that file) -- these loops feed LUFS/true-peak
# measurements the test suite checks to the millidecibel, so exact IEEE754
# semantics matter more than the extra speed fastmath would buy.
try:  # pragma: no cover
    import numba as _nb  # type: ignore[import]
except Exception:  # pragma: no cover
    _nb = None

# Optional C++ kernel for the Limiter's peak-follower + target-gain +
# release-smoothing sequence (dsp_engine/native/limiter_kernel.cpp). Verified
# bit-identical to the scipy/numba path immediately below across 200+ fuzz
# trials spanning both native-rate and 4x-oversampled (true_peak) lookahead
# window sizes, plus edge cases (empty, L > n, all-silence, heavy clipping) --
# see tests/audio_analysis/test_native_limiter.py. Falls back to the Python
# path below when no C++ compiler is available, same pattern as numba above.
from . import native as _native

# 10**(x/20) == exp(x * _LN10_OVER_20) -- numpy's array pow() is a general
# pow() (handles arbitrary/negative/fractional exponents); exp() is a
# dedicated fast path, ~3-4x faster on full-track gain envelopes. Differs
# from ** by ~1e-16 relative (float64 ULP noise), far below the 24-bit
# dither floor (~1e-7) and the golden-metrics regression guard's 1e-9 abs
# tolerance.
_LN10_OVER_20 = math.log(10.0) / 20.0


def _have_numba() -> bool:
    return _nb is not None


def _smooth_attack_release_py(values: np.ndarray, alpha_att: float, alpha_rel: float, init: float, attack_when_less: bool) -> np.ndarray:
    """Pure-Python fallback: state-dependent one-pole smoothing, attacking
    when the target is more restrictive (smaller) than the current value,
    releasing otherwise."""
    n = values.shape[0]
    out = np.empty(n, dtype=np.float64)
    current = init
    for i in range(n):
        target = values[i]
        attacking = (target < current) if attack_when_less else (target <= current)
        if attacking:
            current = alpha_att * current + (1.0 - alpha_att) * target
        else:
            current = alpha_rel * current + (1.0 - alpha_rel) * target
        out[i] = current
    return out


if _nb is not None:  # pragma: no cover
    @_nb.njit(cache=True)
    def _smooth_attack_release_nb(values, alpha_att, alpha_rel, init, attack_when_less):
        n = values.shape[0]
        out = np.empty(n, dtype=np.float64)
        current = init
        for i in range(n):
            target = values[i]
            attacking = (target < current) if attack_when_less else (target <= current)
            if attacking:
                current = alpha_att * current + (1.0 - alpha_att) * target
            else:
                current = alpha_rel * current + (1.0 - alpha_rel) * target
            out[i] = current
        return out


def _smooth_attack_release(values: np.ndarray, alpha_att: float, alpha_rel: float, init: float, attack_when_less: bool) -> np.ndarray:
    if _native is not None:
        try:
            if getattr(_native, "is_smooth_envelope_available", lambda: False)():
                return _native.native_smooth_attack_release(values, alpha_att, alpha_rel, init, attack_when_less)
        except Exception:
            pass
    if _nb is not None:
        return _smooth_attack_release_nb(values, alpha_att, alpha_rel, init, attack_when_less)
    return _smooth_attack_release_py(values, alpha_att, alpha_rel, init, attack_when_less)


def _gate_envelope(level_db: np.ndarray, threshold: float, alpha_att: float, alpha_rel: float, hold_samples: int, target_gain_open: float, target_gain_closed: float) -> np.ndarray:
    try:
        if _native.is_smooth_envelope_available():
            return _native.native_gate_envelope(level_db, threshold, alpha_att, alpha_rel, hold_samples, target_gain_open, target_gain_closed)
    except Exception:
        pass
    if _nb is not None:
        return _gate_envelope_nb(level_db, threshold, alpha_att, alpha_rel, hold_samples, target_gain_open, target_gain_closed)
    return _gate_envelope_py(level_db, threshold, alpha_att, alpha_rel, hold_samples, target_gain_open, target_gain_closed)


def _gate_envelope_py(level_db: np.ndarray, threshold: float, alpha_att: float, alpha_rel: float, hold_samples: int, target_gain_open: float, target_gain_closed: float) -> np.ndarray:
    n = level_db.shape[0]
    g_out = np.empty(n, dtype=np.float64)
    gate_open = False
    hold_counter = 0
    current_gain = target_gain_closed
    for i in range(n):
        level = level_db[i]
        if level > threshold:
            gate_open = True
            hold_counter = hold_samples
        else:
            if hold_counter > 0:
                hold_counter -= 1
            else:
                gate_open = False
        target = target_gain_open if gate_open else target_gain_closed
        if target > current_gain:
            current_gain = alpha_att * current_gain + (1.0 - alpha_att) * target
        else:
            current_gain = alpha_rel * current_gain + (1.0 - alpha_rel) * target
        g_out[i] = current_gain
    return g_out


if _nb is not None:  # pragma: no cover
    @_nb.njit(cache=True)
    def _gate_envelope_nb(level_db, threshold, alpha_att, alpha_rel, hold_samples, target_gain_open, target_gain_closed):
        n = level_db.shape[0]
        g_out = np.empty(n, dtype=np.float64)
        gate_open = False
        hold_counter = 0
        current_gain = target_gain_closed
        for i in range(n):
            level = level_db[i]
            if level > threshold:
                gate_open = True
                hold_counter = hold_samples
            else:
                if hold_counter > 0:
                    hold_counter -= 1
                else:
                    gate_open = False
            target = target_gain_open if gate_open else target_gain_closed
            if target > current_gain:
                current_gain = alpha_att * current_gain + (1.0 - alpha_att) * target
            else:
                current_gain = alpha_rel * current_gain + (1.0 - alpha_rel) * target
            g_out[i] = current_gain
        return g_out


class Compressor:
    """Feed-forward compressor with envelope smoothing in the log domain."""

    def __init__(
        self,
        sample_rate: int = 44100,
        threshold_db: float = -20.0,
        ratio: float = 4.0,
        attack_ms: float = 10.0,
        release_ms: float = 100.0,
        knee_db: float = 5.0,
        makeup_gain_db: float = 0.0,
        detection_mode: str = "rms",  # "rms" or "peak"
        sidechain_hpf_hz: float | None = None,
    ):
        self.sample_rate = sample_rate
        self.threshold_db = threshold_db
        self.ratio = ratio
        self.attack_ms = attack_ms
        self.release_ms = release_ms
        self.knee_db = knee_db
        self.makeup_gain_db = makeup_gain_db
        self.detection_mode = detection_mode.lower()
        self.sidechain_hpf_hz = sidechain_hpf_hz

    def apply(self, samples: np.ndarray | list[float]) -> np.ndarray:
        """Apply compression to mono samples."""
        x = np.asarray(samples, dtype=np.float64)
        if len(x) == 0:
            return x

        fs = float(self.sample_rate)

        # 1. Sidechain Signal Preparation
        sc_sig = x.copy()
        if self.sidechain_hpf_hz is not None and self.sidechain_hpf_hz > 0:
            nyquist = fs / 2.0
            cutoff = min(self.sidechain_hpf_hz, nyquist * 0.99)
            sos = sig.butter(2, cutoff / nyquist, btype="highpass", output="sos")
            sc_sig = sig.sosfilt(sos, sc_sig)

        # 2. Envelope/Level Detection
        if self.detection_mode == "rms":
            # Running RMS approximation using a simple 1st-order low-pass on squared signal
            # RMS integration window approx 10ms
            tau_rms = 0.010
            alpha_rms = math.exp(-1.0 / (fs * tau_rms))
            squared = sc_sig * sc_sig
            # Filter forward to get mean square
            ms = sig.lfilter([1.0 - alpha_rms], [1.0, -alpha_rms], squared)
            level = np.sqrt(np.maximum(ms, 1e-12))
        else:  # peak
            level = np.abs(sc_sig)

        # Convert sidechain level to dBFS
        level_db = 20.0 * np.log10(np.maximum(level, 1e-12))

        # 3. Static Gain Curve (with soft knee)
        t = self.threshold_db
        w = max(0.1, self.knee_db)
        r = self.ratio

        # Initialize output dB levels
        y_db = level_db.copy()

        # Knee boundaries
        below_knee = level_db < (t - w / 2.0)
        above_knee = level_db > (t + w / 2.0)
        in_knee = ~(below_knee | above_knee)

        # Apply transfer function
        # below knee: y_db = level_db (no change, gain reduction = 0)
        # in knee:
        if np.any(in_knee):
            diff = level_db[in_knee] - t + w / 2.0
            y_db[in_knee] = level_db[in_knee] + ((1.0 / r - 1.0) * (diff ** 2)) / (2.0 * w)
        # above knee:
        if np.any(above_knee):
            y_db[above_knee] = t + (level_db[above_knee] - t) / r

        # Raw gain reduction in dB (will be <= 0)
        gr_db = y_db - level_db

        # 4. Temporal Smoothing (Attack and Release) in dB domain
        # Attack / Release coefficients
        alpha_att = math.exp(-1.0 / (fs * (self.attack_ms / 1000.0)))
        alpha_rel = math.exp(-1.0 / (fs * (self.release_ms / 1000.0)))

        # Run smoothing loop (requires step-by-step update). Attacking when
        # the target is more negative (more gain reduction) than the
        # current value -- see _smooth_attack_release.
        smoothed_gr_db = _smooth_attack_release(gr_db, alpha_att, alpha_rel, 0.0, attack_when_less=True)

        # 5. Apply Gain + Makeup Gain
        total_gain_db = smoothed_gr_db + self.makeup_gain_db
        linear_gain = np.exp(total_gain_db * _LN10_OVER_20)

        return x * linear_gain


class Limiter:
    """Look-ahead brickwall limiter."""

    def __init__(
        self,
        sample_rate: int = 44100,
        threshold_db: float = 0.0,
        ceiling_db: float = -1.0,
        release_ms: float = 50.0,
        lookahead_ms: float = 5.0,
        true_peak: bool = False,
    ):
        self.sample_rate = sample_rate
        self.threshold_db = threshold_db
        self.ceiling_db = ceiling_db
        self.release_ms = release_ms
        self.lookahead_ms = lookahead_ms
        self.true_peak = true_peak

    def apply(self, samples: np.ndarray | list[float], *, return_gain: bool = False):
        """Apply brickwall limiting.

        With ``return_gain=True`` also returns ``(total_gain, delay)`` where
        ``total_gain`` is the exact per-output-sample gain applied to the input
        (makeup ``input_gain`` × limiting reduction, aligned to the delayed
        output timeline) and ``delay`` is the look-ahead delay in base-rate
        samples. This lets a stereo-linked caller reproduce the identical gain
        and delay on both channels instead of dividing output by input (which
        is misaligned by the look-ahead and drops the makeup gain)."""
        x = np.asarray(samples, dtype=np.float64)
        if len(x) == 0:
            return (x, np.ones_like(x), 0) if return_gain else x

        fs = float(self.sample_rate)
        
        # Apply initial threshold gain
        input_gain = 10.0 ** (-self.threshold_db / 20.0)
        x_g = x * input_gain

        # 1. True Peak / Peak Analysis
        # If true peak, we upsample 4x, analyze, then downsample gain reduction
        if self.true_peak:
            # 4x upsampling using polyphase resampling
            up_factor = 4
            x_up = sig.resample_poly(x_g, up_factor, 1)
            fs_detect = fs * up_factor
        else:
            x_up = x_g
            fs_detect = fs
            up_factor = 1

        # Look-ahead delay in samples
        lookahead_samples = int(fs_detect * (self.lookahead_ms / 1000.0))
        lookahead_samples = max(1, lookahead_samples)

        # 2-3. Peak Follower + Target Gain + Release Smoothing
        ceiling_linear = 10.0 ** (self.ceiling_db / 20.0)
        alpha_rel = math.exp(-1.0 / (fs_detect * (self.release_ms / 1000.0)))

        if _native.is_available():
            # x_up already has input_gain baked in (x_g = x * input_gain,
            # upsampled) -- pass input_gain=1.0 so the kernel doesn't apply
            # it twice. Single O(n) pass, no chunking needed at any size.
            smoothed_gain, _ = _native.limiter_gain_envelope(
                x_up, 1.0, ceiling_linear, alpha_rel, lookahead_samples,
            )
        else:
            # Find maximum in a rolling window of look-ahead size
            # We can implement this efficiently with a max filter or running maximum
            abs_x = np.abs(x_up)

            # Vectorized rolling window maximum using sliding windows
            # pad abs_x at the end with zeros to allow look-ahead at the end of audio
            pad_len = lookahead_samples - 1
            padded_abs = np.pad(abs_x, (0, pad_len), mode="constant", constant_values=0.0)

            # Use a maximum filter or strides to compute window max
            # For simplicity and speed:
            if len(padded_abs) < 500000: # reasonable size
                from scipy.ndimage import maximum_filter1d
                # Shift the maximum filter window to look forward
                # origin = -pad_len//2 shifts the window so it starts at the current sample
                peaks = maximum_filter1d(padded_abs, size=lookahead_samples, origin=-(lookahead_samples // 2))
                peaks = peaks[:len(x_up)]
            else:
                # Fallback block-based approach for very large files to avoid memory issues
                peaks = np.zeros_like(abs_x)
                for start in range(0, len(abs_x), 100000):
                    end = min(start + 100000, len(abs_x))
                    chunk = padded_abs[start : end + lookahead_samples]
                    from scipy.ndimage import maximum_filter1d
                    peaks_chunk = maximum_filter1d(chunk, size=lookahead_samples, origin=-(lookahead_samples // 2))
                    peaks[start:end] = peaks_chunk[:end-start]

            # Gain reduction needed
            target_gain = np.ones_like(peaks)
            over_threshold = peaks > ceiling_linear
            target_gain[over_threshold] = ceiling_linear / peaks[over_threshold]

            # Instant attack to target gain (<=), smoothed release otherwise --
            # see _smooth_attack_release. Instant attack is alpha_att=0.0: the
            # smoothing formula collapses to current = target exactly.
            smoothed_gain = _smooth_attack_release(target_gain, 0.0, alpha_rel, 1.0, attack_when_less=False)

        # 4. Downsample gain envelope if we upsampled
        if self.true_peak:
            # We take the minimum gain in each 4-sample block to ensure we catch the peaks
            gain_blocks = smoothed_gain.reshape(-1, up_factor)
            gain_down = np.min(gain_blocks, axis=1)
            # Match lengths if needed
            if len(gain_down) < len(x_g):
                gain_down = np.pad(gain_down, (0, len(x_g) - len(gain_down)), mode="edge")
            elif len(gain_down) > len(x_g):
                gain_down = gain_down[:len(x_g)]
        else:
            gain_down = smoothed_gain

        # 5. Apply look-ahead delay to the audio signal and multiply by gain
        # Delay samples is lookahead_samples / up_factor
        delay = lookahead_samples // up_factor
        
        output = np.zeros_like(x_g)
        # Apply gain to delayed audio
        output[delay:] = x_g[:-delay] * gain_down[:-delay]
        # Pad head with quiet signal scaled by gain
        output[:delay] = x_g[:delay] * gain_down[:delay]

        if return_gain:
            # Total gain applied to the ORIGINAL input per output sample, aligned to
            # the delayed output: output = delayed(x) * (input_gain * gain_down).
            total_gain = np.empty_like(x_g)
            total_gain[delay:] = input_gain * gain_down[:-delay]
            total_gain[:delay] = input_gain * gain_down[:delay]
            return output, total_gain, delay

        return output


class Gate:
    """Noise gate with hold and hysteresis."""

    def __init__(
        self,
        sample_rate: int = 44100,
        threshold_db: float = -40.0,
        attack_ms: float = 2.0,
        hold_ms: float = 50.0,
        release_ms: float = 150.0,
        range_db: float = -60.0,
        sidechain_hpf_hz: float | None = None,
    ):
        self.sample_rate = sample_rate
        self.threshold_db = threshold_db
        self.attack_ms = attack_ms
        self.hold_ms = hold_ms
        self.release_ms = release_ms
        self.range_db = range_db
        self.sidechain_hpf_hz = sidechain_hpf_hz

    def apply(self, samples: np.ndarray | list[float]) -> np.ndarray:
        """Apply noise gating to mono samples."""
        x = np.asarray(samples, dtype=np.float64)
        if len(x) == 0:
            return x

        fs = float(self.sample_rate)

        # 1. Sidechain Signal Preparation
        sc_sig = x.copy()
        if self.sidechain_hpf_hz is not None and self.sidechain_hpf_hz > 0:
            nyquist = fs / 2.0
            cutoff = min(self.sidechain_hpf_hz, nyquist * 0.99)
            sos = sig.butter(2, cutoff / nyquist, btype="highpass", output="sos")
            sc_sig = sig.sosfilt(sos, sc_sig)

        # Envelope detection (Peak detection for gate response)
        level_db = 20.0 * np.log10(np.maximum(np.abs(sc_sig), 1e-12))

        # Gate targets
        target_gain_closed = 10.0 ** (self.range_db / 20.0)
        target_gain_open = 1.0

        # Coefficients
        alpha_att = math.exp(-1.0 / (fs * (self.attack_ms / 1000.0)))
        alpha_rel = math.exp(-1.0 / (fs * (self.release_ms / 1000.0)))
        hold_samples = int(fs * (self.hold_ms / 1000.0))

        threshold = self.threshold_db
        g_out = _gate_envelope(
            level_db, threshold, alpha_att, alpha_rel, hold_samples,
            target_gain_open, target_gain_closed,
        )

        return x * g_out
