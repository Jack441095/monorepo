"""Broadcast-style loudness and true peak measurements.

Libraries: pyloudnorm (MIT) for ITU-R BS.1770 K-weighted loudness, scipy (BSD)
for 8x oversampled true peak. Loudness range follows EBU Tech 3342 using 3 s
short-term windows at a 1 s hop and is labelled as an approximation of a
certified meter. Key and tempo moved to the native extension (see
sample_library.analyze_sample_audio).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np


def _load(source: Path | str | bytes) -> tuple[np.ndarray, int]:
    import io

    import soundfile as sf

    handle = io.BytesIO(source) if isinstance(source, (bytes, bytearray)) else str(source)
    data, rate = sf.read(handle, always_2d=True, dtype="float64")
    return data, int(rate)


def _db(value: float) -> float | None:
    return round(20.0 * math.log10(value), 2) if value > 0 else None


def true_peak_dbtp(data: np.ndarray) -> float | None:
    """8x oversampled inter-sample peak (the ITU-R BS.1770-4 Annex 2 method at twice its minimum ratio).

    8x to match the mix-review meter (see TRUE_PEAK_OVERSAMPLE_FACTOR in
    local_engine.py for the measurement behind it).
    """
    from scipy.signal import resample_poly

    peak = max(float(np.max(np.abs(resample_poly(data[:, ch], 8, 1)))) for ch in range(data.shape[1]))
    return _db(peak)


def _windowed_loudness(meter: Any, data: np.ndarray, rate: int, window_s: float, hop_s: float) -> list[float]:
    window, hop = int(window_s * rate), int(hop_s * rate)
    values = []
    for start in range(0, max(1, data.shape[0] - window + 1), hop):
        chunk = data[start:start + window]
        if chunk.shape[0] < window:
            break
        value = meter.integrated_loudness(chunk)
        if math.isfinite(value):
            values.append(float(value))
    return values


def loudness_range_lu(short_term: list[float]) -> float | None:
    """EBU Tech 3342: gate at -70 LUFS and -20 LU relative, then P95 - P10."""
    gated = [v for v in short_term if v > -70.0]
    if len(gated) < 2:
        return None
    mean_power = sum(10 ** (v / 10.0) for v in gated) / len(gated)
    relative = 10.0 * math.log10(mean_power) - 20.0
    kept = sorted(v for v in gated if v > relative)
    if len(kept) < 2:
        return None
    return round(float(np.percentile(kept, 95) - np.percentile(kept, 10)), 2)


def measure_loudness(path: Path | str | bytes) -> dict[str, Any]:
    import pyloudnorm as pyln

    data, rate = _load(path)
    meter = pyln.Meter(rate)
    integrated = float(meter.integrated_loudness(data))
    short_term = _windowed_loudness(pyln.Meter(rate, block_size=0.400), data, rate, 3.0, 1.0)
    momentary = _windowed_loudness(pyln.Meter(rate, block_size=0.400), data, rate, 0.4, 0.1)
    sample_peak = float(np.max(np.abs(data))) if data.size else 0.0
    return {
        "integrated_lufs": round(integrated, 2) if math.isfinite(integrated) else None,
        "short_term_max_lufs": round(max(short_term), 2) if short_term else None,
        "momentary_max_lufs": round(max(momentary), 2) if momentary else None,
        "loudness_range_lu": loudness_range_lu(short_term),
        "true_peak_dbtp": true_peak_dbtp(data),
        "sample_peak_dbfs": _db(sample_peak),
        "duration_s": round(data.shape[0] / rate, 2),
        "method": "ITU-R BS.1770 (pyloudnorm); true peak 8x oversampled; LRA per EBU Tech 3342, approximate",
    }


__all__ = ["loudness_range_lu", "measure_loudness", "true_peak_dbtp"]
