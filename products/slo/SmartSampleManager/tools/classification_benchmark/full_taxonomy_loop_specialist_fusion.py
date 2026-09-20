#!/usr/bin/env python3
"""Collection-held-out fusion of the frozen taxonomy incumbent and loop physics.

The incumbent remains the nearest-centroid Perch+CLAP model.  A separate binary
loop specialist is trained only inside each outer training fold from the
label-free multi-window physics cache.  It may change a compatible one-shot
family into its loop variant; all other predictions remain incumbent output.
This is a read-only research receipt, not a production policy mutation.
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
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


SD = Path(__file__).resolve().parent
PHYSICS_FEATURES = (
    "full_transient", "full_decay_s", "full_low_energy", "full_hf_density",
    "full_onset_rate", "third_onset_cv", "rhythm_ac_peak", "rhythm_ac_lag",
    "repetition_score", "silence_frac",
)
LOOP_TARGETS = ("Drum Loop", "Percussion Loop", "Foley Loop", "Hi-Hat Loop",
                "Bass Loop", "Synth Loop", "Vocal Loop", "Chord Loop", "Kick Loop",
                "Top Loop", "Loop")
FAMILY_LOOP = {
    "Kick": "Kick Loop", "Snare": "Snare Loop", "Hi-Hat": "Hi-Hat Loop",
    "Percussion": "Percussion Loop", "Foley": "Foley Loop", "Bass": "Bass Loop",
    "Synth": "Synth Loop", "Vocal": "Vocal Loop", "Chord": "Chord Loop",
}


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
        raise ValueError(f"physics cache missing {len(missing)} corpus paths")
    return np.asarray([[z["F"][by_path[path], index] for index in indices]
                       for path in paths], dtype=np.float32)


def _metrics(y: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    return {
        "accuracy": round(float(100 * accuracy_score(y, pred)), 3),
        "macro_f1": round(float(100 * f1_score(y, pred, average="macro", zero_division=0)), 3),
    }


def _override(pred: np.ndarray, loop_probability: np.ndarray,
              classes: list[str], threshold: float,
              incumbent_conf: np.ndarray | None = None,
              max_incumbent_conf: float | None = None) -> tuple[np.ndarray, np.ndarray]:
    output = pred.copy()
    changed = np.zeros(len(pred), dtype=bool)
    allowed = set(classes)
    for i, (label, probability) in enumerate(zip(pred, loop_probability)):
        if probability < threshold or label not in FAMILY_LOOP:
            continue
        target = FAMILY_LOOP[label]
        if target not in allowed:
            continue
        if (max_incumbent_conf is not None and incumbent_conf is not None
                and incumbent_conf[i] >= max_incumbent_conf):
            continue
        output[i] = target
        changed[i] = True
    return output, changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=SD / "corpus_v2.npz")
    parser.add_argument("--physics-cache", type=Path, default=SD / "mw_features_v1.npz")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seeds", type=int, default=10)
    parser.add_argument("--splits", type=int, default=5)
    parser.add_argument("--min-examples", type=int, default=5)
    parser.add_argument("--min-collections", type=int, default=5)
    args = parser.parse_args()

    full = _module("full_taxonomy_eval", "full_taxonomy_eval.py")
    incumbent = _module("incumbent_receipt", "incumbent_receipt.py")
    d = full.load(str(args.corpus))
    inventory = full.eligible_classes(d, args.min_examples, args.min_collections)
    classes = [label for label, item in inventory.items() if item["eligible"]]
    keep = np.isin(d["labels"], classes)
    paths = [str(path) for path, use in zip(d["paths"], keep) if use]
    X = np.asarray(d["X"])[keep]
    y = np.asarray(d["labels"])[keep].astype(str)
    groups = np.asarray(d["vendor"])[keep]
    physics_z = np.load(args.physics_cache, allow_pickle=True)
    physics_paths = {os.path.abspath(str(path)) for path in physics_z["paths"]}
    physics_keep = np.asarray([path in physics_paths for path in paths], dtype=bool)
    paths, X, y, groups = ([value[physics_keep] if isinstance(value, np.ndarray)
                             else [item for item, use in zip(value, physics_keep) if use]
                             for value in (paths, X, y, groups)])
    physics = _load_physics(args.physics_cache, paths)
    valid = np.isfinite(X).all(axis=1) & np.isfinite(physics).all(axis=1)
    X, y, groups, physics = X[valid], y[valid], groups[valid], physics[valid]
    loop_y = np.asarray(["Loop" in label for label in y], dtype=np.int8)
    if loop_y.sum() == 0 or loop_y.sum() == len(loop_y):
        raise ValueError("taxonomy corpus must contain both loop and non-loop classes")

    policy_specs = {
        "audio": (None, None),
        "loop_p070": (0.70, None),
        "loop_p080": (0.80, None),
        "loop_p090": (0.90, None),
        "loop_p080_audio_conf_lt_080": (0.80, 0.80),
    }
    raw = {name: [] for name in policy_specs}
    override_stats = {name: [] for name in policy_specs if name != "audio"}
    for seed in range(args.seeds):
        cv = StratifiedGroupKFold(args.splits, shuffle=True, random_state=seed)
        per_policy = {name: {"pred": np.empty(len(y), dtype=object),
                             "conf": np.zeros(len(y)), "changed": np.zeros(len(y), dtype=bool)}
                      for name in policy_specs}
        for train, test in cv.split(X, y, groups):
            if set(groups[train]) & set(groups[test]):
                raise AssertionError("collection leakage")
            pred, conf = incumbent.centroid_fit_predict(X[train], y[train], X[test], classes)
            specialist = make_pipeline(StandardScaler(), LogisticRegression(
                max_iter=3000, class_weight="balanced", random_state=seed))
            specialist.fit(physics[train], loop_y[train])
            loop_probability = specialist.predict_proba(physics[test])[:, 1]
            per_policy["audio"]["pred"][test] = pred
            per_policy["audio"]["conf"][test] = conf
            for name, (threshold, conf_cap) in policy_specs.items():
                if name == "audio":
                    continue
                fused, changed = _override(pred, loop_probability, classes, threshold,
                                           conf, conf_cap)
                per_policy[name]["pred"][test] = fused
                per_policy[name]["conf"][test] = np.where(
                    changed, np.minimum(conf, loop_probability), conf)
                per_policy[name]["changed"][test] = changed
        for name, state in per_policy.items():
            pred, conf = state["pred"], state["conf"]
            correct = pred == y
            result = _metrics(y, pred)
            result.update({
                "coverage_at_90_precision": round(float(incumbent.coverage_at(
                    conf, correct.astype(float), 0.90)), 3),
                "coverage_at_95_precision": round(float(incumbent.coverage_at(
                    conf, correct.astype(float), 0.95)), 3),
            })
            raw[name].append(result)
            if name != "audio":
                changed = state["changed"]
                override_stats[name].append({
                    "overrides": int(changed.sum()),
                    "override_rate": round(float(100 * changed.mean()), 3),
                    "override_precision": round(float(100 * correct[changed].mean()), 3)
                    if changed.any() else 0.0,
                })

    results = {}
    for name, values in raw.items():
        results[name] = {
            "mean": {key: round(float(np.mean([row[key] for row in values])), 3)
                     for key in values[0]},
            "per_seed": values,
        }
        if name != "audio":
            stats = override_stats[name]
            results[name]["override_mean"] = {
                key: round(float(np.mean([row[key] for row in stats])), 3)
                for key in stats[0]
            }

    receipt = {
        "record_type": "slo_full_taxonomy_loop_specialist_fusion",
        "schema_version": "1.0.0",
        "method_version": "full_taxonomy_loop_specialist_fusion_v1",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "protocol": {"split": "StratifiedGroupKFold by vendor/collection",
                     "folds": args.splits, "seeds": args.seeds,
                     "incumbent": "frozen Perch+CLAP nearest centroid",
                     "specialist": "standardized balanced logistic regression on multi-window physics",
                     "policies": policy_specs, "promotion_gate_pp": 2.0},
        "inputs": {"corpus": str(args.corpus.resolve()), "rows": int(len(y)),
                   "classes": classes, "n_classes": len(classes),
                   "loops": int(loop_y.sum()), "non_loops": int((1 - loop_y).sum()),
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
    print(json.dumps({name: {"mean": value["mean"],
                             "override_mean": value.get("override_mean")}
                      for name, value in results.items()}, indent=2))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
