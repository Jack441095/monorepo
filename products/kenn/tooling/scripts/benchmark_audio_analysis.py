#!/usr/bin/env python3
"""Bounded benchmark for the KENN-owned WAV analysis endpoint contract.

The fixtures are generated in memory and are not written to disk.  This is a
resource/latency smoke benchmark, not a perceptual-quality qualification.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import platform
import resource
import statistics
import struct
import subprocess
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


def _percentile(values: list[float], percentile: float) -> float:
    """Return a deterministic linear-interpolated percentile."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _peak_rss_bytes() -> int:
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes; Linux and the BSDs report KiB.
    return int(usage if sys.platform == "darwin" else usage * 1024)


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


def _machine_metadata() -> dict[str, Any]:
    return {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
    }


def _wav_metadata(payload: bytes) -> dict[str, Any]:
    try:
        with wave.open(io.BytesIO(payload), "rb") as handle:
            sample_rate = handle.getframerate()
            frames = handle.getnframes()
            return {
                "channels": handle.getnchannels(),
                "sample_width_bytes": handle.getsampwidth(),
                "sample_rate_hz": sample_rate,
                "frames": frames,
                "duration_seconds": round(frames / sample_rate, 6) if sample_rate else None,
            }
    except (EOFError, OSError, wave.Error) as exc:
        return {"format_error": str(exc)}


def _measure(
    label: str,
    payload: bytes,
    *,
    repeats: int = 3,
    warmups: int = 3,
    include_ltas: bool = False,
) -> dict[str, Any]:
    for _ in range(warmups):
        analyze_wav(payload, filename=f"{label}.wav", include_ltas=include_ltas)
    durations: list[float] = []
    result: dict[str, Any] | None = None
    for _ in range(repeats):
        started = time.perf_counter()
        result = analyze_wav(payload, filename=f"{label}.wav", include_ltas=include_ltas)
        durations.append((time.perf_counter() - started) * 1000.0)
    assert result is not None
    return {
        "label": label,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "within_input_limit": len(payload) <= MAX_INPUT_BYTES,
        "ok": result.get("ok") is True,
        "analysis_status": result.get("analysis_status"),
        "duration_seconds": result.get("metrics", {}).get("duration_seconds"),
        "sample_rate_hz": result.get("metrics", {}).get("sample_rate_hz"),
        "implementation": result.get("spectral", {}).get("implementation", "python-reference"),
        "native_input_copied": result.get("spectral", {}).get("native_input_copied"),
        "runs": repeats,
        "warmups": warmups,
        "samples_ms": [round(value, 3) for value in durations],
        "mean_ms": round(statistics.mean(durations), 3),
        "p50_ms": round(_percentile(durations, 0.50), 3),
        "p95_ms": round(_percentile(durations, 0.95), 3),
        "p99_ms": round(_percentile(durations, 0.99), 3),
        "max_ms": round(max(durations), 3),
        "wav": _wav_metadata(payload),
    }


def _concurrent(payload: bytes, *, workers: int, include_ltas: bool = False) -> dict[str, Any]:
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(
            lambda _: analyze_wav(payload, filename="concurrent.wav", include_ltas=include_ltas),
            range(workers),
        ))
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return {
        "workers": workers,
        "elapsed_ms": round(elapsed_ms, 3),
        "all_ok": all(result.get("ok") is True for result in results),
        "all_complete": all(result.get("analysis_status") == "complete" for result in results),
    }


def run(
    *,
    long_seconds: float,
    workers: int,
    repeats: int = 3,
    include_ltas: bool = False,
    fixture_paths: list[Path] | None = None,
) -> dict[str, Any]:
    if repeats <= 0:
        raise ValueError("repeats must be positive")
    rss_before = _peak_rss_bytes()
    started = time.perf_counter()
    external_sources: list[dict[str, Any]] = []
    if fixture_paths:
        fixtures = []
        labels_seen: set[str] = set()
        for path in fixture_paths:
            payload = path.read_bytes()
            label = path.stem
            if label in labels_seen:
                label = f"{path.parent.parent.name}_{path.stem}"
            suffix = 2
            base_label = label
            while label in labels_seen:
                label = f"{base_label}_{suffix}"
                suffix += 1
            labels_seen.add(label)
            fixtures.append((label, payload))
            external_sources.append(
                {
                    "path": str(path),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "bytes": len(payload),
                    "wav": _wav_metadata(payload),
                }
            )
    else:
        fixtures = [
            ("long_48khz", _wav_bytes(seconds=long_seconds, sample_rate=48_000)),
            ("high_rate_96khz", _wav_bytes(seconds=2.0, sample_rate=96_000)),
        ]
    cases = [_measure(label, payload, repeats=repeats, include_ltas=include_ltas) for label, payload in fixtures]
    concurrent = _concurrent(fixtures[0][1], workers=workers, include_ltas=include_ltas)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    rss_after = _peak_rss_bytes()
    request_samples = [sample for case in cases for sample in case["samples_ms"]]
    qualified = all(case["ok"] and case["within_input_limit"] for case in cases) and concurrent["all_ok"] and concurrent["all_complete"]
    implementations = {str(case["implementation"]) for case in cases}
    selected_backend = (
        next(iter(implementations))
        if len(implementations) == 1
        else "mixed"
    )
    candidate = (
        f"{selected_backend}-nanobind"
        if selected_backend.startswith("cpp-")
        else "python-stdlib-reference"
    )
    return {
        "schema": "kenn.dsp_benchmark.v1",
        "benchmark_version": "kenn.audio_analysis.benchmark.v2",
        "source_revision": _source_revision(),
        "candidate": candidate,
        "build_type": (
            os.environ.get("KENN_DSP_BUILD_TYPE", "release")
            if candidate.startswith("cpp-")
            else "python-reference"
        ),
        "compiler_flags": [],
        "machine": _machine_metadata(),
        "resource_limits": {
            "max_input_bytes": MAX_INPUT_BYTES,
            "fft_windows_cap": 4,
            "audio_retained": False,
        },
        "fixture": {
            "kind": "external_wav" if external_sources else "synthetic",
            "generator": None if external_sources else "deterministic 440 Hz mono PCM16 WAV",
            "long_seconds": long_seconds,
            "workers": workers,
            "repeats": repeats,
            "include_ltas": include_ltas,
            "sources": external_sources,
        },
        "cases": cases,
        "concurrency": concurrent,
        "stage_samples_ms": [{"stage": "complete_request", "samples_ms": [round(value, 3) for value in request_samples]}],
        "peak_rss_bytes": max(rss_before, rss_after),
        "elapsed_ms": round(elapsed_ms, 3),
        "numerical_comparison": {"status": "not_applicable", "reference": "self"},
        "selected_simd_backend": selected_backend if candidate.startswith("cpp-") else "python-stdlib",
        "qualified": qualified,
        "passed": qualified,
        "limitations": (["No perceptual, LUFS, LRA, true-peak, or real-mix quality claim is made."]
                        if external_sources else [
                            "Synthetic PCM fixtures measure bounded runtime behavior only.",
                            "No perceptual, LUFS, LRA, true-peak, or real-mix quality claim is made.",
                        ]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--long-seconds", type=float, default=10.0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--include-ltas", action="store_true", help="include the optional 40-band LTAS report")
    parser.add_argument(
        "--fixture",
        dest="fixture_paths",
        action="append",
        type=Path,
        help="benchmark a private WAV fixture; repeat for multiple fixtures",
    )
    parser.add_argument("--json-out", type=Path, help="also write the JSON receipt to this path")
    args = parser.parse_args()
    if args.long_seconds <= 0 or args.workers <= 0 or args.repeats <= 0:
        parser.error("--long-seconds, --workers, and --repeats must be positive")
    missing = [path for path in (args.fixture_paths or []) if not path.is_file()]
    if missing:
        parser.error("fixture path does not exist or is not a file: " + ", ".join(map(str, missing)))
    result = run(
        long_seconds=args.long_seconds,
        workers=args.workers,
        repeats=args.repeats,
        include_ltas=args.include_ltas,
        fixture_paths=args.fixture_paths,
    )
    rendered = json.dumps(result, indent=2)
    print(rendered)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(rendered + "\n", encoding="utf-8")
    # main() previously always returned 0 regardless of the computed
    # "qualified" verdict -- every sibling eval/qualify script in this repo
    # gates its exit code on its own pass/fail result; this one silently
    # didn't, so a real regression here would never fail a CI/gate check
    # that relies on the exit code rather than parsing the JSON itself.
    return 0 if result["qualified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
