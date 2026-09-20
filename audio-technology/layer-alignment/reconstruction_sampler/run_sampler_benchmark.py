"""Small, deterministic pitch-shifting bake-off on controlled synthetic signals."""
from __future__ import annotations

import csv
import json
import platform
import sys
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly, stft, istft

VERSION = "SAMPLER_RECON_EVAL_0.1"
SEED = 20260822
SAMPLE_RATE = 48_000
DURATION = 1.5
SHIFT = 1.5
N_FFT = 2048
HOP = 512


def synth_fixture(name: str) -> np.ndarray:
    time = np.arange(int(SAMPLE_RATE * DURATION)) / SAMPLE_RATE
    if name == "sine":
        return np.sin(2 * np.pi * 220 * time)
    if name == "saw":
        return 2 * ((220 * time) % 1.0) - 1.0
    if name == "fm":
        carrier = 220 * time + 18 * np.sin(2 * np.pi * 5 * time)
        return 0.8 * np.sin(2 * np.pi * carrier)
    if name == "pluck":
        envelope = np.exp(-7 * time)
        return envelope * (np.sin(2 * np.pi * 220 * time) + 0.35 * np.sin(2 * np.pi * 440 * time))
    if name == "noise_layered_bass":
        rng = np.random.default_rng(SEED)
        envelope = np.exp(-1.2 * time)
        return 0.75 * envelope * np.sin(2 * np.pi * 55 * time) + 0.03 * rng.standard_normal(time.size)
    raise ValueError(name)


def baseline_resample(signal: np.ndarray) -> np.ndarray:
    return resample_poly(signal, 2, 3)


def phase_vocoder_stretch(signal: np.ndarray, rate: float) -> np.ndarray:
    frequencies, times, spectrum = stft(signal, fs=SAMPLE_RATE, nperseg=N_FFT, noverlap=N_FFT - HOP, boundary="zeros")
    time_steps = np.arange(0, spectrum.shape[1], rate)
    phase_acc = np.angle(spectrum[:, 0])
    output = np.zeros((spectrum.shape[0], len(time_steps)), dtype=complex)
    expected = 2 * np.pi * HOP * np.arange(spectrum.shape[0]) / N_FFT
    for index, step in enumerate(time_steps):
        left = min(int(step), spectrum.shape[1] - 1)
        right = min(left + 1, spectrum.shape[1] - 1)
        fraction = step - left
        column = (1 - fraction) * spectrum[:, left] + fraction * spectrum[:, right]
        output[:, index] = np.abs(column) * np.exp(1j * phase_acc)
        phase_delta = np.angle(spectrum[:, right]) - np.angle(spectrum[:, left]) - expected
        phase_delta = phase_delta - 2 * np.pi * np.round(phase_delta / (2 * np.pi))
        phase_acc += expected + phase_delta
    _, stretched = istft(output, fs=SAMPLE_RATE, nperseg=N_FFT, noverlap=N_FFT - HOP, input_onesided=True)
    return stretched.astype(np.float64)


def experimental_pitch_shift(signal: np.ndarray) -> np.ndarray:
    shorter = baseline_resample(signal)
    shifted = phase_vocoder_stretch(shorter, 1 / SHIFT)
    target = len(signal)
    if len(shifted) < target:
        shifted = np.pad(shifted, (0, target - len(shifted)))
    return shifted[:target]


def dominant_frequency(signal: np.ndarray) -> float:
    window = np.hanning(len(signal))
    spectrum = np.abs(np.fft.rfft(signal * window))
    return float(np.argmax(spectrum) * SAMPLE_RATE / len(signal))


def spectral_centroid(signal: np.ndarray) -> float:
    spectrum = np.abs(np.fft.rfft(signal * np.hanning(len(signal))))
    frequencies = np.fft.rfftfreq(len(signal), 1 / SAMPLE_RATE)
    return float(np.sum(frequencies * spectrum) / max(np.sum(spectrum), 1e-12))


def envelope_modulation_rate(signal: np.ndarray) -> float:
    envelope = np.abs(signal)
    frequencies = np.fft.rfftfreq(len(envelope), 1 / SAMPLE_RATE)
    spectrum = np.abs(np.fft.rfft((envelope - np.mean(envelope)) * np.hanning(len(envelope))))
    valid = (frequencies >= 1) & (frequencies <= 30)
    return float(frequencies[valid][np.argmax(spectrum[valid])]) if np.any(valid) else 0.0


def metrics(source: np.ndarray, output: np.ndarray, expected_hz: float) -> dict:
    source_centroid = spectral_centroid(source)
    output_centroid = spectral_centroid(output)
    return {
        "pitch_hz": dominant_frequency(output),
        "pitch_error_hz": abs(dominant_frequency(output) - expected_hz),
        "duration_seconds": len(output) / SAMPLE_RATE,
        "duration_error_seconds": abs(len(output) - len(source)) / SAMPLE_RATE,
        "spectral_centroid_drift_hz": abs(output_centroid - source_centroid * SHIFT),
        "modulation_rate_hz": envelope_modulation_rate(output),
    }


def main() -> None:
    rows = []
    for name in ["sine", "saw", "fm", "pluck", "noise_layered_bass"]:
        source = synth_fixture(name)
        expected = 220 * SHIFT if name != "noise_layered_bass" else 55 * SHIFT
        for method, output in [("resampling_baseline", baseline_resample(source)), ("reconstruction_pv", experimental_pitch_shift(source))]:
            row = {"fixture": name, "method": method, **metrics(source, output, expected)}
            rows.append(row)
    summary = {}
    for method in ["resampling_baseline", "reconstruction_pv"]:
        method_rows = [row for row in rows if row["method"] == method]
        summary[method] = {
            "mean_pitch_error_hz": float(np.mean([row["pitch_error_hz"] for row in method_rows])),
            "mean_duration_error_seconds": float(np.mean([row["duration_error_seconds"] for row in method_rows])),
            "mean_centroid_drift_hz": float(np.mean([row["spectral_centroid_drift_hz"] for row in method_rows])),
        }
    result = {
        "benchmark": VERSION,
        "seed": SEED,
        "shift_factor": SHIFT,
        "environment": {"python": sys.version.split()[0], "numpy": np.__version__, "platform": platform.platform()},
        "summary": summary,
        "rows": rows,
        "observed": "The phase-vocoder path preserves rendered duration while the resampling baseline does not; quality metrics are fixture-dependent.",
        "limitations": ["The phase-vocoder prototype is not production-quality and has no perceptual listening score.", "Synthetic signals do not represent a broad instrument corpus.", "Spectral centroid drift is not a complete timbre metric."],
    }
    root = Path(__file__).resolve().parent
    (root / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    with (root / "results.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = ["fixture", "method", "pitch_hz", "pitch_error_hz", "duration_seconds", "duration_error_seconds", "spectral_centroid_drift_hz", "modulation_rate_hz"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row[field] for field in fields} for row in rows)
    print(json.dumps({"benchmark": VERSION, "summary": summary}, indent=2))


if __name__ == "__main__":
    main()
