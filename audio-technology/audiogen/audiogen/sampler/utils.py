# sampler/utils.py
from fractions import Fraction
import logging
from typing import Optional

import numpy as np
import scipy.signal

# Try to use Numba; fall back to pure Python
try:
    from numba import njit

    NUMBA_AVAILABLE = True
except ImportError:
    NUMBA_AVAILABLE = False
    logging.warning("numba not installed; falling back to pure Python for some operations")


# -------------------------------------------------------------------
# Basic utilities
# -------------------------------------------------------------------


def create_silent_sample(duration_sec: float, sample_rate: int) -> np.ndarray:
    """Generate a silent stereo sample of given duration."""
    return np.zeros((int(duration_sec * sample_rate), 2), dtype=np.float32)


def midi_to_frequency(midi_note: int) -> float:
    """Convert MIDI note number to frequency in Hz (A4 = 440 Hz)."""
    return 440.0 * (2.0 ** ((midi_note - 69) / 12.0))


def dc_block(audio: np.ndarray, sample_rate: int = 44100, cutoff_hz: float = 20.0) -> np.ndarray:
    """
    Simple DC blocker / very-low highpass for stability.
    Uses an efficient 1st-order highpass via lfilter (C-accelerated).
    """
    if audio is None or len(audio) == 0:
        return audio
    x = np.asarray(audio, dtype=np.float32)
    r = float(np.exp(-2.0 * np.pi * float(cutoff_hz) / float(sample_rate)))
    b = np.array([1.0, -1.0], dtype=np.float32)
    a = np.array([1.0, -r], dtype=np.float32)
    if x.ndim == 1:
        return scipy.signal.lfilter(b, a, x).astype(np.float32)
    y = np.empty_like(x)
    for ch in range(x.shape[1]):
        y[:, ch] = scipy.signal.lfilter(b, a, x[:, ch]).astype(np.float32)
    return y


# -------------------------------------------------------------------
# Normalization
# -------------------------------------------------------------------


def normalize_audio(
    audio: np.ndarray,
    target_db: float = -3.0,
    mode: str = "peak",
    prevent_clipping: bool = True,
    sample_rate: int = 44100,
    gate_db: float = -45.0,
    min_active_fraction: float = 0.02,
) -> np.ndarray:
    """
    Normalize audio according to mode ('peak', 'rms', 'loudness').
    Returns normalized copy.
    """
    if len(audio) == 0:
        return audio
    audio = audio.copy()
    # Remove DC offset
    if audio.ndim == 1:
        audio -= np.mean(audio)
    else:
        for ch in range(audio.shape[1]):
            audio[:, ch] -= np.mean(audio[:, ch])

    target_linear = 10 ** (target_db / 20.0)

    def _mono(x: np.ndarray) -> np.ndarray:
        if x.ndim == 1:
            return x
        return np.mean(x, axis=1)

    def _gated_view(x: np.ndarray) -> np.ndarray:
        """
        Return a 1D view (mono) of x with silence gated out.
        Gate is absolute (dBFS), not relative, to avoid over-boosting sparse samples.
        """
        m = _mono(x)
        if len(m) == 0:
            return m
        thr = float(10 ** (float(gate_db) / 20.0))
        mask = np.abs(m) >= thr
        if not np.any(mask):
            return m
        active = m[mask]
        frac = float(min_active_fraction)
        frac = max(0.0, min(1.0, frac))
        if len(active) < int(max(1, round(frac * len(m)))):
            # If too little material passes the gate, fall back to full signal
            # so we don't normalize based on a few transient samples.
            return m
        return active

    if mode == "peak":
        peak = np.max(np.abs(audio))
        if peak > 0:
            audio *= target_linear / peak
    elif mode == "rms":
        m = _gated_view(audio)
        rms = float(np.sqrt(np.mean(m**2))) if len(m) else 0.0
        if rms > 0:
            audio *= target_linear / rms
    elif mode == "loudness":
        # Crude loudness normalisation: high‑pass filter then RMS
        b, a = scipy.signal.butter(1, 40.0 / (sample_rate / 2), "high")
        m = _mono(audio)
        try:
            filtered = scipy.signal.filtfilt(b, a, m)
        except Exception:
            filtered = m
        filtered_gated = _gated_view(filtered)
        rms = float(np.sqrt(np.mean(filtered_gated**2))) if len(filtered_gated) else 0.0
        if rms > 0:
            audio *= target_linear / rms

    if prevent_clipping:
        peak = np.max(np.abs(audio))
        if peak > 0.95:
            audio = np.tanh(audio * (1.0 / 0.95) * 0.9) * 0.95 * 0.95
    return audio


# -------------------------------------------------------------------
# Fades
# -------------------------------------------------------------------


def apply_fade_in(audio: np.ndarray, fade_samples: int) -> np.ndarray:
    if len(audio) == 0 or fade_samples <= 0:
        return audio
    fade_samples = min(fade_samples, len(audio))
    t = np.linspace(0.0, 1.0, fade_samples)
    env = (0.5 * (1.0 - np.cos(np.pi * t))).astype(np.float32)
    if audio.ndim == 1:
        audio[:fade_samples] *= env
    else:
        audio[:fade_samples, :] *= env[:, np.newaxis]
    return audio


def apply_fade_out(audio: np.ndarray, fade_samples: int) -> np.ndarray:
    if len(audio) == 0 or fade_samples <= 0:
        return audio
    fade_samples = min(fade_samples, len(audio))
    t = np.linspace(0.0, 1.0, fade_samples)
    env = (0.5 * (1.0 + np.cos(np.pi * t))).astype(np.float32)
    if audio.ndim == 1:
        audio[-fade_samples:] *= env
    else:
        audio[-fade_samples:, :] *= env[:, np.newaxis]
    return audio


def apply_fade_in_out(audio: np.ndarray, fade_samples: int) -> np.ndarray:
    audio = apply_fade_in(audio, fade_samples)
    audio = apply_fade_out(audio, fade_samples)
    return audio


def high_quality_resample(
    audio: np.ndarray, ratio: float, axis: int = 0, max_denominator: int = 512
) -> np.ndarray:
    if len(audio) == 0 or ratio <= 0.0 or abs(ratio - 1.0) < 1e-9:
        return audio.astype(np.float32, copy=True)

    frac = Fraction(ratio).limit_denominator(max_denominator)
    up = max(1, int(frac.numerator))
    down = max(1, int(frac.denominator))
    resampled = scipy.signal.resample_poly(audio, up, down, axis=axis)
    return resampled.astype(np.float32, copy=False)


# -------------------------------------------------------------------
# Interpolation (with Numba acceleration if available)
# -------------------------------------------------------------------


if NUMBA_AVAILABLE:

    @njit(cache=True)
    def hermite_interp_channel(src: np.ndarray, new_indices: np.ndarray) -> np.ndarray:
        n = len(src)
        floor_idx = np.floor(new_indices).astype(np.int32)
        t = (new_indices - floor_idx).astype(np.float32)

        i0 = np.clip(floor_idx - 1, 0, n - 1)
        i1 = np.clip(floor_idx, 0, n - 1)
        i2 = np.clip(floor_idx + 1, 0, n - 1)
        i3 = np.clip(floor_idx + 2, 0, n - 1)

        y0 = src[i0]
        y1 = src[i1]
        y2 = src[i2]
        y3 = src[i3]

        c0 = y1
        c1 = 0.5 * (y2 - y0)
        c2 = y0 - 2.5 * y1 + 2.0 * y2 - 0.5 * y3
        c3 = -0.5 * y0 + 1.5 * y1 - 1.5 * y2 + 0.5 * y3

        return ((c3 * t + c2) * t + c1) * t + c0

    @njit(cache=True)
    def linear_interp_channel(src: np.ndarray, new_indices: np.ndarray) -> np.ndarray:
        n = len(src)
        floor_idx = np.floor(new_indices).astype(np.int32)
        frac = new_indices - floor_idx
        i1 = np.clip(floor_idx, 0, n - 1)
        i2 = np.clip(floor_idx + 1, 0, n - 1)
        return src[i1] * (1 - frac) + src[i2] * frac

    hermite_interp = hermite_interp_channel
    linear_interp = linear_interp_channel
else:

    def hermite_interp(src, new_indices):
        # Use scipy resample as fallback (reasonably fast)
        import scipy.signal

        new_len = len(new_indices)
        resampled = scipy.signal.resample(src, new_len)
        return resampled.astype(np.float32)

    def linear_interp(src, new_indices):
        n = len(src)
        floor_idx = np.floor(new_indices).astype(np.int32)
        frac = new_indices - floor_idx
        i1 = np.clip(floor_idx, 0, n - 1)
        i2 = np.clip(floor_idx + 1, 0, n - 1)
        return src[i1] * (1 - frac) + src[i2] * frac


# -------------------------------------------------------------------
# Zero‑crossing detection
# -------------------------------------------------------------------


if NUMBA_AVAILABLE:

    @njit(cache=True)
    def find_zero_crossing_nb(mono: np.ndarray, search_start: int, search_end: int) -> int:
        region = mono[search_start:search_end]
        if len(region) < 2:
            return search_start
        signs = np.sign(region)
        pos_crossings = np.where((signs[:-1] <= 0) & (signs[1:] > 0))[0]
        if len(pos_crossings):
            return search_start + int(pos_crossings[0])
        any_crossings = np.where(np.diff(signs) != 0)[0]
        if len(any_crossings):
            return search_start + int(any_crossings[0])
        return search_start

    find_zero_crossing = find_zero_crossing_nb
else:

    def find_zero_crossing(mono, search_start, search_end):
        region = mono[search_start:search_end]
        if len(region) < 2:
            return search_start
        signs = np.sign(region)
        crossings = np.where(np.diff(signs) != 0)[0]
        if len(crossings) == 0:
            return search_start
        middle = len(region) // 2
        closest_idx = crossings[np.argmin(np.abs(crossings - middle))]
        return search_start + closest_idx


def find_nearest_zero_crossing(
    audio: np.ndarray, around_sample: int, search_radius: int = 1024
) -> int:
    """
    Find a nearby zero crossing around `around_sample`.

    Performance note:
    This is called during loop-point snapping. We only need a small local window,
    so we must avoid computing mono over the entire clip (O(N) per call).
    """
    if audio is None:
        return int(max(0, around_sample))

    n = int(len(audio))
    if n <= 0:
        return 0

    around = int(max(0, min(int(around_sample), n - 1)))
    r = int(max(8, int(search_radius)))
    start = int(max(0, around - r))
    end = int(min(n, around + r))
    if end - start < 2:
        return int(start)

    # Compute mono only for the local region (much cheaper than mean over full signal).
    if getattr(audio, "ndim", 1) == 2:
        region = np.asarray(audio[start:end], dtype=np.float32)
        if region.shape[1] >= 2:
            mono = (region[:, 0] + region[:, 1]) * 0.5
        else:
            mono = region.reshape(-1)
    else:
        mono = np.asarray(audio[start:end], dtype=np.float32).reshape(-1)

    # `find_zero_crossing` expects indices into `mono`; offset back into original.
    idx_local = int(find_zero_crossing(mono, 0, int(len(mono))))
    return int(start + idx_local)


# -------------------------------------------------------------------
# Looping (improved with zero‑crossing adjustment)
# -------------------------------------------------------------------


def build_looping_audio(
    source: np.ndarray,
    target_samples: int,
    loop_start: int = 0,
    loop_end: Optional[int] = None,
    crossfade_ms: float = 8.0,
    sample_rate: int = 44100,
    use_zero_crossing: bool = True,
) -> np.ndarray:
    """
    Build a looped version of the source audio.
    If use_zero_crossing is True, adjust loop points to nearest zero crossings.
    """
    src_len = len(source)
    if src_len == 0 or target_samples <= 0:
        return np.zeros((target_samples, 2), dtype=np.float32)

    # If we don't need to loop (source already long enough), just return the first part
    if src_len >= target_samples:
        return source[:target_samples].copy()

    # Validate loop points
    if loop_start >= src_len:
        loop_start = 0
    if loop_end is None or loop_end > src_len:
        loop_end = src_len
    if loop_start >= loop_end:
        loop_start = 0
        loop_end = src_len

    # Adjust to zero‑crossings if requested
    if use_zero_crossing:
        if loop_start > 0:
            loop_start = find_nearest_zero_crossing(source, loop_start)
        if loop_end < src_len:
            loop_end = find_nearest_zero_crossing(source, loop_end)

    loop_body = source[loop_start:loop_end]
    loop_len = len(loop_body)
    if loop_len == 0:
        loop_body = source
        loop_len = src_len
        loop_start = 0
        loop_end = src_len

    # Prepare crossfade envelopes
    cf_smp = min(int(crossfade_ms * sample_rate / 1000.0), loop_len // 4, 512)
    if cf_smp > 0:
        t = np.linspace(0.0, 1.0, cf_smp, dtype=np.float32)
        env_out = (0.5 * (1.0 + np.cos(np.pi * t)))[:, np.newaxis]  # fade out
        env_in = (0.5 * (1.0 - np.cos(np.pi * t)))[:, np.newaxis]  # fade in
    else:
        env_out = env_in = None

    if env_in is not None and cf_smp > 0 and loop_len > cf_smp:
        seamless_body = loop_body.copy()
        tail = seamless_body[-cf_smp:].copy()
        head = seamless_body[:cf_smp].copy()
        seamless_body[:cf_smp] = tail * env_out + head * env_in
        loop_body = seamless_body

    result = np.zeros((target_samples, 2), dtype=np.float32)

    # Keep the original attack/transient once before entering the loop body.
    initial_len = min(loop_end, target_samples)
    result[:initial_len] = source[:initial_len].copy()
    pos = initial_len

    while pos < target_samples:
        remaining = target_samples - pos
        seg_len = min(loop_len, remaining)
        seg = loop_body[:seg_len]

        if env_in is not None and cf_smp > 0:
            cf_len = min(cf_smp, seg_len, pos)
            if cf_len > 0:
                # Overlap‑add with previous segment
                existing = result[pos - cf_len : pos].copy()
                blended = existing * env_out[:cf_len] + seg[:cf_len] * env_in[:cf_len]
                result[pos - cf_len : pos] = blended
                if seg_len > cf_len:
                    result[pos : pos + seg_len - cf_len] = seg[cf_len:seg_len]
            else:
                result[pos : pos + seg_len] = seg
        else:
            result[pos : pos + seg_len] = seg

        pos += seg_len

    return result

