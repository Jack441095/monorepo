from __future__ import annotations

import importlib.util
import math
from cmath import exp, pi

torch = None
TORCH_AVAILABLE = importlib.util.find_spec("torch") is not None


def _load_torch():
    global torch, TORCH_AVAILABLE
    if torch is not None:
        return torch
    if not TORCH_AVAILABLE:
        raise ImportError("Torch is unavailable")
    try:
        import torch as torch_module
    except ImportError:
        TORCH_AVAILABLE = False
        raise
    torch = torch_module
    return torch

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

from audio_analysis.analysis_core.dsp_metrics import band_ratios, percentile, spectral_bands

BANDS = [
    ("sub", 20, 60),
    ("bass", 60, 150),
    ("low_mids", 150, 400),
    ("mids", 400, 2000),
    ("presence", 2000, 6000),
    ("sibilance", 6000, 8000),
    ("air", 8000, 16000),
]


def metric_float(value: object, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def rms_db(samples: list[float]) -> float:
    if not samples:
        return -99.0
    rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
    return 20 * math.log10(max(rms, 1e-9))


def windowed_rms_values(samples: list[float], sample_rate: float, *, window_seconds: float = 0.4) -> list[float]:
    if samples is None or (hasattr(samples, "__len__") and len(samples) == 0) or sample_rate <= 0:
        return []
    window = max(32, int(sample_rate * window_seconds))
    if len(samples) < window:
        return [rms_db(samples)]
    hop = max(1, window // 2)
    if NUMPY_AVAILABLE:
        # Vectorised equivalent of the per-window rms_db loop (profiling showed
        # ~0.8M genexpr calls/analysis): one cumulative sum of squares gives every
        # fixed-size window's mean power. Same values as the loop, differing only
        # in float summation order (golden-verified).
        arr = np.asarray(samples, dtype=np.float64)
        starts = np.arange(0, len(arr) - window + 1, hop)
        csum = np.concatenate(([0.0], np.cumsum(arr * arr)))
        mean_power = (csum[starts + window] - csum[starts]) / window
        rms = np.sqrt(mean_power)
        return (20.0 * np.log10(np.maximum(rms, 1e-9))).tolist()
    values = []
    for start in range(0, len(samples) - window + 1, hop):
        values.append(rms_db(samples[start : start + window]))
    return values



def stereo_metrics(left, right) -> dict:
    # NB: guard with len(), not `not left` — the latter raises on numpy arrays
    # (ambiguous truth value), which is what callers now pass in.
    if left is None or right is None or len(left) == 0 or len(right) == 0:
        return {"stereo_correlation": 1.0, "stereo_width_ratio": 0.0}
    if NUMPY_AVAILABLE:
        # Vectorised equivalent of the pure-Python loop below (profiling showed
        # the zip loop at ~0.8M genexpr calls/analysis). np.dot differs from the
        # sequential sums only in floating-point summation order; verified equal
        # against the golden-metrics snapshot.
        left_arr = np.asarray(left, dtype=np.float64)
        right_arr = np.asarray(right, dtype=np.float64)
        n = min(left_arr.size, right_arr.size)  # zip() truncated to the shorter channel
        left_arr = left_arr[:n]
        right_arr = right_arr[:n]
        left_energy = float(left_arr @ left_arr)
        right_energy = float(right_arr @ right_arr)
        correlation = float(left_arr @ right_arr) / math.sqrt(max(left_energy * right_energy, 1e-12))
        mid = (left_arr + right_arr) * 0.5
        side = (left_arr - right_arr) * 0.5
        mid_rms = math.sqrt(float(mid @ mid) / n)
        side_rms = math.sqrt(float(side @ side) / n)
        return {
            "stereo_correlation": round(max(-1.0, min(1.0, correlation)), 3),
            "stereo_width_ratio": round(side_rms / max(mid_rms, 1e-9), 3),
        }
    pairs = list(zip(left, right))
    left_energy = sum(left_value * left_value for left_value, _right_value in pairs)
    right_energy = sum(right_value * right_value for _left_value, right_value in pairs)
    correlation = sum(left_value * right_value for left_value, right_value in pairs) / math.sqrt(
        max(left_energy * right_energy, 1e-12)
    )
    mid = [(left_value + right_value) * 0.5 for left_value, right_value in pairs]
    side = [(left_value - right_value) * 0.5 for left_value, right_value in pairs]
    mid_rms = math.sqrt(sum(value * value for value in mid) / len(mid))
    side_rms = math.sqrt(sum(value * value for value in side) / len(side))
    return {
        "stereo_correlation": round(max(-1.0, min(1.0, correlation)), 3),
        "stereo_width_ratio": round(side_rms / max(mid_rms, 1e-9), 3),
    }



def _fft(values: list[complex]) -> list[complex]:
    n = len(values)
    if n <= 1:
        return values
    even = _fft(values[0::2])
    odd = _fft(values[1::2])
    factors = [exp(-2j * pi * k / n) * odd[k] for k in range(n // 2)]
    return [even[k] + factors[k] for k in range(n // 2)] + [even[k] - factors[k] for k in range(n // 2)]



def analyze_spectrum_and_correlation_fallback(
    left: list[float],
    right: list[float],
    sample_rate: int
) -> tuple[dict, dict, dict]:
    n_fft = 4096
    num_slices = 16
    step = max(1, (len(left) - n_fft) // num_slices)
    hann = [0.5 - 0.5 * math.cos((2.0 * math.pi * i) / (n_fft - 1)) for i in range(n_fft)]
    
    M_mag_sum = [0.0] * (n_fft // 2)
    S_mag_sum = [0.0] * (n_fft // 2)
    cross_sum = [0.0] * (n_fft // 2)
    L_energy_sum = [0.0] * (n_fft // 2)
    R_energy_sum = [0.0] * (n_fft // 2)
    
    count = 0
    for s in range(num_slices):
        start = s * step
        if start + n_fft > len(left):
            break
        L_window = [left[start + i] * hann[i] for i in range(n_fft)]
        R_window = [right[start + i] * hann[i] for i in range(n_fft)]
        
        L_complex = [complex(val, 0) for val in L_window]
        R_complex = [complex(val, 0) for val in R_window]
        
        L_fft = _fft(L_complex)[:n_fft // 2]
        R_fft = _fft(R_complex)[:n_fft // 2]
        
        for i in range(n_fft // 2):
            l_val = L_fft[i]
            r_val = R_fft[i]
            
            m_val = (l_val + r_val) * 0.5
            s_val = (l_val - r_val) * 0.5
            
            M_mag_sum[i] += abs(m_val)
            S_mag_sum[i] += abs(s_val)
            
            cross_sum[i] += (l_val * r_val.conjugate()).real
            L_energy_sum[i] += l_val.real**2 + l_val.imag**2
            R_energy_sum[i] += r_val.real**2 + r_val.imag**2
            
        count += 1
        
    if count == 0:
        count = 1
        
    M_mag = [val / count for val in M_mag_sum]
    S_mag = [val / count for val in S_mag_sum]
    
    mid_bands = band_ratios(M_mag, sample_rate, n_fft)
    side_bands = band_ratios(S_mag, sample_rate, n_fft)
    
    correlation_bands = {}
    for name, low, high in BANDS:
        low_bin = max(0, int(low * n_fft / sample_rate))
        high_bin = min(len(L_energy_sum), max(low_bin + 1, int(high * n_fft / sample_rate)))
        
        sum_cross = sum(cross_sum[low_bin:high_bin])
        sum_L = sum(L_energy_sum[low_bin:high_bin])
        sum_R = sum(R_energy_sum[low_bin:high_bin])
        
        denom = math.sqrt(max(sum_L * sum_R, 1e-12))
        correlation_bands[name] = round(max(-1.0, min(1.0, sum_cross / denom)), 3)
        
    return mid_bands, side_bands, correlation_bands


def analyze_spectrum_and_correlation_numpy(
    L: np.ndarray,
    R: np.ndarray,
    sample_rate: int
) -> tuple[dict, dict, dict]:
    n_fft = 4096
    hop_length = 2048
    window = np.hanning(n_fft)
    
    n_frames = (len(L) - n_fft) // hop_length + 1
    if n_frames <= 0:
        return {}, {}, {}
        
    M_mag_sum = np.zeros(n_fft // 2 + 1)
    S_mag_sum = np.zeros(n_fft // 2 + 1)
    cross_sum = np.zeros(n_fft // 2 + 1)
    L_energy_sum = np.zeros(n_fft // 2 + 1)
    R_energy_sum = np.zeros(n_fft // 2 + 1)
    
    for s in range(n_frames):
        start = s * hop_length
        L_window = L[start : start + n_fft] * window
        R_window = R[start : start + n_fft] * window
        
        L_spec = np.fft.rfft(L_window)
        R_spec = np.fft.rfft(R_window)
        
        M_spec = (L_spec + R_spec) * 0.5
        S_spec = (L_spec - R_spec) * 0.5
        
        M_mag_sum += np.abs(M_spec)
        S_mag_sum += np.abs(S_spec)
        cross_sum += np.real(L_spec * np.conj(R_spec))
        L_energy_sum += np.abs(L_spec) ** 2
        R_energy_sum += np.abs(R_spec) ** 2
        
    M_mag = (M_mag_sum / n_frames).tolist()
    S_mag = (S_mag_sum / n_frames).tolist()
    
    mid_bands = band_ratios(M_mag, sample_rate, n_fft)
    side_bands = band_ratios(S_mag, sample_rate, n_fft)
    
    cross = cross_sum / n_frames
    L_energy = L_energy_sum / n_frames
    R_energy = R_energy_sum / n_frames
    
    correlation_bands = {}
    for name, low, high in BANDS:
        low_bin = max(0, int(low * n_fft / sample_rate))
        high_bin = min(len(L_energy), max(low_bin + 1, int(high * n_fft / sample_rate)))
        
        sum_cross = np.sum(cross[low_bin:high_bin])
        sum_L = np.sum(L_energy[low_bin:high_bin])
        sum_R = np.sum(R_energy[low_bin:high_bin])
        
        denom = math.sqrt(max(sum_L * sum_R, 1e-12))
        correlation_bands[name] = round(max(-1.0, min(1.0, sum_cross / denom)), 3)
        
    return mid_bands, side_bands, correlation_bands


def analyze_spectrum_and_correlation(
    left_samples: list[float] | torch.Tensor,
    right_samples: list[float] | torch.Tensor,
    sample_rate: int
) -> tuple[dict, dict, dict]:
    if NUMPY_AVAILABLE:
        try:
            l_np = left_samples.numpy() if hasattr(left_samples, "numpy") else np.asarray(left_samples, dtype=np.float64)
            r_np = right_samples.numpy() if hasattr(right_samples, "numpy") else np.asarray(right_samples, dtype=np.float64)
            return analyze_spectrum_and_correlation_numpy(l_np, r_np, sample_rate)
        except Exception:
            pass

    torch_inputs = (
        left_samples.__class__.__module__.startswith("torch")
        and right_samples.__class__.__module__.startswith("torch")
    )
    if TORCH_AVAILABLE and torch_inputs:
        try:
            _load_torch()
            L = left_samples
            R = right_samples
            n_fft = 4096
            hop_length = 2048
            window = torch.hann_window(n_fft, device=L.device)
            
            L_spec = torch.stft(L, n_fft=n_fft, hop_length=hop_length, window=window, return_complex=True)
            R_spec = torch.stft(R, n_fft=n_fft, hop_length=hop_length, window=window, return_complex=True)
            
            M_spec = (L_spec + R_spec) * 0.5
            S_spec = (L_spec - R_spec) * 0.5
            
            M_mag = torch.mean(torch.abs(M_spec), dim=1).tolist()
            S_mag = torch.mean(torch.abs(S_spec), dim=1).tolist()
            
            mid_bands = band_ratios(M_mag, sample_rate, n_fft)
            side_bands = band_ratios(S_mag, sample_rate, n_fft)
            
            cross = torch.mean(torch.real(L_spec * torch.conj(R_spec)), dim=1)
            L_energy = torch.mean(torch.abs(L_spec) ** 2, dim=1)
            R_energy = torch.mean(torch.abs(R_spec) ** 2, dim=1)
            
            correlation_bands = {}
            for name, low, high in BANDS:
                low_bin = max(0, int(low * n_fft / sample_rate))
                high_bin = min(len(L_energy), max(low_bin + 1, int(high * n_fft / sample_rate)))
                
                sum_cross = torch.sum(cross[low_bin:high_bin]).item()
                sum_L = torch.sum(L_energy[low_bin:high_bin]).item()
                sum_R = torch.sum(R_energy[low_bin:high_bin]).item()
                
                denom = math.sqrt(max(sum_L * sum_R, 1e-12))
                correlation_bands[name] = round(max(-1.0, min(1.0, sum_cross / denom)), 3)
                
            return mid_bands, side_bands, correlation_bands
        except Exception:
            pass
            
    l_list = left_samples.tolist() if hasattr(left_samples, "tolist") else list(left_samples)
    r_list = right_samples.tolist() if hasattr(right_samples, "tolist") else list(right_samples)
    return analyze_spectrum_and_correlation_fallback(l_list, r_list, sample_rate)




def tonal_balance_summary(bands: dict, perceived: dict, features: dict) -> dict:
    low_end = round(metric_float(bands.get("sub")) + metric_float(bands.get("bass")), 4)
    body = round(metric_float(bands.get("low_mids")) + metric_float(bands.get("mids")), 4)
    clarity = round(metric_float(bands.get("presence")) + metric_float(bands.get("sibilance")) + metric_float(bands.get("air")), 4)
    perceived_clarity = round(metric_float(perceived.get("presence")) + metric_float(perceived.get("sibilance")) + metric_float(perceived.get("air")), 4)
    outliers: list[str] = []
    if low_end > 0.5:
        outliers.append("low end is dominant")
    elif low_end < 0.06:
        outliers.append("low end is light")
    if body > 0.72:
        outliers.append("mid body is dominant")
    if clarity > 0.42:
        outliers.append("top/presence is forward")
    elif clarity < 0.05 and low_end < 0.35:
        outliers.append("presence is low")
    centroid = metric_float(features.get("centroid_hz"))
    if low_end > 0.5:
        label = "Low-weighted"
    elif clarity > 0.42 or centroid > 3500:
        label = "Bright"
    elif centroid and centroid < 250:
        label = "Low-weighted"
    elif body > max(low_end, clarity):
        label = "Mid-focused"
    else:
        label = "Balanced"
    summary = f"{label} tonal balance"
    if outliers:
        summary += f"; {', '.join(outliers)}."
    else:
        summary += "; no single broad band dominates the first-pass reading."
    return {
        "profile": label,
        "low_end_share": low_end,
        "body_share": body,
        "clarity_share": clarity,
        "perceived_clarity_share": perceived_clarity,
        "outliers": outliers,
        "summary": summary,
    }


def dynamic_profile(samples: list[float], sample_rate: float, peak_db: float, rms_db: float, window_values: list[float]) -> dict:
    short_values = windowed_rms_values(samples, sample_rate, window_seconds=0.05)
    short_range = round(percentile(short_values, 0.95) - percentile(short_values, 0.10), 2) if short_values else 0.0
    section_range = round(percentile(window_values, 0.95) - percentile(window_values, 0.10), 2) if window_values else 0.0
    transient_margin = round(peak_db - max(window_values or [rms_db]), 2)
    crest = round(peak_db - rms_db, 2)
    if crest < 6 or transient_margin < 3:
        label = "Compressed"
    elif transient_margin > 12 and crest > 12:
        label = "Spiky"
    elif section_range > 10:
        label = "Uneven"
    else:
        label = "Controlled"
    return {
        "profile": label,
        "crest_factor_db": crest,
        "transient_margin_db": transient_margin,
        "short_term_range_db": short_range,
        "section_range_db": section_range,
        "summary": (
            f"{label} dynamics: {crest:.1f} dB crest, "
            f"{transient_margin:.1f} dB peak-to-loud-section margin."
        ),
    }


def section_analysis(
    samples: list[float],
    left_samples: list[float],
    right_samples: list[float],
    sample_rate: float,
    *,
    max_sections: int = 12,
) -> dict:
    if not samples or sample_rate <= 0:
        return {"sections": [], "highlights": {}, "summary": "No section analysis available."}
    duration = len(samples) / sample_rate
    section_count = max(1, min(max_sections, int(math.ceil(duration / 8.0))))
    section_len = max(1, len(samples) // section_count)
    sections = []
    for idx in range(section_count):
        start = idx * section_len
        end = len(samples) if idx == section_count - 1 else min(len(samples), (idx + 1) * section_len)
        segment = samples[start:end]
        if not segment:
            continue
        left = left_samples[start:end] if left_samples else segment
        right = right_samples[start:end] if right_samples else left
        peak = max(abs(value) for value in segment) or 1e-9
        rms = math.sqrt(sum(value * value for value in segment) / len(segment))
        rms_db = 20 * math.log10(max(rms, 1e-9))
        peak_db = 20 * math.log10(max(peak, 1e-9))
        bands = spectral_bands(segment, int(sample_rate), size=min(4096, len(segment)))
        stereo = stereo_metrics(left, right)
        low_end = round(metric_float(bands.get("sub")) + metric_float(bands.get("bass")), 4)
        presence = round(
            metric_float(bands.get("presence")) + metric_float(bands.get("sibilance")) + metric_float(bands.get("air")),
            4,
        )
        sections.append(
            {
                "index": idx,
                "label": f"Section {idx + 1}",
                "start_seconds": round(start / sample_rate, 2),
                "end_seconds": round(end / sample_rate, 2),
                "rms_dbfs": round(rms_db, 2),
                "peak_dbfs": round(peak_db, 2),
                "crest_factor_db": round(peak_db - rms_db, 2),
                "low_end_share": low_end,
                "presence_share": presence,
                "stereo_correlation": stereo.get("stereo_correlation"),
                "bands": bands,
            }
        )
    if not sections:
        return {"sections": [], "highlights": {}, "summary": "No section analysis available."}

    loudest = max(sections, key=lambda item: metric_float(item.get("rms_dbfs"), -999.0))
    harshest = max(sections, key=lambda item: metric_float(item.get("presence_share")))
    low_end = max(sections, key=lambda item: metric_float(item.get("low_end_share")))
    lowest_corr = min(sections, key=lambda item: metric_float(item.get("stereo_correlation"), 1.0))
    jumps = []
    for prev, current in zip(sections, sections[1:]):
        jumps.append(
            {
                "from_section": prev["index"],
                "to_section": current["index"],
                "delta_db": round(metric_float(current.get("rms_dbfs")) - metric_float(prev.get("rms_dbfs")), 2),
            }
        )
    biggest_jump = max(jumps, key=lambda item: abs(metric_float(item.get("delta_db"))), default=None)
    highlights = {
        "loudest_section": loudest,
        "presence_heaviest_section": harshest,
        "low_end_heaviest_section": low_end,
        "lowest_correlation_section": lowest_corr,
        "biggest_loudness_jump": biggest_jump,
    }
    return {
        "sections": sections,
        "highlights": highlights,
        "summary": (
            f"Loudest: {loudest['label']} ({loudest['rms_dbfs']} dBFS RMS). "
            f"Lowest stereo correlation: {lowest_corr['label']} ({lowest_corr['stereo_correlation']})."
        ),
    }


def stereo_asymmetry(
    left: list[float],
    right: list[float],
    sample_rate: float,
    *,
    window_seconds: float = 0.4,
) -> dict:
    """Measure real L/R channel imbalance, independent of phase correlation.

    ``stereo_correlation``/``stereo_width_ratio`` (see :func:`stereo_metrics`)
    describe *how similar* L and R are and how much side-channel energy
    exists — a mix can be perfectly correlated (mono-compatible) and still
    be loud on one side the whole track (e.g. a panned lead vocal double, an
    unbalanced hardware chain, or an accidental gain mismatch on export).
    This function measures that imbalance directly via two independent,
    complementary readings:

    1. ``level_asymmetry_db`` — the whole-track RMS level difference between
       channels: ``20*log10(rms_R / rms_L)``. Positive = right louder.
    2. ``mid_side_energy_ratio_db`` — ``10*log10(side_energy / mid_energy)``
       where ``mid = (L+R)/2`` and ``side = (L-R)/2``. This is the standard
       M/S decomposition; a high side/mid ratio means a lot of the track's
       energy is *not* shared between channels (either intentional width or
       imbalance), while asymmetry specifically shows up as a **windowed
       balance metric** below rather than in this ratio alone.
    3. ``windowed_balance`` — per-window (``window_seconds`` long, default
       400 ms to match loudness-metering convention) balance in [-1, 1]
       computed the same way as :func:`stereo_correlation_timeline`'s
       ``balance`` series (``(R_energy - L_energy) / (R_energy + L_energy)``
       per window), from which we derive:
         - ``mean_balance`` — average signed balance (persistent bias)
         - ``balance_std`` — how much the balance wanders over time
           (large values mean the imbalance is localized, e.g. one loud
           panned event, rather than a persistent whole-track skew)
         - ``max_abs_balance`` — worst single-window imbalance

    A mix with ``abs(mean_balance)`` above ~0.15 (roughly a >=1.5 dB
    persistent level difference) or ``level_asymmetry_db`` beyond +/-1.0 dB
    is flagged as asymmetric — thresholds chosen to be well above normal
    single-hardware-chain gain tolerances (~0.1-0.3 dB) but below
    deliberate wide-stereo effects, which show up mostly as
    ``mid_side_energy_ratio_db`` (width), not persistent one-sided balance.
    """
    empty = {
        "level_asymmetry_db": 0.0,
        "mid_side_energy_ratio_db": 0.0,
        "mean_balance": 0.0,
        "balance_std": 0.0,
        "max_abs_balance": 0.0,
        "asymmetric": False,
        "louder_channel": "none",
        "summary": "No stereo asymmetry data available.",
    }
    if not left or not right or sample_rate <= 0:
        return empty
    n = min(len(left), len(right))
    left = left[:n]
    right = right[:n]

    left_rms = math.sqrt(sum(v * v for v in left) / n) if n else 0.0
    right_rms = math.sqrt(sum(v * v for v in right) / n) if n else 0.0
    level_asymmetry_db = round(
        20.0 * math.log10(max(right_rms, 1e-9) / max(left_rms, 1e-9)), 3
    )

    mid = [(l_val + r_val) * 0.5 for l_val, r_val in zip(left, right)]
    side = [(l_val - r_val) * 0.5 for l_val, r_val in zip(left, right)]
    mid_energy = sum(v * v for v in mid)
    side_energy = sum(v * v for v in side)
    mid_side_ratio_db = round(
        10.0 * math.log10(max(side_energy, 1e-12) / max(mid_energy, 1e-12)), 3
    )

    window = max(1, int(sample_rate * window_seconds))
    balances: list[float] = []
    for start in range(0, n - window + 1, window):
        l_chunk = left[start : start + window]
        r_chunk = right[start : start + window]
        l_energy = sum(v * v for v in l_chunk)
        r_energy = sum(v * v for v in r_chunk)
        denom = l_energy + r_energy
        if denom > 1e-12:
            balances.append((r_energy - l_energy) / denom)

    if balances:
        mean_balance = sum(balances) / len(balances)
        variance = sum((b - mean_balance) ** 2 for b in balances) / len(balances)
        balance_std = math.sqrt(variance)
        max_abs_balance = max(abs(b) for b in balances)
    else:
        mean_balance = balance_std = max_abs_balance = 0.0

    asymmetric = abs(mean_balance) > 0.15 or abs(level_asymmetry_db) > 1.0
    if abs(level_asymmetry_db) < 0.05:
        louder_channel = "none"
    elif level_asymmetry_db > 0:
        louder_channel = "right"
    else:
        louder_channel = "left"

    if asymmetric:
        summary = (
            f"Persistent {louder_channel}-channel bias: {level_asymmetry_db:+.2f} dB level "
            f"difference (mean windowed balance {mean_balance:+.2f})."
        )
    else:
        summary = f"L/R levels are balanced ({level_asymmetry_db:+.2f} dB difference)."

    return {
        "level_asymmetry_db": level_asymmetry_db,
        "mid_side_energy_ratio_db": mid_side_ratio_db,
        "mean_balance": round(mean_balance, 4),
        "balance_std": round(balance_std, 4),
        "max_abs_balance": round(max_abs_balance, 4),
        "asymmetric": asymmetric,
        "louder_channel": louder_channel,
        "summary": summary,
    }


def stereo_field_summary(metrics: dict) -> dict:
    side_bands = metrics.get("side_bands") or {}
    correlation_bands = metrics.get("correlation_bands") or {}
    low_side = round(metric_float(side_bands.get("sub")) + metric_float(side_bands.get("bass")), 4)
    low_corr = min(metric_float(correlation_bands.get("sub"), 1.0), metric_float(correlation_bands.get("bass"), 1.0))
    width = metric_float(metrics.get("stereo_width_ratio"))
    corr = metric_float(metrics.get("stereo_correlation"), 1.0)
    if corr < 0.2 or low_corr < 0.4:
        image = "Phase risk"
    elif width > 0.9:
        image = "Very wide"
    elif width < 0.08:
        image = "Narrow"
    else:
        image = "Stable"
    low_end = "mono-safe" if low_side <= 0.04 and low_corr >= 0.7 else "check low-end mono"
    return {
        "image": image,
        "low_side_share": low_side,
        "low_band_correlation": round(low_corr, 3),
        "low_end": low_end,
        "summary": f"{image} stereo image; low end is {low_end}.",
    }


def ms_band_ratio(mid_bands: dict, side_bands: dict) -> dict:
    """Per-band Side/Mid spectral-share ratio.

    Both ``mid_bands`` and ``side_bands`` are independently normalised so that
    each sums to 1.0 within its own M or S spectrum (output of
    ``band_ratios()``).  The ratio therefore expresses relative spectral share
    rather than absolute energy — a value above 1.0 means the Side channel
    devotes a proportionally larger share of its energy to that band than the
    Mid channel does.
    """
    return {
        name: round(metric_float(side_bands.get(name)) / max(metric_float(mid_bands.get(name)), 1e-6), 3)
        for name, _low, _high in BANDS
    }


def stereo_correlation_timeline(
    left: list[float],
    right: list[float],
    sample_rate: float,
    *,
    window_seconds: float = 0.1,
    dip_threshold: float = 0.2,
    vectorscope_points: int = 2000,
) -> dict:
    """Time-windowed L/R correlation, stereo balance, phase-dip detection,
    and downsampled vectorscope scatter data.

    Uses non-overlapping windows of ``window_seconds`` duration.  Returns a
    dict suitable for direct inclusion in the mix-review report metrics:

    ``timestamps``           — window start times in seconds
    ``correlation``          — per-window L/R correlation in [-1, 1]
    ``balance``              — per-window L/R level balance in [-1, 1]
                               (positive = right-heavy)
    ``dip_events``           — list of {start_seconds, end_seconds,
                               duration_seconds, min_correlation} for
                               contiguous runs below ``dip_threshold``
    ``vectorscope_points``   — list of [x, y] pairs in standard 45°-rotated
                               M/S coordinates (x = Side, y = Mid), down-
                               sampled to at most ``vectorscope_points`` pairs
    """
    empty: dict = {
        "window_seconds": window_seconds,
        "timestamps": [],
        "correlation": [],
        "balance": [],
        "dip_events": [],
        "vectorscope_points": [],
    }
    if not left or not right or sample_rate <= 0:
        return empty

    n = min(len(left), len(right))
    window = max(1, int(sample_rate * window_seconds))

    timestamps: list[float] = []
    correlation: list[float] = []
    balance: list[float] = []

    for start in range(0, n - window + 1, window):
        l_chunk = left[start : start + window]
        r_chunk = right[start : start + window]
        l_energy = sum(v * v for v in l_chunk)
        r_energy = sum(v * v for v in r_chunk)
        cross = sum(lv * rv for lv, rv in zip(l_chunk, r_chunk))
        denom = math.sqrt(max(l_energy * r_energy, 0.0))
        corr = max(-1.0, min(1.0, cross / denom)) if denom > 1e-9 else 1.0
        bal = (r_energy - l_energy) / max(r_energy + l_energy, 1e-12)
        timestamps.append(round(start / sample_rate, 3))
        correlation.append(round(corr, 3))
        balance.append(round(bal, 3))

    if not timestamps:
        return empty

    # --- dip-event detection -------------------------------------------
    dip_events: list[dict] = []
    in_dip = False
    dip_start_idx = 0
    for i, corr in enumerate(correlation):
        if corr < dip_threshold and not in_dip:
            in_dip = True
            dip_start_idx = i
        elif corr >= dip_threshold and in_dip:
            in_dip = False
            dip_events.append({
                "start_seconds": timestamps[dip_start_idx],
                "end_seconds": round(timestamps[i - 1] + window_seconds, 3),
                "duration_seconds": round(timestamps[i - 1] + window_seconds - timestamps[dip_start_idx], 3),
                "min_correlation": round(min(correlation[dip_start_idx:i]), 3),
            })
    if in_dip:
        dip_events.append({
            "start_seconds": timestamps[dip_start_idx],
            "end_seconds": round(timestamps[-1] + window_seconds, 3),
            "duration_seconds": round(timestamps[-1] + window_seconds - timestamps[dip_start_idx], 3),
            "min_correlation": round(min(correlation[dip_start_idx:]), 3),
        })

    # --- vectorscope scatter (downsampled, 45°-rotated M/S) -------------
    _SQRT2_INV = 0.70710678118
    step = max(1, n // vectorscope_points)
    vs_points: list[list[float]] = [
        [round((left[i] - right[i]) * _SQRT2_INV, 4), round((left[i] + right[i]) * _SQRT2_INV, 4)]
        for i in range(0, n, step)
    ]

    return {
        "window_seconds": window_seconds,
        "timestamps": timestamps,
        "correlation": correlation,
        "balance": balance,
        "dip_events": dip_events,
        "vectorscope_points": vs_points,
    }
