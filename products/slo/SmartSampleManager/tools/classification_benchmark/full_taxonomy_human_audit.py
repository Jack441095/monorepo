#!/usr/bin/env python3
"""Audit full-taxonomy audio/fusion predictions against existing human labels.

Only consensus labels from the two core drum CSVs are used. Rows with a label
conflict, a rejection label, or a class outside the eligible full taxonomy are
excluded. Predictions are still produced by collection-held-out folds, so rows
that trained the final centroid model are not evaluated in-sample.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import time
from collections import defaultdict

import numpy as np

SD = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(SD, "corpus_v2.npz")
OUT = os.path.join(SD, "results_full_taxonomy_human_audit_v1.json")
REJECT = {"", "__skip__", "Misc/Review", "Other/none"}
TRUSTED_NAME = {
    "Kick": 0.97, "Hi-Hat": 0.94, "Snare": 0.92, "Clap": 0.90,
    "Crash": 0.89, "Percussion Loop": 1.00, "Drum Loop": 0.78,
}


def human_labels():
    by = defaultdict(list)
    for filename in ("verified_drums.csv", "verified_drums_expanded.csv"):
        with open(os.path.join(SD, filename), newline="") as f:
            for row in csv.DictReader(f):
                path = os.path.abspath(row.get("path") or "")
                label = (row.get("label") or "").strip()
                if path and label not in REJECT:
                    by[path].append(label)
    return {p: next(iter(set(labels))) for p, labels in by.items()
            if len(set(labels)) == 1}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--splits", type=int, default=5)
    ap.add_argument("--corpus", default=CORPUS)
    ap.add_argument("--eval-corpus", default=None,
                    help="optional path set to restrict scoring rows")
    ap.add_argument("--eval-manifest", default=None,
                    help="optional JSONL manifest whose paths define scoring rows")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    import full_taxonomy_eval as full
    import incumbent_receipt as ir
    import name_detect
    from sklearn.metrics import f1_score, precision_recall_fscore_support
    from sklearn.model_selection import StratifiedGroupKFold

    d = full.load(args.corpus)
    eval_paths = None
    if args.eval_corpus:
        eval_paths = set(full.load(args.eval_corpus)["paths"])
    if args.eval_manifest:
        with open(args.eval_manifest) as f:
            manifest = [json.loads(line) for line in f if line.strip()]
        if manifest and manifest[0].get("record_type"):
            manifest = manifest[1:]
        manifest_paths = {os.path.abspath(str(r["path"])) for r in manifest
                          if r.get("path")}
        eval_paths = manifest_paths if eval_paths is None else eval_paths & manifest_paths
    inv = full.eligible_classes(d, 5, 5)
    classes = [c for c, v in inv.items() if v["eligible"]]
    path_to_idx = {p: i for i, p in enumerate(d["paths"])}
    gold = human_labels()
    selected = [path_to_idx[p] for p, label in gold.items()
                if p in path_to_idx and label in classes and
                (eval_paths is None or p in eval_paths)]
    if len(selected) < 20:
        raise SystemExit(f"FAIL CLOSED: only {len(selected)} usable human rows")
    selected = np.asarray(selected, dtype=int)
    # Train each fold on the complete eligible corpus. Only the rows with
    # independent human labels are scored; restricting training to the audit
    # subset would leave sparse classes with empty centroids.
    eligible = np.isin(d["labels"], classes)
    corpus_indices = np.flatnonzero(eligible)
    X = d["X"][corpus_indices]
    y_model = d["labels"][corpus_indices]
    groups = d["vendor"][corpus_indices]
    selected_lookup = {idx: j for j, idx in enumerate(selected)}
    eval_positions = np.asarray([
        j for j, idx in enumerate(corpus_indices) if idx in selected_lookup
    ], dtype=int)
    eval_global = corpus_indices[eval_positions]
    y_gold = np.asarray([gold[d["paths"][i]] for i in eval_global], dtype=object)
    paths = np.asarray(d["paths"])[eval_global]
    fn = []
    for p in paths:
        c, _ = name_detect.detect(os.path.basename(p))
        fn.append(c if c in TRUSTED_NAME and c in classes else "")
    fn = np.asarray(fn, dtype=object)
    override_by_class = {}
    for name_class in TRUSTED_NAME:
        mask = fn == name_class
        n = int(mask.sum())
        correct = int(np.sum(y_gold[mask] == name_class))
        if n:
            override_by_class[name_class] = {
                "support": n,
                "correct": correct,
                "precision": correct / n,
            }

    policies = {"audio": None, "name_if_audio_conf_below_0.70": 0.70,
                "name_always": 999.0}
    results = {}
    for policy, cutoff in policies.items():
        all_pred, all_gold, all_conf, all_over = [], [], [], []
        per_seed = []
        for seed in range(args.seeds):
            pred = np.empty(len(y_gold), dtype=object)
            conf = np.zeros(len(y_gold), dtype=float)
            over = np.zeros(len(y_gold), dtype=bool)
            cv = StratifiedGroupKFold(args.splits, shuffle=True,
                                      random_state=seed)
            for tr, te in cv.split(X, y_model, groups=groups):
                if set(groups[tr]) & set(groups[te]):
                    raise AssertionError("collection leakage")
                eval_mask = np.isin(corpus_indices[te], eval_global)
                if not eval_mask.any():
                    continue
                te_eval_global = corpus_indices[te][eval_mask]
                target = np.asarray([np.flatnonzero(eval_global == idx)[0]
                                     for idx in te_eval_global], dtype=int)
                p, c = ir.centroid_fit_predict(X[tr], y_model[tr],
                                               X[te][eval_mask], classes)
                pred[target], conf[target] = p, c
                if policy != "audio":
                    for j, target_idx in enumerate(target):
                        if fn[target_idx] and (policy == "name_always" or c[j] < cutoff):
                            pred[target_idx] = fn[target_idx]
                            conf[target_idx] = TRUSTED_NAME[fn[target_idx]]
                            over[target_idx] = True
            per_seed.append(float(np.mean(pred == y_gold)))
            all_pred.extend(pred.tolist()); all_gold.extend(y_gold.tolist())
            all_conf.extend(conf.tolist()); all_over.extend(over.tolist())
        correct = np.asarray(all_pred, dtype=object) == np.asarray(all_gold, dtype=object)
        pred_arr = np.asarray(all_pred, dtype=object)
        gold_arr = np.asarray(all_gold, dtype=object)
        p, r, f, support = precision_recall_fscore_support(
            gold_arr, pred_arr, labels=classes, zero_division=0)
        per_class = {
            c: {"precision": round(float(p[i]), 4),
                "recall": round(float(r[i]), 4),
                "f1": round(float(f[i]), 4), "n": int(support[i])}
            for i, c in enumerate(classes) if support[i]
        }
        results[policy] = {
            "accuracy_mean": round(100 * float(np.mean(per_seed)), 2),
            "accuracy_sd": round(100 * float(np.std(per_seed)), 2),
            "macro_f1": round(100 * float(f1_score(gold_arr, pred_arr,
                                                     labels=classes,
                                                     average="macro",
                                                     zero_division=0)), 2),
            "override_precision": round(100 * float(np.mean(correct[np.asarray(all_over, dtype=bool)])), 2)
            if any(all_over) else None,
            "override_rate": round(100 * float(np.mean(all_over)), 2),
            "per_seed_accuracy": [round(100 * x, 2) for x in per_seed],
            "per_class": per_class,
        }
        operating = {}
        target_classes = [c for c in
                          ("Bass Loop", "Crash", "Hi-Hat Loop", "Percussion Loop")
                          if c in classes]
        pred_vec = np.asarray(all_pred, dtype=object)
        gold_vec = np.asarray(all_gold, dtype=object)
        conf_vec = np.asarray(all_conf, dtype=float)
        for threshold in (0.40, 0.50, 0.60, 0.685):
            key = f"{threshold:.3f}"
            operating[key] = {}
            for cls in target_classes:
                mask = (pred_vec == cls) & (conf_vec >= threshold)
                n = int(mask.sum())
                hits = int(np.sum(pred_vec[mask] == gold_vec[mask]))
                operating[key][cls] = {
                    "selected": n,
                    "precision": hits / n if n else None,
                    "coverage": n / len(pred_vec) if len(pred_vec) else 0.0,
                }
        results[policy]["suggestion_operating_points"] = operating
        print(policy, results[policy]["accuracy_mean"],
              results[policy]["override_precision"],
              "rows", len(all_gold))

    payload = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "protocol": {
            "split": "StratifiedGroupKFold by vendor/collection",
            "seeds": args.seeds, "splits": args.splits,
            "human_sources": ["verified_drums.csv", "verified_drums_expanded.csv"],
            "training_corpus": os.path.abspath(args.corpus),
            "evaluation_path_set": os.path.abspath(args.eval_corpus) if args.eval_corpus else None,
            "evaluation_manifest": os.path.abspath(args.eval_manifest) if args.eval_manifest else None,
            "conflicting_rows_excluded": True,
            "trusted_name_precision": TRUSTED_NAME,
        },
        "n_rows": int(len(selected)), "n_collections": int(len(set(groups))),
        "classes": classes, "trusted_name_override_by_class": override_by_class,
        "results": results,
    }
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    raise SystemExit(main())
