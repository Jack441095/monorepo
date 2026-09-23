"""Broadcast-style loudness, true peak, key, and tempo measurements.

Libraries: pyloudnorm (MIT) for ITU-R BS.1770 K-weighted loudness, scipy (BSD)
for 4x oversampled true peak, librosa (ISC) for chroma and beat tracking.
Loudness range follows EBU Tech 3342 using 3 s short-term windows at a 1 s
hop and is labelled as an approximation of a certified meter. Key and tempo
are estimates with explicit confidence; they are never presented as facts.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
# Krumhansl-Kessler key profiles.
_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def _load(source: Path | str | bytes) -> tuple[np.ndarray, int]:
    import io

    import soundfile as sf

    handle = io.BytesIO(source) if isinstance(source, (bytes, bytearray)) else str(source)
    data, rate = sf.read(handle, always_2d=True, dtype="float64")
    return data, int(rate)


def _db(value: float) -> float | None:
    return round(20.0 * math.log10(value), 2) if value > 0 else None


def true_peak_dbtp(data: np.ndarray) -> float | None:
    """4x oversampled inter-sample peak (ITU-R BS.1770-4 Annex 2 method)."""
    from scipy.signal import resample_poly

    peak = max(float(np.max(np.abs(resample_poly(data[:, ch], 4, 1)))) for ch in range(data.shape[1]))
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
        "method": "ITU-R BS.1770 (pyloudnorm); true peak 4x oversampled; LRA per EBU Tech 3342, approximate",
    }


def estimate_key_and_tempo(path: Path | str | bytes) -> dict[str, Any]:
    import librosa

    data, rate = _load(path)
    mono = data.mean(axis=1).astype(np.float32)
    chroma = librosa.feature.chroma_cqt(y=mono, sr=rate).mean(axis=1)
    scores = []
    for tonic in range(12):
        for mode, profile in (("major", _MAJOR), ("minor", _MINOR)):
            scores.append((float(np.corrcoef(chroma, np.roll(profile, tonic))[0, 1]), tonic, mode))
    scores.sort(reverse=True)
    best, runner_up = scores[0], scores[1]
    tempo, _beats = librosa.beat.beat_track(y=mono, sr=rate)
    tempo_bpm = float(np.atleast_1d(tempo)[0])
    relative = ((best[1] + 9) % 12, "minor") if best[2] == "major" else ((best[1] + 3) % 12, "major")
    # Relative keys share every note, so chroma alone rarely separates them;
    # always report both rather than claim one.
    return {
        "key": f"{NOTE_NAMES[best[1]]} {best[2]}",
        "key_relative": f"{NOTE_NAMES[relative[0]]} {relative[1]}",
        "key_correlation": round(best[0], 3),
        "key_margin": round(best[0] - runner_up[0], 3),
        "key_confidence": "high" if best[0] - runner_up[0] > 0.1 else "medium" if best[0] - runner_up[0] > 0.04 else "low",
        "tempo_bpm": round(tempo_bpm, 1) if tempo_bpm > 0 else None,
        "method": "chroma CQT + Krumhansl-Kessler profiles; librosa beat tracker (estimates)",
    }


__all__ = ["estimate_key_and_tempo", "loudness_range_lu", "measure_loudness", "true_peak_dbtp"]
