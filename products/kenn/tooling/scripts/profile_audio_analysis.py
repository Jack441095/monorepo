#!/usr/bin/env python3
"""Emit a deterministic cProfile receipt for the bounded WAV analyser.

This is intentionally an observational Phase 1 tool. It profiles the active
Python reference without changing the production analysis API or introducing a
native candidate.
"""

from __future__ import annotations

import argparse
import cProfile
import json
import os
import pstats
import sys
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import benchmark_audio_analysis as benchmark

SOURCE_ROOT = SCRIPT_ROOT.parents[1] / "apps" / "backend" / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from kenn.core.audio_analysis import analyze_wav


def _stage_stats(profile: cProfile.Profile) -> dict[str, dict[str, float | int]]:
    stats = pstats.Stats(profile).stats
    result: dict[str, dict[str, float | int]] = {}
    for name in (
        "analyze_wav",
        "_decode",
        "_spectral_measurement",
        "_dominant_peaks",
        "_fft",
        "decode_pcm",
        "spectral_powers",
    ):
        matching = [value for key, value in stats.items() if key[2] == name]
        if not matching:
            continue
        calls = sum(value[0] for value in matching)
        total_seconds = sum(value[2] for value in matching)
        cumulative_seconds = sum(value[3] for value in matching)
        result[name] = {
            "calls": calls,
            "exclusive_ms": round(total_seconds * 1000.0, 3),
            "cumulative_ms": round(cumulative_seconds * 1000.0, 3),
        }
    return result


def run(*, seconds: float, repeats: int) -> dict[str, Any]:
    payload = benchmark._wav_bytes(seconds=seconds, sample_rate=48_000)
    profile = cProfile.Profile()
    profile.enable()
    for _ in range(repeats):
        analyze_wav(payload, filename="phase1-profile.wav")
    profile.disable()
    stages = _stage_stats(profile)
    total_ms = float(stages.get("analyze_wav", {}).get("cumulative_ms", 0.0))
    native_enabled = os.environ.get("KENN_DSP_NATIVE", "0").strip().lower() in {"1", "true", "on", "yes"}
    dominant_candidates = {
        name: float(value.get("exclusive_ms", 0.0))
        for name, value in stages.items()
        if name != "analyze_wav"
    }
    dominant = max(dominant_candidates, key=dominant_candidates.get, default="unknown")
    return {
        "schema": "kenn.dsp_profile.v1",
        "source_revision": benchmark._source_revision(),
        "candidate": "cpp-native-opt-in" if native_enabled else "python-stdlib-reference",
        "machine": benchmark._machine_metadata(),
        "fixture": {
            "generator": "deterministic 440 Hz mono PCM16 WAV",
            "seconds": seconds,
            "sample_rate_hz": 48_000,
            "bytes": len(payload),
        },
        "repeats": repeats,
        "total_profiled_ms": total_ms,
        "stages": stages,
        "dominant_stage": dominant,
        "native_poc_candidate": None if native_enabled else "fft",
        "interpretation": (
            "Native mode profiles the current C++ decoder/spectral boundary and retained Python report "
            "orchestration. Reference mode preserves the original FFT candidate note. cProfile stage "
            "totals overlap by design, so complete-request benchmarks remain the adoption gate."
            if native_enabled else
            "The FFT is the first native POC candidate: it is the largest exclusive hot function "
            "inside spectral measurement. cProfile stage totals overlap by design, so complete-request "
            "benchmarks remain the adoption gate."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=2.0)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    if args.seconds <= 0 or args.repeats <= 0:
        parser.error("--seconds and --repeats must be positive")
    result = run(seconds=args.seconds, repeats=args.repeats)
    rendered = json.dumps(result, indent=2)
    print(rendered)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
