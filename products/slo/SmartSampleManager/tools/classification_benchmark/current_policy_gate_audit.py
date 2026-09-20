#!/usr/bin/env python3
"""Audit conservative auto/suggest/review actions on the current corpus."""
from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from pathlib import Path

import numpy as np


TRUSTED_NAME = {"Kick", "Hi-Hat", "Snare", "Clap", "Crash",
                "Percussion Loop", "Drum Loop"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--splits", type=int, default=5)
    args = ap.parse_args()
    from sklearn.model_selection import StratifiedGroupKFold
    import decision_policy as dp
    import name_detect

    z = np.load(args.corpus, allow_pickle=True)
    by_path = {os.path.abspath(str(p)): i for i, p in enumerate(z["paths"])}
    rows = json.loads(args.manifest.read_text(encoding="utf-8"))["rows"]
    paths = [os.path.abspath(str(r["path"])) for r in rows]
    idx = [by_path[p] for p in paths]
    X = np.asarray(z["emb"], dtype=np.float32)[idx]
    y = np.asarray([str(r["label"]) for r in rows], dtype=object)
    g = np.asarray([str(r["vendor"]) for r in rows], dtype=object)
    inventory = {c: (int((y == c).sum()), int(len(set(g[y == c])))) for c in sorted(set(y))}
    classes = [c for c, (n, ng) in inventory.items() if n >= 5 and ng >= 5]
    keep = np.isin(y, classes)
    X, y, g = X[keep], y[keep], g[keep]
    paths = np.asarray(paths, dtype=object)[keep]
    filename = []
    for p in paths:
        label, _ = name_detect.detect(os.path.basename(str(p)))
        filename.append(label if label in TRUSTED_NAME and label in classes else "")
    filename = np.asarray(filename, dtype=object)

    from incumbent_receipt import centroid_fit_predict
    results = {}
    for name_threshold in (None, 0.4, 0.5, 0.6):
        label = "audio_only" if name_threshold is None else f"name_if_audio_conf_below_{name_threshold:.2f}"
        actions = Counter(); correct = Counter(); by_action_class = Counter(); by_action_class_correct = Counter(); seed_auto = []
        for seed in range(args.seeds):
            pred = np.empty(len(y), dtype=object)
            conf = np.zeros(len(y), dtype=float)
            cv = StratifiedGroupKFold(args.splits, shuffle=True, random_state=seed)
            for tr, te in cv.split(X, y, groups=g):
                if set(g[tr]) & set(g[te]):
                    raise AssertionError("collection leakage")
                p, c = centroid_fit_predict(X[tr], y[tr], X[te], classes)
                pred[te], conf[te] = p, c
                if name_threshold is not None:
                    for j, row in enumerate(te):
                        if filename[row] and c[j] < name_threshold:
                            pred[row] = filename[row]
                            conf[row] = 0.9
            auto_n = auto_c = 0
            for i in range(len(y)):
                d = dp.decide(predicted_class=str(pred[i]), confidence=float(conf[i]),
                              path=str(paths[i]), filename_class=str(filename[i]) or None,
                              threshold=0.5, arm="current_audio_filename_audit")
                actions[d.action] += 1
                correct[d.action] += int(pred[i] == y[i])
                by_action_class[(d.action, str(pred[i]))] += 1
                by_action_class_correct[(d.action, str(pred[i]))] += int(pred[i] == y[i])
                if d.action == "auto_rename":
                    auto_n += 1; auto_c += int(pred[i] == y[i])
            seed_auto.append({"n": auto_n, "precision": 100 * auto_c / max(auto_n, 1)})
        total = len(y) * args.seeds
        auto_classes = {}
        for (action, cls), n in sorted(by_action_class.items()):
            if action == "auto_rename":
                auto_classes[cls] = {"n": int(n), "precision": round(100 * by_action_class_correct[(action, cls)] / max(n, 1), 2)}
        results[label] = {
            "actions": {a: {"n": int(actions[a]), "share": round(100 * actions[a] / total, 2),
                             "precision": round(100 * correct[a] / max(actions[a], 1), 2)}
                         for a in ("auto_rename", "suggest", "review", "never_act")},
            "auto_per_seed": seed_auto,
            "auto_by_class": auto_classes,
            "filename_override_threshold": name_threshold,
        }
        print(label, results[label], flush=True)

    payload = {
        "record_type": "slo_current_policy_gate_audit",
        "schema_version": "1.0.0", "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "protocol": {"split": "StratifiedGroupKFold by vendor/collection", "seeds": args.seeds,
                     "splits": args.splits, "policy_threshold": 0.5,
                     "trusted_filename_classes": sorted(TRUSTED_NAME)},
        "inventory": {"n_rows": int(len(y)), "n_classes": len(classes),
                      "n_collections": int(len(set(g))), "classes": classes},
        "results": results,
        "decision": "audit only; no approval, rename, or policy mutation",
        "safety": {"read_only": True, "source_audio_modified": False,
                   "production_model_changed": False, "rename_actions": False},
    }
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
