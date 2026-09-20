#!/usr/bin/env python3
"""Selective operating-point test for the periodicity+FFT+physics specialist."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import time
from pathlib import Path

import numpy as np


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
    cached_paths = [os.path.abspath(str(path)) for path in z["paths"]]
    by_path = {path: i for i, path in enumerate(cached_paths)}
    cached_names = [str(name) for name in z["names"]]
    missing = [path for path in paths if path not in by_path]
    if missing:
        raise ValueError(f"physics cache missing {len(missing)} requested paths")
    indices = [cached_names.index(name) for name in names]
    return np.asarray([[z[matrix_key][by_path[path], index] for index in indices]
                       for path in paths], dtype=np.float32)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", type=Path, default=SD / "verified_drums.csv")
    parser.add_argument("--periodicity-cache", type=Path, default=SD / "loop_periodicity_feats.npz")
    parser.add_argument("--fft-cache", type=Path, required=True)
    parser.add_argument("--physics-cache", type=Path, default=SD / "mw_features_v1.npz")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seeds", type=int, default=10)
    parser.add_argument("--splits", type=int, default=5)
    parser.add_argument("--min-accepted", type=int, default=10)
    parser.add_argument("--wilson-z", type=float, default=1.96)
    args = parser.parse_args()

    benchmark = _module("periodicity_fft_loop_benchmark", "periodicity_fft_loop_benchmark.py")
    selective = _module("periodicity_fft_loop_selective_benchmark",
                        "periodicity_fft_loop_selective_benchmark.py")
    rows = benchmark._rows(args.labels)
    paths = [path for path, _ in rows]
    y = np.asarray([label for _, label in rows], dtype=np.int8)
    physics_z = np.load(args.physics_cache, allow_pickle=True)
    physics_paths = {os.path.abspath(str(path)) for path in physics_z["paths"]}
    keep = np.asarray([path in physics_paths for path in paths], dtype=bool)
    paths, y = [path for path, use in zip(paths, keep) if use], y[keep]
    periodicity = benchmark._load_periodicity(args.periodicity_cache, paths)
    fft, _ = benchmark._load_fft(paths, args.fft_cache, workers=4)
    physics = _load_named(args.physics_cache, paths, PHYSICS_FEATURES, "F")
    valid = (np.isfinite(periodicity).all(axis=1) & np.isfinite(fft).all(axis=1)
             & np.isfinite(physics).all(axis=1))
    y, periodicity, fft, physics = y[valid], periodicity[valid], fft[valid], physics[valid]
    paths = [path for path, use in zip(paths, valid) if use]
    groups = np.asarray([os.path.dirname(os.path.dirname(path)) for path in paths], dtype=object)

    arms = {
        "periodicity_fft": np.hstack([periodicity, fft[:, 2:]]),
        "periodicity_physics": np.hstack([periodicity, physics]),
        "periodicity_fft_physics": np.hstack([periodicity, fft[:, 2:], physics]),
    }
    results = {}
    for name, features in arms.items():
        per_seed = [selective._nested_arm(
            features, y, groups, seed, selective.TARGETS,
            args.min_accepted, args.splits, args.wilson_z)
                    for seed in range(args.seeds)]
        results[name] = {"per_seed": per_seed, "calibrated": {}, "fixed": {}}
        for target in selective.TARGETS:
            rows_for_target = [seed["calibrated"][str(target)]["mean"] for seed in per_seed]
            results[name]["calibrated"][str(target)] = {
                "mean": {key: round(float(np.mean([row[key] for row in rows_for_target])), 3)
                         for key in rows_for_target[0]}}
        for threshold in selective.FIXED_THRESHOLDS:
            rows_for_threshold = [seed["fixed"][str(threshold)]["mean"] for seed in per_seed]
            results[name]["fixed"][str(threshold)] = {
                "mean": {key: round(float(np.mean([row[key] for row in rows_for_threshold])), 3)
                         for key in rows_for_threshold[0]}}

    receipt = {
        "record_type": "slo_periodicity_fft_physics_selective_benchmark",
        "schema_version": "1.0.0",
        "method_version": "periodicity_fft_physics_selective_v1",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "protocol": {"outer_split": "StratifiedGroupKFold by two-level collection",
                     "inner_calibration": "three-fold StratifiedGroupKFold by collection",
                     "folds": args.splits, "seeds": args.seeds,
                     "minimum_inner_accepted": args.min_accepted,
                     "inner_precision_criterion": "Wilson lower bound",
                     "wilson_z": args.wilson_z,
                     "fixed_thresholds": list(selective.FIXED_THRESHOLDS),
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
    print(json.dumps({name: {"calibrated": value["calibrated"], "fixed": value["fixed"]}
                      for name, value in results.items()}, indent=2))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
