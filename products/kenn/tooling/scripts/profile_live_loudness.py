#!/usr/bin/env python3
"""Measure clip-kernel reuse costs without enabling a live loudness meter.

All inputs are synthetic. Timings include the Python/native call boundary and
serial processing of distinct insert buffers, but exclude capture, FFT, HTTP and
host scheduling. Numerical agreement with our existing reference is not meter
conformance; the native API returns gated integrated loudness, not live M/S.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import math
import platform
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pyloudnorm as pyln
from scipy.signal import resample_poly

PRODUCT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = PRODUCT_ROOT / "apps" / "backend" / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

# These match the existing callback matrix. The windows and 10 Hz cadence come
# from EBU Tech 3341 (2023), sections 2.2–2.3; HTTP publication stays separate.
RATES = (44_100, 48_000, 96_000)  # samples per second
WINDOWS = (0.4, 3.0)  # seconds: candidate momentary and short-term inputs
INSERT_COUNTS = (1, 8, 32, 64)
UPDATE_HZ = 10.0
WARMUPS = 3  # untimed batches warm dispatch and allocator paths
METRIC_TOLERANCE_DB = 1e-5  # Much finer than report rounding; this is a parity tolerance, not an EBU limit.
STANDARD_URL = "https://tech.ebu.ch/docs/tech/tech3341.pdf"


def _load_native() -> Any:
    """Load the installed opt-in kernel explicitly; never substitute Python."""
    try:
        module = importlib.import_module("kenn.core._kenn_dsp_native")
    except (ImportError, OSError) as exc:
        # A fallback would mislabel reference timing as native and invalidate the receipt.
        raise RuntimeError("The existing optional native DSP module must be built before profiling.") from exc
    if not callable(getattr(module, "loudness_metrics", None)):
        # An older wheel cannot measure this candidate; stop before collecting timings.
        raise RuntimeError("The installed native DSP module has no loudness_metrics kernel.")
    return module


def _finite_or_none(value: float) -> float | None:
    # Silence has no finite loudness/peak; JSON null preserves that absence.
    return float(value) if math.isfinite(value) else None


def reference_metrics(samples: np.ndarray, rate: int) -> dict[str, float | None]:
    """Return unrounded clip LUFS/4x peak; silence returns absent measurements."""
    values = samples.astype(np.float64)
    peak = float(np.max(np.abs(resample_poly(values, 4, 1, axis=0))))
    return {
        "integrated_lufs": _finite_or_none(pyln.Meter(rate).integrated_loudness(values)),
        "true_peak_dbtp": 20.0 * math.log10(peak) if peak > 0.0 else None,
    }


def ungated_loudness(samples: np.ndarray, rate: int) -> float | None:
    """Return whole-buffer K-weighted loudness, or None for zero filtered energy."""
    values = samples.astype(np.float64)
    # The installed reference exposes its weighting stages here. Recording its
    # version lets a changed private API fail visibly instead of inventing M/S.
    for stage in pyln.Meter(rate)._filters.values():
        for channel in range(values.shape[1]):
            values[:, channel] = stage.apply_filter(values[:, channel])
    energy = float(np.mean(np.sum(values * values, axis=1)))
    return -0.691 + 10.0 * math.log10(energy) if energy > 0.0 else None  # BS.1770 loudness offset in dB.


def _fixture(rate: int, seconds: float) -> np.ndarray:
    """Build contiguous float32 stereo audio with independent high/low tones."""
    t = np.arange(round(rate * seconds), dtype=np.float64) / rate
    return np.ascontiguousarray(np.column_stack((
        0.1 * np.sin(2.0 * np.pi * 997.0 * t),  # -20 dBFS peak at 997 Hz
        0.08 * np.sin(2.0 * np.pi * 53.0 * t + 0.4),  # 53 Hz; 0.4-radian phase offset
    )), dtype=np.float32)


def _measure_batch(
    function: Callable, inputs: list[np.ndarray], rate: int, repeats: int,
) -> dict[str, Any]:
    """Time complete serial batches after warming, with buffers already prepared."""
    for _ in range(WARMUPS):
        for values in inputs:
            function(values, rate)
    wall_ms, cpu_ms = [], []
    for _ in range(repeats):
        cpu_started = time.process_time_ns()
        wall_started = time.perf_counter_ns()
        for values in inputs:
            function(values, rate)
        wall_ms.append((time.perf_counter_ns() - wall_started) / 1e6)
        cpu_ms.append((time.process_time_ns() - cpu_started) / 1e6)
    return {
        "inserts": len(inputs), "input_bytes": sum(values.nbytes for values in inputs),
        "repeats": repeats, "warmup_batches": WARMUPS,
        "wall_mean_ms": statistics.mean(wall_ms),
        "wall_p99_ms": float(np.percentile(wall_ms, 99)),
        "wall_max_ms": max(wall_ms), "process_cpu_mean_ms": statistics.mean(cpu_ms),
        # One second has 1,000 ms; multiplying by Hz then /10 gives percent of
        # one core. This is extrapolated demand, not a sustained worker CPU test.
        "projected_one_core_cpu_percent_at_10hz": statistics.mean(cpu_ms) * UPDATE_HZ / 10.0,
        "projected_serial_wall_percent_at_10hz": statistics.mean(wall_ms) * UPDATE_HZ / 10.0,
        "samples_wall_ms": wall_ms,
    }


def _parity(native: dict, reference: dict) -> dict[str, Any]:
    """Compare required clip metrics; missing keys and one-sided absence fail."""
    deltas: dict[str, float | None] = {}
    passed = True
    for name in ("integrated_lufs", "true_peak_dbtp"):
        left, right = native.get(name), reference.get(name)
        passed = passed and name in native and name in reference
        if left is None or right is None:
            # A one-sided absence is a failed comparison, including silence handling.
            deltas[name] = None
            passed = passed and left is None and right is None
        else:
            delta = abs(float(left) - float(right))
            deltas[name] = delta if math.isfinite(delta) else None
            passed = passed and math.isfinite(delta) and delta <= METRIC_TOLERANCE_DB
    return {"passed": passed, "absolute_deltas_db": deltas,
            "native": {name: native.get(name) for name in deltas}, "reference": reference}


def semantic_probes(native: Any) -> dict[str, Any]:
    """Show why clip results cannot be relabelled as a continuous live meter."""
    rate = 48_000  # samples per second; semantic probes are separate from the rate matrix.
    t = np.arange(3 * rate) / rate
    level = np.where(t < 0.4, 0.1, 0.001)  # First 400 ms at -20 dBFS peak, then -60 dBFS.
    gated_input = np.ascontiguousarray(np.column_stack((level * np.sin(2 * np.pi * 997 * t),) * 2), dtype=np.float32)
    gated = float(native.loudness_metrics(gated_input, rate)["integrated_lufs"])
    ungated = ungated_loudness(gated_input, rate)

    dc = np.full((5 * rate, 2), 0.1, dtype=np.float32)  # Five seconds of constant DC isolates filter restart.
    filtered = dc.astype(np.float64)
    for stage in pyln.Meter(rate)._filters.values():
        for channel in range(2):
            filtered[:, channel] = stage.apply_filter(filtered[:, channel])
    tail_energy = float(np.mean(np.sum(filtered[-round(0.4 * rate):] ** 2, axis=1)))
    continuous = -0.691 + 10 * math.log10(tail_energy) if tail_energy > 0 else None
    restarted = native.loudness_metrics(dc[-round(0.4 * rate):].copy(), rate)["integrated_lufs"]
    return {
        "gating": {"native_3s_integrated_lufs": gated, "reference_3s_ungated_lufs": ungated,
                   "difference_db": None if ungated is None else gated - ungated},
        "filter_restart": {"native_restarted_400ms_lufs": restarted,
                           "reference_continuous_tail_400ms_lufs": continuous},
        "interpretation": "Gating and filter reset change readings. Live M/S needs continuous weighting and ungated rolling energy.",
    }


def run(
    *, repeats: int = 20, rates: tuple[int, ...] = RATES,
    windows: tuple[float, ...] = WINDOWS, insert_counts: tuple[int, ...] = INSERT_COUNTS,
) -> dict[str, Any]:
    """Return a bounded synthetic profile and parity receipt; leave runtime flags alone."""
    if isinstance(repeats, bool) or not isinstance(repeats, int) or not 3 <= repeats <= 100:
        raise ValueError("repeats must be an integer from 3 to 100 batches")
    for name, chosen, allowed in (("rates", rates, RATES), ("windows", windows, WINDOWS),
                                  ("insert_counts", insert_counts, INSERT_COUNTS)):
        if (not chosen or len(chosen) > len(allowed) or len(set(chosen)) != len(chosen)
                or any(isinstance(value, bool) or value not in allowed for value in chosen)
                or (name != "windows" and any(not isinstance(value, int) for value in chosen))):
            raise ValueError(f"{name} must be a non-empty subset of {allowed}")
    native = _load_native()
    cases = []
    for rate in rates:
        for seconds in windows:
            values = _fixture(rate, seconds)
            # Buffers differ in level and storage, so repeated insert calls do
            # not accidentally profile a single shared clip's cache behavior.
            inputs = [np.ascontiguousarray(values * (1 - 0.5 * index / max(insert_counts)))
                      for index in range(max(insert_counts))]
            reference = reference_metrics(values, rate)
            measured = dict(native.loudness_metrics(values, rate))
            cases.append({
                "rate_hz": rate, "window_seconds": seconds,
                "fixture_sha256": hashlib.sha256(values.tobytes()).hexdigest(),
                "parity": _parity(measured, reference),
                "reference": _measure_batch(reference_metrics, [values], rate, repeats),
                "native_batches": [_measure_batch(native.loudness_metrics, inputs[:count], rate, repeats)
                                   for count in insert_counts],
            })
    return {
        "schema": "kenn.live_loudness_reuse_profile.v1", "passed": all(case["parity"]["passed"] for case in cases),
        "machine": {"system": platform.system(), "release": platform.release(),
                    "machine": platform.machine(), "python": platform.python_version()},
        "versions": {name: importlib.metadata.version(name) for name in ("numpy", "scipy", "pyloudnorm")},
        "identity": {"native_binary_sha256": hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest(),
                     "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                     "native_source_sha256": hashlib.sha256((PRODUCT_ROOT / "tooling/native/dsp_core/loudness_bindings.cpp").read_bytes()).hexdigest()},
        "update_hz": UPDATE_HZ, "cases": cases, "semantic_probes": semantic_probes(native),
        "measurement_scope": {
            "native": "Complete existing clip API: integrated LUFS, LRA and 4x peak, including per-call workspace allocation.",
            "reference": "Integrated LUFS and 4x peak only; no LRA. This is a parity oracle and timing context, not an equal-work speed comparison.",
        },
        "promotion_decision": "Do not attach the stateless clip kernel to the realtime worker as a live M/S meter.",
        "limitations": [
            "CPU demand is extrapolated from short serial batches; no sustained deadline or host claim.",
            "Timings exclude capture, existing analysis, publication and model contention; fixture memory is not plug-in memory.",
            "The installed native binary is identified by hash; the current source hash does not prove that binary was built from it.",
            "Parity covers our existing pyloudnorm/scipy clip algorithms; no EBU/ITU conformance claim or live LUFS/dBTP output.",
        ],
        "standard": {"url": STANDARD_URL, "sections": "2.2–2.3", "revision": "November 2023"},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=20)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args(argv)
    try:
        result = run(repeats=args.repeats)
    except (ValueError, RuntimeError) as exc:
        # Invalid inputs or a missing native kernel must stop rather than emit a success receipt.
        parser.error(str(exc))
    rendered = json.dumps(result, indent=2, allow_nan=False) + "\n"
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
