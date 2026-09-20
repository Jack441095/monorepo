#!/usr/bin/env python3
"""Collection-held-out loop specialist using periodicity plus FFT evidence.

This is a research receipt for the next classifier route.  It uses the
existing by-ear loop/one-shot corpus, reuses the cached autocorrelation and
recurrence features, and evaluates whether the FFT sidecar adds anything
independent.  The unstable head/tail splice feature is intentionally excluded
from every arm.  No production weights, labels, or audio are modified.
"""

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
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


SD = Path(__file__).resolve().parent
ALLOWED_FEATURES = ("dur", "sustain", "ac_peak", "ac_ratio", "recur", "onsets", "tempo_conf")


def _module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SD / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rows(labels: Path) -> list[tuple[str, int]]:
    result = []
    seen: dict[str, str] = {}
    for row in csv.DictReader(labels.open(newline="")):
        label = row.get("label", "")
        if label in {"__skip__", "Misc/Review"}:
            continue
        path = os.path.abspath(row.get("path", ""))
        if path and os.path.exists(path):
            previous = seen.get(path)
            if previous is not None:
                if previous != label:
                    raise ValueError(f"conflicting labels for duplicate path: {path}")
                continue
            seen[path] = label
            result.append((path, int("Loop" in label)))
    return result


def _load_periodicity(cache: Path, paths: list[str]) -> np.ndarray:
    if not cache.exists():
        raise FileNotFoundError(f"periodicity cache missing: {cache}")
    z = np.load(cache, allow_pickle=True)
    cached_paths = [os.path.abspath(str(p)) for p in z["paths"]]
    index = {path: i for i, path in enumerate(cached_paths)}
    names = [str(x) for x in z["names"]] if "names" in z.files else []
    if not names:
        names = ["dur", "sustain", "ac_peak", "ac_lag_s", "ac_ratio",
                 "recur", "splice", "onsets", "tempo_conf"]
    indices = [names.index(name) for name in ALLOWED_FEATURES]
    missing = [path for path in paths if path not in index]
    if missing:
        raise ValueError(f"periodicity cache missing {len(missing)} requested paths")
    return np.asarray([[z["X"][index[path], i] for i in indices] for path in paths], dtype=np.float32)


def _fft_one(path: str):
    fft = _module("fft_sidecar_benchmark_worker", "fft_sidecar_benchmark.py")
    return path, fft.extract(path)


def _load_fft(paths: list[str], cache: Path, workers: int) -> tuple[np.ndarray, list[str]]:
    fft = _module("fft_sidecar_benchmark", "fft_sidecar_benchmark.py")
    names = list(fft.FEATURE_NAMES)
    found: dict[str, np.ndarray] = {}
    if cache.exists():
        z = np.load(cache, allow_pickle=True)
        cached_names = [str(x) for x in z["names"]] if "names" in z.files else []
        if cached_names == names and "X" in z.files and "paths" in z.files:
            found = {os.path.abspath(str(path)): z["X"][i]
                     for i, path in enumerate(z["paths"])}
    todo = [path for path in paths if path not in found]
    if todo:
        # Importing the worker module in each process keeps this script usable
        # from a clean shell without relying on package installation state.
        with mp.Pool(max(1, workers)) as pool:
            for path, values in pool.imap_unordered(_fft_one, todo):
                if values is not None:
                    found[path] = values
    missing = [path for path in paths if path not in found]
    # A small number of inventory files may be truncated or undecodable. Keep
    # them out of the comparison rather than imputing FFT values or changing
    # labels; the receipt records the exact exclusion count.
    result = np.asarray([
        found[path] if path in found else np.full(len(names), np.nan, dtype=np.float32)
        for path in paths
    ], dtype=np.float32)
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez(cache, X=result, paths=np.asarray(paths, dtype=object),
             names=np.asarray(names, dtype=object), version="fft_sidecar_v2")
    return result, missing


def _metrics(y: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    return {
        "accuracy": round(float(100.0 * accuracy_score(y, pred)), 3),
        "macro_f1": round(float(100.0 * f1_score(y, pred, average="macro", zero_division=0)), 3),
        "loop_precision": round(float(100.0 * precision_score(y, pred, zero_division=0)), 3),
        "loop_recall": round(float(100.0 * recall_score(y, pred, zero_division=0)), 3),
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
    parser.add_argument("--periodicity-cache", type=Path,
                        default=SD / "loop_periodicity_feats.npz")
    parser.add_argument("--fft-cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--seeds", type=int, default=5)
    args = parser.parse_args()
    rows = _rows(args.labels)
    paths = [path for path, _ in rows]
    y = np.asarray([label for _, label in rows], dtype=np.int8)
    periodicity = _load_periodicity(args.periodicity_cache, paths)
    fft, fft_missing = _load_fft(paths, args.fft_cache, args.workers)
    valid = np.isfinite(periodicity).all(axis=1) & np.isfinite(fft).all(axis=1)
    if not np.all(valid):
        paths = [path for path, keep in zip(paths, valid) if keep]
        y = y[valid]
        periodicity = periodicity[valid]
        fft = fft[valid]
    if len(set(y.tolist())) < 2:
        raise ValueError("need both loop and one-shot rows after feature filtering")
    groups = np.asarray([os.path.dirname(os.path.dirname(path)) for path in paths], dtype=object)
    # periodicity columns: dur, sustain, ac_peak, ac_ratio, recur, onsets, tempo_conf
    arms = {
        "duration_sustain": periodicity[:, :2],
        "periodicity": periodicity[:, 2:],
        "duration_sustain_periodicity": periodicity,
        "duration_sustain_periodicity_fft": np.hstack([periodicity, fft[:, 2:]]),
    }
    raw = {name: [_score(features, y, groups, seed) for seed in range(args.seeds)]
           for name, features in arms.items()}
    results = {name: {
        "mean": {key: round(float(np.mean([item[key] for item in values])), 3)
                 for key in values[0]},
        "per_seed": values,
    } for name, values in raw.items()}
    receipt = {
        "record_type": "slo_periodicity_fft_loop_benchmark",
        "schema_version": "1.0.0",
        "method_version": "periodicity_fft_loop_v1",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "protocol": {"split": "StratifiedGroupKFold by two-level collection",
                     "folds": 5, "seeds": args.seeds,
                     "model": "standardized balanced logistic regression",
                     "excluded_feature": "splice (unstable head/tail normalizer)",
                     "promotion_gate_pp": 2.0},
        "inputs": {"labels": str(args.labels.resolve()), "rows": int(len(y)),
                   "loops": int(y.sum()), "one_shots": int((1 - y).sum()),
                   "collections": int(len(set(groups))),
                   "fft_rows": int(len(y)), "fft_excluded": int(len(fft_missing))},
        "features": {"periodicity": list(ALLOWED_FEATURES),
                     "fft_sidecar": list(_module("fft_names", "fft_sidecar_benchmark.py").FEATURE_NAMES)},
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
