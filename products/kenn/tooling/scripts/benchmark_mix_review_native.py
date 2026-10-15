#!/usr/bin/env python3
"""Compare existing Mix Review implementations on generated PCM, without promotion.

Every native claim requires successful calls observed inside the measured requests.
The Python/SciPy implementation is the agreement reference, not a perceptual oracle.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import copy
import hashlib
import importlib.metadata
import io
import json
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
from typing import Any
import wave

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
for path in (REPO_ROOT / "apps/backend/src", REPO_ROOT / "packages/mix-review"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
from core import local_engine
from core.local_engine import analyze_wav
from kenn.core import native_fft

GATES = ("KENN_DSP_NATIVE", "KENN_DSP_MIX_REVIEW_DECODE_NATIVE", "KENN_DSP_LOUDNESS_NATIVE", "KENN_DSP_MASKING_NATIVE", "KENN_DSP_METRICS_NATIVE")
VARIANTS = {"reference": (False, False), "decode_only": (True, False), "loudness_only": (False, True), "combined": (True, True)}
METERS = ("integrated_lufs", "loudness_range_lu", "true_peak_dbtp")
TOLERANCE = 0.01  # LU or dB; reports round readings to two decimal places.


def _wav_bytes(seconds: float, sample_rate: int, channels: int = 2, kind: str = "steady") -> bytes:
    """Return deterministic PCM16 bytes; no private audio or fixture files are used."""
    count = int(seconds * sample_rate)
    index = np.arange(count, dtype=np.float64)
    left = 0.2 * np.sin(2.0 * np.pi * 440.0 * index / sample_rate)
    right = 0.15 * np.sin(2.0 * np.pi * 660.0 * index / sample_rate + 0.17)
    if kind == "stepped":
        # Two equal-duration plateaus exercise overlapping loudness/LRA windows.
        envelope = np.where(index < count // 2, 1.0, 0.1)
        left, right = left * envelope, right * envelope
    elif kind == "anti_phase":
        right = -left
    elif kind == "silence":
        left, right = np.zeros(count), np.zeros(count)
    data = left[:, None] if channels == 1 else np.column_stack((left, right))
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)  # PCM16 uses two bytes per sample.
        handle.setframerate(sample_rate)
        handle.writeframes(np.rint(data * 32767.0).astype("<i2").tobytes())
    return output.getvalue()


def _accepted_native_result(name: str, result: object) -> bool:
    """Mirror the engine's acceptance boundary so rejected output cannot prove work."""
    if not isinstance(result, dict):
        return False  # The engine uses its existing reference when native output is absent.
    if name == "loudness_metrics":
        # A missing native peak silently invokes SciPy inside the engine. Require
        # all quoted meters here so that hybrid fallback cannot earn native parity.
        return all(isinstance(result.get(key), (int, float))
                   and not isinstance(result[key], bool) and math.isfinite(result[key])
                   for key in METERS)
    try:
        channels = [np.asarray(channel, dtype=np.float32, order="C") for channel in result["channels"]]
        count = int(result["channel_count"])
        return (count in (1, 2) and int(result["sample_rate"]) > 0 and len(channels) == count
                and all(channel.ndim == 1 and channel.size for channel in channels)
                and all(channel.shape == channels[0].shape for channel in channels))
    except (KeyError, TypeError, ValueError):
        return False  # Malformed decoder output makes the production engine fall back.


@contextmanager
def _execution(variant: str):
    """Isolate all relevant gates and count successful native calls, restoring both."""
    saved = {name: os.environ.get(name) for name in GATES}
    decode, loudness = VARIANTS[variant]
    originals = {name: getattr(native_fft, name) for name in ("decode_pcm", "loudness_metrics")}
    proof = {name: {"attempts": 0, "successful": 0} for name in originals}
    def observe(name):
        def call(*args, **kwargs):
            proof[name]["attempts"] += 1
            result = originals[name](*args, **kwargs)
            if _accepted_native_result(name, result):
                proof[name]["successful"] += 1
            return result
        return call
    try:
        for name in GATES:
            os.environ[name] = "0"
        os.environ["KENN_DSP_NATIVE"] = "1" if decode or loudness else "0"
        os.environ["KENN_DSP_MIX_REVIEW_DECODE_NATIVE"] = "1" if decode else "0"
        os.environ["KENN_DSP_LOUDNESS_NATIVE"] = "1" if loudness else "0"
        for name in originals:
            setattr(native_fft, name, observe(name))
        yield proof
    finally:
        for name, function in originals.items():
            setattr(native_fft, name, function)
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _measure(payload: bytes, variant: str, repeats: int) -> dict[str, Any]:
    durations = []
    requests = []
    # Warm each implementation independently; proof only covers measured requests.
    with _execution(variant):
        analyze_wav(payload, filename="benchmark.wav")
    with _execution(variant) as proof:
        for _ in range(repeats):
            before = copy.deepcopy(proof)
            started = time.perf_counter()
            result = analyze_wav(payload, filename="benchmark.wav")
            elapsed = (time.perf_counter() - started) * 1000.0
            durations.append(elapsed)
            # Keep each request's facts and call deltas; a later healthy request
            # must never hide an earlier fallback or compensate with extra calls.
            requests.append(copy.deepcopy({
                "ok": result.get("ok") is True, "metrics": {key: result.get("metrics", {}).get(key) for key in METERS},
                "findings": result.get("findings", []), "elapsed_ms": elapsed,
                "proof": {name: {field: value - before[name][field]
                                 for field, value in counts.items()}
                          for name, counts in proof.items()},
            }))
    return {"ok": result.get("ok") is True, "metrics": {key: result.get("metrics", {}).get(key) for key in METERS},
            "findings": result.get("findings", []), "proof": proof, "requests": requests,
            "samples_ms": durations, "p50_ms": statistics.median(durations),
            "mean_ms": statistics.mean(durations), "max_ms": max(durations)}


def _compare_request(reference: dict, candidate: dict, variant: str, abstains: bool) -> dict:
    """Require equal missingness and meter agreement plus actual requested execution."""
    errors = {}
    agreement = reference["ok"] and candidate["ok"]
    for key in METERS:
        a, b = reference["metrics"].get(key), candidate["metrics"].get(key)
        if a is None or b is None:
            errors[key] = None
            agreement = agreement and a is None and b is None
        elif isinstance(a, bool) or isinstance(b, bool) or not (math.isfinite(a) and math.isfinite(b)):
            errors[key] = None
            agreement = False
        else:
            errors[key] = b - a
            agreement = agreement and abs(b - a) <= TOLERANCE + 1e-12
    # Findings carry the meter's refusal reason as well as its detected status.
    findings_equal = reference["findings"] == candidate["findings"]
    agreement = agreement and findings_equal
    decode, loudness = VARIANTS[variant]
    proof = candidate["proof"]
    execution = (not decode or proof["decode_pcm"] == {"attempts": 1, "successful": 1})
    if loudness and not abstains:
        execution = execution and proof["loudness_metrics"] == {"attempts": 1, "successful": 1}
    if abstains:
        # Short/silent inputs must refuse all calibrated meters, not earn zero.
        refusal = any(item.get("detected") is False and item.get("severity") == "unknown"
                      and "abstained" in item.get("explanation", "") for item in candidate["findings"])
        agreement = agreement and all(candidate["metrics"].get(key) is None for key in METERS) and refusal
    return {"meter_deltas": errors, "findings_equal": findings_equal,
            "execution_verified": bool(execution), "qualified": bool(agreement and execution)}


def _compare(reference: dict, candidate: dict, variant: str, repeats: int, abstains: bool) -> dict:
    """Qualify every timed request; aggregate counters cannot compensate for fallback."""
    # Single-request inputs remain useful for isolated comparison tests. Repeated
    # measurements require their complete per-request evidence, never a final-only summary.
    reference_requests = reference.get("requests", [reference] if repeats == 1 else [])
    candidate_requests = candidate.get("requests", [candidate] if repeats == 1 else [])
    complete = len(reference_requests) == len(candidate_requests) == repeats
    comparisons = [_compare_request(a, b, variant, abstains)
                   for a, b in zip(reference_requests, candidate_requests)]
    summary = _compare_request(reference, candidate, variant, abstains)
    return {"meter_deltas": summary["meter_deltas"],
            "findings_equal": complete and all(item["findings_equal"] for item in comparisons),
            "execution_verified": complete and all(item["execution_verified"] for item in comparisons),
            "qualified": complete and all(item["qualified"] for item in comparisons),
            "request_comparisons": comparisons}


def _metadata() -> dict:
    def digest(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest() if path and Path(path).is_file() else None
    try:
        revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        revision = None  # A source archive has no Git revision; hashes still identify code.
    versions = {}
    for package in ("numpy", "scipy", "pyloudnorm"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None  # Missing optional packages are recorded rather than inferred.
    module = native_fft._load()
    return {"source_revision": revision, "harness_sha256": digest(__file__),
            "engine_sha256": digest(sys.modules[analyze_wav.__module__].__file__),
            "extension_sha256": digest(getattr(module, "__file__", None)),
            "system": platform.system(), "release": platform.release(), "machine": platform.machine(),
            "python": platform.python_version(), "versions": versions, "load_average": list(os.getloadavg()),
            "timing_scope": "observational wall-clock; power and background load not controlled"}


def run(*, seconds: float, sample_rate: int, repeats: int, matrix: bool = False) -> dict[str, Any]:
    if (isinstance(seconds, bool) or not math.isfinite(seconds) or seconds <= 0
            or isinstance(sample_rate, bool) or not isinstance(sample_rate, int) or sample_rate <= 0
            or isinstance(repeats, bool) or not isinstance(repeats, int) or repeats <= 0):
        raise ValueError("seconds, sample_rate and repeats must be finite and positive")
    if matrix and seconds < 3.0:
        raise ValueError("matrix active fixtures require at least 3 seconds for loudness/LRA")
    reference_available = local_engine._pyln is not None and local_engine._resample_poly is not None
    cases = []
    rates = (44_100, 48_000, 96_000) if matrix else (sample_rate,)
    layouts = (1, 2) if matrix else (2,)
    kinds = ("steady", "stepped", "anti_phase", "silence", "short") if matrix else ("steady",)
    for rate in rates:
        for channels in layouts:
            for kind in kinds:
                if kind == "anti_phase" and channels == 1:
                    continue  # Phase cancellation requires two channels.
                duration = 0.2 if kind == "short" else seconds  # 200 ms is below the 400 ms loudness gate.
                payload = _wav_bytes(duration, rate, channels, kind)
                measurements = {name: _measure(payload, name, repeats) for name in VARIANTS}
                parity = {name: _compare(measurements["reference"], value, name, repeats, kind in {"silence", "short"}) for name, value in measurements.items() if name != "reference"}
                cases.append({"fixture": {"kind": kind, "seconds": duration, "sample_rate_hz": rate,
                              "channels": channels, "sha256": hashlib.sha256(payload).hexdigest()},
                              "measurements": measurements, "comparisons": parity,
                              "qualified": all(item["qualified"] for item in parity.values())})
    # Load metadata with explicit opt-in so an inherited disabled gate cannot hide the extension identity.
    with _execution("combined"):
        metadata = _metadata()
    return {"schema": "kenn.dsp_mix_review_native_benchmark.v2", "machine": metadata,
            "repeats": repeats, "cases": cases, "qualified": reference_available and all(case["qualified"] for case in cases),
            "reference_available": reference_available, "reference": "pyloudnorm + scipy",
            "compared_scope": "rounded integrated LUFS, LRA, true peak and all finding fields; other report metrics excluded",
            "tolerance": {"rounded_report_meter_absolute": TOLERANCE, "units": "LU or dB"},
            "limitations": ["Agreement with existing Python/SciPy is not independent meter conformance or perceptual validation.",
                            "Native fallbacks never qualify active candidate measurements.",
                            "Synthetic observational timings do not authorize production promotion."]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=6.0)
    parser.add_argument("--sample-rate", type=int, default=48_000)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--matrix", action="store_true")
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    if not math.isfinite(args.seconds) or args.seconds <= 0 or args.sample_rate <= 0 or args.repeats <= 0:
        parser.error("seconds, sample-rate and repeats must be finite and positive")
    result = run(seconds=args.seconds, sample_rate=args.sample_rate, repeats=args.repeats, matrix=args.matrix)
    rendered = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    print(rendered, end="")
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(rendered, encoding="utf-8")
    return 0 if result["qualified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
