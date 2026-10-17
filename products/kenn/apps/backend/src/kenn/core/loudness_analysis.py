"""Broadcast-style loudness and true peak measurements backed by the C++ DSP extension.

ITU-R BS.1770-4 K-weighted loudness, 8x oversampled Kaiser polyphase FIR true
peak, and EBU Tech 3342 loudness range (3.0 s short-term windows at a 1.0 s
hop, labelled as an approximation of a certified meter) all execute in
``_kenn_dsp_native`` without importing ``pyloudnorm``, ``scipy``, or ``soundfile``.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np

from kenn.core import native_fft


def _load(source: Path | str | bytes | bytearray | memoryview) -> tuple[list[np.ndarray], int]:
    """Decode WAV or AIFF/AIFC audio into contiguous float32 channel arrays via the C++ decoder."""
    raw = bytes(source) if isinstance(source, (bytes, bytearray, memoryview)) else Path(source).read_bytes()
    decoded = native_fft.decode_pcm(raw, allow_8bit=True, max_channels=2, allow_aiff=True)
    if decoded is None:
        if not native_fft.available():
            raise RuntimeError("Native decode_pcm kernel is required for loudness measurement")
        raise ValueError("Unsupported or malformed WAV/AIFF container for loudness measurement")
    return decoded["channels"], int(decoded["sample_rate"])


def _round_metric(value: Any) -> float | None:
    """Round a finite scalar metric to 0.01 dB/LU, returning None when gated out or absent."""
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
        return round(float(value), 2)
    return None


def true_peak_dbtp(data: np.ndarray) -> float | None:
    """8x oversampled inter-sample peak (the ITU-R BS.1770-4 Annex 2 method at twice its minimum ratio).

    8x to match the mix-review meter (see TRUE_PEAK_OVERSAMPLE_FACTOR in
    local_engine.py for the measurement behind it).
    """
    if not native_fft.available():
        raise RuntimeError("Native true_peak_dbtp kernel is required")
    return _round_metric(native_fft.true_peak_dbtp(data))


def _windowed_loudness(
    meter: Any,
    data: np.ndarray,
    rate: int,
    window_s: float,
    hop_s: float,
) -> list[float]:
    """Return K-weighted rectangular window LUFS readings at the requested window and hop seconds.

    ``meter`` is retained as an unused positional parameter for callers that
    still pass a legacy meter handle.
    """
    del meter
    values = native_fft.windowed_loudness(data, rate, window_s, hop_s)
    if values is None:
        raise RuntimeError("Native windowed_loudness kernel is required")
    return values


def loudness_range_lu(short_term: list[float]) -> float | None:
    """EBU Tech 3342: gate at -70.0 LUFS and -20.0 LU relative, then P95 - P10."""
    if not native_fft.available():
        raise RuntimeError("Native loudness_range_lu kernel is required")
    if len(short_term) < 2:
        # A single short-term window has no distribution to span P95 - P10.
        return None
    return _round_metric(native_fft.loudness_range_lu(short_term))


def measure_loudness(path: Path | str | bytes) -> dict[str, Any]:
    """Measure integrated/short-term/momentary LUFS, LRA, 8x true peak, and sample peak in C++."""
    channels, rate = _load(path)
    metrics = native_fft.loudness_metrics(channels, rate)
    if metrics is None:
        raise RuntimeError("Native loudness_metrics kernel is required")
    frame_count = int(channels[0].shape[0]) if channels else 0
    return {
        "integrated_lufs": _round_metric(metrics.get("integrated_lufs")),
        "short_term_max_lufs": _round_metric(metrics.get("short_term_max_lufs")),
        "momentary_max_lufs": _round_metric(metrics.get("momentary_max_lufs")),
        "loudness_range_lu": _round_metric(metrics.get("short_term_lra_lu")),
        "true_peak_dbtp": _round_metric(metrics.get("true_peak_dbtp")),
        "sample_peak_dbfs": _round_metric(metrics.get("sample_peak_dbfs")),
        "duration_s": round(frame_count / rate, 2),
        "method": "ITU-R BS.1770 (cpp-native-k-weighting); true peak 8x oversampled; LRA per EBU Tech 3342, approximate",
    }


__all__ = ["loudness_range_lu", "measure_loudness", "true_peak_dbtp"]

