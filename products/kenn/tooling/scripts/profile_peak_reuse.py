#!/usr/bin/env python3
"""Compare prepared native true-peak filters offline using generated stereo audio.

The sinusoid reference is its known continuous amplitude, independent of either
filter. CPU cells are serial microbenchmarks, not Live deadline qualification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import statistics
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

PRODUCT_ROOT = Path(__file__).resolve().parents[2]
RATES = (44_100, 48_000, 96_000)  # Stereo input frames per second.
INSERT_COUNTS = (1, 8, 32, 64)
MODES = ("current", "juce4", "juce8", "juce8_frame")
FREQUENCIES = (.125, .25, .375, .4, .425, .45)  # Cycles per input frame.
PHASE_COUNT = 16  # Uniform phases over half a cycle; absolute peaks repeat there.
METADATA = {
    "current": (4, 5.875, 0.0), "juce4": (4, 35.75, 59.5),
    "juce8": (8, 38.625, 64.25), "juce8_frame": (8, 38.625, 64.25),
}  # Factor, measured upsampling delay and API round-trip delay, in input frames.
JUCE_COMMIT = "4ada2e1f4db082f5dd803f249f37b3bf9c5f55ef"  # Cached JUCE 8.0.2 source.
# Half the selected Tech 3341 cases' -0.4/+0.2 dB tolerance leaves engineering
# margin. This bounded tone sweep is not a standards conformance test.
ERROR_BOUNDS_DB = (-.2, .1)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _number(value: Any, *, positive: bool = False) -> bool:
    return (type(value) in (float, int) and math.isfinite(value)
            and (value > 0 if positive else value >= 0))


def _call(binary: Path, *arguments: str) -> dict[str, Any]:
    result = subprocess.run([str(binary), *arguments], check=True, capture_output=True, text=True, timeout=60)
    try:
        payload = json.loads(result.stdout)
    except ValueError as exc:
        # Tool diagnostics must fail instead of being interpreted as evidence.
        raise ValueError("Native comparison did not return JSON.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Native comparison must return an object.")  # Reject ambiguous output before interpreting measurements.
    return payload


def tone_cases() -> list[dict[str, Any]]:
    """Describe steady sinusoids with a known 0.5 full-scale continuous peak."""
    cases = [{"name": f"tone_{frequency}_{phase}", "frequency": frequency,
              "phase_rad": math.pi * phase / PHASE_COUNT}
             for frequency in FREQUENCIES for phase in range(PHASE_COUNT)]
    cases += [
        {"name": "short_fir_underread", "frequency": .45, "phase_rad": .37},
        # cos(2*pi*.4*(n-.125)) places its maxima halfway between the 4x grid.
        {"name": "four_times_grid_miss", "frequency": .4, "phase_rad": math.pi / 2 - 2 * math.pi * .4 * .125},
    ]
    return cases


def tone(rate: int, case: dict[str, Any]) -> np.ndarray:
    """Generate three 100 ms bins, preserving opposite stereo channel phases."""
    positions = np.arange(3 * (rate // 10), dtype=np.float64)
    values = .5 * np.sin(2 * np.pi * case["frequency"] * positions + case["phase_rad"])
    return np.column_stack((values, -values)).astype("<f4")


def native_trace(binary: Path, samples: np.ndarray, rate: int, mode: str) -> dict[str, Any]:
    """Reject malformed fixtures/output and return contiguous causal 100 ms peaks."""
    values = np.asarray(samples)
    if (rate not in RATES or mode not in MODES or values.ndim != 2 or values.shape[1] != 2
            or not len(values) or len(values) % (rate // 10) or len(values) > 10 * rate
            or not np.isfinite(values).all()):
        raise ValueError("Trace requires finite stereo audio in complete qualified 100 ms bins.")  # No silent tail truncation.
    with tempfile.TemporaryDirectory(prefix="kenn-peak-reuse-") as directory:
        fixture = Path(directory) / "synthetic.f32"
        values.astype("<f4").tofile(fixture)
        payload = _call(binary, "--trace", mode, str(rate), str(fixture))
    metadata = tuple(payload.get(key) for key in ("factor", "upsampling_delay_frames", "round_trip_delay_frames"))
    peaks = payload.get("peaks")
    if (metadata != METADATA[mode] or type(payload.get("cpp_heap_calls")) is not int
            or payload["cpp_heap_calls"] < 0 or not isinstance(peaks, list)
            or len(peaks) != len(values) // (rate // 10) or not all(_number(value) for value in peaks)):
        raise ValueError("Native trace has incorrect delay/factor, heap count or peaks.")  # Wrong units and missing windows cannot qualify a filter.
    return payload


def summarize_timings(cells: list[dict[str, Any]], repeats: int) -> list[dict[str, Any]]:
    """Require the entire warmed matrix and retain raw process CPU/wall samples."""
    expected = {(rate, inserts, mode) for rate in RATES for inserts in INSERT_COUNTS for mode in MODES}
    seen = set()
    summaries = []
    for cell in cells:
        key = (cell.get("rate"), cell.get("inserts"), cell.get("mode"))
        if (key not in expected or key in seen or cell.get("warmup_ticks") != 32
                or type(cell.get("cpp_heap_calls")) is not int or cell["cpp_heap_calls"] < 0
                or not _number(cell.get("checksum"), positive=True)):
            raise ValueError("Invalid or duplicate timing matrix cell.")  # Never average missing coverage into a passing benchmark.
        seen.add(key)
        for field in ("wall_ms", "cpu_ms"):
            samples = cell.get(field)
            if not isinstance(samples, list) or len(samples) != repeats or not all(_number(value, positive=True) for value in samples):
                raise ValueError("Invalid timing samples.")  # Clock failures and cold/missing repeats are not zero-cost work.
        wall, cpu = cell["wall_ms"], cell["cpu_ms"]
        summaries.append({**cell, "wall_mean_ms": statistics.mean(wall),
                          "wall_p99_ms": float(np.quantile(wall, .99)), "wall_max_ms": max(wall),
                          "process_cpu_mean_ms": statistics.mean(cpu),
                          # One serial 100 ms tick runs at 10 Hz. CPU ms/tick has
                          # the same numeric value as percent of one full core.
                          "projected_one_core_percent_at_10hz": statistics.mean(cpu)})
    if seen != expected:
        raise ValueError("Timing matrix is incomplete.")  # A fast subset cannot stand in for 64 inserts at every rate.
    return summaries


def _continuity_fixtures(rate: int) -> dict[str, np.ndarray]:
    frames = 5 * (rate // 10)  # 500 ms crosses four publication boundaries.
    silence = np.zeros((frames, 2), dtype="<f4")
    dc = silence.copy(); dc[:, 1] = .25  # Right-only DC also exercises independent channels.
    impulses = silence.copy()
    for offset in (-1, 0, 1, 35, 39):  # Input frames around a boundary and each measured FIR delay.
        impulses[2 * (rate // 10) + offset, offset % 2] = .5
    noise = np.random.default_rng(121).uniform(-.25, .25, (frames, 2)).astype("<f4")
    return {"silence": silence, "right_dc": dc, "boundary_impulses": impulses, "seeded_stereo_noise": noise}


def run(binary: Path, juce_source: Path, repeats: int = 20) -> dict[str, Any]:
    """Return measured comparison evidence, keeping all implementations disabled."""
    if type(repeats) is not int or not 3 <= repeats <= 30:
        raise ValueError("Repeats must be an integer from 3 through 30.")  # Bound warmed timing receipts before starting a native process.
    info = _call(binary, "--info")
    if (info.get("juce_version") != "8.0.2" or info.get("assertions_enabled") is not False
            or info.get("pointer_bits") != 64 or not _number(info.get("current_meter_bytes"), positive=True)
            or not isinstance(info.get("compiler"), str) or not info["compiler"]):
        raise ValueError("Comparison requires the qualified 64-bit Release build.")  # Debug and unknown builds cannot support the CPU decision.
    commit = subprocess.run(["git", "-C", str(juce_source), "rev-parse", "HEAD"], check=True,
                            capture_output=True, text=True, timeout=10).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(juce_source), "status", "--porcelain", "--untracked-files=no"],
                           check=True, capture_output=True, text=True, timeout=10).stdout
    if commit != JUCE_COMMIT or dirty:
        raise ValueError("JUCE source must be the unmodified cached 8.0.2 checkout.")  # Version macros alone cannot identify modified filter code.
    cases = tone_cases()
    accuracy, continuity = [], []
    for rate in RATES:
        for mode in MODES:
            results = []
            heap_calls = 0
            for case in cases:
                trace = native_trace(binary, tone(rate, case), rate, mode)
                # Discard the first 200 ms, longer than every measured filter
                # delay; the final continuous 100 ms interval contains many peaks.
                error = 20 * math.log10(trace["peaks"][-1] / .5)
                results.append({**case, "error_db": error})
                heap_calls += trace["cpp_heap_calls"]
            minimum = min(results, key=lambda row: row["error_db"])
            maximum = max(results, key=lambda row: row["error_db"])
            failures = sum(not ERROR_BOUNDS_DB[0] <= row["error_db"] <= ERROR_BOUNDS_DB[1] for row in results)
            accuracy.append({"rate": rate, "mode": mode, "cases": len(results),
                             "failed_cases": failures, "passed": failures == 0,
                             "minimum": minimum, "maximum": maximum, "cpp_heap_calls": heap_calls,
                             "factor": METADATA[mode][0], "upsampling_delay_frames": METADATA[mode][1],
                             "round_trip_delay_frames": METADATA[mode][2]})
        for name, fixture in _continuity_fixtures(rate).items():
            batched = native_trace(binary, fixture, rate, "juce8")
            single = native_trace(binary, fixture, rate, "juce8_frame")
            delta = float(np.max(np.abs(np.array(batched["peaks"]) - np.array(single["peaks"]))))
            continuity.append({"rate": rate, "fixture": name, "maximum_linear_delta": delta,
                               "passed": delta <= 1e-12 and (name != "silence" or not any(batched["peaks"])),
                               "cpp_heap_calls": batched["cpp_heap_calls"] + single["cpp_heap_calls"],
                               "batched_peaks": batched["peaks"], "single_frame_peaks": single["peaks"]})
        print(f"Completed accuracy and continuity at {rate} Hz", flush=True)
    timings = summarize_timings([
        _call(binary, "--profile", mode, str(rate), str(inserts), str(repeats))
        for rate in RATES for inserts in INSERT_COUNTS for mode in MODES
    ], repeats)
    source_files = ("tooling/native/peak_compare/CMakeLists.txt", "tooling/native/peak_compare/main.cpp",
                    "tooling/scripts/profile_peak_reuse.py", "plugins/kenn-vst3-au/Source/StreamingMeter.h")
    juce_files = ("modules/juce_dsp/processors/juce_Oversampling.cpp", "modules/juce_dsp/processors/juce_Oversampling.h",
                  "modules/juce_dsp/filter_design/juce_FilterDesign.cpp", "modules/juce_dsp/filter_design/juce_FilterDesign.h")
    heap_passed = all(row["cpp_heap_calls"] == 0 for row in accuracy + continuity + timings)
    return {
        "schema": "kenn.peak_reuse_comparison.v1", "repeats": repeats,
        "provenance": {"native": info, "machine": platform.machine(), "python": platform.python_version(),
                       "numpy": np.__version__, "binary_sha256": _hash(binary), "juce_commit": commit,
                       "source_sha256": {name: _hash(PRODUCT_ROOT / name) for name in source_files},
                       "juce_source_sha256": {name: _hash(juce_source / name) for name in juce_files}},
        "accuracy_method": {"input": "Generated float32 antiphase stereo; continuous sinusoid amplitude 0.5",
                            "frequencies_cycles_per_frame": FREQUENCIES, "uniform_half_cycle_phases": PHASE_COUNT,
                            "tone_cases": cases,
                            "cases_per_rate_and_mode": len(cases), "warmup_ms": 200, "peak_interval_ms": 100,
                            "error_bounds_db": ERROR_BOUNDS_DB, "bounds_are_engineering_margin": True},
        "accuracy": accuracy, "continuity": continuity, "timings": timings,
        "ordinary_cpp_new_guard_passed": heap_passed,
        "juce8_bounded_checks_passed": heap_passed and all(row["passed"] for row in continuity)
            and all(row["passed"] for row in accuracy if row["mode"] in ("juce8", "juce8_frame")),
        "limitations": [
            "Tone sweep and continuity checks are bounded comparisons, not full BS.1770/EBU conformance.",
            "Peaks describe delayed causal output bins, not corrected input intervals.",
            "Current workload includes K-weighting and rolling M/S; JUCE modes include interpolation and peak scan only.",
            "Timings exclude capture/FFT worker, HTTP, model contention and host scheduling; not callback deadlines.",
            "C++ guard counts ordinary new/new[] only, not malloc or aligned allocations; no full heap proof.",
            "JUCE prepared state size and process RSS remain unmeasured; no native runtime/build change or installation.",
            "Passing bounded checks does not select a runtime implementation or qualify its CPU cost.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--juce-source", required=True, type=Path)
    parser.add_argument("--repeats", type=int, default=20)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args(argv)
    receipt = run(args.binary.resolve(), args.juce_source.resolve(), args.repeats)
    encoded = json.dumps(receipt, indent=2, allow_nan=False) + "\n"
    if args.json_out:
        args.json_out.write_text(encoded)
    else:
        print(encoded)
    # A failing baseline is useful comparison evidence. This exit code covers
    # the bounded accuracy/history/new checks, not a runtime selection or cost gate.
    return 0 if receipt["juce8_bounded_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
