#!/usr/bin/env python3
"""Collection-held-out model bake-off for the FFT/physics loop specialist.

This compares a small, reproducible set of classifiers on the already verified
loop corpus.  It is deliberately research-only: no weights, labels, or rename
actions are changed.  The split and feature loaders are shared with the
canonical periodicity/FFT/physics benchmark to prevent protocol drift.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import time
from pathlib import Path

import numpy as np
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC


SD = Path(__file__).resolve().parent


def _module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SD / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _metrics(y: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    return {
        "accuracy": round(float(100 * accuracy_score(y, pred)), 3),
        "macro_f1": round(float(100 * f1_score(y, pred, average="macro", zero_division=0)), 3),
    }


def _cached_map(cache: Path, matrix_key: str) -> tuple[dict[str, np.ndarray], list[str]]:
    """Read a cache without triggering dynamic-module multiprocessing."""
    z = np.load(cache, allow_pickle=True)
    if "paths" not in z.files or matrix_key not in z.files:
        raise ValueError(f"cache missing paths/{matrix_key}: {cache}")
    paths = [os.path.abspath(str(path)) for path in z["paths"]]
    return ({path: np.asarray(z[matrix_key][i], dtype=np.float32)
             for i, path in enumerate(paths)}, paths)


def _models(seed: int):
    return {
        "logistic": make_pipeline(StandardScaler(), LogisticRegression(
            max_iter=3000, class_weight="balanced", random_state=seed)),
        "linear_svm": make_pipeline(StandardScaler(), SVC(
            kernel="linear", class_weight="balanced", C=1.0)),
        "rbf_svm": make_pipeline(StandardScaler(), SVC(
            kernel="rbf", class_weight="balanced", C=1.0, gamma="scale")),
        "extra_trees": ExtraTreesClassifier(
            n_estimators=400, class_weight="balanced", min_samples_leaf=2,
            max_features="sqrt", n_jobs=1, random_state=seed),
        "random_forest": RandomForestClassifier(
            n_estimators=400, class_weight="balanced", min_samples_leaf=2,
            max_features="sqrt", n_jobs=1, random_state=seed),
        "hist_gradient_boosting": HistGradientBoostingClassifier(
            max_iter=180, learning_rate=0.04, max_leaf_nodes=15,
            l2_regularization=1.0, random_state=seed),
    }


def _score(X: np.ndarray, y: np.ndarray, groups: np.ndarray, seed: int, model_name: str):
    pred = np.zeros(len(y), dtype=np.int8)
    cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=seed)
    for train, test in cv.split(X, y, groups):
        model = _models(seed)[model_name]
        model.fit(X[train], y[train])
        pred[test] = model.predict(X[test])
    return _metrics(y, pred)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", type=Path, default=SD / "verified_drums.csv")
    parser.add_argument("--periodicity-cache", type=Path, default=SD / "loop_periodicity_feats.npz")
    parser.add_argument("--fft-cache", type=Path, required=True)
    parser.add_argument("--physics-cache", type=Path, default=SD / "mw_features_v1.npz")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seeds", type=int, default=5)
    args = parser.parse_args()

    benchmark = _module("periodicity_fft_loop_benchmark_bakeoff", "periodicity_fft_loop_benchmark.py")
    physics_benchmark = _module("periodicity_fft_physics_bakeoff", "periodicity_fft_physics_benchmark.py")
    rows = benchmark._rows(args.labels)
    paths = [path for path, _ in rows]
    y = np.asarray([label for _, label in rows], dtype=np.int8)
    physics_map, physics_paths_list = _cached_map(args.physics_cache, "F")
    physics_paths = set(physics_paths_list)
    fft_map, fft_paths_list = _cached_map(args.fft_cache, "X")
    fft_paths = set(fft_paths_list)
    periodicity_z = np.load(args.periodicity_cache, allow_pickle=True)
    periodicity_paths = {os.path.abspath(str(path)) for path in periodicity_z["paths"]}
    keep = np.asarray([path in physics_paths and path in fft_paths and path in periodicity_paths
                       for path in paths], dtype=bool)
    paths, y = [p for p, k in zip(paths, keep) if k], y[keep]
    periodicity = benchmark._load_periodicity(args.periodicity_cache, paths)
    fft = np.asarray([fft_map[path] for path in paths], dtype=np.float32)
    physics = physics_benchmark._load_named(args.physics_cache, paths,
                                             physics_benchmark.PHYSICS_FEATURES, "F")
    valid = (np.isfinite(periodicity).all(axis=1) & np.isfinite(fft).all(axis=1)
             & np.isfinite(physics).all(axis=1))
    paths = [p for p, k in zip(paths, valid) if k]
    y, periodicity, fft, physics = y[valid], periodicity[valid], fft[valid], physics[valid]
    groups = np.asarray([os.path.dirname(os.path.dirname(path)) for path in paths], dtype=object)
    arms = {
        "periodicity_physics": np.hstack([periodicity, physics]),
        "periodicity_fft_physics": np.hstack([periodicity, fft[:, 2:], physics]),
    }
    model_names = list(_models(0))
    raw = {arm: {name: [_score(features, y, groups, seed, name)
                       for seed in range(args.seeds)]
                 for name in model_names}
           for arm, features in arms.items()}
    results = {arm: {name: {
        "mean": {key: round(float(np.mean([row[key] for row in values])), 3)
                 for key in values[0]},
        "per_seed": values,
    } for name, values in models.items()} for arm, models in raw.items()}
    receipt = {
        "record_type": "slo_periodicity_fft_physics_model_bakeoff",
        "schema_version": "1.0.0",
        "method_version": "periodicity_fft_physics_model_bakeoff_v1",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "protocol": {"split": "StratifiedGroupKFold by two-level collection",
                     "folds": 5, "seeds": args.seeds,
                     "models": model_names, "promotion_gate_pp": 2.0},
        "inputs": {"labels": str(args.labels.resolve()), "rows": int(len(y)),
                   "loops": int(y.sum()), "one_shots": int((1 - y).sum()),
                   "collections": int(len(set(groups)))},
        "results": results,
        "decision": "research evidence only; no production weights or rename actions",
        "safety": {"read_only": True, "source_audio_modified": False,
                   "production_model_changed": False, "rename_actions": False},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({arm: {name: value["mean"] for name, value in models.items()}
                      for arm, models in results.items()}, indent=2))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
