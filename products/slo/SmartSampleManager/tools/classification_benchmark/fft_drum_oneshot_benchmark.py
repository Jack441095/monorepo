#!/usr/bin/env python3
"""Collection-grouped FFT ablation for drum one-shot mechanisms."""
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
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import StratifiedGroupKFold

import drum_detector_features as drum
from fft_sidecar_benchmark import FEATURE_NAMES as FFT_NAMES
from fft_sidecar_benchmark import extract as extract_fft

ALLOWED = {"Kick", "Snare", "Clap", "Hi-Hat", "Crash", "Percussion", "Rimshot"}


def _extract_one(path: str):
    return path, extract_fft(path), drum.extract(path)


def _score(x, y, groups, seed):
    pred = np.empty(y.size, dtype=object)
    cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=seed)
    for train, test in cv.split(x, y, groups):
        model = RandomForestClassifier(n_estimators=300, class_weight="balanced",
                                       min_samples_leaf=2, random_state=seed, n_jobs=1)
        model.fit(x[train], y[train])
        pred[test] = model.predict(x[test])
    return {"accuracy": round(float(100 * accuracy_score(y, pred)), 3),
            "macro_f1": round(float(100 * f1_score(y, pred, average="macro",
                                                   zero_division=0)), 3)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", type=Path,
                    default=Path(__file__).with_name("verified_drums.csv"))
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seeds", type=int, default=5)
    args = ap.parse_args()

    rows = []
    for row in csv.DictReader(args.labels.open(newline="")):
        if row["label"] in ALLOWED:
            path = os.path.abspath(row["path"])
            if os.path.exists(path):
                rows.append((path, row["label"]))

    cached = {}
    if args.cache.exists():
        z = np.load(args.cache, allow_pickle=True)
        if list(z["fft_names"].astype(str)) == FFT_NAMES:
            cached = {os.path.abspath(str(p)): (z["fft"][i], z["drum"][i])
                      for i, p in enumerate(z["paths"])}
    todo = [p for p, _ in rows if p not in cached]
    if todo:
        with mp.Pool(max(1, args.workers)) as pool:
            for n, (path, fft, drum_features) in enumerate(pool.imap_unordered(_extract_one, todo), 1):
                if fft is not None and drum_features is not None:
                    cached[path] = (fft, drum_features)
                if n % 100 == 0:
                    print(f"extracted {n}/{len(todo)}", flush=True)

    rows = [(p, label) for p, label in rows if p in cached]
    inventory = {}
    for label in sorted({label for _, label in rows}):
        paths = [p for p, y in rows if y == label]
        inventory[label] = {"rows": len(paths),
                            "collections": len({os.path.dirname(os.path.dirname(p)) for p in paths})}
    viable = [label for label, stats in inventory.items()
              if stats["rows"] >= 10 and stats["collections"] >= 5]
    rows = [(p, label) for p, label in rows if label in viable]
    paths = np.asarray([p for p, _ in rows], dtype=object)
    y = np.asarray([label for _, label in rows], dtype=object)
    fft = np.asarray([cached[p][0] for p in paths], dtype=np.float32)
    drum_features = np.asarray([cached[p][1] for p in paths], dtype=np.float32)
    groups = np.asarray([os.path.dirname(os.path.dirname(p)) for p in paths], dtype=object)
    args.cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez(args.cache, paths=paths, fft=fft, drum=drum_features,
             fft_names=np.asarray(FFT_NAMES, dtype=object))

    arms = {"drum_attack": drum_features, "fft_sidecar": fft,
            "drum_attack_plus_fft": np.hstack([drum_features, fft])}
    per_seed = {name: [_score(features, y, groups, seed)
                       for seed in range(args.seeds)]
                for name, features in arms.items()}
    summary = {
        name: {"accuracy": round(float(np.mean([r["accuracy"] for r in values])), 3),
               "macro_f1": round(float(np.mean([r["macro_f1"] for r in values])), 3),
               "per_seed": values}
        for name, values in per_seed.items()}
    receipt = {
        "record_type": "slo_fft_drum_oneshot_benchmark",
        "schema_version": "1.0.0",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "protocol": {"split": "StratifiedGroupKFold by two-level collection",
                     "seeds": args.seeds, "folds": 5,
                     "model": "balanced RF, 300 trees, min_samples_leaf=2",
                     "minimum_examples": 10, "minimum_collections": 5,
                     "promotion_gate_pp": 2.0},
        "inputs": {"labels": str(args.labels.resolve()), "rows": int(len(y)),
                   "collections": int(len(set(groups))), "viable_classes": viable,
                   "inventory": inventory},
        "features": {"fft_sidecar": FFT_NAMES, "drum_attack_dimensions": int(drum_features.shape[1])},
        "results": summary,
        "decision": "research evidence only; no production weights or rename actions",
        "safety": {"read_only": True, "source_audio_modified": False,
                   "production_model_changed": False, "rename_actions": False},
    }
    args.out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
