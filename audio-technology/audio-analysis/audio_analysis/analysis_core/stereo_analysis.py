"""Phase 9.1 — L/R Phase Correlation & Stereo Image Analyzer.

Performs STFT-based analysis of Left/Right channels to identify:
  - Per-band phase correlation (Pearson, via cross-spectral density)
  - Mono-compatibility score (overall and per-band)
  - Stereo width coefficient per frequency band
  - Corrective advice for common stereo imaging issues
"""

from __future__ import annotations

import math
from typing import Tuple

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False


# Frequency bands aligned with the rest of the analysis tool
BANDS = [
    ("sub", 20, 60),
    ("bass", 60, 150),
    ("low_mids", 150, 400),
    ("mids", 400, 2000),
    ("presence", 2000, 6000),
    ("sibilance", 6000, 8000),
    ("air", 8000, 16000),
]

# Phase correlation thresholds for mono-compatibility warnings
_CRITICAL_PHASE_THRESHOLD = 0.0    # Below this → severe mono cancellation
_WARNING_PHASE_THRESHOLD = 0.3     # Below this → potential mono issues
_SAFE_PHASE_THRESHOLD = 0.7        # Above this → mono-safe

# Bands that MUST be mono-compatible for professional mixes
_MONO_CRITICAL_BANDS = {"sub", "bass"}

# Maximum acceptable stereo width for low-frequency content
_MAX_LOW_FREQ_WIDTH = 0.25


def _bin_range(band_low: float, band_high: float, sample_rate: int, n_fft: int) -> Tuple[int, int]:
    """Convert frequency range to FFT bin indices."""
    low_bin = max(0, int(band_low * n_fft / sample_rate))
    high_bin = min(n_fft // 2, max(low_bin + 1, int(band_high * n_fft / sample_rate)))
    return low_bin, high_bin


def stereo_image_analysis(
    left: list[float],
    right: list[float],
    sample_rate: int,
    *,
    n_fft: int = 4096,
    hop_length: int = 2048,
) -> dict:
    """Perform full stereo image analysis across frequency bands.

    Returns a dict containing:
      - ``band_correlation``: per-band phase correlation coefficients [-1.0, 1.0]
      - ``band_width``: per-band stereo width coefficients [0.0, ∞)
      - ``mono_compatibility``: per-band mono-compatibility scores [0.0, 1.0]
      - ``overall_correlation``: single broadband correlation value
      - ``overall_width``: single broadband stereo width value
      - ``mono_safe``: boolean, True if no critical mono issues detected
      - ``flags``: list of flagged stereo issues (dicts with label + severity)
      - ``advice``: list of human-readable corrective recommendations
    """
    if left is None or right is None or len(left) == 0 or len(right) == 0 or sample_rate <= 0:
        return _empty_result()

    min_len = min(len(left), len(right))
    if min_len < n_fft:
        return _empty_result()

    # Try numpy path first for performance
    if NUMPY_AVAILABLE:
        return _analyze_numpy(left[:min_len], right[:min_len], sample_rate, n_fft, hop_length)

    return _analyze_fallback(left[:min_len], right[:min_len], sample_rate, n_fft, hop_length)


def _empty_result() -> dict:
    """Return a neutral empty result for insufficient data."""
    band_keys = [name for name, _, _ in BANDS]
    return {
        "band_correlation": {k: 1.0 for k in band_keys},
        "band_width": {k: 0.0 for k in band_keys},
        "mono_compatibility": {k: 1.0 for k in band_keys},
        "overall_correlation": 1.0,
        "overall_width": 0.0,
        "mono_safe": True,
        "flags": [],
        "advice": [],
    }


def _analyze_numpy(
    left: list[float],
    right: list[float],
    sample_rate: int,
    n_fft: int,
    hop_length: int,
) -> dict:
    """Numpy-accelerated STFT stereo analysis."""
    L = np.asarray(left, dtype=np.float64)
    R = np.asarray(right, dtype=np.float64)
    window = np.hanning(n_fft)

    n_frames = max(1, (len(L) - n_fft) // hop_length + 1)

    half = n_fft // 2 + 1
    cross_sum = np.zeros(half)
    L_energy_sum = np.zeros(half)
    R_energy_sum = np.zeros(half)
    M_energy_sum = np.zeros(half)
    S_energy_sum = np.zeros(half)

    for s in range(n_frames):
        start = s * hop_length
        if start + n_fft > len(L):
            break
        L_w = L[start:start + n_fft] * window
        R_w = R[start:start + n_fft] * window

        L_spec = np.fft.rfft(L_w)
        R_spec = np.fft.rfft(R_w)

        M_spec = (L_spec + R_spec) * 0.5
        S_spec = (L_spec - R_spec) * 0.5

        cross_sum += np.real(L_spec * np.conj(R_spec))
        L_energy_sum += np.abs(L_spec) ** 2
        R_energy_sum += np.abs(R_spec) ** 2
        M_energy_sum += np.abs(M_spec) ** 2
        S_energy_sum += np.abs(S_spec) ** 2

    band_correlation = {}
    band_width = {}
    mono_compatibility = {}

    total_cross = 0.0
    total_L = 0.0
    total_R = 0.0
    total_M = 0.0
    total_S = 0.0

    for name, low, high in BANDS:
        lo, hi = _bin_range(low, high, sample_rate, n_fft)
        c = float(np.sum(cross_sum[lo:hi]))
        le = float(np.sum(L_energy_sum[lo:hi]))
        re = float(np.sum(R_energy_sum[lo:hi]))
        me = float(np.sum(M_energy_sum[lo:hi]))
        se = float(np.sum(S_energy_sum[lo:hi]))

        denom = math.sqrt(max(le * re, 1e-12))
        corr = max(-1.0, min(1.0, c / denom))
        band_correlation[name] = round(corr, 4)

        mid_rms = math.sqrt(max(me, 0.0))
        side_rms = math.sqrt(max(se, 0.0))
        width = side_rms / max(mid_rms, 1e-9)
        band_width[name] = round(width, 4)

        # Mono compatibility: how much energy survives summing to mono
        # 1.0 = perfect mono compat, 0.0 = total cancellation
        total_energy = le + re
        if total_energy > 1e-12:
            mono_compat = min(1.0, 4.0 * me / total_energy)
        else:
            mono_compat = 1.0
        mono_compatibility[name] = round(mono_compat, 4)

        total_cross += c
        total_L += le
        total_R += re
        total_M += me
        total_S += se

    overall_denom = math.sqrt(max(total_L * total_R, 1e-12))
    overall_corr = round(max(-1.0, min(1.0, total_cross / overall_denom)), 4)
    overall_mid_rms = math.sqrt(max(total_M, 0.0))
    overall_side_rms = math.sqrt(max(total_S, 0.0))
    overall_width = round(overall_side_rms / max(overall_mid_rms, 1e-9), 4)

    flags, advice = _generate_flags_and_advice(band_correlation, band_width, mono_compatibility)
    mono_safe = not any(f.get("severity") == "critical" for f in flags)

    return {
        "band_correlation": band_correlation,
        "band_width": band_width,
        "mono_compatibility": mono_compatibility,
        "overall_correlation": overall_corr,
        "overall_width": overall_width,
        "mono_safe": mono_safe,
        "flags": flags,
        "advice": advice,
    }


def _analyze_fallback(
    left: list[float],
    right: list[float],
    sample_rate: int,
    n_fft: int,
    hop_length: int,
) -> dict:
    """Pure-Python fallback STFT stereo analysis (slower, no numpy)."""
    from cmath import exp, pi as cpi

    def _fft(values: list[complex]) -> list[complex]:
        n = len(values)
        if n <= 1:
            return values
        even = _fft(values[0::2])
        odd = _fft(values[1::2])
        factors = [exp(-2j * cpi * k / n) * odd[k] for k in range(n // 2)]
        return [even[k] + factors[k] for k in range(n // 2)] + [even[k] - factors[k] for k in range(n // 2)]

    # Ensure n_fft is a power of 2
    actual_n = 1
    while actual_n * 2 <= min(n_fft, len(left)):
        actual_n *= 2
    if actual_n < 256:
        return _empty_result()

    hann = [0.5 - 0.5 * math.cos(2.0 * math.pi * i / (actual_n - 1)) for i in range(actual_n)]
    n_frames = max(1, (len(left) - actual_n) // hop_length + 1)
    # Limit frames for performance in pure-Python
    n_frames = min(n_frames, 16)

    half = actual_n // 2

    cross_sum = [0.0] * half
    L_energy_sum = [0.0] * half
    R_energy_sum = [0.0] * half
    M_energy_sum = [0.0] * half
    S_energy_sum = [0.0] * half

    for s in range(n_frames):
        start = s * hop_length
        if start + actual_n > len(left):
            break

        L_w = [complex(left[start + i] * hann[i], 0) for i in range(actual_n)]
        R_w = [complex(right[start + i] * hann[i], 0) for i in range(actual_n)]

        L_fft = _fft(L_w)[:half]
        R_fft = _fft(R_w)[:half]

        for i in range(half):
            l_v = L_fft[i]
            r_v = R_fft[i]
            m_v = (l_v + r_v) * 0.5
            s_v = (l_v - r_v) * 0.5

            cross_sum[i] += (l_v * r_v.conjugate()).real
            L_energy_sum[i] += l_v.real ** 2 + l_v.imag ** 2
            R_energy_sum[i] += r_v.real ** 2 + r_v.imag ** 2
            M_energy_sum[i] += m_v.real ** 2 + m_v.imag ** 2
            S_energy_sum[i] += s_v.real ** 2 + s_v.imag ** 2

    band_correlation = {}
    band_width = {}
    mono_compatibility = {}

    total_cross = 0.0
    total_L = 0.0
    total_R = 0.0
    total_M = 0.0
    total_S = 0.0

    for name, low, high in BANDS:
        lo, hi = _bin_range(low, high, sample_rate, actual_n)
        hi = min(hi, half)

        c = sum(cross_sum[lo:hi])
        le = sum(L_energy_sum[lo:hi])
        re = sum(R_energy_sum[lo:hi])
        me = sum(M_energy_sum[lo:hi])
        se = sum(S_energy_sum[lo:hi])

        denom = math.sqrt(max(le * re, 1e-12))
        corr = max(-1.0, min(1.0, c / denom))
        band_correlation[name] = round(corr, 4)

        mid_rms = math.sqrt(max(me, 0.0))
        side_rms = math.sqrt(max(se, 0.0))
        width = side_rms / max(mid_rms, 1e-9)
        band_width[name] = round(width, 4)

        total_energy = le + re
        if total_energy > 1e-12:
            mono_compat = min(1.0, 4.0 * me / total_energy)
        else:
            mono_compat = 1.0
        mono_compatibility[name] = round(mono_compat, 4)

        total_cross += c
        total_L += le
        total_R += re
        total_M += me
        total_S += se

    overall_denom = math.sqrt(max(total_L * total_R, 1e-12))
    overall_corr = round(max(-1.0, min(1.0, total_cross / overall_denom)), 4)
    overall_mid_rms = math.sqrt(max(total_M, 0.0))
    overall_side_rms = math.sqrt(max(total_S, 0.0))
    overall_width = round(overall_side_rms / max(overall_mid_rms, 1e-9), 4)

    flags, advice = _generate_flags_and_advice(band_correlation, band_width, mono_compatibility)
    mono_safe = not any(f.get("severity") == "critical" for f in flags)

    return {
        "band_correlation": band_correlation,
        "band_width": band_width,
        "mono_compatibility": mono_compatibility,
        "overall_correlation": overall_corr,
        "overall_width": overall_width,
        "mono_safe": mono_safe,
        "flags": flags,
        "advice": advice,
    }


def _generate_flags_and_advice(
    band_correlation: dict[str, float],
    band_width: dict[str, float],
    mono_compatibility: dict[str, float],
) -> Tuple[list[dict], list[str]]:
    """Generate stereo imaging flags and corrective advice from per-band metrics."""
    flags: list[dict] = []
    advice: list[str] = []

    # --- Low-frequency mono compatibility checks ---
    for band_name in _MONO_CRITICAL_BANDS:
        corr = band_correlation.get(band_name, 1.0)
        width = band_width.get(band_name, 0.0)
        if corr < _CRITICAL_PHASE_THRESHOLD:
            flags.append({
                "label": "Low-End Phase Cancellation",
                "band": band_name,
                "severity": "critical",
                "correlation": corr,
                "detail": (
                    f"The {band_name} band has a phase correlation of {corr:.2f}, "
                    f"indicating severe L/R phase opposition. This content will "
                    f"cancel almost entirely when summed to mono."
                ),
            })
            advice.append(
                f"CRITICAL: {band_name.replace('_', ' ').title()} ({_band_freq_label(band_name)}) "
                f"has phase correlation of {corr:.2f}. Use a utility plug-in to force mono "
                f"below 100 Hz to prevent phase cancellation in mono playback systems."
            )
        elif corr < _WARNING_PHASE_THRESHOLD:
            flags.append({
                "label": "Low-End Stereo Risk",
                "band": band_name,
                "severity": "warning",
                "correlation": corr,
                "detail": (
                    f"The {band_name} band has a stereo width coefficient of {width:.2f} "
                    f"with phase correlation of {corr:.2f}. This can cause phase smear "
                    f"in mono playback."
                ),
            })
            advice.append(
                f"WARNING: {band_name.replace('_', ' ').title()} ({_band_freq_label(band_name)}) "
                f"has a stereo width coefficient of {width:.2f}. Suggest using a utility "
                f"plug-in to force mono below 100 Hz."
            )

        if width > _MAX_LOW_FREQ_WIDTH and band_name in _MONO_CRITICAL_BANDS:
            if not any(f.get("band") == band_name for f in flags):
                flags.append({
                    "label": "Excessive Low-End Width",
                    "band": band_name,
                    "severity": "warning",
                    "width": width,
                    "detail": (
                        f"The {band_name} band has a stereo width of {width:.2f}. "
                        f"Low frequencies should generally be centered for maximum "
                        f"punch and mono compatibility."
                    ),
                })
                advice.append(
                    f"The {band_name} band has excessive stereo width ({width:.2f}). "
                    f"Narrow the stereo image below 150 Hz for a tighter, more "
                    f"professional low-end."
                )

    # --- Mid/high frequency phase issues ---
    for name, _, _ in BANDS:
        if name in _MONO_CRITICAL_BANDS:
            continue  # Already handled above
        corr = band_correlation.get(name, 1.0)
        if corr < _CRITICAL_PHASE_THRESHOLD:
            flags.append({
                "label": "Phase Cancellation Risk",
                "band": name,
                "severity": "warning",
                "correlation": corr,
                "detail": (
                    f"The {name.replace('_', ' ')} band has a phase correlation of "
                    f"{corr:.2f}. Elements in this range will lose significant energy "
                    f"in mono playback."
                ),
            })
            advice.append(
                f"The {name.replace('_', ' ')} band ({_band_freq_label(name)}) has "
                f"near-zero or negative phase correlation ({corr:.2f}). Check for "
                f"comb-filtering from unaligned delays or excessive stereo widening "
                f"on instruments in this range."
            )

    # --- Overall mono compatibility ---
    overall_corr = sum(band_correlation.values()) / max(len(band_correlation), 1)
    if overall_corr < _WARNING_PHASE_THRESHOLD:
        flags.append({
            "label": "Mono Compatibility Risk",
            "band": "overall",
            "severity": "warning",
            "correlation": overall_corr,
            "detail": (
                f"The overall stereo correlation is {overall_corr:.2f}. This mix "
                f"may sound significantly different or thinner on mono playback "
                f"systems (phone speakers, club mono subs, Bluetooth speakers)."
            ),
        })
        advice.append(
            f"Overall mono compatibility is low (avg correlation: {overall_corr:.2f}). "
            f"Check your mix in mono to identify the elements that lose the most energy."
        )

    return flags, advice


def _band_freq_label(band_name: str) -> str:
    """Return a human-readable frequency label for a band."""
    labels = {
        "sub": "20-60 Hz",
        "bass": "60-150 Hz",
        "low_mids": "150-400 Hz",
        "mids": "400 Hz - 2 kHz",
        "presence": "2-6 kHz",
        "sibilance": "6-8 kHz",
        "air": "8-16 kHz",
    }
    return labels.get(band_name, band_name)


def stereo_analysis_summary(result: dict) -> str:
    """Generate a compact text summary suitable for injection into KENN context."""
    lines = ["[Stereo Image Analysis]"]
    lines.append(f"Overall Correlation: {result.get('overall_correlation', 1.0):.2f}")
    lines.append(f"Overall Width: {result.get('overall_width', 0.0):.2f}")
    lines.append(f"Mono Safe: {'Yes' if result.get('mono_safe', True) else 'No'}")

    band_corr = result.get("band_correlation", {})
    band_width = result.get("band_width", {})
    if band_corr:
        lines.append("Per-band correlation:")
        for name, _, _ in BANDS:
            c = band_corr.get(name, 1.0)
            w = band_width.get(name, 0.0)
            marker = " ⚠" if c < _WARNING_PHASE_THRESHOLD else ""
            lines.append(f"  {name}: corr={c:.2f}, width={w:.2f}{marker}")

    for a in result.get("advice", []):
        lines.append(f"→ {a}")

    return "\n".join(lines)
