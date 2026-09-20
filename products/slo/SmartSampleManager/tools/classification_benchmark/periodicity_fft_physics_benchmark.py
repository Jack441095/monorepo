#!/usr/bin/env python3
"""Grouped ablation of periodicity, FFT sidecar, and multi-window physics.

The physics cache is label-free and contains windowed spectral/temporal
descriptors.  This receipt tests whether those descriptors add independent
signal to the existing loop specialist; it never changes production weights.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import time
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


SD = Path(__file__).resolve().parent
PHYSICS_FEATURES = (
    "full_transient", "full_decay_s", "full_low_energy", "full_hf_density",
    "full_onset_rate", "third_onset_cv", "rhythm_ac_peak", "rhythm_ac_lag",
    "repetition_score", "silence_frac",
)


def _module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SD / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_named(cache: Path, paths: list[str], names: tuple[str, ...], matrix_key: str) -> np.ndarray:
    z = np.load(cache, allow_pickle=True)
    if "paths" not in z.files or matrix_key not in z.files or "names" not in z.files:
        raise ValueError(f"cache missing paths/{matrix_key}/names: {cache}")
    cached_paths = [os.path.abspath(str(path)) for path in z["paths"]]
    by_path = {path: i for i, path in enumerate(cached_paths)}
    cached_names = [str(name) for name in z["names"]]
    indices = [cached_names.index(name) for name in names]
    missing = [path for path in paths if path not in by_path]
    if missing:
        raise ValueError(f"cache missing {len(missing)} requested paths: {cache}")
    return np.asarray([[z[matrix_key][by_path[path], index] for index in indices]
                       for path in paths], dtype=np.float32)


def _metrics(y: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    return {
        "accuracy": round(float(100 * accuracy_score(y, pred)), 3),
        "macro_f1": round(float(100 * f1_score(y, pred, average="macro", zero_division=0)), 3),
        "loop_precision": round(float(100 * precision_score(y, pred, zero_division=0)), 3),
        "loop_recall": round(float(100 * recall_score(y, pred, zero_division=0)), 3),
    }


def _score(X: np.ndarray, y: np.ndarray, groups: np.ndarray, seed: int) -> dict[str, float]:
    pred = np.zeros(len(y), dtype=np.int8)
    cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=seed)
    for train, test in cv.split(X, y, groups):
        model = make_pipeline(StandardScaler(), LogisticRegression(
            max_iter=3000, class_weight="balanced", random_state=seed))
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

    benchmark = _module("periodicity_fft_loop_benchmark", "periodicity_fft_loop_benchmark.py")
    rows = benchmark._rows(args.labels)
    paths = [path for path, _ in rows]
    y = np.asarray([label for _, label in rows], dtype=np.int8)
    physics_z = np.load(args.physics_cache, allow_pickle=True)
    physics_paths = {os.path.abspath(str(path)) for path in physics_z["paths"]}
    physics_keep = np.asarray([path in physics_paths for path in paths], dtype=bool)
    paths = [path for path, keep in zip(paths, physics_keep) if keep]
    y = y[physics_keep]
    periodicity = benchmark._load_periodicity(args.periodicity_cache, paths)
    fft, _ = benchmark._load_fft(paths, args.fft_cache, workers=4)
    physics = _load_named(args.physics_cache, paths, PHYSICS_FEATURES, "F")
    valid = (np.isfinite(periodicity).all(axis=1) & np.isfinite(fft).all(axis=1)
             & np.isfinite(physics).all(axis=1))
    paths = [path for path, keep in zip(paths, valid) if keep]
    y, periodicity, fft, physics = y[valid], periodicity[valid], fft[valid], physics[valid]
    groups = np.asarray([os.path.dirname(os.path.dirname(path)) for path in paths], dtype=object)
    if len(set(y.tolist())) < 2:
        raise ValueError("need both loop and one-shot rows after filtering")

    arms = {
        "periodicity": periodicity,
        "periodicity_fft": np.hstack([periodicity, fft[:, 2:]]),
        "periodicity_physics": np.hstack([periodicity, physics]),
        "periodicity_fft_physics": np.hstack([periodicity, fft[:, 2:], physics]),
    }
    raw = {name: [_score(features, y, groups, seed) for seed in range(args.seeds)]
           for name, features in arms.items()}
    results = {name: {
        "mean": {key: round(float(np.mean([row[key] for row in values])), 3)
                 for key in values[0]},
        "per_seed": values,
    } for name, values in raw.items()}
    receipt = {
        "record_type": "slo_periodicity_fft_physics_benchmark",
        "schema_version": "1.0.0",
        "method_version": "periodicity_fft_physics_v1",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "protocol": {"split": "StratifiedGroupKFold by two-level collection",
                     "folds": 5, "seeds": args.seeds,
                     "model": "standardized balanced logistic regression",
                     "promotion_gate_pp": 2.0},
        "inputs": {"labels": str(args.labels.resolve()), "rows": int(len(y)),
                   "loops": int(y.sum()), "one_shots": int((1 - y).sum()),
                   "collections": int(len(set(groups)))},
        "features": {"periodicity": list(benchmark.ALLOWED_FEATURES),
                     "fft_sidecar": list(_module("fft_names", "fft_sidecar_benchmark.py").FEATURE_NAMES),
                     "physics": list(PHYSICS_FEATURES)},
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
