#!/usr/bin/env python3
"""Compare old/new labels on identical rows and identical grouped folds."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

SD = Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", type=Path,
                    default=SD / "corpus_v4b_escape_recovered.npz")
    ap.add_argument("--new", type=Path,
                    default=SD / "corpus_granularity_relabelled_v1.npz")
    ap.add_argument("--out", type=Path,
                    default=SD / "results_granularity_label_effect_v1.json")
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--splits", type=int, default=5)
    args = ap.parse_args()

    sys.path.insert(0, str(SD))
    import full_taxonomy_eval as fe
    import incumbent_receipt as ir
    from sklearn.model_selection import StratifiedGroupKFold

    old, new = fe.load(str(args.old)), fe.load(str(args.new))
    if old["paths"] != new["paths"] or not np.array_equal(old["X"], new["X"]):
        raise SystemExit("FAIL CLOSED: old/new corpora do not share identical rows/features")
    old_inv = fe.eligible_classes(old, 5, 5)
    new_inv = fe.eligible_classes(new, 5, 5)
    classes = sorted(set(c for c, v in old_inv.items() if v["eligible"]) &
                     set(c for c, v in new_inv.items() if v["eligible"]))
    if len(classes) < 2:
        raise SystemExit("FAIL CLOSED: fewer than two shared eligible classes")
    mask = np.isin(old["labels"], classes) & np.isin(new["labels"], classes)
    X = old["X"][mask]
    old_y, new_y = old["labels"][mask], new["labels"][mask]
    groups = old["vendor"][mask]
    per_seed = []
    for seed in range(args.seeds):
        cv = StratifiedGroupKFold(args.splits, shuffle=True, random_state=seed)
        old_acc, new_acc = [], []
        for tr, te in cv.split(X, old_y, groups=groups):
            if set(groups[tr]) & set(groups[te]):
                raise SystemExit("FAIL CLOSED: collection leakage")
            old_pred, _ = ir.centroid_fit_predict(X[tr], old_y[tr], X[te], classes)
            new_pred, _ = ir.centroid_fit_predict(X[tr], new_y[tr], X[te], classes)
            old_acc.append(float(np.mean(old_pred == old_y[te])))
            new_acc.append(float(np.mean(new_pred == new_y[te])))
        per_seed.append({
            "seed": seed,
            "old_accuracy": float(np.mean(old_acc)),
            "new_accuracy": float(np.mean(new_acc)),
            "delta_pp": float(100 * (np.mean(new_acc) - np.mean(old_acc))),
        })
    deltas = np.asarray([r["delta_pp"] for r in per_seed], dtype=float)
    result = {
        "record_type": "slo_granularity_label_effect",
        "schema_version": "1.0.0",
        "safety": "research-only; identical rows/features; source audio read-only",
        "protocol": {
            "split": "StratifiedGroupKFold by vendor/collection",
            "same_folds": True,
            "seeds": args.seeds,
            "splits": args.splits,
            "estimator": "standardized L2 cosine nearest centroid",
            "shared_classes": classes,
            "n_rows_scored": int(mask.sum()),
        },
        "per_seed": per_seed,
        "summary": {
            "old_accuracy_mean": float(np.mean([r["old_accuracy"] for r in per_seed])),
            "new_accuracy_mean": float(np.mean([r["new_accuracy"] for r in per_seed])),
            "delta_pp_mean": float(deltas.mean()),
            "delta_pp_sd": float(deltas.std(ddof=1)) if len(deltas) > 1 else 0.0,
            "positive_seed_count": int(np.sum(deltas > 0)),
            "seed_count": len(deltas),
        },
    }
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
