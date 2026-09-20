#!/usr/bin/env python3
"""A-01: energy-based OOD signal vs the shipping centroid-cosine gate (part 1).

Compares candidate OOD scores on FRESH end-to-end benchmark scans (full
decode -> ONNX -> 520-D head -> gate path):

  known group : 60 KSHMR vocals/ethnic files (in-taxonomy content)
  OOD group   : 39 noise/texture + guitar loops + pads (out-of-taxonomy)

The shipped binary emits diagMlLogitEnergy (research -logsumexp),
diagMlCentroidCos (drives the shipping gate), diagMlEntropy, diagMlMargin,
diagMlConfidence per row. Scores evaluated BOTH orientations; better AUROC
reported with its orientation.

Kill criterion: no lift vs shipping centroid gate -> stop, gate untouched.
"""

import argparse
import json
import sys
from pathlib import Path

CANDIDATES = {
    "diagMlCentroidCos": "centroid cosine (shipping gate score)",
    "diagMlLogitEnergy": "logit energy = -logsumexp (research field)",
    "diagMlEntropy": "softmax entropy (nats)",
    "diagMlMargin": "top1-top2 softmax margin",
    "diagMlConfidence": "top1 softmax confidence",
}


def load_rows(path):
    p = Path(path)
    if not p.is_file():
        print(f"FAIL: missing artifact: {p}", file=sys.stderr)
        sys.exit(2)
    with open(p) as f:
        rows = json.load(f)

    def usable(r):
        return bool(r.get("diagMlEvaluated")) and all(
            isinstance(r.get(k), (int, float)) for k in CANDIDATES)

    return [r for r in rows if usable(r)]


def auroc(known_scores, ood_scores):
    """P(score_random_known > score_random_ood) via rank statistic."""
    labelled = [(s, 1) for s in known_scores] + [(s, 0) for s in ood_scores]
    labelled.sort(key=lambda t: t[0])
    n = len(labelled)
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and labelled[j + 1][0] == labelled[i][0]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[k] = avg
        i = j + 1
    rank_sum = sum(r for r, (_, c) in zip(ranks, labelled) if c == 1)
    nk, no = len(known_scores), len(ood_scores)
    return (rank_sum - nk * (nk + 1) / 2.0) / (nk * no)


def op90(known_scores, ood_scores, higher_is_known):
    """Threshold at ~90pct known acceptance; returns (t, accept, falsknown)."""
    idx = int(len(known_scores) * 0.10)
    if higher_is_known:
        t = sorted(known_scores)[idx]
        ka = sum(1 for s in known_scores if s >= t) / len(known_scores)
        fk = sum(1 for s in ood_scores if s >= t) / len(ood_scores)
    else:
        t = sorted(known_scores, reverse=True)[idx]
        ka = sum(1 for s in known_scores if s <= t) / len(known_scores)
        fk = sum(1 for s in ood_scores if s <= t) / len(ood_scores)
    return t, ka, fk


def fpr95(known_scores, ood_scores, higher_is_known):
    """Min false-unknown at >=95pct OOD rejection; (fpr, thresh, rej)."""
    best = (1.0, None, 0.0)
    for t in sorted(set(ood_scores)):
        if higher_is_known:
            rej = sum(1 for s in ood_scores if s < t) / len(ood_scores)
            fpr = sum(1 for s in known_scores if s < t) / len(known_scores)
        else:
            rej = sum(1 for s in ood_scores if s > t) / len(ood_scores)
            fpr = sum(1 for s in known_scores if s > t) / len(known_scores)
        if rej >= 0.95 and fpr < best[0]:
            best = (fpr, t, rej)
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("known_scan")
    ap.add_argument("ood_scan")
    ap.add_argument("--receipt", default="results_ood_energy_v1.json")
    args = ap.parse_args()

    known = load_rows(args.known_scan)
    ood = load_rows(args.ood_scan)
    if not known or not ood:
        print("FAIL: empty group after usability filter", file=sys.stderr)
        sys.exit(2)

    results = {"known_n": len(known), "ood_n": len(ood), "scores": {}}
    for field, desc in CANDIDATES.items():
        ks = [r[field] for r in known]
        os_ = [r[field] for r in ood]
        a_hi = auroc(ks, os_)
        hik = a_hi >= 1 - a_hi
        best = max(a_hi, 1 - a_hi)
        t, ka, fk = op90(ks, os_, hik)
        fpr, ft, rej = fpr95(ks, os_, hik)
        results["scores"][field] = {
            "description": desc,
            "auroc": round(best, 4),
            "orientation": "higher_is_known" if hik else "higher_is_ood",
            "op90_threshold": t,
            "op90_known_accept": round(ka, 4),
            "op90_false_known": round(fk, 4),
            "fpr_at_95_rej": round(fpr, 4) if ft is not None else None,
            "fpr_threshold": ft,
            "achieved_rej": round(rej, 4),
        }
        fpr_s = f"{fpr:.3f}" if ft is not None else "UNREACHABLE"
        ori = "higher_is_known" if hik else "higher_is_ood"
        print(f"{field}: AUROC={best:.4f} ({ori}) "
              f"op90: accept={ka:.1%} false-known={fk:.1%} "
              f"FPR@95={fpr_s}")

    e = results["scores"]["diagMlLogitEnergy"]["auroc"]
    c = results["scores"]["diagMlCentroidCos"]["auroc"]
    # Promotion requires BOTH an absolute floor (well above chance+noise:
    # SE of AUROC at n=60/39 is ~+/-0.065) AND a clear margin over the
    # shipping gate -- the V4-G precedent adopted at 0.911 vs 0.68.
    # A bare +0.02 edge at chance level (e.g. 0.56 vs 0.50) is noise.
    results["verdict"] = (
        "PROMOTE to threshold-calibration experiment"
        if (e >= 0.65 and e > c + 0.05) else "KILL (no lift)")
    results["notes"] = (
        "Fresh end-to-end scans (decode->ONNX->520-D head->gate). "
        "Near-taxonomy-boundary set: KSHMR vocals/ethnic vs "
        "noise/guitar/pads. Even the shipping centroid gate scores ~0.50 "
        "here (vs 0.911 on the V4-G KSHMR holdout split) -- the set tests "
        "boundary content the taxonomy itself does not separate. No "
        "head-derived score clears the promotion floor (energy 0.56 < "
        "0.65 floor). Gate untouched per kill criterion.")
    with open(args.receipt, "w") as f:
        json.dump(results, f, indent=2)
    print(f"receipt: {args.receipt} verdict={results['verdict']}")


if __name__ == "__main__":
    main()

