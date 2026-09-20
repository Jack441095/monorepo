#!/usr/bin/env python3
"""Measure a fixed filename/audio fusion policy on grouped full-taxonomy CV.

Filename overrides are restricted to tokens already measured as high precision
on the by-ear corpus. The script reports accuracy and gated coverage for the
same collection-held-out folds as the audio incumbent; it does not alter the
production policy.
"""
from __future__ import annotations

import argparse
import json
import os
import time

import numpy as np

SD = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(SD, "results_full_taxonomy_fusion_eval_v1.json")

# Frozen from the existing filename-validation receipt. These are not fitted
# on the grouped evaluation rows.
TRUSTED_NAME = {
    "Kick": 0.97,
    "Hi-Hat": 0.94,
    "Snare": 0.92,
    "Clap": 0.90,
    "Crash": 0.89,
    "Percussion Loop": 1.00,
    "Drum Loop": 0.78,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--splits", type=int, default=5)
    ap.add_argument("--min-examples", type=int, default=5)
    ap.add_argument("--min-collections", type=int, default=5)
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    import full_taxonomy_eval as full
    import incumbent_receipt as ir
    import name_detect
    from sklearn.model_selection import StratifiedGroupKFold

    d = full.load()
    inventory = full.eligible_classes(d, args.min_examples, args.min_collections)
    classes = [c for c, v in inventory.items() if v["eligible"]]
    keep = np.isin(d["labels"], classes)
    paths = np.asarray(d["paths"])[keep]
    X, y, groups = d["X"][keep], d["labels"][keep], d["vendor"][keep]
    fn = []
    for path in paths:
        label, _ = name_detect.detect(os.path.basename(path))
        fn.append(label if label in TRUSTED_NAME and label in classes else "")
    fn = np.asarray(fn, dtype=object)

    policies = {"audio": None}
    for threshold in (0.40, 0.50, 0.60, 0.70):
        policies[f"name_if_audio_conf_below_{threshold:.2f}"] = threshold
    policies["name_always"] = 999.0
    results = {}
    for policy, threshold in policies.items():
        accs, f1s, c90, c95, override_rates = [], [], [], [], []
        override_correct, override_total = 0, 0
        for seed in range(args.seeds):
            pred = np.empty(len(y), dtype=object)
            conf = np.zeros(len(y), dtype=float)
            overridden = np.zeros(len(y), dtype=bool)
            cv = StratifiedGroupKFold(args.splits, shuffle=True,
                                      random_state=seed)
            for tr, te in cv.split(X, y, groups=groups):
                if set(groups[tr]) & set(groups[te]):
                    raise AssertionError("collection leakage")
                p, c = ir.centroid_fit_predict(X[tr], y[tr], X[te], classes)
                pred[te], conf[te] = p, c
                if policy != "audio":
                    for j, idx in enumerate(te):
                        if fn[idx] and (policy == "name_always" or c[j] < threshold):
                            pred[idx] = fn[idx]
                            conf[idx] = TRUSTED_NAME[fn[idx]]
                            overridden[idx] = True
            correct = (pred == y).astype(float)
            override_correct += int((correct * overridden).sum())
            override_total += int(overridden.sum())
            accs.append(100 * float(correct.mean()))
            from sklearn.metrics import f1_score
            f1s.append(100 * f1_score(y, pred.astype(str), average="macro",
                                      zero_division=0))
            c90.append(ir.coverage_at(conf, correct, .90))
            c95.append(ir.coverage_at(conf, correct, .95))
            override_rates.append(100 * float(overridden.mean()))
        results[policy] = {
            "accuracy_mean": round(float(np.mean(accs)), 2),
            "accuracy_sd": round(float(np.std(accs)), 2),
            "macro_f1": round(float(np.mean(f1s)), 2),
            "coverage_at_90_precision": round(float(np.mean(c90)), 1),
            "coverage_at_95_precision": round(float(np.mean(c95)), 1),
            "override_rate": round(float(np.mean(override_rates)), 1),
            "override_precision": round(100 * override_correct / override_total, 2)
            if override_total else None,
            "per_seed_accuracy": [round(float(x), 2) for x in accs],
        }
        r = results[policy]
        print(f"{policy:34} accuracy={r['accuracy_mean']:.2f}% "
              f"F1={r['macro_f1']:.2f} cov95={r['coverage_at_95_precision']:.1f}% "
              f"override={r['override_rate']:.1f}%")

    payload = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "protocol": {
            "split": "StratifiedGroupKFold by vendor/collection",
            "seeds": args.seeds, "splits": args.splits,
            "min_examples": args.min_examples,
            "min_collections": args.min_collections,
            "trusted_name_precision": TRUSTED_NAME,
        },
        "n_files": int(len(y)), "n_classes": len(classes),
        "classes": classes, "results": results,
        "interpretation": "Filename overrides are admissible only if they improve the grouped incumbent; otherwise retain filename evidence for explanation/review.",
    }
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    raise SystemExit(main())
