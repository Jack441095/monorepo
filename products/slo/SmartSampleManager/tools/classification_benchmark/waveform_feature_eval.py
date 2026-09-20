#!/usr/bin/env python3
"""Evaluate interpretable waveform evidence against the current incumbent.

The physics layer is not allowed to manufacture a win from a different subset:
all arms use the same rows, collection-held-out folds, seeds and class floor.
The output is a receipt for deciding whether waveform features are useful as a
fusion signal or only as an explanation layer.
"""
import argparse
import hashlib
import json
import os
import time

import numpy as np

SD = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(SD, "corpus_v2.npz")
OUT = os.path.join(SD, "results_waveform_feature_eval_v1.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--splits", type=int, default=5)
    ap.add_argument("--min-examples", type=int, default=5)
    ap.add_argument("--min-collections", type=int, default=5)
    a = ap.parse_args()

    import acoustic_evidence as ae
    import incumbent_receipt as ir
    import full_taxonomy_eval as full
    from sklearn.model_selection import StratifiedGroupKFold
    from sklearn.metrics import f1_score
    from sklearn.preprocessing import StandardScaler

    d = full.load()
    inventory = full.eligible_classes(d, a.min_examples, a.min_collections)
    classes = [c for c, v in inventory.items() if v["eligible"]]
    M, mask = ae.load_aligned(d["paths"])
    if M is None:
        raise SystemExit("run acoustic_evidence.py first")
    # load_aligned returns rows only for paths present in the cache.
    d = dict(paths=[p for p, k in zip(d["paths"], mask) if k],
             labels=d["labels"][mask], X=d["X"][mask],
             vendor=d["vendor"][mask])
    keep = np.isin(d["labels"], classes)
    X, W, y, g = d["X"][keep], M[keep], d["labels"][keep], d["vendor"][keep]
    classes = list(classes)
    print(f"{len(y)} files, {len(classes)} classes, {len(set(g))} collections, "
          f"{W.shape[1]} waveform features")

    # All transforms are fitted within the incumbent itself per training fold.
    # Concatenation is intentionally simple so this is a clean ablation.
    arms = {"audio": X, "waveform": W, "audio+waveform": np.hstack([X, W])}
    results = {}
    for name, features in arms.items():
        accs, f1s, c90, c95 = [], [], [], []
        for seed in range(a.seeds):
            pred = np.empty(len(y), dtype=object)
            conf = np.zeros(len(y))
            cv = StratifiedGroupKFold(a.splits, shuffle=True,
                                      random_state=seed)
            for tr, te in cv.split(features, y, groups=g):
                assert not (set(g[tr]) & set(g[te])), "collection leak"
                p, c = ir.centroid_fit_predict(features[tr], y[tr],
                                                features[te], classes)
                pred[te], conf[te] = p, c
            correct = (pred == y).astype(float)
            accs.append(100 * float(correct.mean()))
            f1s.append(100 * f1_score(y, pred.astype(str), average="macro",
                                      zero_division=0))
            c90.append(ir.coverage_at(conf, correct, .90))
            c95.append(ir.coverage_at(conf, correct, .95))
        results[name] = {
            "accuracy_mean": round(float(np.mean(accs)), 2),
            "accuracy_sd": round(float(np.std(accs)), 2),
            "per_seed": [round(float(x), 2) for x in accs],
            "macro_f1": round(float(np.mean(f1s)), 2),
            "coverage_at_90_precision": round(float(np.mean(c90)), 1),
            "coverage_at_95_precision": round(float(np.mean(c95)), 1),
        }
        r = results[name]
        print(f"  {name:15} {r['accuracy_mean']:6.2f}% +/- {r['accuracy_sd']:.2f} "
              f"F1 {r['macro_f1']:5.2f} cov90 {r['coverage_at_90_precision']:5.1f}% "
              f"cov95 {r['coverage_at_95_precision']:5.1f}%")

    identity = {
        "corpus_sha256": full.sha256(CORPUS),
        "acoustic_feature_version": ae.FEATURE_VERSION,
        "acoustic_cache_sha256": full.sha256(ae.CACHE),
        "n_files": int(len(y)), "n_classes": len(classes),
        "classes": classes,
        "feature_hash_audio": hashlib.sha256(
            np.ascontiguousarray(X).tobytes()).hexdigest(),
        "feature_hash_waveform": hashlib.sha256(
            np.ascontiguousarray(W).tobytes()).hexdigest(),
    }
    payload = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "protocol": {"split": "StratifiedGroupKFold by vendor/collection",
                     "seeds": a.seeds, "splits": a.splits,
                     "min_examples": a.min_examples,
                     "min_collections": a.min_collections},
        "identity": identity, "results": results,
        "interpretation": "Use waveform features for fusion only if the audio+waveform arm improves the frozen audio arm on the same folds; otherwise retain them for explanations and targeted mechanism rules.",
    }
    with open(OUT, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
