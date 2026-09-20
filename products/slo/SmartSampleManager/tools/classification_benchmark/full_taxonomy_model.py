#!/usr/bin/env python3
"""Freeze a deployable full-taxonomy nearest-centroid model.

The classifier is intentionally the incumbent that survived collection-held-
out evaluation, not a new unvalidated head. This command freezes its scaler,
centroids, class inventory and gates in a standalone artifact that future
embedding extraction can consume without retraining or silently changing the
taxonomy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time

import numpy as np

SD = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(SD, "corpus_v2.npz")
MODEL = os.path.join(SD, "full_taxonomy_model_v1.npz")
META = os.path.join(SD, "full_taxonomy_model_v1.json")


def gate_at_precision(conf, correct, target):
    order = np.argsort(-conf)
    c = correct[order]
    cumulative = np.cumsum(c) / np.arange(1, len(c) + 1)
    ok = np.where(cumulative >= target)[0]
    if not len(ok):
        return {"coverage": 0.0, "threshold": 1.0, "n": 0}
    k = int(ok[-1] + 1)
    return {"coverage": float(k / len(c)),
            "threshold": float(conf[order][k - 1]), "n": k}


def fit_predict(Xtr, ytr, Xte, classes):
    from sklearn.preprocessing import StandardScaler
    scaler = StandardScaler().fit(Xtr)
    Ztr = scaler.transform(Xtr)
    Zte = scaler.transform(Xte)
    Ztr /= np.linalg.norm(Ztr, axis=1, keepdims=True) + 1e-9
    Zte /= np.linalg.norm(Zte, axis=1, keepdims=True) + 1e-9
    C = np.vstack([Ztr[ytr == c].mean(axis=0) for c in classes])
    C /= np.linalg.norm(C, axis=1, keepdims=True) + 1e-9
    sims = Zte @ C.T
    logits = (sims - sims.max(axis=1, keepdims=True)) * 8.0
    probs = np.exp(logits); probs /= probs.sum(axis=1, keepdims=True)
    return np.asarray(classes)[sims.argmax(axis=1)], probs.max(axis=1), scaler, C, sims.max(axis=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--splits", type=int, default=5)
    ap.add_argument("--min-examples", type=int, default=5)
    ap.add_argument("--min-collections", type=int, default=5)
    ap.add_argument("--corpus", default=CORPUS)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--meta", default=META)
    args = ap.parse_args()

    import full_taxonomy_eval as full
    from sklearn.model_selection import StratifiedGroupKFold

    d = full.load(args.corpus)
    inv = full.eligible_classes(d, args.min_examples, args.min_collections)
    classes = [c for c, v in inv.items() if v["eligible"]]
    keep = np.isin(d["labels"], classes)
    X, y, groups = d["X"][keep], d["labels"][keep], d["vendor"][keep]
    print(f"freezing {len(classes)} classes, {len(y)} files, "
          f"{len(set(groups))} collections")

    # Honest OOF measurements are used only to set operating gates.
    all_conf, all_correct, all_sim = [], [], []
    per_seed = []
    for seed in range(args.seeds):
        cv = StratifiedGroupKFold(args.splits, shuffle=True,
                                  random_state=seed)
        pred = np.empty(len(y), dtype=object)
        conf = np.zeros(len(y)); sim = np.zeros(len(y))
        for tr, te in cv.split(X, y, groups=groups):
            if set(groups[tr]) & set(groups[te]):
                raise AssertionError("collection leakage")
            p, c, _, _, s = fit_predict(X[tr], y[tr], X[te], classes)
            pred[te], conf[te], sim[te] = p, c, s
        correct = (pred == y).astype(float)
        per_seed.append(float(correct.mean()))
        all_conf.append(conf); all_correct.append(correct); all_sim.append(sim)

    conf = np.concatenate(all_conf)
    correct = np.concatenate(all_correct)
    sim = np.concatenate(all_sim)
    gates = {str(p): gate_at_precision(conf, correct, p)
             for p in (0.90, 0.95, 0.98)}
    # A similarity gate is a second, independent open-set signal. It is
    # reported, not silently substituted for confidence: later product work
    # can choose an operating point based on measured precision.
    sim_gate = gate_at_precision(sim, correct, 0.95)
    print(f"OOF accuracy {100*np.mean(correct):.2f}% +/- "
          f"{100*np.std(per_seed):.2f}%")
    print(f"confidence gates: " + ", ".join(
        f"{int(float(k)*100)}%={v['threshold']:.3f} "
        f"({100*v['coverage']:.1f}% coverage)" for k, v in gates.items()))
    print(f"similarity gate at 95%: {sim_gate['threshold']:.3f} "
          f"({100*sim_gate['coverage']:.1f}% coverage)")

    # Fit the final model on all eligible labelled data.
    from sklearn.preprocessing import StandardScaler
    scaler = StandardScaler().fit(X)
    Z = scaler.transform(X)
    Z /= np.linalg.norm(Z, axis=1, keepdims=True) + 1e-9
    centroids = np.vstack([Z[y == c].mean(axis=0) for c in classes])
    centroids /= np.linalg.norm(centroids, axis=1, keepdims=True) + 1e-9

    identity = {
        "corpus_sha256": full.sha256(args.corpus),
        "n_files": int(len(y)), "n_classes": len(classes),
        "classes": classes,
        "embedding_hash": hashlib.sha256(
            np.ascontiguousarray(X).tobytes()).hexdigest(),
        "label_hash": hashlib.sha256("\n".join(y).encode()).hexdigest(),
    }
    metadata = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "model": "StandardScaler -> L2 -> cosine nearest centroid",
        "feature_contract": "frozen Perch+CLAP 2048-D corpus_v2 embedding",
        "classes": classes, "label_inventory": inv,
        "gates": gates, "similarity_gate_95": sim_gate,
        "oof_accuracy_mean": float(np.mean(per_seed)),
        "oof_accuracy_sd": float(np.std(per_seed)),
        "seeds": args.seeds, "splits": args.splits,
        "identity": identity,
        "rejection_policy": "Other/none is a rejection class; all actions remain policy-gated and require a calibrated operating point.",
    }
    np.savez(args.model, mean=scaler.mean_.astype(np.float32),
             scale=scaler.scale_.astype(np.float32),
             centroids=centroids.astype(np.float32),
             classes=np.asarray(classes, dtype=object),
             confidence_gate_90=np.float32(gates["0.9"]["threshold"]),
             confidence_gate_95=np.float32(gates["0.95"]["threshold"]),
             confidence_gate_98=np.float32(gates["0.98"]["threshold"]),
             similarity_gate_95=np.float32(sim_gate["threshold"]))
    with open(args.meta, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"wrote {args.model}")
    print(f"wrote {args.meta}")


if __name__ == "__main__":
    raise SystemExit(main())
