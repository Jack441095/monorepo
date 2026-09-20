"""Dynamic EQ band processor — the "processor" half of the dynamic EQ plan.

See docs/SPECTRAL_DYNAMIC_EQ_PLUGIN_PLAN.md and
analysis_core/resonance_detection.py (the "detection brain" half — decides
*where* to place a band and how persistently it's a problem). This module
is deliberately just the DSP primitive: given a center frequency, reduce
gain at that narrow band only when its own level crosses a threshold, same
mental model as the existing `Compressor`/`Limiter` in `dynamics.py`, kept
as a clearly separate, independently-testable unit from the detector —
the same detector/processor split the limiter-ceiling bug earlier this
project taught us to respect.

Architecture: isolate the narrow band with a resonant bandpass filter
(`scipy.signal.iirpeak`, Q-controlled), envelope-follow that isolated
signal, compute a compressor-style gain-reduction curve from it, then
subtract only the reduced portion back out of the original signal
(``output = original - isolated * (1 - gain)``). This touches only the
targeted band — everything outside it passes through unchanged, which is
what makes it surgical rather than a broad tonal shift.
"""

from __future__ import annotations

import math

import numpy as np
import scipy.signal as sig

# 10**(x/20) == exp(x * _LN10_OVER_20) -- see mix_renderer.py's identical
# constant for the full rationale (numpy's array pow() is slower than exp(),
# ~1e-16 relative difference, far below the 24-bit dither floor).
_LN10_OVER_20 = math.log(10.0) / 20.0

# Optional numba acceleration with a pure-Python/numpy fallback — the exact
# same pattern the sibling `dynamics.py` uses for its compressor/gate envelopes.
# The envelope follower is a state-dependent one-pole recursion (each sample
# depends on the previous), so it cannot be a single-coefficient lfilter and a
# per-sample Python loop is the only numpy-only option. Over a full-length stem
# (~9M samples) that loop costs ~2s per band; run per-band across every stem
# plus the master bus it was a multi-minute chunk of each render. njit collapses
# it to milliseconds. No fastmath: keep exact IEEE754 semantics, same reasoning
# as dynamics.py.
try:  # pragma: no cover
    import numba as _nb  # type: ignore[import]
except Exception:  # pragma: no cover
    _nb = None


def _envelope_follow_py(
    level: np.ndarray, alpha_att: float, alpha_rel: float
) -> np.ndarray:
    """Pure-Python fallback: fast attack on rising level, smoothed release on
    falling level. Bit-identical to the original loop this replaced."""
    n = level.shape[0]
    out = np.zeros(n, dtype=np.float64)
    current = 0.0
    for i in range(n):
        target = level[i]
        if target > current:
            current = alpha_att * current + (1.0 - alpha_att) * target
        else:
            current = alpha_rel * current + (1.0 - alpha_rel) * target
        out[i] = current
    return out


if _nb is not None:  # pragma: no cover
    @_nb.njit(cache=True)
    def _envelope_follow_nb(level, alpha_att, alpha_rel):
        n = level.shape[0]
        out = np.zeros(n, dtype=np.float64)
        current = 0.0
        for i in range(n):
            target = level[i]
            if target > current:
                current = alpha_att * current + (1.0 - alpha_att) * target
            else:
                current = alpha_rel * current + (1.0 - alpha_rel) * target
            out[i] = current
        return out


def _envelope_follow(
    level: np.ndarray, sample_rate: float, *, attack_ms: float, release_ms: float
) -> np.ndarray:
    """Fast attack on rising level, smoothed release — same shape as the
    compressor envelope already used in mix_renderer.py's
    _apply_stereo_compressor. numba-accelerated when available."""
    alpha_att = math.exp(-1.0 / (sample_rate * (attack_ms / 1000.0)))
    alpha_rel = math.exp(-1.0 / (sample_rate * (release_ms / 1000.0)))
    level = np.ascontiguousarray(level, dtype=np.float64)
    if _nb is not None:
        return _envelope_follow_nb(level, alpha_att, alpha_rel)
    return _envelope_follow_py(level, alpha_att, alpha_rel)


def apply_dynamic_eq_band(
    left: np.ndarray,
    right: np.ndarray,
    *,
    frequency_hz: float,
    sample_rate: int,
    q: float = 6.0,
    threshold_db: float = -24.0,
    ratio: float = 3.0,
    max_reduction_db: float = 6.0,
    attack_ms: float = 10.0,
    release_ms: float = 150.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Reduce gain at ``frequency_hz`` only while that narrow band's own
    level exceeds ``threshold_db`` — transparent when the band is quiet.

    ``q`` matches the plan's "surgical, not broad" requirement (4-10 is the
    documented target range). ``max_reduction_db`` caps how much any single
    band can be pulled down, so a detection false-positive or aggressive
    threshold can't dull the mix — mirrors the plan's "max total reduction
    capped (3-6 dB per band)" design constraint.
    """
    nyq = 0.5 * sample_rate
    w0 = max(1.0, min(frequency_hz, nyq - 1.0)) / nyq
    b, a = sig.iirpeak(w0, q)

    # Stereo-linked detection (same pattern as _apply_stereo_compressor):
    # one envelope drives gain reduction on both channels, avoiding a
    # stereo-image shift that independent per-channel detection would cause.
    band_l = sig.lfilter(b, a, left)
    band_r = sig.lfilter(b, a, right)
    band_max = np.maximum(np.abs(band_l), np.abs(band_r))
    band_db = 20.0 * np.log10(np.maximum(band_max, 1e-12))

    gr_db = np.zeros_like(band_db)
    above = band_db > threshold_db
    if np.any(above):
        gr_db[above] = (threshold_db - band_db[above]) * (1.0 - 1.0 / ratio)
    gr_db = np.maximum(gr_db, -max_reduction_db)

    smoothed_gr_db = _envelope_follow(
        gr_db, float(sample_rate), attack_ms=attack_ms, release_ms=release_ms
    )
    reduction_linear = np.exp(smoothed_gr_db * _LN10_OVER_20)  # 1.0 = no reduction, <1.0 = reduced

    # Subtract only the reduced portion of the isolated band back out of
    # the original signal — everything outside this band is untouched.
    out_l = left - band_l * (1.0 - reduction_linear)
    out_r = right - band_r * (1.0 - reduction_linear)
    return out_l, out_r


def apply_dynamic_eq_bands(
    left: np.ndarray,
    right: np.ndarray,
    *,
    bands: list[dict],
    sample_rate: int,
    max_simultaneous_bands: int = 6,
    q: float = 6.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply dynamic EQ for multiple detected resonant bands in sequence.

    ``bands`` is the output of
    ``analysis_core.resonance_detection.detect_resonant_bands`` (already
    sorted by persistence then prominence) — only the top
    ``max_simultaneous_bands`` are processed, per the plan's "cap total
    simultaneous processing" requirement, so a busy spectrum with many
    minor resonances doesn't get over-processed everywhere at once.
    Threshold and ratio for each band scale from its detected prominence,
    so a mildly-persistent resonance gets gentler treatment than a
    consistently loud one.
    """
    out_l, out_r = left, right
    for band in bands[:max_simultaneous_bands]:
        prominence_db = float(band.get("mean_prominence_db", 6.0))
        # A band that sticks out by prominence_db over its neighborhood
        # roughly needs that much reduction to blend back in; ratio scales
        # gently with how bad it is, capped for stability.
        ratio = min(2.0 + prominence_db / 6.0, 6.0)
        out_l, out_r = apply_dynamic_eq_band(
            out_l, out_r,
            frequency_hz=float(band["frequency_hz"]),
            sample_rate=sample_rate,
            q=q,
            ratio=ratio,
            max_reduction_db=min(prominence_db, 6.0),
        )
    return out_l, out_r
