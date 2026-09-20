#!/usr/bin/env python3
"""
Native (C++) vs pure-Python compute timing for the look-ahead limiter.

This is the first rung of the "earn the C++ port" ladder (see
docs/ANALYSIS_AND_DSP_DIRECTION_2026-07-23.md): the streaming budget benchmark
flagged the look-ahead limiter as the flattest per-block margin — a per-sample
Python loop (monotonic deque + release). This measures what a compiled kernel
actually buys for that specific processor.

It (1) confirms the C++ kernel is bit-identical to the Python limiter, then
(2) times the whole-signal limiter-envelope compute in both, at a few signal
lengths, and reports the speedup.

IMPORTANT framing: this speeds up COMPUTE, not latency. The limiter's look-ahead
latency (StreamingLimiter.latency_samples) is inherent to the algorithm and is
identical in C++ and Python. A native port shrinks the CPU cost per block; it
does not — and cannot — remove the look-ahead delay.

    python scripts/eval/native_kernel_bench.py
"""

from __future__ import annotations

import math
import sys
import time

import numpy as np

from audio_analysis.dsp_engine import native
from audio_analysis.dsp_engine.streaming import StreamingLimiter

SAMPLE_RATE = 48000
CFG = {"threshold_db": 0.0, "ceiling_db": -1.0, "release_ms": 50.0, "lookahead_ms": 5.0}


def _signal(seconds: float) -> np.ndarray:
    t = np.arange(int(SAMPLE_RATE * seconds)) / SAMPLE_RATE
    rng = np.random.default_rng(2)
    x = (0.7 * np.sin(2 * np.pi * 150 * t) + 0.5 * np.sin(2 * np.pi * 2000 * t)
         + 0.2 * rng.standard_normal(len(t)))
    if len(x) > 5010:
        x[5000:5010] += 3.0
    return x.astype(np.float64)


def _params():
    input_gain = 10.0 ** (-CFG["threshold_db"] / 20.0)
    ceiling = 10.0 ** (CFG["ceiling_db"] / 20.0)
    alpha_rel = math.exp(-1.0 / (SAMPLE_RATE * (CFG["release_ms"] / 1000.0)))
    lookahead = max(1, int(SAMPLE_RATE * CFG["lookahead_ms"] / 1000.0))
    return input_gain, ceiling, alpha_rel, lookahead


def _bench(fn, reps: int) -> float:
    fn()  # warm
    t0 = time.perf_counter()
    for _ in range(reps):
        fn()
    return (time.perf_counter() - t0) / reps * 1e3


def main() -> int:
    if not native.is_available():
        print("native C++ kernel unavailable (no C++ compiler) — skipping.")
        return 0

    input_gain, ceiling, alpha_rel, lookahead = _params()
    print(f"look-ahead limiter, native vs Python  (sample_rate={SAMPLE_RATE} Hz, "
          f"lookahead={CFG['lookahead_ms']} ms -> latency {lookahead - 1} samples)")

    # equivalence on a representative signal
    x = _signal(4.0)
    py_out, py_gain = StreamingLimiter(SAMPLE_RATE, **CFG).process_stream(x, block_size=128)
    c_gain, c_out = native.limiter_gain_envelope(x, input_gain, ceiling, alpha_rel, lookahead)
    print(f"  equivalence: audio max|Δ|={np.max(np.abs(c_out - py_out)):.2e}  "
          f"gain max|Δ|={np.max(np.abs(c_gain - py_gain)):.2e}  "
          f"{'IDENTICAL ✓' if np.max(np.abs(c_out - py_out)) == 0.0 else 'MISMATCH ✗'}")

    print(f"\n  {'seconds':>8} {'samples':>9} {'python_ms':>11} {'c++_ms':>9} {'speedup':>8}")
    for secs in (1.0, 4.0, 16.0):
        x = _signal(secs)
        reps = 20 if secs <= 4.0 else 8
        py_ms = _bench(lambda: StreamingLimiter(SAMPLE_RATE, **CFG).process_stream(x, block_size=128), reps)
        c_ms = _bench(lambda: native.limiter_gain_envelope(x, input_gain, ceiling, alpha_rel, lookahead), reps)
        print(f"  {secs:>8.1f} {len(x):>9} {py_ms:>11.3f} {c_ms:>9.3f} {py_ms / c_ms:>7.1f}×")

    print("\nCompute only. The look-ahead LATENCY is identical in both and is inherent")
    print("to the algorithm — a native port does not remove it (see the doc's Round 4).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
