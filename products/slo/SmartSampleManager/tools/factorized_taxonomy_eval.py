#!/usr/bin/env python3
"""Evaluate a family -> class specialist cascade on grouped folds."""
from __future__ import annotations

import argparse
import json
import os
import time

import numpy as np

FAMILY = {
    "Bass Hit": "bass", "Bass Loop": "bass", "Bass Reese": "bass",
    "Clap": "drums", "Crash": "drums", "Drum Fill": "drums",
    "Drum Loop": "drums", "Hi-Hat": "drums", "Hi-Hat Loop": "drums",
    "Kick": "drums", "Kick Loop": "drums", "Percussion": "drums",
    "Percussion Loop": "drums", "Rimshot": "drums", "Snare": "drums",
    "Top Loop": "drums",
    "Foley": "fx", "Foley Loop": "fx", "Impact": "fx", "Riser": "fx",
    "SFX": "fx", "Atmosphere": "fx",
    "Chord Loop": "tonal", "Loop": "tonal", "Pad": "tonal",
    "Synth Loop": "tonal", "Synth One-Shot": "tonal",
    "Vocal Loop": "tonal", "Vocal One-Shot": "tonal",
    "Weather/Nature Atmos": "tonal", "Other/none": "reject",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--splits", type=int, default=5)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    import full_taxonomy_eval as full
    import incumbent_receipt as ir
    from sklearn.metrics import f1_score
    from sklearn.model_selection import StratifiedGroupKFold

    d = full.load(args.corpus)
    inv = full.eligible_classes(d, 5, 5)
    classes = [c for c, v in inv.items() if v["eligible"] and c in FAMILY]
    keep = np.isin(d["labels"], classes)
    X, y, groups = d["X"][keep], d["labels"][keep], d["vendor"][keep]
    fam = np.asarray([FAMILY[c] for c in y], dtype=object)
    family_classes = sorted(set(fam))
    accs, f1s, per_seed = [], [], []
    for seed in range(args.seeds):
        pred = np.empty(len(y), dtype=object)
        cv = StratifiedGroupKFold(args.splits, shuffle=True,
                                  random_state=seed)
        for tr, te in cv.split(X, y, groups=groups):
            if set(groups[tr]) & set(groups[te]):
                raise AssertionError("collection leakage")
            pred_family, _ = ir.centroid_fit_predict(
                X[tr], fam[tr], X[te], family_classes)
            for family in family_classes:
                test_mask = pred_family == family
                if not test_mask.any():
                    continue
                train_mask = fam[tr] == family
                family_labels = sorted(set(y[tr][train_mask]))
                if len(family_labels) == 1:
                    pred[te[test_mask]] = family_labels[0]
                    continue
                local_pred, _ = ir.centroid_fit_predict(
                    X[tr][train_mask], y[tr][train_mask],
                    X[te][test_mask], family_labels)
                pred[te[test_mask]] = local_pred
        correct = (pred == y).astype(float)
        accs.append(100 * float(correct.mean()))
        f1s.append(100 * f1_score(y, pred.astype(str), average="macro",
                                  zero_division=0))
        per_seed.append(round(100 * float(correct.mean()), 2))
    result = {
        "accuracy_mean": round(float(np.mean(accs)), 2),
        "accuracy_sd": round(float(np.std(accs)), 2),
        "macro_f1": round(float(np.mean(f1s)), 2),
        "per_seed_accuracy": per_seed,
    }
    payload = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "corpus": os.path.abspath(args.corpus),
        "protocol": {"split": "StratifiedGroupKFold by vendor/collection",
                     "seeds": args.seeds, "splits": args.splits},
        "family_mapping": FAMILY, "n_files": int(len(y)),
        "n_classes": len(classes), "n_families": len(family_classes),
        "result": result,
    }
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=2)
    print(result)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    raise SystemExit(main())
