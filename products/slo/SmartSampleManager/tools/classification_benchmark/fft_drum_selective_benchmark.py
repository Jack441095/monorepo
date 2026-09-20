#!/usr/bin/env python3
"""Measure FFT sidecar value at selective operating points.

The ordinary ablation showed little global accuracy gain.  This follow-up
tests the product-relevant question: can FFT features improve precision when
the classifier is allowed to abstain?  It uses collection-held-out folds and
reports precision/coverage at fixed confidence thresholds for the existing
attack feature set versus attack+FFT fusion.  No weights or source audio are
modified.
"""

from __future__ import annotations

import argparse
import csv
import json
import multiprocessing as mp
import os
import time
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score
from sklearn.model_selection import StratifiedGroupKFold

import drum_detector_features as drum
from fft_sidecar_benchmark import FEATURE_NAMES as FFT_NAMES
from fft_sidecar_benchmark import extract as extract_fft


ALLOWED = {"Kick", "Snare", "Clap", "Hi-Hat", "Crash", "Percussion", "Rimshot"}
THRESHOLDS = (0.60, 0.70, 0.80, 0.90)


def selective_metrics(y: np.ndarray, pred: np.ndarray, confidence: np.ndarray,
                      threshold: float) -> dict[str, float | int]:
    accepted = confidence >= threshold
    n = int(accepted.sum())
    if n == 0:
        return {"threshold": threshold, "accepted": 0, "coverage": 0.0,
                "precision": 0.0, "macro_f1_accepted": 0.0}
    truth = y[accepted]
    guesses = pred[accepted]
    return {
        "threshold": threshold,
        "accepted": n,
        "coverage": round(float(100.0 * n / len(y)), 3),
        "precision": round(float(100.0 * np.mean(truth == guesses)), 3),
        "macro_f1_accepted": round(float(100.0 * f1_score(
            truth, guesses, average="macro", zero_division=0)), 3),
    }


def _extract_one(path: str):
    return path, extract_fft(path), drum.extract(path)


def _read_labels(path: Path) -> list[tuple[str, str]]:
    rows = []
    for row in csv.DictReader(path.open(newline="")):
        if row.get("label") in ALLOWED:
            audio = os.path.abspath(row["path"])
            if os.path.exists(audio):
                rows.append((audio, row["label"]))
    return rows


def _evaluate(features: np.ndarray, y: np.ndarray, groups: np.ndarray,
              seeds: int) -> dict[str, list[dict[str, float | int]]]:
    all_metrics: dict[str, list[dict[str, float | int]]] = {str(t): [] for t in THRESHOLDS}
    for seed in range(seeds):
        pred = np.empty(len(y), dtype=object)
        confidence = np.zeros(len(y), dtype=np.float32)
        cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=seed)
        for train, test in cv.split(features, y, groups):
            model = RandomForestClassifier(
                n_estimators=300, class_weight="balanced", min_samples_leaf=2,
                random_state=seed, n_jobs=1,
            )
            model.fit(features[train], y[train])
            pred[test] = model.predict(features[test])
            confidence[test] = model.predict_proba(features[test]).max(axis=1)
        for threshold in THRESHOLDS:
            all_metrics[str(threshold)].append(
                selective_metrics(y, pred, confidence, threshold))
    return all_metrics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", type=Path,
                        default=Path(__file__).with_name("verified_drums.csv"))
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--seeds", type=int, default=5)
    args = parser.parse_args()

    rows = _read_labels(args.labels)
    cached: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    if args.cache.exists():
        z = np.load(args.cache, allow_pickle=True)
        if list(z["fft_names"].astype(str)) == list(FFT_NAMES):
            cached = {os.path.abspath(str(path)): (z["fft"][i], z["drum"][i])
                      for i, path in enumerate(z["paths"])}
    todo = [path for path, _ in rows if path not in cached]
    if todo:
        with mp.Pool(max(1, args.workers)) as pool:
            for path, fft, attack in pool.imap_unordered(_extract_one, todo):
                if fft is not None and attack is not None:
                    cached[path] = (fft, attack)
    rows = [(path, label) for path, label in rows if path in cached]
    paths = np.asarray([path for path, _ in rows], dtype=object)
    y = np.asarray([label for _, label in rows], dtype=object)
    fft = np.asarray([cached[path][0] for path in paths], dtype=np.float32)
    attack = np.asarray([cached[path][1] for path in paths], dtype=np.float32)
    groups = np.asarray([os.path.dirname(os.path.dirname(path)) for path in paths], dtype=object)
    args.cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez(args.cache, paths=paths, fft=fft, drum=attack,
             fft_names=np.asarray(FFT_NAMES, dtype=object))

    arms = {"drum_attack": attack, "drum_attack_plus_fft": np.hstack([attack, fft])}
    raw = {name: _evaluate(features, y, groups, args.seeds)
           for name, features in arms.items()}
    results = {}
    for name, by_threshold in raw.items():
        results[name] = {}
        for threshold, values in by_threshold.items():
            results[name][threshold] = {
                "mean": {key: round(float(np.mean([v[key] for v in values])), 3)
                          for key in ("accepted", "coverage", "precision", "macro_f1_accepted")},
                "per_seed": values,
            }
    receipt = {
        "record_type": "slo_fft_drum_selective_benchmark",
        "schema_version": "1.0.0",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "protocol": {"split": "StratifiedGroupKFold by two-level collection",
                     "folds": 5, "seeds": args.seeds,
                     "model": "balanced RF, 300 trees, min_samples_leaf=2",
                     "thresholds": list(THRESHOLDS), "promotion_gate_pp": 2.0},
        "inputs": {"labels": str(args.labels.resolve()), "rows": int(len(y)),
                   "collections": int(len(set(groups))),
                   "classes": sorted(set(y.tolist()))},
        "features": {"fft_sidecar": list(FFT_NAMES),
                     "drum_attack_dimensions": int(attack.shape[1])},
        "results": results,
        "decision": "research evidence only; no production weights or rename actions",
        "safety": {"read_only": True, "source_audio_modified": False,
                   "production_model_changed": False, "rename_actions": False},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({name: {t: v["mean"] for t, v in values.items()}
                      for name, values in results.items()}, indent=2))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
