"""Analysis features wrapper functions.

Delegates to :mod:`audio_analysis_tool.analysis_features`,
:mod:`audio_analysis_tool.dsp_metrics`, and
:mod:`audio_analysis_tool.music_theory`.

Simple pass-through wrappers that bind project-level defaults for
convenience calls from :mod:`audio_analysis_tool.mix_review`.
"""

from __future__ import annotations

import numpy as np

from audio_analysis.analysis_core.analysis_features import (
    _fft as _features_fft,
    dynamic_profile as _features_dynamic_profile,
    rms_db as _features_rms_db,
    section_analysis as _features_section_analysis,
    stereo_field_summary as _features_stereo_field_summary,
    stereo_metrics as _features_stereo_metrics,
    tonal_balance_summary as _features_tonal_balance_summary,
    windowed_rms_values as _features_windowed_rms_values,
)
from audio_analysis.analysis_core.dsp_metrics import (
    a_weighting_gain as _dsp_a_weighting_gain,
    band_ratios as _dsp_band_ratios,
    perceptual_bands as _dsp_perceptual_bands,
    perceptual_summary as _dsp_perceptual_summary,
    percentile as _dsp_percentile,
    spectral_bands as _dsp_spectral_bands,
    spectral_features as _dsp_spectral_features,
    spectrum_magnitudes as _dsp_spectrum_magnitudes,
)
from audio_analysis.analysis_core.music_theory import detect_chords_and_key as _music_theory_detect_chords_and_key


# ---------------------------------------------------------------------------
# DSP/metric wrappers
# ---------------------------------------------------------------------------


def _fft(values: list[complex]) -> list[complex]:
    """Compute FFT of complex values."""
    return _features_fft(values)


def a_weighting_gain(frequency: float) -> float:
    """A-weighting gain at the given frequency."""
    return _dsp_a_weighting_gain(frequency)


def detect_chords_and_key(samples: list[float], sample_rate: float) -> dict:
    """Detect chords and key from audio samples."""
    return _music_theory_detect_chords_and_key(samples, sample_rate)


def spectrum_magnitudes(
    samples: list[float], sample_rate: int, *, size: int = 4096
) -> tuple[list[float], int]:
    """Compute spectrum magnitude from audio samples."""
    return _dsp_spectrum_magnitudes(samples, sample_rate, size=size)


def band_ratios(
    magnitudes: list[float],
    sample_rate: int,
    n: int,
    *,
    perceptual: bool = False,
    phon_level: float = 60.0,
) -> dict:
    """Compute band energy ratios from a spectrum magnitude array."""
    return _dsp_band_ratios(magnitudes, sample_rate, n, perceptual=perceptual, phon_level=phon_level)


def spectral_bands(samples: list[float], sample_rate: int, *, size: int = 4096) -> dict:
    """Compute spectral band analysis from audio samples."""
    return _dsp_spectral_bands(samples, sample_rate, size=size)


def perceptual_bands(
    samples: list[float], sample_rate: int, *, size: int = 4096, phon_level: float = 60.0
) -> dict:
    """Compute perceptual band analysis from audio samples."""
    return _dsp_perceptual_bands(samples, sample_rate, size=size, phon_level=phon_level)


def perceptual_summary(perceived: dict, phon_level: float = 60.0) -> dict:
    """Summarise a perceptual band dict."""
    return _dsp_perceptual_summary(perceived, phon_level=phon_level)


def percentile(values: list[float], q: float) -> float:
    """Compute the q-th percentile of a list of values."""
    return _dsp_percentile(values, q)


def spectral_features(magnitudes: list[float], sample_rate: int, n: int) -> dict:
    """Compute spectral features (centroid, rolloff, etc.)."""
    return _dsp_spectral_features(magnitudes, sample_rate, n)


def tonal_balance_summary(bands: dict, perceived: dict, features: dict) -> dict:
    """Combine band, perceptual, and spectral features into a tonal balance summary."""
    return _features_tonal_balance_summary(bands, perceived, features)


def dynamic_profile(
    samples: list[float],
    sample_rate: float,
    peak_db: float,
    rms_db: float,
    window_values: list[float],
) -> dict:
    """Compute dynamics profile (crest factor, short-term range, etc.)."""
    return _features_dynamic_profile(samples, sample_rate, peak_db, rms_db, window_values)


def section_analysis(
    samples: list[float],
    left_samples: list[float],
    right_samples: list[float],
    sample_rate: float,
    *,
    max_sections: int = 12,
) -> dict:
    """Detect structural sections in audio."""
    return _features_section_analysis(
        samples, left_samples, right_samples, sample_rate, max_sections=max_sections
    )


def stereo_field_summary(metrics: dict) -> dict:
    """Summarise stereo field from stereo metrics."""
    return _features_stereo_field_summary(metrics)


def rms_db(samples: list[float]) -> float:
    """Compute RMS level in dB."""
    return _features_rms_db(samples)


def windowed_rms_values(
    samples: list[float], sample_rate: float, *, window_seconds: float = 0.4
) -> list[float]:
    """Compute RMS values over sliding windows."""
    return _features_windowed_rms_values(samples, sample_rate, window_seconds=window_seconds)


def stereo_metrics(left: list[float], right: list[float]) -> dict:
    """Compute stereo correlation, balance, and width metrics."""
    return _features_stereo_metrics(left, right)


def leading_silence_seconds(
    samples: list[float], sample_rate: float, *, threshold: float = 0.003
) -> float:
    """Detect leading silence duration in seconds."""
    if not samples or sample_rate <= 0:
        return 0.0
    try:
        arr = np.asarray(samples)
        above = np.where(np.abs(arr) >= threshold)[0]
        count = int(above[0]) if len(above) > 0 else len(arr)
    except Exception:
        count = 0
        for sample in samples:
            if abs(sample) >= threshold:
                break
            count += 1
    return round(count / sample_rate, 2)


def trailing_silence_seconds(
    samples: list[float], sample_rate: float, *, threshold: float = 0.003
) -> float:
    """Detect trailing silence duration in seconds."""
    if not samples or sample_rate <= 0:
        return 0.0
    try:
        arr = np.asarray(samples)
        above = np.where(np.abs(arr) >= threshold)[0]
        count = len(arr) - int(above[-1]) - 1 if len(above) > 0 else len(arr)
    except Exception:
        count = 0
        for sample in reversed(samples):
            if abs(sample) >= threshold:
                break
            count += 1
    return round(count / sample_rate, 2)


def metric_float(value: object, fallback: float = 0.0) -> float:
    """Safely convert a value to float, returning fallback on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback
