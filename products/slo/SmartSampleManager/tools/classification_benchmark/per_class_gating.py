#!/usr/bin/env python3
"""
Per-class confidence gates instead of one global threshold.

The renamer only acts above a confidence threshold, so COVERAGE AT A PRECISION
TARGET is the product metric. The v2 receipt puts it at 18.8% for 95% precision
and 5.4% for 98%.

The incumbent's per-class behaviour is very uneven -- Clap recall 91.8% and Kick
85.9% against Percussion 17.9% -- so a single global gate forces the reliable
classes to pay for the unreliable ones. A per-class gate lets the renamer act
confidently where it is trustworthy and abstain where it is not.

METHOD, and the part that matters: thresholds are fitted on the TRAINING FOLD
ONLY, using an inner split, then applied unchanged to the held-out collections.
Fitting a threshold on the same data it is scored on would manufacture coverage
out of nothing, which is the single easiest way to fake this metric.

Compared:
  global      one threshold for every class (the incumbent)
  per-class   one threshold per predicted class
  oracle      per-class thresholds fitted ON THE TEST FOLD -- NOT a candidate,
              only an upper bound showing how much is theoretically available
"""
import os, json, argparse, warnings
import numpy as np
warnings.filterwarnings("ignore")

SD = os.path.dirname(os.path.abspath(__file__))
import incumbent_receipt as ir
import eval_corpus_v2 as ec
from sklearn.model_selection import StratifiedGroupKFold

OUT = os.path.join(SD, "results_per_class_gating.json")


def coverage_precision(conf, correct, keep):
    """Coverage and precision over the accepted subset."""
    if keep.sum() == 0:
        return 0.0, 1.0
    return float(keep.mean()), float(correct[keep].mean())


def global_threshold(conf, correct, target):
    """Lowest global threshold whose accepted set still hits the target."""
    best_t, best_cov = 1.01, 0.0
    for t in np.unique(np.round(conf, 4)):
        keep = conf >= t
        if keep.sum() < 5:
            continue
        cov, prec = coverage_precision(conf, correct, keep)
        if prec >= target and cov > best_cov:
            best_cov, best_t = cov, float(t)
    return best_t


def per_class_thresholds(conf, correct, pred, classes, target, min_n=5):
    """One threshold per predicted class, each meeting the target alone."""
    th = {}
    for c in classes:
        m = pred == c
        if m.sum() < min_n:
            th[c] = 1.01                      # never accept a class we cannot fit
            continue
        cc, kk = conf[m], correct[m]
        best_t, best_cov = 1.01, 0.0
        for t in np.unique(np.round(cc, 4)):
            keep = cc >= t
            if keep.sum() < 3:
                continue
            cov, prec = coverage_precision(cc, kk, keep)
            if prec >= target and cov > best_cov:
                best_cov, best_t = cov, float(t)
        th[c] = best_t
    return th


def apply_per_class(conf, pred, th):
    return np.array([conf[i] >= th.get(pred[i], 1.01) for i in range(len(pred))])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--splits", type=int, default=5)
    ap.add_argument("--targets", default="0.90,0.95,0.98")
    ap.add_argument("--rejection-mapped", action="store_true")
    a = ap.parse_args()
    targets = [float(t) for t in a.targets.split(",")]

    d = ec.load(map_rejection=a.rejection_mapped)
    if not a.rejection_mapped:
        keep = np.isin(d["y"], ec.DRUM10)
        X, y, g = d["X"][keep], d["y"][keep], d["vendor"][keep]
        classes = ec.DRUM10
    else:
        X, y, g = d["X"], d["y"], d["vendor"]
        classes = d["classes"]
    print(f"{len(y)} files, {len(set(g))} collections, {len(classes)} classes"
          f"{'  [rejection-mapped]' if a.rejection_mapped else ''}\n")

    res = {f"{t:.2f}": {"global": [], "per_class": [], "oracle": [],
                        "global_prec": [], "per_class_prec": []}
           for t in targets}

    for s in range(a.seeds):
        cv = StratifiedGroupKFold(a.splits, shuffle=True, random_state=s)
        for tr, te in cv.split(X, y, groups=g):
            assert not (set(g[tr]) & set(g[te])), "collection leak"
            # inner split of the TRAINING fold, grouped, to fit thresholds
            inner = StratifiedGroupKFold(3, shuffle=True, random_state=s)
            itr, ical = next(inner.split(X[tr], y[tr], groups=g[tr]))
            p_cal, c_cal = ir.centroid_fit_predict(X[tr][itr], y[tr][itr],
                                                   X[tr][ical], classes)
            corr_cal = (p_cal == y[tr][ical]).astype(float)
            # final model on the whole training fold, scored on held-out colls
            p_te, c_te = ir.centroid_fit_predict(X[tr], y[tr], X[te], classes)
            corr_te = (p_te == y[te]).astype(float)

            for t in targets:
                k = f"{t:.2f}"
                gt = global_threshold(c_cal, corr_cal, t)
                keep = c_te >= gt
                cov, prec = coverage_precision(c_te, corr_te, keep)
                res[k]["global"].append(100 * cov)
                res[k]["global_prec"].append(100 * prec)

                pth = per_class_thresholds(c_cal, corr_cal, p_cal, classes, t)
                keep = apply_per_class(c_te, p_te, pth)
                cov, prec = coverage_precision(c_te, corr_te, keep)
                res[k]["per_class"].append(100 * cov)
                res[k]["per_class_prec"].append(100 * prec)

                # upper bound: thresholds fitted on the test fold itself
                oth = per_class_thresholds(c_te, corr_te, p_te, classes, t)
                keep = apply_per_class(c_te, p_te, oth)
                cov, _ = coverage_precision(c_te, corr_te, keep)
                res[k]["oracle"].append(100 * cov)

    print(f"{'target':>7} {'global cov':>12} {'(prec)':>8} "
          f"{'per-class cov':>15} {'(prec)':>8} {'delta':>8} {'oracle':>8}")
    out = {}
    for t in targets:
        k = f"{t:.2f}"
        gc = np.array(res[k]["global"]); pc = np.array(res[k]["per_class"])
        gp = np.mean(res[k]["global_prec"]); pp = np.mean(res[k]["per_class_prec"])
        orc = np.mean(res[k]["oracle"])
        n = min(len(gc), len(pc))
        diff = pc[:n] - gc[:n]
        se = diff.std(ddof=1) / np.sqrt(n) if n > 1 else float("inf")
        tstat = diff.mean() / se if se > 0 else 0.0
        sig = "*" if abs(tstat) > 2 else " "
        print(f"{t:7.2f} {gc.mean():11.1f}% {gp:7.1f}% "
              f"{pc.mean():14.1f}% {pp:7.1f}% {diff.mean():+7.2f}{sig} "
              f"{orc:7.1f}%")
        out[k] = {"global_coverage": round(float(gc.mean()), 2),
                  "global_precision": round(float(gp), 2),
                  "per_class_coverage": round(float(pc.mean()), 2),
                  "per_class_precision": round(float(pp), 2),
                  "delta": round(float(diff.mean()), 2),
                  "paired_t": round(float(tstat), 2),
                  "oracle_coverage": round(float(orc), 2),
                  "folds": int(n)}
    print("\n  * = paired |t| > 2")
    print("  oracle fits thresholds on the test fold -- an upper bound, NOT a "
          "deployable option")
    json.dump({"rejection_mapped": a.rejection_mapped, "seeds": a.seeds,
               "results": out}, open(OUT, "w"), indent=2)
    print(f"wrote {os.path.basename(OUT)}")


if __name__ == "__main__":
    main()
