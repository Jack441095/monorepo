"""Validate bounded FFT features; raw bins and audio never enter the companion."""

from __future__ import annotations

import math
from typing import Any


def _integer(value: Any, *, signed: bool = False) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and (-2**53 if signed else 0) <= value <= 2**53


def _finite(value: Any) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False  # Booleans and strings cannot carry a DSP unit.
    try:
        return math.isfinite(value)
    except OverflowError:
        return False  # A JSON integer beyond float64 range cannot represent a finite audio feature.


def validate_host_timeline(raw: Any, window: dict[str, Any]) -> dict[str, Any] | None:
    """Return a qualified sample clock or reject contradictory timing with ValueError."""
    if raw is None:
        return None  # Older publishers have local timing only and cannot ground paired analysis.
    if not isinstance(raw, dict) or raw.get("schema") != "kenn.host_timeline.v1" or not isinstance(raw.get("valid"), bool):
        raise ValueError("Invalid host timeline.")
    if not _integer(raw.get("transport_epoch")) or raw["transport_epoch"] == 0:
        raise ValueError("Host timeline requires a positive transport epoch.")
    if raw["valid"]:
        span = window["end_sample"] - window["start_sample"]
        if (not window["valid"] or not _integer(raw.get("start_sample"), signed=True)
                or not _integer(raw.get("end_sample"), signed=True)
                or raw["end_sample"] - raw["start_sample"] != span or raw["start_sample"] % span != 0):
            raise ValueError("Host sample bounds must describe the same aligned continuous window.")
    elif any(raw.get(key) is not None and not _integer(raw[key], signed=True) for key in ("start_sample", "end_sample")):
        raise ValueError("Unavailable host sample positions must be null or bounded integers.")
    return {key: raw.get(key) for key in ("schema", "valid", "transport_epoch", "start_sample", "end_sample")}


def validate_fft_spectra(raw: Any, window: dict[str, Any] | None, rate: float) -> dict[str, Any] | None:
    """Validate stereo Hann-power spectra against their containing publication."""
    if raw is None:
        return None  # Legacy filter-bank publishers do not imply calibrated FFT measurements.
    if not isinstance(raw, dict) or raw.get("schema") != "kenn.fft_spectra.v1" or not window:
        raise ValueError("FFT spectra require a continuous publication.")
    result: dict[str, Any] = {"schema": raw["schema"]}
    for key, size in (("fast", 2048), ("low", 8192)):  # Samples: fast detail and finer low-frequency resolution.
        fft = raw.get(key)
        if fft is None:
            result[key] = None  # Warm-up and discontinuities have no complete transform.
            continue
        if not isinstance(fft, dict) or not window["valid"] or not _integer(fft.get("size_samples")) or fft["size_samples"] != size:
            raise ValueError(f"Invalid {key} FFT size or publication validity.")
        if not all(_integer(fft.get(field)) for field in ("start_sample", "end_sample")):
            raise ValueError(f"Invalid {key} FFT sample bounds.")
        lag = window["end_sample"] - fft["end_sample"]
        if fft["end_sample"] - fft["start_sample"] != size or not 0 <= lag <= window["end_sample"] - window["start_sample"]:
            raise ValueError(f"{key} FFT duration or capture interval disagrees.")
        if key == "fast" and lag != 0:
            raise ValueError("Fast FFT must end at the current measurement window.")
        if not _finite(fft.get("bin_hz")) or abs(fft["bin_hz"] - rate / size) > 1e-6:
            raise ValueError(f"{key} FFT bin spacing disagrees with sample rate.")
        if not _finite(fft.get("peak_hz")) or not 0 <= fft["peak_hz"] <= rate / 2:
            raise ValueError(f"Invalid {key} FFT peak frequency.")
        if not _finite(fft.get("mean_square")) or not 0 <= fft["mean_square"] <= 16.0:
            raise ValueError(f"Invalid {key} FFT mean-square power.")
        power = fft.get("band_power")
        if not isinstance(power, list) or len(power) != 32 or not all(_finite(p) and 0 <= p <= 16.0 for p in power):
            raise ValueError(f"{key} FFT requires 32 finite non-negative group powers.")
        # Groups omit DC and frequencies outside 20 Hz–20 kHz. Rounding of
        # float32 accumulations permits 1e-5 relative error in their power sum.
        if sum(power) > fft["mean_square"] * (1 + 1e-5) + 1e-12:
            raise ValueError(f"{key} FFT group power exceeds total mean square.")
        result[key] = {field: fft[field] for field in ("size_samples", "start_sample", "end_sample", "bin_hz", "mean_square", "peak_hz")}
        result[key]["band_power"] = list(power)
    return result
