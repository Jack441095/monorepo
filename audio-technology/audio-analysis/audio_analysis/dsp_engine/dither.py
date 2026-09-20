"""Psychoacoustic dither for bit-depth reduction (M8.4c).

Triangular PDF (TPDF) dither removes quantisation-distortion artefacts
at the cost of a tiny noise floor increase that is perceptually benign
at normal listening levels.
"""

from __future__ import annotations

import numpy as np

# Optional numba acceleration with a pure-Python fallback (same pattern as
# dynamics.py / dynamic_eq.py). The noise-shaped quantiser is a sequential
# error-feedback loop — each sample's quantisation error feeds the next — so it
# cannot be vectorised; the per-sample Python loop over a full-length master was
# several seconds per render and runs on both channels. njit collapses it.
try:  # pragma: no cover
    import numba as _nb  # type: ignore[import]
except Exception:  # pragma: no cover
    _nb = None


def _noise_shape_quantise_py(x64: np.ndarray, tpdf: np.ndarray, lsb: float, feedback_coeff: float) -> np.ndarray:
    out = np.empty_like(x64)
    error = 0.0
    for i in range(x64.shape[0]):
        shaped = x64[i] + tpdf[i] + feedback_coeff * error
        q = round(shaped / lsb) * lsb
        error = shaped - q
        out[i] = q
    return out


if _nb is not None:  # pragma: no cover
    @_nb.njit(cache=True)
    def _noise_shape_quantise_nb(x64, tpdf, lsb, feedback_coeff):
        out = np.empty_like(x64)
        error = 0.0
        for i in range(x64.shape[0]):
            shaped = x64[i] + tpdf[i] + feedback_coeff * error
            q = round(shaped / lsb) * lsb
            error = shaped - q
            out[i] = q
        return out


def _noise_shape_quantise(x64: np.ndarray, tpdf: np.ndarray, lsb: float, feedback_coeff: float) -> np.ndarray:
    if _nb is not None:
        return _noise_shape_quantise_nb(x64, tpdf, lsb, feedback_coeff)
    return _noise_shape_quantise_py(x64, tpdf, lsb, feedback_coeff)


def apply_tpdf_dither(
    samples: np.ndarray,
    bit_depth: int = 16,
    *,
    seed: int | None = None,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Add triangular PDF dither noise before truncating to ``bit_depth``.

    TPDF = sum of two independent uniform noise signals each spanning
    ±0.5 LSB, giving a triangular distribution over ±1 LSB.  This
    de-correlates quantisation error from the signal without introducing
    bias.

    Args:
        samples:   Float32 or Float64 array normalised to [-1, 1].
        bit_depth: Target bit depth (default 16).
        seed:      Optional seed for deterministic RNG.
        rng:       Optional numpy random Generator.

    Returns:
        Dithered float array, still normalised to [-1, 1].  Pass this
        to the WAV writer — the integer conversion step clamps and
        truncates as normal.
    """
    if samples.size == 0:
        return samples
    # 1 LSB in the target integer domain mapped back to normalised float
    lsb = 2.0 / (2 ** bit_depth)
    if rng is None:
        rng = np.random.default_rng(seed)
    noise = (rng.uniform(-0.5, 0.5, samples.shape) + rng.uniform(-0.5, 0.5, samples.shape)) * lsb
    return (samples + noise).astype(samples.dtype)


def apply_noise_shaped_dither(
    samples: np.ndarray,
    bit_depth: int = 16,
    *,
    seed: int | None = None,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """TPDF-dithered, error-feedback noise-shaped quantisation (Stage 7 mastering chain).

    This is the mastering-grade sibling of :func:`apply_tpdf_dither`: it performs
    the same triangular-PDF dithering *and* quantises to the target bit-depth
    grid immediately, feeding the per-sample quantisation error forward into the
    next sample (1st-order error feedback / noise shaping). This pushes
    quantisation noise energy up in frequency (toward the noise floor at the top
    of the audible band) rather than leaving it spectrally flat, which is the
    standard technique used by mastering limiters/dither plugins.

    This function must only be called once, immediately before the final
    bit-depth reduction (e.g. float -> 24-bit or float -> 16-bit) — applying it
    earlier in the chain would bake quantisation noise into further processing.

    Args:
        samples:   Float32 or Float64 array normalised to [-1, 1].
        bit_depth: Target bit depth (default 16).
        seed:      Optional seed for deterministic RNG.
        rng:       Optional numpy random Generator (for reproducible tests).

    Returns:
        Dithered + noise-shaped float array, still normalised to [-1, 1] and
        quantised onto the target bit-depth grid. Safe to pass directly to the
        WAV writer's integer conversion step.
    """
    x = np.asarray(samples)
    if x.size == 0:
        return x

    lsb = 2.0 / (2 ** bit_depth)
    if rng is None:
        rng = np.random.default_rng(seed)
    tpdf = (rng.uniform(-0.5, 0.5, x.shape) + rng.uniform(-0.5, 0.5, x.shape)) * lsb

    x64 = x.astype(np.float64)
    feedback_coeff = 0.5
    out = _noise_shape_quantise(
        np.ascontiguousarray(x64), np.ascontiguousarray(tpdf.astype(np.float64)), lsb, feedback_coeff
    )
    return out.astype(x.dtype)
