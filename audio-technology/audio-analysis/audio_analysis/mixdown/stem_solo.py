"""Stage 10 — stem solo: frequency-range isolation and stem spectrum comparison.

Two capabilities:

1. :func:`solo_frequency_range` — actually isolates a frequency band out of
   an audio signal (a real bandpass filter, not just an analysis reading),
   so a caller can, e.g., render "just the low end of this bass stem" for
   auditioning.
2. :func:`stem_spectrum_comparison` — compares the spectral balance of
   multiple stems band-by-band, including a dedicated low-end view
   ("here's what's happening in the low end across all your stems"),
   reusing the existing FFT/band utilities in
   :mod:`audio_analysis.analysis_core.dsp_metrics` rather than
   reimplementing spectrum analysis.
"""

from __future__ import annotations

import math
from typing import Callable

from audio_analysis.analysis_core.dsp_metrics import (
    BANDS,
    band_ratios,
    log_band_ratios,
    spectrum_magnitudes,
)
from audio_analysis.analysis_core.loudness import apply_biquad
from audio_analysis.analysis_core.analysis_features import rms_db

LOW_END_BANDS = ("sub", "bass")


# ---------------------------------------------------------------------------
# Frequency-range isolation (real audio filtering)
# ---------------------------------------------------------------------------
#
# Uses the RBJ ("Audio EQ Cookbook") biquad low-pass/high-pass design
# equations — the same reference used elsewhere in this codebase for the
# K-weighting filter (see analysis_core/loudness.py::get_k_filter_coefficients,
# which cites the same cookbook for its high-shelf/high-pass stages). We
# reuse :func:`apply_biquad` from that module to actually run the filter
# rather than re-deriving a second biquad-application implementation.


def _lowpass_coefficients(cutoff_hz: float, fs: float, q: float = 0.7071) -> tuple[float, float, float, float, float]:
    w0 = 2.0 * math.pi * cutoff_hz / fs
    cos_w0 = math.cos(w0)
    alpha = math.sin(w0) / (2.0 * q)
    b0 = (1.0 - cos_w0) / 2.0
    b1 = 1.0 - cos_w0
    b2 = (1.0 - cos_w0) / 2.0
    a0 = 1.0 + alpha
    a1 = -2.0 * cos_w0
    a2 = 1.0 - alpha
    return b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0


def _highpass_coefficients(cutoff_hz: float, fs: float, q: float = 0.7071) -> tuple[float, float, float, float, float]:
    w0 = 2.0 * math.pi * cutoff_hz / fs
    cos_w0 = math.cos(w0)
    alpha = math.sin(w0) / (2.0 * q)
    b0 = (1.0 + cos_w0) / 2.0
    b1 = -(1.0 + cos_w0)
    b2 = (1.0 + cos_w0) / 2.0
    a0 = 1.0 + alpha
    a1 = -2.0 * cos_w0
    a2 = 1.0 - alpha
    return b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0


def solo_frequency_range(
    samples: list[float],
    sample_rate: float,
    low_hz: float,
    high_hz: float,
    *,
    stages: int = 2,
) -> list[float]:
    """Isolate ``[low_hz, high_hz]`` out of ``samples`` via a cascaded
    Butterworth-style bandpass (high-pass at ``low_hz`` cascaded with
    low-pass at ``high_hz``).

    ``stages`` controls filter steepness: each stage is a second-order
    (12 dB/octave) section, so ``stages=2`` (the default) gives a
    4th-order (~24 dB/octave) bandpass — enough to meaningfully solo a
    band for auditioning without the very slow rolloff of a single
    biquad letting adjacent bands bleed through.

    ``low_hz`` of ``0`` (or below) skips the high-pass stage (isolates
    everything up to ``high_hz``); ``high_hz`` at or above the Nyquist
    frequency skips the low-pass stage (isolates everything above
    ``low_hz``).
    """
    if not samples or sample_rate <= 0:
        return []
    nyquist = sample_rate / 2.0
    signal = list(samples)

    if low_hz and low_hz > 0:
        hp_cutoff = min(max(low_hz, 1.0), nyquist * 0.99)
        b0, b1, b2, a1, a2 = _highpass_coefficients(hp_cutoff, sample_rate)
        for _ in range(stages):
            signal = apply_biquad(signal, b0, b1, b2, a1, a2)

    if high_hz and high_hz < nyquist:
        lp_cutoff = max(min(high_hz, nyquist * 0.99), 1.0)
        b0, b1, b2, a1, a2 = _lowpass_coefficients(lp_cutoff, sample_rate)
        for _ in range(stages):
            signal = apply_biquad(signal, b0, b1, b2, a1, a2)

    return signal


def solo_band_by_name(samples: list[float], sample_rate: float, band_name: str) -> list[float]:
    """Solo one of the standard mix-review bands (``sub``, ``bass``,
    ``low_mids``, ``mids``, ``presence``, ``sibilance``, ``air``) by name."""
    for name, low, high in BANDS:
        if name == band_name:
            return solo_frequency_range(samples, sample_rate, low, high)
    raise ValueError(f"Unknown band '{band_name}'. Expected one of {[b[0] for b in BANDS]}.")


# ---------------------------------------------------------------------------
# Stem spectrum comparison
# ---------------------------------------------------------------------------


def _stem_bands(samples: list[float], sample_rate: int, *, size: int = 4096) -> dict:
    magnitudes, n = spectrum_magnitudes(samples, sample_rate, size=size)
    return band_ratios(magnitudes, sample_rate, n)


def _stem_log_bands(samples: list[float], sample_rate: int, *, size: int = 4096) -> list[float]:
    magnitudes, n = spectrum_magnitudes(samples, sample_rate, size=size)
    return log_band_ratios(magnitudes, sample_rate, n)


def stem_spectrum_comparison(
    stems: list[dict],
    *,
    read_wav_mono: Callable | None = None,
) -> dict:
    """Rank active stems by the low-end fraction of each stem's own spectrum.

    Accept raw mono ``samples`` with ``sample_rate``, or ``file_bytes`` with
    a decoder. Both full-source RMS and the actual centered FFT window must
    exceed -60 dBFS before publishing ratios or ranks. The FFT still selects
    its existing centered power-of-two window (256 to 4096 samples).

    ``dominant_band`` retains its historical key but selects the largest
    within-stem fraction, not the loudest stem in the mix. These ratios do
    not establish simultaneous overlap, audible masking, or an EQ repair.
    Unusable sources retain identity in ``abstentions``; qualified sources
    remain independent of unrelated failed uploads.
    """
    resolved = []
    abstentions = []
    active_floor_dbfs = -60.0  # Existing upload floor, applied before normalized ratios.
    max_frame_samples = 4096  # Existing spectrum_magnitudes window limit, unchanged.
    min_frame_samples = 256  # Existing FFT minimum; shorter inputs have no measured spectrum.
    names = [stem.get("name") for stem in stems]
    for stem, name in zip(stems, names):
        if not isinstance(name, str) or not name.strip() or name != name.strip() or len(name) > 96 or names.count(name) != 1:
            # Match the bounded handoff identity contract without rewriting source names.
            abstentions.append({"name": name, "reason": "Missing, invalid, or duplicate stem identity (trimmed string, at most 96 characters)."})
            continue
        try:
            if "samples" in stem and "sample_rate" in stem:
                samples = list(stem["samples"])
                sample_rate = stem["sample_rate"]
                source_rms_dbfs = rms_db(samples)
            elif "file_bytes" in stem and read_wav_mono is not None:
                decoded = read_wav_mono(stem["file_bytes"])
                samples = list(decoded.get("samples", []))
                sample_rate = decoded.get("analysis_sample_rate", decoded.get("sample_rate"))
                source_rms = decoded.get("true_rms")
                if isinstance(source_rms, bool) or not isinstance(source_rms, (int, float)) or not math.isfinite(source_rms) or source_rms < 0:
                    raise ValueError("Full-source mono RMS is unavailable or invalid.")
                # The decoder already measured the full raw mono source. Reuse
                # its RMS through the existing dB helper without remeasuring a decimated preview.
                source_rms_dbfs = rms_db([source_rms])
            else:
                # No raw audio means the filename alone cannot enter spectral rankings.
                abstentions.append({"name": name, "reason": "No decodable audio provided."})
                continue
            if isinstance(sample_rate, bool) or not isinstance(sample_rate, (int, float)) or not math.isfinite(sample_rate) or sample_rate <= 0:
                raise ValueError("Effective sample rate is unavailable or invalid.")
            if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in samples):
                raise ValueError("Decoded samples are not finite audio amplitudes.")
            if not math.isfinite(source_rms_dbfs) or source_rms_dbfs <= active_floor_dbfs:
                # A tiny source must not become a large normalized low-end fraction.
                abstentions.append({"name": name, "reason": "Source RMS does not exceed -60 dBFS."})
                continue
            frame_size = 1
            while frame_size * 2 <= min(max_frame_samples, len(samples)):
                frame_size *= 2
            if frame_size < min_frame_samples:
                # Preserve the FFT's existing minimum instead of padding short uploads into evidence.
                abstentions.append({"name": name, "reason": "Fewer than 256 decoded samples are available for a spectrum."})
                continue
            window_start = max(0, (len(samples) - frame_size) // 2)
            window_rms_dbfs = rms_db(samples[window_start:window_start + frame_size])
            if not math.isfinite(window_rms_dbfs) or window_rms_dbfs <= active_floor_dbfs:
                # Whole-file activity cannot qualify a quiet centered analysis window.
                abstentions.append({"name": name, "reason": "Centered spectrum-window RMS does not exceed -60 dBFS."})
                continue
            bands = _stem_bands(samples, sample_rate)
            if not bands or any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in bands.values()):
                raise ValueError("Measured band fractions are unavailable or invalid.")
            activity = {
                "schema": "kenn.low_end_stem.activity.v1", "active_floor_dbfs": active_floor_dbfs,
                "source_rms_dbfs": source_rms_dbfs, "window_rms_dbfs": window_rms_dbfs,
                "sample_rate": float(sample_rate), "analysis_sample_count": len(samples),
                "frame_size_samples": frame_size, "window_start_sample": window_start,
            }
            resolved.append({"name": name, "bands": bands, "activity": activity})
        except Exception:
            # One failed decode or invalid measurement abstains locally, preserving other stem results.
            abstentions.append({"name": name, "reason": "Decoded audio, source level, or spectral measurement is unavailable or invalid."})

    dominant_band = {}
    for band_name, _low, _high in BANDS:
        if not resolved:
            # No qualified source means no band winner; even a zero placeholder would imply measurement.
            break
        best = max(resolved, key=lambda stem: stem["bands"].get(band_name, 0.0))
        dominant_band[band_name] = {"stem": best["name"], "share": best["bands"].get(band_name, 0.0)}
    ranked = []
    for stem in resolved:
        share = sum(stem["bands"].get(band, 0.0) for band in LOW_END_BANDS)
        if share > 1.0:
            # At short FFT sizes the existing sub/bass bins can overlap. Preserve
            # measured bands, but their sum cannot be published as a fraction.
            abstentions.append({"name": stem["name"], "reason": "Overlapping FFT bins make the combined low-end share exceed 1; ranking is unavailable."})
            continue
        ranked.append({"name": stem["name"], "low_end_share": round(share, 4), "activity": dict(stem["activity"])})
    ranked.sort(key=lambda item: item["low_end_share"], reverse=True)
    return {
        "stems": resolved,
        "dominant_band": dominant_band,
        "low_end_summary": {"ranked": ranked, "overlap_warning": None},
        "abstentions": abstentions,
        "limitations": ["Low-end ranks compare the fraction of each active stem's own spectrum; they do not measure relative stem level, simultaneous overlap, audible masking, or a need for EQ or sidechain ducking."],
    }
