#!/usr/bin/env python3
"""Deterministic microbenchmarks for the qualified native DSP kernels.

This measures kernel runtime only; it makes no perceptual or real-mix claim.
The complete-request benchmark remains the end-to-end qualification gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPO_ROOT / "apps" / "backend" / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))


def _source_revision() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _measure(call: Callable[[], Any], repeats: int) -> dict[str, Any]:
    for _ in range(3):
        call()
    samples: list[float] = []
    result: Any = None
    for _ in range(repeats):
        started = time.perf_counter()
        result = call()
        samples.append((time.perf_counter() - started) * 1000.0)
    return {
        "samples_ms": [round(value, 4) for value in samples],
        "mean_ms": round(statistics.mean(samples), 4),
        "p50_ms": round(statistics.median(samples), 4),
        "p95_ms": round(_percentile(samples, 0.95), 4),
        "result": result,
    }


def run(*, seconds: float, sample_rate: int, repeats: int) -> dict[str, Any]:
    if seconds <= 0 or sample_rate <= 0 or repeats <= 0:
        raise ValueError("seconds, sample_rate, and repeats must be positive")
    try:
        from kenn.core import _kenn_dsp_native as native
    except (ImportError, OSError) as exc:
        raise RuntimeError("the native extension is not loadable") from exc

    count = int(seconds * sample_rate)
    generator = np.random.default_rng(0x4B454E4E)
    samples = (generator.standard_normal(count).astype(np.float32) * np.float32(0.1))
    digest = hashlib.sha256(samples.tobytes()).hexdigest()
    spectral = _measure(
        lambda: dict(native.spectral_power(samples, 16_384, sample_rate, False)),
        repeats,
    )
    masking = _measure(
        lambda: dict(native.masking_band_energy(samples, sample_rate, 4_096, 2_048)),
        repeats,
    )
    spectral_result = spectral.pop("result")
    masking_result = masking.pop("result")
    return {
        "schema": "kenn.dsp_native_kernel_benchmark.v1",
        "source_revision": _source_revision(),
        "candidate": "cpp-native",
        "machine": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "fixture": {
            "kind": "deterministic_synthetic",
            "seconds": seconds,
            "sample_rate_hz": sample_rate,
            "frames": count,
            "float32_sha256": digest,
        },
        "kernels": {
            "spectral_power": {
                **spectral,
                "backend": spectral_result.get("backend"),
                "fft_size": spectral_result.get("fft_size"),
                "window_count": len(spectral_result.get("window_starts", [])),
            },
            "masking_band_energy": {
                **masking,
                "backend": masking_result.get("backend"),
                "fft_size": masking_result.get("fft_size"),
                "hop": masking_result.get("hop"),
                "frame_count": int(np.asarray(masking_result["energy"]).shape[0]),
            },
        },
        "qualified": True,
        "limitations": [
            "Kernel timing only; not an end-to-end request measurement.",
            "Synthetic noise exercises runtime and memory behavior, not perceptual quality.",
            "Compare against the complete-request benchmark before promoting a backend.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument("--sample-rate", type=int, default=48_000)
    parser.add_argument("--repeats", type=int, default=20)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    result = run(seconds=args.seconds, sample_rate=args.sample_rate, repeats=args.repeats)
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    print(encoded, end="")
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(encoded, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
