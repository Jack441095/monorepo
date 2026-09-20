#!/usr/bin/env python3
"""
Streaming-DSP-core spike: prove streamed == offline, then measure the per-block
real-time budget.

This is the honest answer to "what would real-time / Wwise / FMOD actually
take?" — it turns "latency" from an aspiration into a measured number. It:

  1. Builds a parametric EQ (a few RBJ biquad bands).
  2. Renders a signal OFFLINE (ParametricEQ.apply — whole-signal sosfilt).
  3. Renders the SAME signal STREAMING (StreamingEQ, fixed-size blocks with
     carried state) and checks the two are identical (they are, to float
     exactness — that equality IS the correctness proof).
  4. Times per-block processing warm and compares it to the real-time budget
     (block_size / sample_rate), for several block sizes.

A block "fits the budget" if it processes in well under the time that block of
audio represents (e.g. 128 samples @ 48kHz = 2.67ms). This script reports the
margin per block size so we know, with numbers, what is already real-time-
capable in pure Python and what (if anything) would need numba/C to be.

    python scripts/eval/streaming_dsp_budget.py
"""

from __future__ import annotations

import sys
import time

import numpy as np

from audio_analysis.dsp_engine.dynamics import Compressor, Gate
from audio_analysis.dsp_engine.eq import ParametricEQ
from audio_analysis.dsp_engine.streaming import (
    StreamingCompressor,
    StreamingEQ,
    StreamingGate,
    StreamingLimiter,
)

SAMPLE_RATE = 48000
BLOCK_SIZES = (64, 128, 256, 512, 1024)


def _build_eq(cls):
    eq = cls(SAMPLE_RATE)
    eq.add_band("highpass", 80.0, q=0.707)
    eq.add_band("peaking", 300.0, gain_db=-3.0, q=1.2)
    eq.add_band("peaking", 3000.0, gain_db=2.5, q=1.0)
    eq.add_band("highshelf", 8000.0, gain_db=1.5, q=0.707)
    return eq


def _build_comp(cls):
    return cls(SAMPLE_RATE, threshold_db=-18.0, ratio=4.0, attack_ms=5.0,
               release_ms=80.0, knee_db=6.0, makeup_gain_db=3.0, detection_mode="rms")


def _build_gate(cls):
    return cls(SAMPLE_RATE, threshold_db=-45.0, attack_ms=1.0, hold_ms=40.0,
               release_ms=120.0, range_db=-70.0)


def _signal(seconds: float = 4.0) -> np.ndarray:
    t = np.linspace(0, seconds, int(SAMPLE_RATE * seconds), endpoint=False)
    rng = np.random.default_rng(5)
    sig = sum(0.1 * np.sin(2 * np.pi * f * t) for f in (60, 220, 1000, 5000, 12000))
    sig += 0.02 * rng.standard_normal(len(t))
    return sig.astype(np.float64)


# Each processor: (label, offline callable, streaming instance factory)
def _eq_offline(x):
    return _build_eq(ParametricEQ).apply(x, linear_phase=False)


def _comp_offline(x):
    return _build_comp(Compressor).apply(x)


def _gate_offline(x):
    return _build_gate(Gate).apply(x)


PROCESSORS = (
    ("4-band EQ (linear)", _eq_offline, lambda: _build_eq(StreamingEQ)),
    ("compressor (nonlinear/stateful)", _comp_offline, lambda: _build_comp(StreamingCompressor)),
    ("gate (state machine + hold)", _gate_offline, lambda: _build_gate(StreamingGate)),
)


def _limiter_section(x: np.ndarray) -> None:
    """The limiter is the one processor that CANNOT stream at zero latency: it
    looks ahead to catch peaks, so it must delay output. Report the declared
    latency budget alongside the per-block compute cost."""
    lookahead_ms = 5.0
    lim = StreamingLimiter(SAMPLE_RATE, threshold_db=0.0, ceiling_db=-1.0,
                           release_ms=50.0, lookahead_ms=lookahead_ms).reset(block_size=128)
    lat = lim.latency_samples
    print("LOOK-AHEAD LIMITER — latency is inherent, not optional")
    print(f"  lookahead={lookahead_ms} ms  ->  latency_samples={lat} "
          f"({lat / SAMPLE_RATE * 1e3:.2f} ms of added output delay, on TOP of block latency)")
    print(f"\nPER-BLOCK BUDGET  (sample_rate={SAMPLE_RATE} Hz, look-ahead limiter)")
    print(f"  {'block':>6} {'budget_ms':>10} {'proc_ms(med)':>13} "
          f"{'proc_ms(p95)':>13} {'margin×':>9}  verdict")
    for bs in BLOCK_SIZES:
        lim = StreamingLimiter(SAMPLE_RATE, threshold_db=0.0, ceiling_db=-1.0,
                               release_ms=50.0, lookahead_ms=lookahead_ms).reset(block_size=bs)
        blocks = [x[i:i + bs] for i in range(0, len(x) - bs, bs)]
        for b in blocks[:50]:
            lim.process_block(b)
        times_ms = []
        for b in blocks:
            t0 = time.perf_counter()
            lim.process_block(b)
            times_ms.append((time.perf_counter() - t0) * 1e3)
        times_ms.sort()
        med = times_ms[len(times_ms) // 2]
        p95 = times_ms[int(len(times_ms) * 0.95)]
        budget_ms = bs / SAMPLE_RATE * 1e3
        margin = budget_ms / p95 if p95 > 0 else float("inf")
        verdict = "real-time OK" if p95 < budget_ms else "OVER BUDGET"
        print(f"  {bs:>6} {budget_ms:>10.3f} {med:>13.4f} {p95:>13.4f} "
              f"{margin:>8.1f}×  {verdict}")
    print("  (pure-Python monotonic-deque rolling max — the honest cost of the")
    print("   look-ahead; a C port would shrink compute but NOT the latency budget.)")
    print()


def main() -> int:
    x = _signal()

    for label, offline_fn, stream_factory in PROCESSORS:
        # --- 1. equivalence: streamed == offline ---
        offline = offline_fn(x)
        streamed = stream_factory().process_stream(x, block_size=128)
        max_abs = float(np.max(np.abs(offline - streamed)))
        exact = max_abs < 1e-9
        print(f"STREAMED vs OFFLINE — {label}")
        print(f"  samples={len(x)}  max|Δ|={max_abs:.2e}  "
              f"{'IDENTICAL ✓' if exact else 'MISMATCH ✗'}")
        if not exact:
            print("  streaming core is NOT equivalent to offline — stop here.")
            return 1

        # --- 2. per-block real-time budget ---
        print(f"\nPER-BLOCK BUDGET  (sample_rate={SAMPLE_RATE} Hz, {label})")
        print(f"  {'block':>6} {'budget_ms':>10} {'proc_ms(med)':>13} "
              f"{'proc_ms(p95)':>13} {'margin×':>9}  verdict")
        for bs in BLOCK_SIZES:
            proc = stream_factory()
            proc.reset(block_size=bs)
            blocks = [x[i:i + bs] for i in range(0, len(x) - bs, bs)]
            # warm (also pays numba JIT for the compressor's envelope loop)
            for b in blocks[:50]:
                proc.process_block(b)
            times_ms = []
            for b in blocks:
                t0 = time.perf_counter()
                proc.process_block(b)
                times_ms.append((time.perf_counter() - t0) * 1e3)
            times_ms.sort()
            med = times_ms[len(times_ms) // 2]
            p95 = times_ms[int(len(times_ms) * 0.95)]
            budget_ms = bs / SAMPLE_RATE * 1e3
            margin = budget_ms / p95 if p95 > 0 else float("inf")
            verdict = "real-time OK" if p95 < budget_ms else "OVER BUDGET"
            print(f"  {bs:>6} {budget_ms:>10.3f} {med:>13.4f} {p95:>13.4f} "
                  f"{margin:>8.1f}×  {verdict}")
        print()

    # --- Limiter: the look-ahead / latency-budget case (special-cased) ---
    _limiter_section(x)

    print("Note: pure-Python + scipy per-block. A comfortable margin here means")
    print("the algorithm is real-time-shaped; a thin/negative margin is exactly")
    print("what would justify a numba/C port for that processor — measured, not")
    print("assumed. This is the gate before any Wwise/FMOD plugin work.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
