#!/usr/bin/env python3
"""
Post-extraction checks on the 520-D hybrid dataset, then write the
hybrid_x.npy / hybrid_y.npy arrays the trainer consumes.

Checks, in order of what they would catch:
  1. dim 5 is no longer a duplicate of dim 0 -- this was the trainer bug
     (norm_duration written into the decay slot), so if the fix took, these
     two columns must differ.
  2. dims 6 and 7 sum to 1.0 -- expected, since both are derived from the
     single spectral-rolloff scalar. Confirms the C++-matched spec, and
     documents that one of the two carries no extra information.
  3. Per-dimension distribution, including columns that are constant or
     all-zero (a dead feature the model cannot use).
  4. Duration distribution, which sizes the separate PANNs window skew:
     production truncates at 5s, so the fraction above 5s is the fraction
     of the corpus whose production embedding loses content.
"""

import os
import sys
import numpy as np

NPZ = "slo_all_packs_hybrid_v4.npz"
X_OUT = "hybrid_x.npy"
Y_OUT = "hybrid_y.npy"

NAMES = ["duration", "centroid", "flatness", "zcr", "rms", "decay", "low_r", "high_r"]


def main():
    if not os.path.exists(NPZ):
        print(f"ERROR: {NPZ} not found - extraction has not finished")
        return 1

    d = np.load(NPZ, allow_pickle=True)
    X = d["embeddings"].astype(np.float32)
    y = d["labels"]
    dsp = d["dsp_features"].astype(np.float32)
    classes = [str(c) for c in d["classes"]]

    print(f"Hybrid dataset: {X.shape}, labels {y.shape}, {len(classes)} classes\n")

    status = 0

    # --- 1. dim 5 must no longer duplicate dim 0 ---
    dup = np.array_equal(dsp[:, 5], dsp[:, 0])
    n_same = int(np.sum(dsp[:, 5] == dsp[:, 0]))
    print("=== Check 1: dim 5 (decay) is not a copy of dim 0 (duration) ===")
    if dup:
        print(f"  FAIL: columns identical across all {len(dsp)} rows - the "
              f"duplicate-feature bug is still present")
        status = 1
    else:
        pct = 100.0 * n_same / len(dsp)
        print(f"  PASS: columns differ. {n_same}/{len(dsp)} ({pct:.1f}%) rows "
              f"coincide, expected from the documented "
              f"'decay <= 0.001 -> fall back to duration' rule.")

    # --- 2. dims 6 and 7 are complements ---
    s = dsp[:, 6] + dsp[:, 7]
    print("\n=== Check 2: dims 6 + 7 == 1.0 (both derived from rolloff) ===")
    print(f"  sum: min={s.min():.6f} max={s.max():.6f} mean={s.mean():.6f}")
    if np.allclose(s, 1.0, atol=1e-5):
        print("  As specified. Note one of the two carries no extra information.")
    else:
        print("  Unexpected - dims 6/7 are not exact complements.")

    # --- 3. per-dimension distribution ---
    print("\n=== Check 3: per-dimension distribution ===")
    for j, name in enumerate(NAMES):
        col = dsp[:, j]
        nz = int(np.count_nonzero(col))
        flag = ""
        if col.std() < 1e-9:
            flag = "   <-- CONSTANT, model cannot use this"
        elif nz == 0:
            flag = "   <-- ALL ZERO"
        print(f"  [{j}] {name:>9s}: mean={col.mean():.4f} std={col.std():.4f} "
              f"min={col.min():.4f} max={col.max():.4f} nonzero={nz}{flag}")

    zero_rows = int(np.sum(~dsp.any(axis=1)))
    if zero_rows:
        print(f"\n  NOTE: {zero_rows} rows are all-zero (file missing or unreadable "
              f"at extraction time)")

    # --- 4. correlation between DSP dims ---
    print("\n=== Check 4: DSP inter-dimension correlation (|r| > 0.9) ===")
    with np.errstate(invalid="ignore", divide="ignore"):
        corr = np.corrcoef(dsp.T)
    found = False
    for a in range(8):
        for b in range(a + 1, 8):
            r = corr[a, b]
            if np.isfinite(r) and abs(r) > 0.9:
                print(f"  {NAMES[a]} vs {NAMES[b]}: r={r:+.4f}")
                found = True
    if not found:
        print("  none")

    # --- 5. duration distribution / PANNs window skew sizing ---
    # dim 0 = min(duration/10, 1), so duration = dim0*10 for anything under 10s.
    dur = dsp[:, 0] * 10.0
    capped = int(np.sum(dsp[:, 0] >= 1.0))
    over5 = int(np.sum(dur > 5.0))
    print("\n=== Check 5: duration distribution (sizes the PANNs window skew) ===")
    print(f"  median {np.median(dur):.2f}s   mean {dur.mean():.2f}s")
    for thresh in (1.0, 2.0, 5.0, 8.0):
        n = int(np.sum(dur > thresh))
        print(f"  > {thresh:>4.1f}s: {n:6d} ({100.0 * n / len(dur):5.1f}%)")
    print(f"  at the 10s cap: {capped} ({100.0 * capped / len(dur):.1f}%) "
          f"- true duration unknown, >= 10s")
    print(f"\n  Production truncates at 5s, so {over5} files "
          f"({100.0 * over5 / len(dur):.1f}%) get an embedding built from less "
          f"audio than the one the model trained on.")

    # --- write trainer inputs ---
    # Labels are stored as class-name strings, not indices. Map them through
    # the dataset's own `classes` order, which is the same order the trainer's
    # CLASSES list uses -- so index i means the same class on both sides.
    class_to_idx = {c: i for i, c in enumerate(classes)}
    y_str = [str(v) for v in y]
    unknown = sorted({v for v in y_str if v not in class_to_idx})
    if unknown:
        print(f"\nERROR: labels not present in the class list: {unknown}")
        return 1
    y_idx = np.array([class_to_idx[v] for v in y_str], dtype=np.int64)

    counts = np.bincount(y_idx, minlength=len(classes))
    print("\n=== Class distribution ===")
    order = np.argsort(-counts)
    for i in order:
        print(f"  {classes[i]:>14s}: {counts[i]:5d} ({100.0 * counts[i] / len(y_idx):5.1f}%)")
    print(f"  imbalance ratio (max/min): {counts.max() / max(counts.min(), 1):.1f}x")

    np.save(X_OUT, X)
    np.save(Y_OUT, y_idx)
    print(f"\nWrote {X_OUT} {X.shape} and {Y_OUT} {y_idx.shape}")
    return status


if __name__ == "__main__":
    sys.exit(main())
