#!/usr/bin/env python3
"""Compare simple full-taxonomy heads on identical grouped folds."""
from __future__ import annotations

import argparse
import json
import os
import time

import numpy as np

SD = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--seeds", type=int, default=4)
    ap.add_argument("--splits", type=int, default=5)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    import full_taxonomy_eval as full
    import incumbent_receipt as ir
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import f1_score
    from sklearn.model_selection import StratifiedGroupKFold
    from sklearn.preprocessing import StandardScaler

    d = full.load(args.corpus)
    inv = full.eligible_classes(d, 5, 5)
    classes = [c for c, v in inv.items() if v["eligible"]]
    keep = np.isin(d["labels"], classes)
    X, y, groups = d["X"][keep], d["labels"][keep], d["vendor"][keep]
    classes = list(classes)
    results = {}
    for arm in ("centroid", "logistic"):
        accs, f1s, cov90, cov95 = [], [], [], []
        for seed in range(args.seeds):
            pred = np.empty(len(y), dtype=object)
            conf = np.zeros(len(y), dtype=float)
            cv = StratifiedGroupKFold(args.splits, shuffle=True,
                                      random_state=seed)
            for tr, te in cv.split(X, y, groups=groups):
                if set(groups[tr]) & set(groups[te]):
                    raise AssertionError("collection leakage")
                if arm == "centroid":
                    p, c = ir.centroid_fit_predict(X[tr], y[tr], X[te], classes)
                else:
                    scaler = StandardScaler().fit(X[tr])
                    ztr = scaler.transform(X[tr])
                    zte = scaler.transform(X[te])
                    clf = LogisticRegression(
                        max_iter=400, C=1.0, class_weight="balanced",
                        solver="lbfgs", multi_class="auto", random_state=seed)
                    clf.fit(ztr, y[tr])
                    p = clf.predict(zte)
                    c = clf.predict_proba(zte).max(axis=1)
                pred[te], conf[te] = p, c
            correct = (pred == y).astype(float)
            accs.append(100 * float(correct.mean()))
            f1s.append(100 * f1_score(y, pred.astype(str), average="macro",
                                      zero_division=0))
            cov90.append(ir.coverage_at(conf, correct, .90))
            cov95.append(ir.coverage_at(conf, correct, .95))
        results[arm] = {
            "accuracy_mean": round(float(np.mean(accs)), 2),
            "accuracy_sd": round(float(np.std(accs)), 2),
            "macro_f1": round(float(np.mean(f1s)), 2),
            "coverage_at_90_precision": round(float(np.mean(cov90)), 1),
            "coverage_at_95_precision": round(float(np.mean(cov95)), 1),
            "per_seed_accuracy": [round(float(x), 2) for x in accs],
        }
        print(arm, results[arm])

    payload = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "corpus": os.path.abspath(args.corpus),
        "protocol": {"split": "StratifiedGroupKFold by vendor/collection",
                     "seeds": args.seeds, "splits": args.splits},
        "n_files": int(len(y)), "n_classes": len(classes),
        "classes": classes, "results": results,
        "decision": "retain centroid unless another arm clears it on the same folds",
    }
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    raise SystemExit(main())

