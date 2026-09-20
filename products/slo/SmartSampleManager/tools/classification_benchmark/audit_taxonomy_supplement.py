#!/usr/bin/env python3
"""OOF audit of a labelled supplement against a grouped full corpus."""
from __future__ import annotations

import argparse
import json
import os
import time
from collections import defaultdict

import numpy as np

TRUSTED_NAME = {
    "Kick": 0.97, "Hi-Hat": 0.94, "Snare": 0.92, "Clap": 0.90,
    "Crash": 0.89, "Percussion Loop": 1.00, "Drum Loop": 0.78,
}


def manifest_rows(path):
    with open(path) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    return rows[1:] if rows and rows[0].get("record_type") else rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--splits", type=int, default=5)
    args = ap.parse_args()

    import full_taxonomy_eval as full
    import incumbent_receipt as ir
    import name_detect
    from sklearn.metrics import f1_score, precision_recall_fscore_support
    from sklearn.model_selection import StratifiedGroupKFold

    d = full.load(args.corpus)
    inv = full.eligible_classes(d, 5, 5)
    classes = [c for c, v in inv.items() if v["eligible"]]
    path_to_idx = {p: i for i, p in enumerate(d["paths"])}
    gold = {}
    for row in manifest_rows(args.manifest):
        p = os.path.abspath(str(row.get("path") or ""))
        label = str(row.get("label") or "")
        if p in path_to_idx and label in classes:
            gold[p] = label
    eval_global = np.asarray([path_to_idx[p] for p in sorted(gold)], dtype=int)
    if len(eval_global) < 20:
        raise SystemExit(f"FAIL CLOSED: only {len(eval_global)} eligible supplement rows")

    eligible = np.isin(d["labels"], classes)
    corpus_indices = np.flatnonzero(eligible)
    X = d["X"][corpus_indices]
    y = d["labels"][corpus_indices]
    groups = d["vendor"][corpus_indices]
    pos = {idx: j for j, idx in enumerate(eval_global)}
    eval_positions = np.asarray([j for j, idx in enumerate(corpus_indices)
                                 if idx in pos], dtype=int)
    eval_global = corpus_indices[eval_positions]
    y_gold = np.asarray([gold[d["paths"][i]] for i in eval_global], dtype=object)
    paths = np.asarray(d["paths"])[eval_global]
    fn = np.asarray([
        (name_detect.detect(os.path.basename(p))[0]
         if name_detect.detect(os.path.basename(p))[0] in TRUSTED_NAME else "")
        for p in paths
    ], dtype=object)

    policies = {"audio": None, "name_if_audio_conf_below_0.70": 0.70,
                "name_always": 999.0}
    all_results = {}
    for policy, cutoff in policies.items():
        seed_acc, all_pred, all_gold, all_conf, all_over = [], [], [], [], []
        for seed in range(args.seeds):
            pred = np.empty(len(y_gold), dtype=object)
            conf = np.zeros(len(y_gold), dtype=float)
            over = np.zeros(len(y_gold), dtype=bool)
            cv = StratifiedGroupKFold(args.splits, shuffle=True,
                                      random_state=seed)
            for tr, te in cv.split(X, y, groups=groups):
                if set(groups[tr]) & set(groups[te]):
                    raise AssertionError("collection leakage")
                mask = np.isin(corpus_indices[te], eval_global)
                if not mask.any():
                    continue
                te_global = corpus_indices[te][mask]
                targets = np.asarray([pos[idx] for idx in te_global], dtype=int)
                p, c = ir.centroid_fit_predict(X[tr], y[tr], X[te][mask], classes)
                pred[targets], conf[targets] = p, c
                if policy != "audio":
                    for j, target in enumerate(targets):
                        if fn[target] and (policy == "name_always" or c[j] < cutoff):
                            pred[target] = fn[target]
                            conf[target] = TRUSTED_NAME[fn[target]]
                            over[target] = True
            seed_acc.append(float(np.mean(pred == y_gold)))
            all_pred.extend(pred.tolist()); all_gold.extend(y_gold.tolist())
            all_conf.extend(conf.tolist()); all_over.extend(over.tolist())
        pred_arr = np.asarray(all_pred, dtype=object)
        gold_arr = np.asarray(all_gold, dtype=object)
        conf_arr = np.asarray(all_conf, dtype=float)
        over_arr = np.asarray(all_over, dtype=bool)
        p, r, f, support = precision_recall_fscore_support(
            gold_arr, pred_arr, labels=classes, zero_division=0)
        per_class = {
            c: {"precision": round(float(p[i]), 4),
                "recall": round(float(r[i]), 4),
                "f1": round(float(f[i]), 4), "n": int(support[i])}
            for i, c in enumerate(classes) if support[i]
        }
        operating = {}
        for threshold in (0.40, 0.50, 0.60, 0.685):
            op = {}
            for c in ("Bass Loop", "Crash", "Hi-Hat Loop", "Percussion Loop"):
                m = (pred_arr == c) & (conf_arr >= threshold)
                op[c] = {"selected": int(m.sum()),
                          "precision": float(np.mean(pred_arr[m] == gold_arr[m])) if m.any() else None}
            operating[f"{threshold:.3f}"] = op
        correct_over = (pred_arr[over_arr] == gold_arr[over_arr]) if over_arr.any() else []
        all_results[policy] = {
            "accuracy_mean": round(100 * float(np.mean(seed_acc)), 2),
            "accuracy_sd": round(100 * float(np.std(seed_acc)), 2),
            "macro_f1": round(100 * float(f1_score(gold_arr, pred_arr,
                                                     labels=classes,
                                                     average="macro", zero_division=0)), 2),
            "override_rate": round(100 * float(over_arr.mean()), 2),
            "override_precision": round(100 * float(np.mean(correct_over)), 2) if over_arr.any() else None,
            "per_seed_accuracy": [round(100 * x, 2) for x in seed_acc],
            "per_class": per_class, "suggestion_operating_points": operating,
        }
        r = all_results[policy]
        print(policy, r["accuracy_mean"], r["override_precision"], "rows", len(gold_arr))

    payload = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "protocol": {"split": "StratifiedGroupKFold by vendor/collection",
                      "seeds": args.seeds, "splits": args.splits,
                      "corpus": os.path.abspath(args.corpus),
                      "manifest": os.path.abspath(args.manifest)},
        "n_rows": len(gold), "n_collections": len(set(d["vendor"][eval_global])),
        "classes": classes, "results": all_results,
    }
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    raise SystemExit(main())
