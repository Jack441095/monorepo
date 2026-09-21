#!/usr/bin/env python3
"""Benchmark the opt-in C++ K-weighting candidate in Mix Review.

The Python/pyloudnorm path remains the oracle. This script compares complete
reports on the same deterministic fixture and measures the full request.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import platform
import statistics
import struct
import sys
import time
import wave
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPO_ROOT / "apps" / "backend" / "src"
MIX_REVIEW_ROOT = REPO_ROOT / "packages" / "mix-review"
for path in (SOURCE_ROOT, MIX_REVIEW_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from core.local_engine import analyze_wav


def _wav_bytes(seconds: float, sample_rate: int) -> bytes:
    frames = int(seconds * sample_rate)
    index = np.arange(frames, dtype=np.float64)
    left = 0.2 * np.sin(2.0 * np.pi * 440.0 * index / sample_rate)
    right = 0.15 * np.sin(2.0 * np.pi * 660.0 * index / sample_rate + 0.17)
    interleaved = np.empty(frames * 2, dtype=np.int16)
    interleaved[0::2] = np.rint(left * 32767.0).astype(np.int16)
    interleaved[1::2] = np.rint(right * 32767.0).astype(np.int16)
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(interleaved.tobytes())
    return output.getvalue()


def _measure(payload: bytes, native: bool, repeats: int) -> tuple[dict[str, Any], list[float]]:
    os.environ["KENN_DSP_LOUDNESS_NATIVE"] = "1" if native else "0"
    os.environ["KENN_DSP_MIX_REVIEW_DECODE_NATIVE"] = "1" if native else "0"
    for _ in range(2):
        analyze_wav(payload, filename="benchmark.wav")
    durations: list[float] = []
    result: dict[str, Any] | None = None
    for _ in range(repeats):
        started = time.perf_counter()
        result = analyze_wav(payload, filename="benchmark.wav")
        durations.append((time.perf_counter() - started) * 1000.0)
    assert result is not None
    return result, durations


def _summary(values: list[float]) -> dict[str, Any]:
    ordered = sorted(values)
    return {
        "samples_ms": [round(value, 3) for value in values],
        "mean_ms": round(statistics.mean(values), 3),
        "p50_ms": round(statistics.median(values), 3),
        "p95_ms": round(ordered[min(len(ordered) - 1, int(0.95 * (len(ordered) - 1)))], 3),
    }


def run(*, seconds: float, sample_rate: int, repeats: int) -> dict[str, Any]:
    payload = _wav_bytes(seconds, sample_rate)
    reference, reference_times = _measure(payload, False, repeats)
    native, native_times = _measure(payload, True, repeats)
    reference_families = sorted(
        item["fault_family"] for item in reference["findings"] if item.get("detected")
    )
    native_families = sorted(item["fault_family"] for item in native["findings"] if item.get("detected"))
    reference_metrics = reference.get("metrics", {})
    native_metrics = native.get("metrics", {})
    parity = {
        "finding_families_equal": reference_families == native_families,
        "integrated_lufs_delta_db": round(
            float(native_metrics["integrated_lufs"]) - float(reference_metrics["integrated_lufs"]), 6
        ) if reference_metrics.get("integrated_lufs") is not None and native_metrics.get("integrated_lufs") is not None else None,
        "loudness_range_delta_lu": round(
            float(native_metrics["loudness_range_lu"]) - float(reference_metrics["loudness_range_lu"]), 6
        ) if reference_metrics.get("loudness_range_lu") is not None and native_metrics.get("loudness_range_lu") is not None else None,
        "true_peak_equal": native_metrics.get("true_peak_dbtp") == reference_metrics.get("true_peak_dbtp"),
    }
    return {
        "schema": "kenn.dsp_mix_review_native_benchmark.v1",
        "candidate": "cpp-native-decode-k-weighting-truepeak-opt-in",
        "machine": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "fixture": {
            "kind": "deterministic_synthetic_stereo_pcm16",
            "seconds": seconds,
            "sample_rate_hz": sample_rate,
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        },
        "reference": _summary(reference_times),
        "native": _summary(native_times),
        "parity": parity,
        "qualified": bool(
            reference.get("ok") is True
            and native.get("ok") is True
            and parity["finding_families_equal"]
            and parity["integrated_lufs_delta_db"] is not None
            and abs(float(parity["integrated_lufs_delta_db"])) <= 0.01
            and parity["loudness_range_delta_lu"] is not None
            and abs(float(parity["loudness_range_delta_lu"])) <= 0.01
            and parity["true_peak_equal"]
        ),
        "limitations": [
            "The C++ candidate replaces K-weighted loudness/LRA and true peak with the same audited FIR contract.",
            "Synthetic timing is not a perceptual or real-mix quality claim.",
            "The candidate remains opt-in until cross-platform and real-corpus evidence is available.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument("--sample-rate", type=int, default=48_000)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    if args.seconds <= 0 or args.sample_rate <= 0 or args.repeats <= 0:
        parser.error("seconds, sample-rate, and repeats must be positive")
    result = run(seconds=args.seconds, sample_rate=args.sample_rate, repeats=args.repeats)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    print(rendered, end="")
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(rendered, encoding="utf-8")
    return 0 if result["qualified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
