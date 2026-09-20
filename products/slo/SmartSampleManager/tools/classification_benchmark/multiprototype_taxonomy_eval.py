#!/usr/bin/env python3
"""Collection-held-out evaluation of multiple prototypes per exact class."""
from __future__ import annotations

import argparse
import json
import os
import time

import numpy as np


def norm(x):
    return x / (np.linalg.norm(x, axis=1, keepdims=True) + 1e-9)


def predict(xtr, ytr, xte, classes, k, seed):
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler

    ztr = norm(StandardScaler().fit_transform(xtr))
    zte = norm(StandardScaler().fit(xtr).transform(xte))
    prototypes, proto_labels = [], []
    for c in classes:
        xc = ztr[ytr == c]
        if k == 1 or len(xc) < k:
            centres = xc.mean(axis=0, keepdims=True)
        else:
            km = KMeans(n_clusters=k, n_init=5, max_iter=100,
                        random_state=seed)
            km.fit(xc)
            centres = km.cluster_centers_
        prototypes.append(norm(centres))
        proto_labels.extend([c] * len(centres))
    p = norm(np.vstack(prototypes))
    sim = zte @ p.T
    best = sim.argmax(axis=1)
    return np.asarray(proto_labels, dtype=object)[best]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--splits", type=int, default=5)
    args = ap.parse_args()

    import full_taxonomy_eval as full
    from sklearn.metrics import f1_score
    from sklearn.model_selection import StratifiedGroupKFold

    d = full.load(args.corpus)
    inventory = full.eligible_classes(d, 5, 5)
    classes = [c for c, v in inventory.items() if v["eligible"]]
    keep = np.isin(d["labels"], classes)
    X, y, groups = d["X"][keep], d["labels"][keep], d["vendor"][keep]
    results = {}
    for k in (1, 2, 3):
        accs, f1s, per_seed = [], [], []
        for seed in range(args.seeds):
            pred = np.empty(len(y), dtype=object)
            cv = StratifiedGroupKFold(args.splits, shuffle=True,
                                      random_state=seed)
            for tr, te in cv.split(X, y, groups=groups):
                if set(groups[tr]) & set(groups[te]):
                    raise AssertionError("collection leakage")
                pred[te] = predict(X[tr], y[tr], X[te], classes, k, seed)
            acc = 100 * float((pred == y).mean())
            f1 = 100 * float(f1_score(y, pred.astype(str), average="macro",
                                      zero_division=0))
            accs.append(acc); f1s.append(f1); per_seed.append(round(acc, 2))
        results[f"k{k}"] = {
            "k": k, "accuracy_mean": round(float(np.mean(accs)), 2),
            "accuracy_sd": round(float(np.std(accs)), 2),
            "macro_f1": round(float(np.mean(f1s)), 2),
            "per_seed_accuracy": per_seed,
        }
    base = results["k1"]["accuracy_mean"]
    for r in results.values():
        r["delta_vs_k1"] = round(r["accuracy_mean"] - base, 2)
    payload = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "corpus": os.path.abspath(args.corpus),
        "protocol": {"split": "StratifiedGroupKFold by vendor/collection",
                      "seeds": args.seeds, "splits": args.splits,
                      "standardize_then_l2": True},
        "n_files": int(len(y)), "n_classes": len(classes),
        "results": results,
    }
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=2)
    for name, r in results.items():
        print(name, r["accuracy_mean"], r["macro_f1"], r["delta_vs_k1"])
    print(f"wrote {args.out}")


if __name__ == "__main__":
    raise SystemExit(main())
