#!/usr/bin/env python3
"""Nested-calibrated loop/one-shot routing with periodicity and FFT evidence.

This is a research-only operating-point test.  For each outer collection-held
out fold, a threshold is selected on inner out-of-fold predictions to meet a
target precision, then applied once to the untouched outer fold.  Samples below
the threshold are explicitly deferred to review.  No labels, weights, or audio
files are modified.
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
from sklearn.metrics import f1_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


SD = Path(__file__).resolve().parent
TARGETS = (0.90, 0.95)
FIXED_THRESHOLDS = (0.90, 0.95, 0.98, 0.99)


def _module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SD / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _wilson_lower(successes: int, total: int, z: float = 1.96) -> float:
    if total <= 0:
        return 0.0
    p = successes / total
    denominator = 1.0 + z * z / total
    centre = p + z * z / (2.0 * total)
    margin = z * np.sqrt((p * (1.0 - p) + z * z / (4.0 * total)) / total)
    return float(max(0.0, (centre - margin) / denominator))


def _select_threshold(confidence: np.ndarray, correct: np.ndarray,
                      target: float, min_accepted: int,
                      wilson_z: float = 1.96) -> float | None:
    """Choose the lowest score whose Wilson lower bound meets target precision."""
    if len(confidence) == 0:
        return None
    candidates = np.unique(np.asarray(confidence, dtype=np.float64))
    best: float | None = None
    for threshold in np.sort(candidates):
        accepted = confidence >= threshold
        n = int(accepted.sum())
        if n < min_accepted:
            continue
        if _wilson_lower(int(correct[accepted].sum()), n, wilson_z) >= target:
            best = float(threshold)
            break
    return best


def _selective_metrics(y: np.ndarray, pred: np.ndarray, confidence: np.ndarray,
                       threshold: float | None, target: float) -> dict[str, float | int | None]:
    accepted = np.zeros(len(y), dtype=bool) if threshold is None else confidence >= threshold
    n = int(accepted.sum())
    correct = int(np.sum(accepted & (pred == y)))
    return {
        "target_precision": target,
        "threshold": None if threshold is None else round(float(threshold), 6),
        "accepted": n,
        "deferred": int(len(y) - n),
        "coverage": round(float(100.0 * n / max(len(y), 1)), 3),
        "accepted_precision": round(float(100.0 * correct / max(n, 1)), 3),
        "accepted_macro_f1": round(float(100.0 * f1_score(
            y[accepted], pred[accepted], average="macro", zero_division=0)), 3)
        if n else 0.0,
    }


def _fit():
    return make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=3000, class_weight="balanced"),
    )


def _nested_arm(X: np.ndarray, y: np.ndarray, groups: np.ndarray,
                seed: int, targets: tuple[float, ...], min_accepted: int,
                splits: int, wilson_z: float) -> dict[str, object]:
    outer = StratifiedGroupKFold(n_splits=splits, shuffle=True, random_state=seed)
    by_target: dict[float, list[dict[str, object]]] = {target: [] for target in targets}
    by_fixed: dict[float, list[dict[str, object]]] = {
        threshold: [] for threshold in FIXED_THRESHOLDS
    }
    for train, test in outer.split(X, y, groups):
        # Inner OOF predictions are used only to choose the confidence gate.
        inner = StratifiedGroupKFold(3, shuffle=True, random_state=seed + 1000)
        inner_conf = np.zeros(len(train), dtype=np.float64)
        inner_correct = np.zeros(len(train), dtype=bool)
        for itr, iva in inner.split(X[train], y[train], groups[train]):
            if set(groups[train][itr]) & set(groups[train][iva]):
                raise AssertionError("inner collection leakage")
            model = _fit()
            model.fit(X[train][itr], y[train][itr])
            prob = model.predict_proba(X[train][iva])
            pred = model.classes_[np.argmax(prob, axis=1)]
            inner_conf[iva] = np.max(prob, axis=1)
            inner_correct[iva] = pred == y[train][iva]

        model = _fit()
        model.fit(X[train], y[train])
        prob = model.predict_proba(X[test])
        pred = model.classes_[np.argmax(prob, axis=1)]
        confidence = np.max(prob, axis=1)
        for target in targets:
            threshold = _select_threshold(inner_conf, inner_correct, target,
                                          min_accepted, wilson_z)
            by_target[target].append(_selective_metrics(
                y[test], pred, confidence, threshold, target))
        for threshold in FIXED_THRESHOLDS:
            by_fixed[threshold].append(_selective_metrics(
                y[test], pred, confidence, threshold, threshold))

    def summarize(values: dict[float, list[dict[str, object]]]) -> dict[str, object]:
        results: dict[str, object] = {}
        for target, folds in values.items():
            numeric = ("accepted", "deferred", "coverage", "accepted_precision", "accepted_macro_f1")
            results[str(target)] = {
                "mean": {key: round(float(np.mean([float(row[key]) for row in folds])), 3)
                         for key in numeric},
                "folds": folds,
            }
        return results

    return {"calibrated": summarize(by_target), "fixed": summarize(by_fixed)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", type=Path, default=SD / "verified_drums.csv")
    parser.add_argument("--periodicity-cache", type=Path,
                        default=SD / "loop_periodicity_feats.npz")
    parser.add_argument("--fft-cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--splits", type=int, default=5)
    parser.add_argument("--min-accepted", type=int, default=10)
    parser.add_argument("--wilson-z", type=float, default=1.96,
                        help="confidence multiplier for the inner Wilson lower bound")
    args = parser.parse_args()

    benchmark = _module("periodicity_fft_loop_benchmark", "periodicity_fft_loop_benchmark.py")
    rows = benchmark._rows(args.labels)
    paths = [path for path, _ in rows]
    y = np.asarray([label for _, label in rows], dtype=np.int8)
    periodicity = benchmark._load_periodicity(args.periodicity_cache, paths)
    fft, fft_missing = benchmark._load_fft(paths, args.fft_cache, workers=4)
    valid = np.isfinite(periodicity).all(axis=1) & np.isfinite(fft).all(axis=1)
    fft_excluded = int((~valid).sum())
    paths = [path for path, keep in zip(paths, valid) if keep]
    y = y[valid]
    periodicity = periodicity[valid]
    fft = fft[valid]
    groups = np.asarray([os.path.dirname(os.path.dirname(path)) for path in paths], dtype=object)
    if len(set(y.tolist())) < 2:
        raise ValueError("need both loop and one-shot rows after feature filtering")

    arms = {
        "duration_sustain_periodicity": periodicity,
        "duration_sustain_periodicity_fft": np.hstack([periodicity, fft[:, 2:]]),
    }
    results: dict[str, dict[str, object]] = {}
    for name, features in arms.items():
        per_seed = [_nested_arm(features, y, groups, seed, TARGETS,
                                args.min_accepted, args.splits, args.wilson_z)
                    for seed in range(args.seeds)]
        results[name] = {"per_seed": per_seed}
        for target in TARGETS:
            rows_for_target = [seed["calibrated"][str(target)]["mean"] for seed in per_seed]
            results[name].setdefault("calibrated", {})[str(target)] = {
                "mean": {key: round(float(np.mean([row[key] for row in rows_for_target])), 3)
                         for key in rows_for_target[0]},
            }
        for threshold in FIXED_THRESHOLDS:
            rows_for_threshold = [seed["fixed"][str(threshold)]["mean"] for seed in per_seed]
            results[name].setdefault("fixed", {})[str(threshold)] = {
                "mean": {key: round(float(np.mean([row[key] for row in rows_for_threshold])), 3)
                         for key in rows_for_threshold[0]},
            }

    receipt = {
        "record_type": "slo_periodicity_fft_loop_selective_benchmark",
        "schema_version": "1.0.0",
        "method_version": "periodicity_fft_loop_selective_v1",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "protocol": {
            "outer_split": "StratifiedGroupKFold by two-level collection",
            "inner_calibration": "three-fold StratifiedGroupKFold by collection",
            "folds": args.splits, "seeds": args.seeds,
            "model": "standardized balanced logistic regression",
            "targets": list(TARGETS), "fixed_thresholds": list(FIXED_THRESHOLDS),
            "minimum_inner_accepted": args.min_accepted,
            "inner_precision_criterion": "Wilson lower bound",
            "wilson_z": args.wilson_z,
            "promotion_gate_pp": 2.0,
        },
        "inputs": {
            "labels": str(args.labels.resolve()), "rows": int(len(y)),
            "loops": int(y.sum()), "one_shots": int((1 - y).sum()),
            "collections": int(len(set(groups))),
            "fft_excluded": fft_excluded,
        },
        "features": {
            "periodicity": ["dur", "sustain", "ac_peak", "ac_ratio", "recur", "onsets", "tempo_conf"],
            "fft_sidecar": list(_module("fft_names", "fft_sidecar_benchmark.py").FEATURE_NAMES),
        },
        "results": results,
        "routing": {
            "accepted_route": "auto_candidate_only_after_threshold",
            "deferred_route": "human_review_or_downstream_evidence",
            "semantic_labels_created": False,
        },
        "decision": "research evidence only; no production weights or rename actions",
        "safety": {"read_only": True, "source_audio_modified": False,
                   "production_model_changed": False, "rename_actions": False},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({name: {"calibrated": value["calibrated"], "fixed": value["fixed"]}
                      for name, value in results.items()}, indent=2))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
