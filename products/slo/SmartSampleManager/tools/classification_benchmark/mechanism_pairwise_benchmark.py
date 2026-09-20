#!/usr/bin/env python3
"""Evaluate physical evidence on known difficult class boundaries.

Research-only, collection-held-out pairwise ablation.  A positive result here
is intentionally interpreted as a targeted mechanism/review rule, not as
evidence for replacing the global classifier.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import numpy as np

PAIRS = [
    ("Bass Hit", "Bass Reese"),
    ("Percussion", "Percussion Loop"),
    ("Hi-Hat", "Hi-Hat Loop"),
    ("Synth Loop", "Synth One-Shot"),
    ("Vocal Loop", "Vocal One-Shot"),
    ("Foley", "Impact"),
]


def predict(xtr, ytr, xte, classes):
    mean = xtr.mean(0)
    scale = xtr.std(0)
    scale[scale < 1e-6] = 1.0
    a = (xtr - mean) / scale
    b = (xte - mean) / scale
    a /= np.linalg.norm(a, axis=1, keepdims=True) + 1e-9
    b /= np.linalg.norm(b, axis=1, keepdims=True) + 1e-9
    c = np.asarray([a[ytr == cls].mean(0) for cls in classes])
    c /= np.linalg.norm(c, axis=1, keepdims=True) + 1e-9
    return np.asarray(classes, dtype=object)[(b @ c.T).argmax(1)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--waveform-cache", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--splits", type=int, default=5)
    args = ap.parse_args()

    from sklearn.model_selection import StratifiedGroupKFold

    z = np.load(args.corpus, allow_pickle=True)
    by_path = {os.path.abspath(str(p)): i for i, p in enumerate(z["paths"])}
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    rows = manifest["rows"]
    paths = [os.path.abspath(str(r["path"])) for r in rows]
    indices = [by_path[p] for p in paths]
    emb = np.asarray(z["emb"], dtype=np.float32)[indices]
    labels = np.asarray([str(r["label"]) for r in rows], dtype=object)
    groups = np.asarray([str(r["vendor"]) for r in rows], dtype=object)
    wcache = np.load(args.waveform_cache, allow_pickle=True)
    wf = {os.path.abspath(str(p)): wcache["F"][i]
          for i, p in enumerate(wcache["paths"])}

    results = {}
    for left, right in PAIRS:
        keep = np.isin(labels, [left, right]) & np.asarray([p in wf for p in paths])
        x, w, y, g = emb[keep], np.asarray([wf[p] for p in np.asarray(paths)[keep]], dtype=np.float32), labels[keep], groups[keep]
        counts = {c: int((y == c).sum()) for c in (left, right)}
        collections = {c: int(len(set(g[y == c]))) for c in (left, right)}
        if min(counts.values()) < 5 or min(collections.values()) < 5:
            results[f"{left}__vs__{right}"] = {"status": "ineligible", "counts": counts, "collections": collections}
            continue
        arms = {"embedding": x, "waveform": w, "fused": np.hstack([x, w])}
        arm_results = {}
        for name, features in arms.items():
            accs = []
            for seed in range(args.seeds):
                pred = np.empty(len(y), dtype=object)
                cv = StratifiedGroupKFold(args.splits, shuffle=True, random_state=seed)
                for tr, te in cv.split(features, y, groups=g):
                    if set(g[tr]) & set(g[te]):
                        raise AssertionError(f"collection leakage in {left}/{right}")
                    pred[te] = predict(features[tr], y[tr], features[te], [left, right])
                accs.append(100.0 * float((pred == y).mean()))
            arm_results[name] = {"accuracy": round(float(np.mean(accs)), 3),
                                "accuracy_sd": round(float(np.std(accs)), 3),
                                "per_seed": [round(float(v), 3) for v in accs]}
        base = arm_results["embedding"]["accuracy"]
        for value in arm_results.values():
            value["delta_pp_vs_embedding"] = round(value["accuracy"] - base, 3)
        results[f"{left}__vs__{right}"] = {
            "status": "evaluated", "counts": counts, "collections": collections,
            "n_rows": int(len(y)), "arms": arm_results,
        }
        print(f"{left} vs {right}: {arm_results}", flush=True)

    payload = {
        "record_type": "slo_mechanism_pairwise_benchmark",
        "schema_version": "1.0.0",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "protocol": {"split": "StratifiedGroupKFold by vendor/collection",
                     "seeds": args.seeds, "splits": args.splits,
                     "decision_gate_pp": 2.0},
        "pairs": results,
        "decision": "research evidence only; pairwise gains may inform targeted review rules but do not change global policy",
        "safety": {"read_only": True, "source_audio_modified": False,
                   "production_model_changed": False, "rename_actions": False},
    }
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

