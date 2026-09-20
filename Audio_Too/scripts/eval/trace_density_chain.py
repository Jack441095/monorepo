#!/usr/bin/env python3
"""
Diagnostic (read-only, no render): reconstruct the master bus sum from
exported processed stems, then run it through each master-bus stage manually
(A saturation, B glue compressor, C multiband compressor, C2 EQ) with a
density measurement (median RMS over 50ms windows) after every stage, to find
exactly where the "compressor override barely worked" finding comes from.

See docs/audits/2026-07-17-reference-track-comparison.md's "Combined
candidate + honest dynamics finding" section for context: median RMS moved
only -18.2->-17.6dB despite a full ratio-3:1/-19.6dBFS glue compressor
override, against a 6.6dB gap to the reference.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "studio" / "audio_analysis"))

import numpy as np  # noqa: E402
from audio_analysis.utils.audio_io import read_wav_mono  # noqa: E402
from audio_analysis.mixdown.mix_renderer import (  # noqa: E402
    _apply_stereo_compressor,
    _apply_multiband_compressor,
)
from audio_analysis.dsp_engine import ParametricEQ, apply_saturation  # noqa: E402


def median_rms_db(left: np.ndarray, right: np.ndarray, sr: int, win_s: float = 0.05) -> dict:
    mono = 0.5 * (left + right)
    win = int(win_s * sr)
    n = len(mono) // win
    rms_db = []
    for i in range(n):
        seg = mono[i * win:(i + 1) * win]
        rms = np.sqrt(np.mean(seg ** 2)) + 1e-12
        rms_db.append(20 * np.log10(rms))
    rms_db = np.array(rms_db)
    return {
        "median": float(np.percentile(rms_db, 50)),
        "p10": float(np.percentile(rms_db, 10)),
        "p90": float(np.percentile(rms_db, 90)),
    }


def main():
    stems_dir = ROOT / "artifacts" / "real_stem_validation_2026-07-15" / "stranger-monocompat-v8" / "stems_v1"
    paths = sorted(stems_dir.glob("*.wav"))
    print(f"Reconstructing master-bus sum from {len(paths)} exported processed stems...")

    sr = None
    sum_l = sum_r = None
    for p in paths:
        d = read_wav_mono(p.read_bytes(), max_samples=0)
        if sr is None:
            sr = d["sample_rate"]
            n = len(d["left_samples"])
            sum_l = np.zeros(n)
            sum_r = np.zeros(n)
        left = np.asarray(d["left_samples"])
        right = np.asarray(d["right_samples"])
        m = min(len(left), len(sum_l))
        sum_l[:m] += left[:m]
        sum_r[:m] += right[:m]

    print(f"sr={sr}  master-sum peak: L={np.max(np.abs(sum_l)):.3f} R={np.max(np.abs(sum_r)):.3f}\n")

    stages = []

    def record(label, left, right):
        d = median_rms_db(left, right, sr)
        stages.append((label, d))
        print(f"  {label:<45} median={d['median']:>6.1f}dB  p10={d['p10']:>6.1f}dB  p90={d['p90']:>6.1f}dB")

    record("0. Master bus sum (pre-processing)", sum_l, sum_r)

    # A. Saturation (default drive 0.5, mix 0.4 -- matches decision-engine default)
    left = apply_saturation(sum_l, drive_db=0.5, mix=0.4, oversample=True)
    right = apply_saturation(sum_r, drive_db=0.5, mix=0.4, oversample=True)
    record("A. + saturation", left, right)

    # B. Glue compressor -- the override tested in the combined candidate
    bus_compressor = {"ratio": 3.0, "attack_ms": 10.0, "release_ms": 150.0, "threshold_db": -19.6, "makeup_gain_db": 0.0}
    left, right = _apply_stereo_compressor(left, right, bus_compressor, sr)
    record("B. + glue compressor (ratio3:1 @-19.6dB, the override)", left, right)

    # C. Multiband compressor -- fixed internal thresholds, NOT overridable
    left, right = _apply_multiband_compressor(left, right, sr)
    record("C. + multiband compressor (FIXED, not overridable)", left, right)

    # C2. Low-shelf EQ (validated v2)
    eq = ParametricEQ(sample_rate=sr)
    eq.add_band("lowshelf", 300.0, 4.0, 0.707)
    left = eq.apply(left, linear_phase=True)
    right = eq.apply(right, linear_phase=True)
    record("C2. + low-shelf EQ (300Hz +4dB)", left, right)

    print("\n=== Same chain WITHOUT the glue-compressor override (default ratio~2.0 @-12dB) ===")
    l2 = apply_saturation(sum_l, drive_db=0.5, mix=0.4, oversample=True)
    r2 = apply_saturation(sum_r, drive_db=0.5, mix=0.4, oversample=True)
    record("A. + saturation", l2, r2)
    default_compressor = {"ratio": 2.0, "attack_ms": 30.0, "release_ms": 150.0, "threshold_db": -12.0, "makeup_gain_db": 0.0}
    l2, r2 = _apply_stereo_compressor(l2, r2, default_compressor, sr)
    record("B. + glue compressor (DEFAULT ratio2:1 @-12dB)", l2, r2)
    l2, r2 = _apply_multiband_compressor(l2, r2, sr)
    record("C. + multiband compressor (FIXED)", l2, r2)

    print(f"\n{'='*70}\nReference target: median RMS = -11.6dB\n{'='*70}")
    print("\nDelta contributed by each stage (override chain):")
    prev = stages[0][1]["median"]
    for label, d in stages[1:]:
        print(f"  {label:<45} {d['median']-prev:+.2f}dB")
        prev = d["median"]


if __name__ == "__main__":
    main()
