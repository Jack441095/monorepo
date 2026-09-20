"""Loudness analysis wrapper functions — delegates to :mod:`audio_analysis_tool.loudness`.

Simple pass-through wrappers that expose loudness and true-peak
calculation functions for convenience from
:mod:`audio_analysis_tool.mix_review`.
"""

from __future__ import annotations

from audio_analysis.analysis_core.loudness import (
    apply_biquad as _loudness_apply_biquad,
    calculate_lufs as _loudness_calculate_lufs,
    calculate_lufs_fallback as _loudness_calculate_lufs_fallback,
    calculate_lufs_numpy as _loudness_calculate_lufs_numpy,
    calculate_lufs_torch as _loudness_calculate_lufs_torch,
    calculate_true_peak as _loudness_calculate_true_peak,
    calculate_true_peak_fallback as _loudness_calculate_true_peak_fallback,
    calculate_true_peak_fallback_efficient as _loudness_calculate_true_peak_fallback_efficient,
    calculate_true_peak_numpy as _loudness_calculate_true_peak_numpy,
    calculate_true_peak_numpy_efficient as _loudness_calculate_true_peak_numpy_efficient,
    calculate_true_peak_torch as _loudness_calculate_true_peak_torch,
    get_k_filter_coefficients as _loudness_get_k_filter_coefficients,
    oversample_fft_torch as _loudness_oversample_fft_torch,
    calculate_loudness_profile as _loudness_calculate_loudness_profile,
    loudness_range_for_span as _loudness_range_for_span,
    loudness_range_by_section as _loudness_range_by_section,
)


def get_k_filter_coefficients(
    fs: float,
) -> tuple[tuple[float, float, float, float, float], tuple[float, float, float, float, float]]:
    """Return K-filter biquad coefficients for the given sample rate."""
    return _loudness_get_k_filter_coefficients(fs)


def apply_biquad(
    x: list[float], b0: float, b1: float, b2: float, a1: float, a2: float
) -> list[float]:
    """Apply a biquad filter to a signal."""
    return _loudness_apply_biquad(x, b0, b1, b2, a1, a2)


def calculate_lufs_fallback(left: list[float], right: list[float], fs: int) -> float:
    """Compute integrated LUFS using pure-Python fallback."""
    return _loudness_calculate_lufs_fallback(left, right, fs)


def calculate_lufs_torch(left: list[float], right: list[float], fs: int) -> float:
    """Compute integrated LUFS using PyTorch."""
    return _loudness_calculate_lufs_torch(left, right, fs)


def calculate_lufs_numpy(left: list[float], right: list[float], fs: int) -> float:
    """Compute integrated LUFS using NumPy."""
    return _loudness_calculate_lufs_numpy(left, right, fs)


def calculate_lufs(
    left: list[float],
    right: list[float],
    fs: int,
    *,
    diagnostics: list[str] | None = None,
) -> float:
    """Compute integrated LUFS, auto-selecting the best available backend."""
    return _loudness_calculate_lufs(left, right, fs, diagnostics=diagnostics)


def oversample_fft_torch(x: list[float], factor: int = 4) -> list[float]:
    """Oversample a signal using FFT interpolation (PyTorch)."""
    return _loudness_oversample_fft_torch(x, factor)


def calculate_true_peak_torch(samples: list[float], fs: int) -> float:
    """Compute true-peak level using PyTorch."""
    return _loudness_calculate_true_peak_torch(samples, fs)


def calculate_true_peak_fallback(left: list[float], right: list[float]) -> float:
    """Compute true-peak level using pure-Python fallback."""
    return _loudness_calculate_true_peak_fallback(left, right)


def calculate_true_peak_numpy(left: list[float], right: list[float]) -> float:
    """Compute true-peak level using NumPy."""
    return _loudness_calculate_true_peak_numpy(left, right)


def calculate_true_peak_numpy_efficient(raw_bytes: bytes) -> float:
    """Compute true-peak level from raw PCM bytes (NumPy)."""
    return _loudness_calculate_true_peak_numpy_efficient(raw_bytes)


def calculate_true_peak_fallback_efficient(raw_bytes: bytes) -> float:
    """Compute true-peak level from raw PCM bytes (pure-Python)."""
    return _loudness_calculate_true_peak_fallback_efficient(raw_bytes)


def calculate_true_peak(
    left: list[float],
    right: list[float],
    fs: int,
    raw_bytes: bytes,
    *,
    diagnostics: list[str] | None = None,
) -> float:
    """Compute true-peak level, auto-selecting the best available backend."""
    return _loudness_calculate_true_peak(left, right, fs, raw_bytes, diagnostics=diagnostics)


def calculate_loudness_profile(
    left: list[float],
    right: list[float],
    fs: int,
    *,
    diagnostics: list[str] | None = None,
) -> dict:
    """Compute full BS.1770-4 + EBU R128 loudness profile, auto-selecting the best available backend."""
    return _loudness_calculate_loudness_profile(left, right, fs, diagnostics=diagnostics)


def loudness_range_for_span(left: list[float], right: list[float], fs: int) -> float | None:
    """Compute EBU R128 LRA for a single contiguous span of audio."""
    return _loudness_range_for_span(left, right, fs)


def loudness_range_by_section(
    left: list[float], right: list[float], fs: int, sections: list[dict]
) -> list[dict]:
    """Compute per-section LRA for structural sections (see :mod:`analysis_core.loudness`)."""
    return _loudness_range_by_section(left, right, fs, sections)
