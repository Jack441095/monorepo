#!/usr/bin/env python3
"""Collection-held-out bake-off for cached MERT and AST representations."""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import numpy as np


def predict(xtr, ytr, xte, classes):
    mean = xtr.mean(0)
    scale = xtr.std(0)
    scale[scale < 1e-8] = 1.0
    a = (xtr - mean) / scale
    b = (xte - mean) / scale
    a /= np.linalg.norm(a, axis=1, keepdims=True) + 1e-9
    b /= np.linalg.norm(b, axis=1, keepdims=True) + 1e-9
    c = np.asarray([a[ytr == cls].mean(0) for cls in classes])
    c /= np.linalg.norm(c, axis=1, keepdims=True) + 1e-9
    score = b @ c.T
    return np.asarray(classes, dtype=object)[score.argmax(1)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--encoders", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--splits", type=int, default=5)
    args = ap.parse_args()
    from sklearn.metrics import f1_score
    from sklearn.model_selection import StratifiedGroupKFold

    z = np.load(args.corpus, allow_pickle=True)
    by_path = {os.path.abspath(str(p)): i for i, p in enumerate(z["paths"])}
    rows = json.loads(args.manifest.read_text(encoding="utf-8"))["rows"]
    paths = [os.path.abspath(str(r["path"])) for r in rows]
    indices = [by_path[p] for p in paths]
    base = np.asarray(z["emb"], dtype=np.float32)[indices]
    labels = np.asarray([str(r["label"]) for r in rows], dtype=object)
    groups = np.asarray([str(r["vendor"]) for r in rows], dtype=object)
    enc = np.load(args.encoders, allow_pickle=True)
    by_encoder_path = {os.path.abspath(str(p)): i for i, p in enumerate(enc["paths"])}
    valid = np.asarray([p in by_encoder_path for p in paths], dtype=bool)
    paths = np.asarray(paths, dtype=object)[valid]
    base, labels, groups = base[valid], labels[valid], groups[valid]
    eidx = [by_encoder_path[str(p)] for p in paths]
    mert = np.asarray(enc["mert"], dtype=np.float32)[eidx]
    ast = np.asarray(enc["ast"], dtype=np.float32)[eidx]
    inventory = {c: (int((labels == c).sum()), int(len(set(groups[labels == c]))))
                 for c in sorted(set(labels))}
    classes = [c for c, (n, ng) in inventory.items() if n >= 5 and ng >= 5]
    keep = np.isin(labels, classes)
    base, mert, ast, labels, groups = (v[keep] for v in (base, mert, ast, labels, groups))
    print(f"rows={len(labels)} classes={len(classes)} collections={len(set(groups))}", flush=True)

    arms = {
        "incumbent": base,
        "mert": mert,
        "ast": ast,
        "incumbent+mert": np.hstack([base, mert]),
        "incumbent+ast": np.hstack([base, ast]),
        "incumbent+mert+ast": np.hstack([base, mert, ast]),
    }
    results = {}
    for name, features in arms.items():
        accs, f1s = [], []
        for seed in range(args.seeds):
            pred = np.empty(len(labels), dtype=object)
            cv = StratifiedGroupKFold(args.splits, shuffle=True, random_state=seed)
            for tr, te in cv.split(features, labels, groups=groups):
                if set(groups[tr]) & set(groups[te]):
                    raise AssertionError("collection leakage")
                pred[te] = predict(features[tr], labels[tr], features[te], classes)
            accs.append(100 * float((pred == labels).mean()))
            f1s.append(100 * float(f1_score(labels, pred.astype(str), average="macro", zero_division=0)))
        results[name] = {"accuracy": round(float(np.mean(accs)), 3),
                         "accuracy_sd": round(float(np.std(accs)), 3),
                         "macro_f1": round(float(np.mean(f1s)), 3),
                         "per_seed": [round(float(v), 3) for v in accs]}
        print(name, results[name], flush=True)
    base_acc = results["incumbent"]["accuracy"]
    for row in results.values():
        row["delta_pp_vs_incumbent"] = round(row["accuracy"] - base_acc, 3)
    payload = {
        "record_type": "slo_encoder_bakeoff_current",
        "schema_version": "1.0.0", "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "protocol": {"split": "StratifiedGroupKFold by vendor/collection",
                     "seeds": args.seeds, "splits": args.splits,
                     "minimum_examples": 5, "minimum_collections": 5,
                     "decision_gate_pp": 2.0},
        "inventory": {"n_rows": int(len(labels)), "n_manifest_rows": len(rows),
                      "n_encoder_rows": int(valid.sum()), "n_classes": len(classes),
                      "n_collections": int(len(set(groups))),
                      "encoder_missing_paths": [str(row["path"]) for row, ok in zip(rows, valid) if not ok]},
        "results": results,
        "decision": "research evidence only; no production weights or rename actions",
        "safety": {"read_only": True, "source_audio_modified": False,
                   "production_model_changed": False, "rename_actions": False},
    }
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
