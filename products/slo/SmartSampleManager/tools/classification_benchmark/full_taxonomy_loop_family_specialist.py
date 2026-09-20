#!/usr/bin/env python3
"""Evaluate a class-conditional loop-family specialist on the taxonomy corpus."""

from __future__ import annotations

import argparse
import importlib.util
import json
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
CONFIDENCE_THRESHOLDS = (0.50, 0.60, 0.70, 0.80, 0.90)
LOOP_TARGETS = ("Drum Loop", "Percussion Loop", "Foley Loop", "Hi-Hat Loop",
                "Bass Loop", "Synth Loop", "Vocal Loop", "Chord Loop", "Kick Loop",
                "Top Loop", "Loop")


def _module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SD / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def _metrics(y: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    return {
        "accuracy": round(float(100 * accuracy_score(y, pred)), 3),
        "macro_f1": round(float(100 * f1_score(y, pred, average="macro", zero_division=0)), 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=SD / "corpus_v2.npz")
    parser.add_argument("--physics-cache", type=Path, default=SD / "mw_features_v1.npz")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seeds", type=int, default=10)
    parser.add_argument("--splits", type=int, default=5)
    parser.add_argument("--min-class", type=int, default=10)
    parser.add_argument("--min-collections", type=int, default=5)
    args = parser.parse_args()

    full = _module("full_taxonomy_eval", "full_taxonomy_eval.py")
    incumbent = _module("incumbent_receipt", "incumbent_receipt.py")
    d = full.load(str(args.corpus))
    inventory = full.eligible_classes(d, args.min_class, args.min_collections)
    specialist_classes = [label for label in sorted(inventory)
                          if "Loop" in label and inventory[label]["examples"] >= args.min_class
                          and inventory[label]["collections"] >= args.min_collections]
    eligible_all = [label for label, item in inventory.items() if item["eligible"]]
    keep = np.isin(d["labels"], eligible_all)
    paths = [str(path) for path, use in zip(d["paths"], keep) if use]
    X = np.asarray(d["X"])[keep]
    y = np.asarray(d["labels"])[keep].astype(str)
    groups = np.asarray(d["vendor"])[keep]
    physics_z = np.load(args.physics_cache, allow_pickle=True)
    physics_paths = {os.path.abspath(str(path)) for path in physics_z["paths"]}
    aligned = np.asarray([path in physics_paths for path in paths], dtype=bool)
    paths = [path for path, use in zip(paths, aligned) if use]
    X, y, groups = X[aligned], y[aligned], groups[aligned]
    physics = _load_physics(args.physics_cache, paths)
    valid = np.isfinite(X).all(axis=1) & np.isfinite(physics).all(axis=1)
    X, y, groups, physics = X[valid], y[valid], groups[valid], physics[valid]
    loop_mask = np.isin(y, specialist_classes)
    if len(specialist_classes) < 2 or int(loop_mask.sum()) < 20:
        raise ValueError("not enough supported loop-family rows")

    raw = {str(threshold): [] for threshold in CONFIDENCE_THRESHOLDS}
    specialist_only = []
    incumbent_only = []
    override_stats = {str(threshold): [] for threshold in CONFIDENCE_THRESHOLDS}
    for seed in range(args.seeds):
        cv = StratifiedGroupKFold(args.splits, shuffle=True, random_state=seed)
        fold_specialist, fold_incumbent = [], []
        for train, test in cv.split(X, y, groups):
            if set(groups[train]) & set(groups[test]):
                raise AssertionError("collection leakage")
            pred_audio, conf_audio = incumbent.centroid_fit_predict(
                X[train], y[train], X[test], eligible_all)
            specialist = RandomForestClassifier(
                n_estimators=400, class_weight="balanced", min_samples_leaf=2,
                random_state=seed, n_jobs=1,
            )
            train_loop = loop_mask[train]
            specialist.fit(physics[train][train_loop], y[train][train_loop])
            loop_test = loop_mask[test]
            specialist_pred = specialist.predict(physics[test])
            specialist_prob = specialist.predict_proba(physics[test]).max(axis=1)
            # Report specialist quality only where the ground-truth class is
            # in its declared support; out-of-support loop families are not
            # silently converted into a supported class.
            if loop_test.any():
                fold_specialist.append(_metrics(y[test][loop_test], specialist_pred[loop_test]))
                fold_incumbent.append(_metrics(y[test][loop_test], pred_audio[loop_test]))
            for threshold in CONFIDENCE_THRESHOLDS:
                fused = pred_audio.copy()
                changed = (np.isin(pred_audio, specialist_classes)
                           & (specialist_prob >= threshold))
                fused[changed] = specialist_pred[changed]
                raw[str(threshold)].append(_metrics(y[test], fused))
                override_stats[str(threshold)].append({
                    "overrides": int(changed.sum()),
                    "override_rate": round(float(100 * changed.mean()), 3),
                    "override_precision": round(float(100 * (fused[changed] == y[test][changed]).mean()), 3)
                    if changed.any() else 0.0,
                })
        specialist_only.append({key: round(float(np.mean([row[key] for row in fold_specialist])), 3)
                                for key in fold_specialist[0]})
        incumbent_only.append({key: round(float(np.mean([row[key] for row in fold_incumbent])), 3)
                               for key in fold_incumbent[0]})

    results = {
        "incumbent_on_supported_loop_rows": {
            "mean": {key: round(float(np.mean([row[key] for row in incumbent_only])), 3)
                     for key in incumbent_only[0]},
            "per_seed": incumbent_only,
        },
        "specialist_only_on_supported_loop_rows": {
            "mean": {key: round(float(np.mean([row[key] for row in specialist_only])), 3)
                     for key in specialist_only[0]},
            "per_seed": specialist_only,
        },
    }
    for threshold in CONFIDENCE_THRESHOLDS:
        values = raw[str(threshold)]
        stats = override_stats[str(threshold)]
        results[f"conditional_fusion_{threshold:.2f}"] = {
            "mean": {key: round(float(np.mean([row[key] for row in values])), 3)
                     for key in values[0]},
            "per_seed": values,
            "override_mean": {key: round(float(np.mean([row[key] for row in stats])), 3)
                              for key in stats[0]},
        }

    receipt = {
        "record_type": "slo_full_taxonomy_loop_family_specialist",
        "schema_version": "1.0.0",
        "method_version": "full_taxonomy_loop_family_specialist_v1",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "protocol": {"split": "StratifiedGroupKFold by vendor/collection",
                     "folds": args.splits, "seeds": args.seeds,
                     "incumbent": "frozen Perch+CLAP nearest centroid",
                     "specialist": "balanced random forest on multi-window physics",
                     "confidence_thresholds": list(CONFIDENCE_THRESHOLDS),
                     "promotion_gate_pp": 2.0},
        "inputs": {"corpus": str(args.corpus.resolve()), "rows": int(len(y)),
                   "supported_loop_rows": int(loop_mask.sum()),
                   "classes": specialist_classes, "n_classes": len(eligible_all),
                   "collections": int(len(set(groups)))},
        "features": {"physics": list(PHYSICS_FEATURES)},
        "results": results,
        "decision": "research evidence only; no production weights, semantic labels, or rename actions",
        "safety": {"read_only": True, "source_audio_modified": False,
                   "production_model_changed": False, "rename_actions": False,
                   "auto_action_allowed": False},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({name: {"mean": value["mean"], "override_mean": value.get("override_mean")}
                      for name, value in results.items()}, indent=2))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
