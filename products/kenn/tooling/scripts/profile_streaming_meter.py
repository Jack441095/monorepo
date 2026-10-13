#!/usr/bin/env python3
"""Qualify the disabled native streaming candidate using generated audio only.

SciPy filters the entire continuous input once; every native rolling window is
compared with a slice of that reference. Timings use the real capture/FFT worker
drained synchronously, excluding host scheduling, HTTP and model contention.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import io
import json
import math
import platform
import statistics
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from scipy.signal import bilinear_zpk, lfilter, tf2zpk, upfirdn, zpk2tf

PRODUCT_ROOT = Path(__file__).resolve().parents[2]
RATES = (44_100, 48_000, 96_000)  # Qualified stereo frames per second.
INSERT_COUNTS = (1, 8, 32, 64)
MODES = ("baseline_worker", "streaming_meter", "combined_worker")
STANDARD_URL = "https://www.itu.int/rec/R-REC-BS.1770-5-202311-I/en"
EBU_URL = "https://tech.ebu.ch/docs/tech/tech3341.pdf"
TERMS_URL = "https://tech.ebu.ch/files/live/sites/tech/files/shared/testmaterial/use%20of%20EBU%20AUDIO%20test%20sequences.pdf"
# The reference deliberately uses one full causal 48-tap convolution, rather
# than copying the native four-phase ring algorithm (BS.1770-5 Annex 2).
PEAK_FIR = np.array([
    .0017089843750, -.0291748046875, -.0189208984375, -.0083007812500,
    .0109863281250, .0292968750000, .0330810546875, .0148925781250,
    -.0196533203125, -.0517578125000, -.0582275390625, -.0266113281250,
    .0332031250000, .0891113281250, .1015625000000, .0476074218750,
    -.0594482421875, -.1665039062500, -.2003173828125, -.1022949218750,
    .1373291015625, .4650878906250, .7797851562500, .9721679687500,
    .9721679687500, .7797851562500, .4650878906250, .1373291015625,
    -.1022949218750, -.2003173828125, -.1665039062500, -.0594482421875,
    .0476074218750, .1015625000000, .0891113281250, .0332031250000,
    -.0266113281250, -.0582275390625, -.0517578125000, -.0196533203125,
    .0148925781250, .0330810546875, .0292968750000, .0109863281250,
    -.0083007812500, -.0189208984375, -.0291748046875, .0017089843750,
])  # Dimensionless interpolation gain; four phase sums are approximately unity.


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _at_rate(b: list[float], a: list[float], rate: int) -> tuple[np.ndarray, np.ndarray]:
    """Map the published 48 kHz filters through an independent ZPK transform."""
    if rate == 48_000:
        return np.asarray(b), np.asarray(a)  # Keep the standard's coefficients exact at its reference rate.
    zeros, poles, gain = tf2zpk(b, a)
    # Invert the 48 kHz bilinear transform, then let SciPy discretise that
    # analogue prototype at the requested rate. Native code uses polynomials.
    analogue_zeros = 96_000.0 * (zeros - 1.0) / (zeros + 1.0)
    analogue_poles = 96_000.0 * (poles - 1.0) / (poles + 1.0)
    analogue_gain = gain * np.prod(1.0 + zeros) / np.prod(1.0 + poles)
    return tuple(np.real_if_close(value) for value in zpk2tf(*bilinear_zpk(
        analogue_zeros, analogue_poles, analogue_gain, rate,
    )))


def reference_trace(samples: np.ndarray, rate: int) -> np.ndarray:
    """Return [end, M-ready, S-ready, M-energy, S-energy, FIR-peak] every 100 ms."""
    values = np.asarray(samples, dtype=np.float64)
    if rate not in RATES or values.ndim != 2 or values.shape[1] != 2 or not len(values) or not np.isfinite(values).all():
        # A malformed synthetic reference cannot qualify a native implementation.
        raise ValueError("Reference requires finite stereo audio at a qualified sample rate.")
    weighted = values.copy()
    for b, a in (
        ([1.53512485958697, -2.69169618940638, 1.19839281085285], [1.0, -1.69065929318241, .73248077421585]),
        ([1.0, -2.0, 1.0], [1.0, -1.99004745483398, .99007225036621]),
    ):
        numerator, denominator = _at_rate(b, a, rate)
        weighted = lfilter(numerator, denominator, weighted, axis=0)
    energy = np.sum(weighted * weighted, axis=1)
    peaks = np.max(np.abs(upfirdn(PEAK_FIR, values, up=4, axis=0)[:4 * len(values)]).reshape(len(values), 4, 2), axis=(1, 2))
    step = rate // 10  # Frames in exactly 100 ms at each qualified rate.
    rows = []
    for end in range(step, len(values) + 1, step):
        rows.append([
            end, end >= 4 * step, end >= 30 * step,
            float(np.mean(energy[end - 4 * step:end])) if end >= 4 * step else 0.0,
            float(np.mean(energy[end - 30 * step:end])) if end >= 30 * step else 0.0,
            float(np.max(peaks[end - step:end])),
        ])
    return np.asarray(rows, dtype=np.float64).reshape(-1, 6)


def native_trace(binary: Path, samples: np.ndarray, rate: int) -> np.ndarray:
    """Trace temporary generated stereo float32 input; keep audio out of the repo."""
    with tempfile.TemporaryDirectory(prefix="kenn-streaming-meter-") as directory:
        fixture = Path(directory) / "synthetic.f32"
        np.asarray(samples, dtype="<f4").tofile(fixture)
        result = subprocess.run([str(binary), "--trace", str(rate), str(fixture)], check=True, capture_output=True, text=True, timeout=30)
    try:
        values = np.loadtxt(io.StringIO(result.stdout), delimiter=",", ndmin=2)
    except ValueError as exc:
        # Diagnostics or malformed output must never become a passing trace.
        raise ValueError("Native trace was not six numeric columns.") from exc
    if values.shape != (len(samples) // (rate // 10), 6) or not np.isfinite(values).all():
        raise ValueError("Native trace has missing rows, wrong columns or non-finite values.")
    return values


def compare_trace(actual: np.ndarray, expected: np.ndarray) -> dict[str, Any]:
    """Require exact sample/readiness metadata and fine linear-energy/FIR parity."""
    if actual.shape != expected.shape or actual.ndim != 2 or actual.shape[1] != 6 or not len(actual):
        raise ValueError("Comparable traces require equal nonempty six-column shapes.")
    if not np.isfinite(actual).all() or not np.isfinite(expected).all():
        raise ValueError("A trace with non-finite measurements cannot pass.")
    metadata_ok = bool(np.array_equal(actual[:, :3], expected[:, :3]))
    # Below -150 LUFS the double-precision IIR tail is sensitive to arithmetic
    # rounding. Compare absolute energy there; do not interpret log differences
    # as audible errors or introduce that floor into the native meter.
    energy_ok = bool(np.allclose(actual[:, 3:5], expected[:, 3:5], rtol=1e-8, atol=1e-15))
    peak_ok = bool(np.allclose(actual[:, 5], expected[:, 5], rtol=1e-12, atol=1e-15))
    audible = (expected[:, 3:5] > 1e-15) & (actual[:, 3:5] > 0.0)
    delta = np.abs(10.0 * np.log10(actual[:, 3:5][audible] / expected[:, 3:5][audible]))
    return {
        "passed": metadata_ok and energy_ok and peak_ok, "windows": len(actual),
        "metadata_passed": metadata_ok, "energy_passed": energy_ok, "peak_passed": peak_ok,
        "maximum_loudness_delta_above_numerical_floor_db": float(np.max(delta)) if len(delta) else None,
        "maximum_energy_delta": float(np.max(np.abs(actual[:, 3:5] - expected[:, 3:5]))),
        "maximum_peak_linear_delta": float(np.max(np.abs(actual[:, 5] - expected[:, 5]))),
    }


def _fixture(rate: int, name: str) -> np.ndarray:
    """Generate calibration, changing-level, DC, silence or phased peak inputs."""
    seconds = 5.0 if name == "dc" else 1.0 if name.startswith("peak_") else 4.0
    t = np.arange(round(rate * seconds), dtype=np.float64) / rate
    if name.startswith("peak_"):
        # Generated descriptions of Tech 3341 cases 15–19, including 10 ms
        # fades. No downloaded EBU audio or commercial programme material.
        divisor, phase, gain = {
            "peak_15": (4, 0.0, 0.5), "peak_16": (4, 45.0, 0.5),
            "peak_17": (6, 60.0, 0.5), "peak_18": (8, 67.5, 0.5), "peak_19": (4, 45.0, 1.41),
        }[name]
        fade = np.minimum(1.0, np.minimum(t / .01, (seconds - t) / .01))  # 10 ms fade, dimensionless gain.
        left = gain * np.sin(2.0 * np.pi * rate / divisor * t + np.deg2rad(phase)) * fade
        right = left
    elif name == "calibration":
        left = np.power(10.0, -23.0 / 20.0) * np.sin(2.0 * np.pi * 1000.0 * t)
        right = left
    elif name == "anti_phase":
        left = np.power(10.0, -33.0 / 20.0) * np.sin(2.0 * np.pi * 1000.0 * t)
        right = -left
    elif name == "changing_level":
        gain = np.where(t < .4, .1, .001)  # 400 ms loud then 3.6 seconds quiet: gating would erase the intended history.
        left = gain * np.sin(2.0 * np.pi * 997.0 * t)
        right = gain * np.sin(2.0 * np.pi * 53.0 * t + .4)  # Radians.
    elif name == "dc":
        left = np.full(len(t), .1); right = left  # Linear full-scale level; persistent weighting must remove its startup transient.
    elif name == "silence":
        left = np.zeros(len(t)); right = left
    elif name == "noise":
        noise = np.random.default_rng(1770).normal(0.0, .05, (len(t), 2))  # Fixed seed and .05 full-scale RMS.
        left, right = noise.T
    else:
        raise ValueError("Unknown synthetic fixture.")  # Refuse a misspelt fixture instead of changing the signal being qualified.
    return np.ascontiguousarray(np.column_stack((left, right)), dtype=np.float32)


def qualify(binary: Path) -> list[dict[str, Any]]:
    """Compare all rolling windows and generated calibration/peak tolerances."""
    reports = []
    names = ("calibration", "anti_phase", "changing_level", "dc", "silence", "noise", *(f"peak_{i}" for i in range(15, 20)))
    for rate in RATES:
        for name in names:
            samples = _fixture(rate, name)
            actual = native_trace(binary, samples, rate)
            report = {"rate": rate, "fixture": name, "fixture_sha256": hashlib.sha256(samples.tobytes()).hexdigest(),
                      **compare_trace(actual, reference_trace(samples, rate))}
            if name in ("calibration", "anti_phase"):
                expected = -23.0 if name == "calibration" else -33.0
                readings = -.691 + 10.0 * np.log10(actual[actual[:, 2] == 1, 3:5])  # LUFS offset, dB.
                report["maximum_calibration_error_lu"] = float(np.max(np.abs(readings - expected)))
                report["passed"] &= report["maximum_calibration_error_lu"] <= .1  # Tech 3341 cases 1/2 tolerance, LU.
            elif name.startswith("peak_"):
                expected = 3.0 if name == "peak_19" else -6.0  # Tech 3341's rounded target, dBTP.
                measured = 20.0 * math.log10(float(np.max(actual[:, 5])))
                report.update(true_peak_dbtp=measured, target_dbtp=expected, error_db=measured - expected)
                report["passed"] &= -.4 <= measured - expected <= .2  # Tech 3341 cases 15–19 total error, dB.
            elif name == "dc":
                report["final_momentary_energy"] = float(actual[-1, 3])
                report["passed"] &= actual[-1, 3] < 1e-15  # Below -150 LUFS numerical-check scale, not a report floor.
            elif name == "silence":
                report["passed"] &= bool(np.array_equal(actual[:, 3:], np.zeros_like(actual[:, 3:])))
            report["passed"] = bool(report["passed"])  # NumPy comparisons must become ordinary JSON booleans.
            reports.append(report)
    return reports


def summarize_native_profile(payload: dict[str, Any], repeats: int) -> dict[str, Any]:
    """Validate the full timing matrix before interpreting percent of one core."""
    expected = {(rate, inserts, mode) for rate in RATES for inserts in INSERT_COUNTS for mode in MODES}
    if payload.get("schema") != "kenn.streaming_meter_native_profile.v1" or payload.get("repeats") != repeats:
        raise ValueError("Native timing schema/repeats mismatch.")  # An older/misconfigured executable cannot label this receipt.
    if not isinstance(payload.get("meter_bytes"), int) or payload["meter_bytes"] <= 0:
        raise ValueError("Native candidate storage is missing.")
    cells = []
    seen = set()
    for cell in payload.get("cells", []):
        identity = (cell["rate"], cell["inserts"], cell["mode"])
        if identity not in expected or identity in seen:
            raise ValueError("Unexpected or duplicate timing cell.")  # Duplicate rows cannot stand in for a missing mode/rate.
        seen.add(identity)
        for key in ("wall_ms", "cpu_ms"):
            values = cell.get(key, [])
            if len(values) != repeats or any(not math.isfinite(value) or value < 0.0 for value in values):
                raise ValueError("Incomplete or non-finite timing samples.")
        if cell.get("warmup_ticks") != 32:
            raise ValueError("Profile did not warm the 3-second history.")
        if cell.get("processing_passed") is not True:
            raise ValueError("Profile did not verify complete candidate/worker processing.")
        wall_mean = statistics.mean(cell["wall_ms"])
        cpu_mean = statistics.mean(cell["cpu_ms"])
        # Ten batches/second: 1 ms CPU per 100 ms batch is 1% of one core.
        cells.append({**cell, "wall_mean_ms": wall_mean, "wall_p99_ms": float(np.percentile(cell["wall_ms"], 99)),
                      "wall_max_ms": max(cell["wall_ms"]), "process_cpu_mean_ms": cpu_mean,
                      "projected_one_core_percent_at_10hz": cpu_mean, "serial_100ms_budget_percent": wall_mean})
    if seen != expected:
        raise ValueError("Native timing matrix is incomplete.")
    return {"candidate_storage_bytes_per_insert": payload["meter_bytes"], "native_compiler": payload.get("compiler"),
            "native_assertions_enabled": payload.get("assertions_enabled"), "cells": cells}


def run(binary: Path, repeats: int = 20) -> dict[str, Any]:
    """Run native retirement tests, independent numerical checks and CPU timings."""
    if isinstance(repeats, bool) or not isinstance(repeats, int) or not 3 <= repeats <= 100:
        raise ValueError("Repeats must be an integer between 3 and 100.")  # Bound local work before starting any native process.
    binary = binary.resolve(strict=True)
    functional = subprocess.run([str(binary)], check=True, capture_output=True, text=True, timeout=60)
    conformance_subset = qualify(binary)
    native = subprocess.run([str(binary), "--profile", str(repeats)], check=True, capture_output=True, text=True, timeout=180)
    timings = summarize_native_profile(json.loads(native.stdout), repeats)
    source_paths = ("plugins/kenn-vst3-au/Source/StreamingMeter.h", "plugins/kenn-vst3-au/Source/ContinuousAnalysis.cpp",
                    "plugins/kenn-vst3-au/Source/ContinuousAnalysis.h", "plugins/kenn-vst3-au/Source/test_streaming_meter_main.cpp")
    return {
        "schema": "kenn.streaming_meter_qualification.v1", "passed": all(item["passed"] for item in conformance_subset),
        "machine": {"platform": platform.platform(), "architecture": platform.machine(), "python": platform.python_version()},
        "versions": {name: importlib.metadata.version(name) for name in ("numpy", "scipy")},
        "binary_sha256": _hash(binary), "tool_sha256": _hash(Path(__file__)),
        "source_sha256": {path: _hash(PRODUCT_ROOT / path) for path in source_paths},
        "source_identity_limit": "Current source hashes alone do not prove binary build provenance.",
        "native_functional_result": functional.stdout.strip(), "generated_signal_checks": conformance_subset, **timings,
        "references": {"bs1770": STANDARD_URL, "tech3341": EBU_URL, "ebu_audio_terms": TERMS_URL},
        "limits": [
            "Generated cases 1/2 and 15–19 plus continuous numerical references; no downloaded EBU audio or complete EBU/ITU conformance suite.",
            "No integrated loudness, LRA or maximum momentary/short-term display; not an EBU Mode meter.",
            "100 ms FIR-output peak intervals are delayed 5.875 input samples; they are not exactly aligned loudness-input peaks.",
            "Fixed 4x interpolation has frequency-dependent under-read; 44.1 kHz produces 176.4 kHz, below Annex 2's 192 kHz guideline. Passing selected tones is not universal accuracy.",
            "Thirty-two warm-up ticks and short serial timing batches; synchronous real worker includes capture, FFT and filtering, excludes thread scheduling, HTTP, model and Ableton.",
            "CPU percent is projected from process CPU per 100 ms batch, not sustained host CPU or a callback deadline guarantee.",
            "Candidate is disabled in normal plug-in calls and absent from published LUFS/dBTP fields.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=20)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args(argv)
    report = run(args.binary, args.repeats)
    encoded = json.dumps(report, indent=2, allow_nan=False) + "\n"
    if args.json_out:
        args.json_out.write_text(encoded)
    else:
        print(encoded, end="")
    return 0 if report["passed"] else 1  # Preserve failed numerical qualification in both the receipt and exit status.


if __name__ == "__main__":
    raise SystemExit(main())
