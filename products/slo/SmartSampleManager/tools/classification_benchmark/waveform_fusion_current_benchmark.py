#!/usr/bin/env python3
"""Collection-held-out ablation of interpretable waveform evidence.

This is research-only.  It aligns the existing physics_v1_1 descriptors to
the frozen factorised training manifest, computes missing descriptors without
touching source audio, and compares the frozen embedding with embedding plus
waveform evidence on identical grouped folds.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import os
import time
from pathlib import Path

import numpy as np


def _extract_one(path: str):
    import acoustic_evidence as ae
    value = ae.extract(path)
    if value is None:
        return path, None
    return path, np.asarray([value[name] for name in ae.NAMES], dtype=np.float32)


def _centroid_fit_predict(xtr, ytr, xte, classes):
    mean = xtr.mean(0)
    scale = xtr.std(0)
    scale[scale < 1e-6] = 1.0
    a = (xtr - mean) / scale
    b = (xte - mean) / scale
    a /= np.linalg.norm(a, axis=1, keepdims=True) + 1e-9
    b /= np.linalg.norm(b, axis=1, keepdims=True) + 1e-9
    c = np.asarray([a[ytr == cls].mean(0) for cls in classes])
    c /= np.linalg.norm(c, axis=1, keepdims=True) + 1e-9
    scores = b @ c.T
    order = np.argsort(scores, axis=1)
    confidence = scores[np.arange(len(scores)), order[:, -1]] - scores[np.arange(len(scores)), order[:, -2]]
    return np.asarray(classes, dtype=object)[scores.argmax(1)], confidence


def _load_manifest(corpus: Path, manifest: Path):
    z = np.load(corpus, allow_pickle=True)
    by_path = {os.path.abspath(str(p)): i for i, p in enumerate(z["paths"])}
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    rows = payload["rows"]
    paths, labels, groups, indices = [], [], [], []
    for row in rows:
        path = os.path.abspath(str(row["path"]))
        if path not in by_path:
            raise ValueError(f"manifest path missing from corpus: {path}")
        paths.append(path)
        labels.append(str(row["label"]))
        groups.append(str(row["vendor"]))
        indices.append(by_path[path])
    return (np.asarray(z["emb"], dtype=np.float32)[indices],
            np.asarray(paths, dtype=object), np.asarray(labels, dtype=object),
            np.asarray(groups, dtype=object))


def _features(paths, cache: Path, workers: int):
    import acoustic_evidence as ae

    done = {}
    if cache.exists():
        old = np.load(cache, allow_pickle=True)
        if str(old["version"]) == ae.FEATURE_VERSION:
            done = {os.path.abspath(str(p)): old["F"][i]
                    for i, p in enumerate(old["paths"])}
    todo = [str(p) for p in paths if str(p) not in done]
    print(f"waveform evidence: {len(done)} cached, {len(todo)} to extract", flush=True)
    if todo:
        with mp.Pool(max(1, workers)) as pool:
            for n, (path, value) in enumerate(pool.imap_unordered(_extract_one, todo, chunksize=2), 1):
                if value is not None:
                    done[path] = value
                if n % 100 == 0:
                    print(f"  extracted {n}/{len(todo)}", flush=True)
    missing = [str(p) for p in paths if str(p) not in done]
    if missing:
        print(f"waveform evidence: {len(missing)} files yielded no descriptor; excluding them", flush=True)
    valid_paths = [str(p) for p in paths if str(p) in done]
    ordered = np.asarray([done[p] for p in valid_paths], dtype=np.float32)
    np.savez(cache, F=ordered, paths=np.asarray(valid_paths, dtype=object),
             names=np.asarray(ae.NAMES, dtype=object), version=ae.FEATURE_VERSION)
    return ordered, set(missing)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--splits", type=int, default=5)
    args = ap.parse_args()

    from sklearn.metrics import f1_score
    from sklearn.model_selection import StratifiedGroupKFold

    x, paths, y, groups = _load_manifest(args.corpus, args.manifest)
    w, missing = _features(paths, args.cache, args.workers)
    keep_paths = np.asarray([str(p) not in missing for p in paths], dtype=bool)
    x, paths = x[keep_paths], paths[keep_paths]
    y, groups = y[keep_paths], groups[keep_paths]
    inventory = {cls: (int((y == cls).sum()), int(len(set(groups[y == cls]))))
                 for cls in sorted(set(y))}
    classes = [cls for cls, (n, ng) in inventory.items() if n >= 5 and ng >= 5]
    keep = np.isin(y, classes)
    x, w, y, groups = x[keep], w[keep], y[keep], groups[keep]
    print(f"benchmark rows={len(y)} classes={len(classes)} collections={len(set(groups))}", flush=True)

    results = {}
    arms = {"audio": x, "waveform": w, "audio+waveform": np.hstack([x, w])}
    for name, features in arms.items():
        accs, f1s = [], []
        for seed in range(args.seeds):
            pred = np.empty(len(y), dtype=object)
            cv = StratifiedGroupKFold(args.splits, shuffle=True, random_state=seed)
            for tr, te in cv.split(features, y, groups=groups):
                if set(groups[tr]) & set(groups[te]):
                    raise AssertionError("collection leakage")
                pred[te], _ = _centroid_fit_predict(features[tr], y[tr], features[te], classes)
            accs.append(100.0 * float((pred == y).mean()))
            f1s.append(100.0 * float(f1_score(y, pred.astype(str), average="macro", zero_division=0)))
        results[name] = {
            "accuracy": round(float(np.mean(accs)), 3),
            "accuracy_sd": round(float(np.std(accs)), 3),
            "macro_f1": round(float(np.mean(f1s)), 3),
            "per_seed": [round(float(v), 3) for v in accs],
        }
        print(name, results[name], flush=True)

    payload = {
        "record_type": "slo_waveform_fusion_current_benchmark",
        "schema_version": "1.0.0",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "protocol": {"split": "StratifiedGroupKFold by vendor/collection",
                     "seeds": args.seeds, "splits": args.splits,
                     "minimum_examples": 5, "minimum_collections": 5,
                     "promotion_gate_pp": 2.0},
        "inputs": {"corpus": str(args.corpus.resolve()),
                   "manifest": str(args.manifest.resolve()),
                   "n_rows": int(len(y)), "n_waveform_rows": int(len(w)),
                   "waveform_excluded_paths": sorted(missing),
                   "n_classes": len(classes),
                   "n_collections": int(len(set(groups))),
                   "waveform_feature_version": "physics_v1_1",
                   "waveform_cache_sha256": hashlib.sha256(args.cache.read_bytes()).hexdigest()},
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
