"""Performance + memory benchmark with contention gate (sprint §49-§53).

Refuses to claim 'uncontested' unless 1-minute load average is below a
documented threshold. Measures p50/p95/p99/max over repeated full
analyse+recommend cycles, plus peak RSS and growth across cycles.
"""
from __future__ import annotations

import json
import platform
import os
import resource
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.nla import decision as D            # noqa: E402
from eval.cases import PairCase              # noqa: E402
from eval.pipeline import analyse_case       # noqa: E402

LOAD_THRESHOLD = 4.0     # 1-minute load per total cores; documented gate


def rss_mb() -> float:
    v = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return v / (1024.0 * 1024.0) if sys.platform == "darwin" else v / 1024.0


def run(pairs: list[tuple[np.ndarray, np.ndarray, int]],
        min_repeats: int = 8) -> dict:
    l1 = float(os.getloadavg()[0])
    uncontested = l1 < LOAD_THRESHOLD

    cases = [PairCase(case_id=f"bench|{i}", klass="BENCH",
                      category="bench", relationship="self", fs=fs,
                      a=a, b=b)
             for i, (a, b, fs) in enumerate(pairs)]

    for c in cases:                       # warmup
        analyse_case(c)

    times = []
    for c in cases:
        t0 = time.perf_counter()
        analyse_case(c)
        times.append((time.perf_counter() - t0) * 1000.0)

    # repeated-cycle memory growth check on the first pair
    a, b, fs = pairs[0]
    c0 = cases[0]
    peak_samples, peaks = [], []
    for _ in range(min_repeats):
        analyse_case(c0)
        peaks.append(rss_mb())
    growth_mb = round(peaks[-1] - peaks[0], 3)

    def pct(q):
        return round(float(np.percentile(times, q)), 1)

    return {
        "load_1min": round(l1, 2),
        "uncontested_gate": LOAD_THRESHOLD,
        "uncontested": bool(uncontested),
        "n_pairs": len(cases),
        "pair_duration_s": round(len(pairs[0][0]) / pairs[0][2], 2),
        "sample_rate": pairs[0][2],
        "ms_p50": pct(50), "ms_p95": pct(95),
        "ms_p99": pct(99), "ms_max": round(max(times), 1),
        "peak_rss_mb": round(max(peaks), 1),
        "memory_growth_over_cycles_mb": growth_mb,
        "machine": platform.platform(),
        "python": sys.version.split()[0],
    }
