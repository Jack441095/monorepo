#!/usr/bin/env python3
"""Loop-family specialist using full-file loop spectrum plus FFT physics."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import multiprocessing as mp
import os
import time
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import StratifiedGroupKFold


SD = Path(__file__).resolve().parent
PHYSICS_FEATURES = (
    "full_transient", "full_decay_s", "full_low_energy", "full_hf_density",
    "full_onset_rate", "third_onset_cv", "rhythm_ac_peak", "rhythm_ac_lag",
    "repetition_score", "silence_frac",
)
LOOP_NAMES = ("sub", "low", "mid", "high", "vhigh", "kick", "centroid",
              "flatness", "lowmid_ratio", "onset_reg")


def _module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SD / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _loop_one(path: str):
    module = _module("loop_features_worker", "loop_features.py")
    return path, module.extract(path)


def _load_loop(cache: Path, paths: list[str], workers: int) -> np.ndarray:
    found: dict[str, np.ndarray] = {}
    if cache.exists():
        z = np.load(cache, allow_pickle=True)
        names = [str(name) for name in z["names"]] if "names" in z.files else []
        if names == list(LOOP_NAMES):
            found = {os.path.abspath(str(path)): z["X"][i]
                     for i, path in enumerate(z["paths"])}
    todo = [path for path in paths if path not in found]
    if todo:
        with mp.Pool(max(1, workers)) as pool:
            for path, values in pool.imap_unordered(_loop_one, todo):
                if values is not None and np.isfinite(values).all():
                    found[path] = np.asarray(values, dtype=np.float32)
    result = np.asarray([
        found[path] if path in found else np.full(len(LOOP_NAMES), np.nan, dtype=np.float32)
        for path in paths
    ], dtype=np.float32)
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez(cache, X=result, paths=np.asarray(paths, dtype=object),
             names=np.asarray(LOOP_NAMES, dtype=object), version="loop_features_v1")
    return result


def _load_physics(cache: Path, paths: list[str]) -> np.ndarray:
    z = np.load(cache, allow_pickle=True)
    cached_paths = [os.path.abspath(str(path)) for path in z["paths"]]
    by_path = {path: i for i, path in enumerate(cached_paths)}
    names = [str(name) for name in z["names"]]
    indices = [names.index(name) for name in PHYSICS_FEATURES]
    missing = [path for path in paths if path not in by_path]
    if missing:
        raise ValueError(f"physics cache missing {len(missing)} paths")
    return np.asarray([[z["F"][by_path[path], index] for index in indices]
                       for path in paths], dtype=np.float32)


def _score(X: np.ndarray, y: np.ndarray, groups: np.ndarray, seed: int) -> dict[str, float]:
    pred = np.empty(len(y), dtype=object)
    cv = StratifiedGroupKFold(5, shuffle=True, random_state=seed)
    for train, test in cv.split(X, y, groups):
        model = RandomForestClassifier(n_estimators=400, class_weight="balanced",
                                        min_samples_leaf=2, random_state=seed, n_jobs=1)
        model.fit(X[train], y[train])
        pred[test] = model.predict(X[test])
    return {"accuracy": round(float(100 * accuracy_score(y, pred)), 3),
            "macro_f1": round(float(100 * f1_score(y, pred, average="macro", zero_division=0)), 3)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=SD / "corpus_v2.npz")
    parser.add_argument("--physics-cache", type=Path, default=SD / "mw_features_v1.npz")
    parser.add_argument("--loop-cache", type=Path, default=SD / "full_loop_features_v1.npz")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--seeds", type=int, default=10)
    parser.add_argument("--min-class", type=int, default=10)
    parser.add_argument("--min-collections", type=int, default=5)
    args = parser.parse_args()

    full = _module("full_taxonomy_eval", "full_taxonomy_eval.py")
    d = full.load(str(args.corpus))
    inventory = full.eligible_classes(d, args.min_class, args.min_collections)
    eligible_all = [label for label, item in inventory.items() if item["eligible"]]
    loop_classes = [label for label, item in inventory.items()
                    if "Loop" in label and item["examples"] >= args.min_class
                    and item["collections"] >= args.min_collections]
    keep = np.isin(d["labels"], eligible_all)
    paths = [str(path) for path, use in zip(d["paths"], keep) if use]
    y = np.asarray(d["labels"])[keep].astype(str)
    groups = np.asarray(d["vendor"])[keep]
    physics_z = np.load(args.physics_cache, allow_pickle=True)
    physics_paths = {os.path.abspath(str(path)) for path in physics_z["paths"]}
    aligned = np.asarray([path in physics_paths for path in paths], dtype=bool)
    paths, y, groups = ([value[aligned] if isinstance(value, np.ndarray)
                         else [item for item, use in zip(value, aligned) if use]
                         for value in (paths, y, groups)])
    loop = _load_loop(args.loop_cache, paths, args.workers)
    physics = _load_physics(args.physics_cache, paths)
    valid = np.isfinite(loop).all(axis=1) & np.isfinite(physics).all(axis=1)
    loop, physics, y, groups = loop[valid], physics[valid], y[valid], groups[valid]
    loop_mask = np.isin(y, loop_classes)
    if len(loop_classes) < 2 or int(loop_mask.sum()) < 20:
        raise ValueError("not enough supported loop-family rows")
    X_loop, y_loop, g_loop = loop[loop_mask], y[loop_mask], groups[loop_mask]
    arms = {"loop_spectrum": X_loop,
            "physics": physics[loop_mask],
            "loop_spectrum_physics": np.hstack([X_loop, physics[loop_mask]])}
    raw = {name: [_score(features, y_loop, g_loop, seed) for seed in range(args.seeds)]
           for name, features in arms.items()}
    results = {name: {"mean": {key: round(float(np.mean([row[key] for row in values])), 3)
                                for key in values[0]}, "per_seed": values}
               for name, values in raw.items()}
    receipt = {
        "record_type": "slo_full_taxonomy_loop_family_feature_fusion",
        "schema_version": "1.0.0", "method_version": "full_taxonomy_loop_family_feature_fusion_v1",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "protocol": {"split": "StratifiedGroupKFold by vendor/collection", "folds": 5,
                     "seeds": args.seeds, "model": "balanced RF, 400 trees, min_samples_leaf=2",
                     "minimum_class": args.min_class, "minimum_collections": args.min_collections,
                     "promotion_gate_pp": 2.0},
        "inputs": {"corpus": str(args.corpus.resolve()), "rows": int(len(y_loop)),
                   "aligned_rows": int(len(y)), "classes": loop_classes,
                   "collections": int(len(set(g_loop)))},
        "features": {"loop_spectrum": list(LOOP_NAMES), "physics": list(PHYSICS_FEATURES)},
        "results": results,
        "decision": "research evidence only; no production weights or rename actions",
        "safety": {"read_only": True, "source_audio_modified": False,
                   "production_model_changed": False, "rename_actions": False},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({name: value["mean"] for name, value in results.items()}, indent=2))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
