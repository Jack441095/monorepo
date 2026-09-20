#!/usr/bin/env python3
"""Bounded benchmark for the KENN-owned WAV analysis endpoint contract.

The fixtures are generated in memory and are not written to disk.  This is a
resource/latency smoke benchmark, not a perceptual-quality qualification.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import statistics
import struct
import sys
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

# Make the script runnable from the repository root without requiring callers
# to remember the package-path detail used by the test suite.
REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPO_ROOT / "apps" / "backend" / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from kenn.core.audio_analysis import MAX_INPUT_BYTES, analyze_wav


def _wav_bytes(*, seconds: float, sample_rate: int, amplitude: float = 0.25) -> bytes:
    frames = bytearray()
    count = int(seconds * sample_rate)
    for index in range(count):
        sample = int(round(amplitude * 32767.0 * math.sin(2.0 * math.pi * 440.0 * index / sample_rate)))
        frames.extend(struct.pack("<h", sample))
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(frames)
    return output.getvalue()


def _measure(label: str, payload: bytes, *, repeats: int = 1) -> dict[str, Any]:
    durations: list[float] = []
    result: dict[str, Any] | None = None
    for _ in range(repeats):
        started = time.perf_counter()
        result = analyze_wav(payload, filename=f"{label}.wav")
        durations.append((time.perf_counter() - started) * 1000.0)
    assert result is not None
    return {
        "label": label,
        "bytes": len(payload),
        "within_input_limit": len(payload) <= MAX_INPUT_BYTES,
        "ok": result.get("ok") is True,
        "analysis_status": result.get("analysis_status"),
        "duration_seconds": result.get("metrics", {}).get("duration_seconds"),
        "sample_rate_hz": result.get("metrics", {}).get("sample_rate_hz"),
        "runs": repeats,
        "mean_ms": round(statistics.mean(durations), 3),
        "max_ms": round(max(durations), 3),
    }


def _concurrent(payload: bytes, *, workers: int) -> dict[str, Any]:
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda _: analyze_wav(payload, filename="concurrent.wav"), range(workers)))
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return {
        "workers": workers,
        "elapsed_ms": round(elapsed_ms, 3),
        "all_ok": all(result.get("ok") is True for result in results),
        "all_complete": all(result.get("analysis_status") == "complete" for result in results),
    }


def run(*, long_seconds: float, workers: int) -> dict[str, Any]:
    fixtures = [
        ("long_48khz", _wav_bytes(seconds=long_seconds, sample_rate=48_000)),
        ("high_rate_96khz", _wav_bytes(seconds=2.0, sample_rate=96_000)),
    ]
    cases = [_measure(label, payload) for label, payload in fixtures]
    concurrent = _concurrent(fixtures[0][1], workers=workers)
    return {
        "schema": "kenn.audio_analysis.benchmark.v1",
        "benchmark_version": "kenn.audio_analysis.benchmark.v1",
        "resource_limits": {
            "max_input_bytes": MAX_INPUT_BYTES,
            "fft_windows_cap": 4,
            "audio_retained": False,
        },
        "cases": cases,
        "concurrency": concurrent,
        "qualified": all(case["ok"] and case["within_input_limit"] for case in cases) and concurrent["all_ok"] and concurrent["all_complete"],
        "limitations": [
            "Synthetic PCM fixtures measure bounded runtime behavior only.",
            "No perceptual, LUFS, LRA, true-peak, or real-mix quality claim is made.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--long-seconds", type=float, default=10.0)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.long_seconds <= 0 or args.workers <= 0:
        parser.error("--long-seconds and --workers must be positive")
    result = run(long_seconds=args.long_seconds, workers=args.workers)
    print(json.dumps(result, indent=2))
    # main() previously always returned 0 regardless of the computed
    # "qualified" verdict -- every sibling eval/qualify script in this repo
    # gates its exit code on its own pass/fail result; this one silently
    # didn't, so a real regression here would never fail a CI/gate check
    # that relies on the exit code rather than parsing the JSON itself.
    return 0 if result["qualified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
