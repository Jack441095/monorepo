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
    """Compare per-stem spectral balance across the seven mix-review bands.

    ``stems`` is a list of dicts, each either:
      - ``{"name": str, "samples": list[float], "sample_rate": int}`` (raw
        decoded mono audio — used directly, useful for tests and for
        callers that already have decoded stem audio), or
      - ``{"name": str, "file_bytes": bytes}`` (requires ``read_wav_mono``
        to decode).

    Returns:
      ``stems``          — per-stem ``{"name", "bands"}`` band-ratio dicts
                            (reusing :func:`band_ratios` from dsp_metrics).
      ``dominant_band``   — for each of the 7 bands, which stem has the
                            largest share of that band (i.e. would "win"
                            a frequency clash there).
      ``low_end_summary`` — stems ranked by combined sub+bass share,
                            highest first, plus the two-way overlap
                            (min share in each low band) between the top
                            two — a direct answer to "what's happening in
                            the low end across all my stems".
    """
    if not stems:
        return {"stems": [], "dominant_band": {}, "low_end_summary": {"ranked": [], "overlap_warning": None}}

    resolved = []
    for stem in stems:
        name = str(stem.get("name", "stem"))
        if "samples" in stem and "sample_rate" in stem:
            samples = stem["samples"]
            sample_rate = int(stem["sample_rate"])
        elif "file_bytes" in stem and read_wav_mono is not None:
            decoded = read_wav_mono(stem["file_bytes"])
            samples = decoded.get("samples", [])
            sample_rate = int(decoded.get("analysis_sample_rate") or decoded.get("sample_rate") or 44100)
        else:
            resolved.append({"name": name, "bands": {}, "error": "no decodable audio provided"})
            continue
        bands = _stem_bands(samples, sample_rate)
        resolved.append({"name": name, "bands": bands})

    dominant_band: dict[str, dict] = {}
    for band_name, _low, _high in BANDS:
        best_name = None
        best_value = -1.0
        for stem in resolved:
            value = float((stem.get("bands") or {}).get(band_name, 0.0))
            if value > best_value:
                best_value = value
                best_name = stem["name"]
        dominant_band[band_name] = {"stem": best_name, "share": round(best_value, 4)}

    low_end_ranked = sorted(
        (
            {
                "name": stem["name"],
                "low_end_share": round(
                    sum(float((stem.get("bands") or {}).get(b, 0.0)) for b in LOW_END_BANDS), 4
                ),
            }
            for stem in resolved
            if stem.get("bands")
        ),
        key=lambda item: item["low_end_share"],
        reverse=True,
    )
    overlap_warning = None
    if len(low_end_ranked) >= 2:
        top_two = low_end_ranked[:2]
        if top_two[0]["low_end_share"] > 0.15 and top_two[1]["low_end_share"] > 0.15:
            overlap_warning = (
                f"'{top_two[0]['name']}' and '{top_two[1]['name']}' both carry substantial low-end "
                f"energy ({top_two[0]['low_end_share']:.2f} and {top_two[1]['low_end_share']:.2f} "
                "share of their own spectrum) — likely candidates for low-end EQ carving or sidechain "
                "ducking so they don't fight for the same space."
            )

    return {
        "stems": resolved,
        "dominant_band": dominant_band,
        "low_end_summary": {"ranked": low_end_ranked, "overlap_warning": overlap_warning},
    }
