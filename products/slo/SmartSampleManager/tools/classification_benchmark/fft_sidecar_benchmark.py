#!/usr/bin/env python3
"""Research-only grouped ablation for the production FFT evidence sidecar.

The extractor mirrors the shipped native protocol (2048-point Hann, 512 hop,
150 Hz/2 kHz band edges) and compares a duration+sustain baseline with the
sidecar alone and their fusion.  It never writes source audio or model
weights; the JSON receipt is evidence for deciding whether a future
specialist is worth training.
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
import soundfile as sf
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression


FFT_SIZE = 2048
HOP = 512
FEATURE_NAMES = [
    "duration_s", "sustain_ratio", "low_band_ratio", "mid_band_ratio",
    "high_band_ratio", "flux_mean", "flux_std", "flux_peak_rate",
]


def extract(path: str) -> np.ndarray | None:
    try:
        y, sr = sf.read(path, dtype="float32", always_2d=False)
        if y.ndim > 1:
            y = y.mean(axis=1)
        if y.size < FFT_SIZE:
            return None
        duration = float(y.size / sr)
        # Keep a bounded analysis view so an unusually long recording cannot
        # dominate a grouped fold; duration itself remains full-file.
        y = y[: min(y.size, int(sr * 30.0))]
        third = max(1, y.size // 3)
        head = float(np.mean(y[:third] ** 2))
        tail = float(np.mean(y[-third:] ** 2))
        sustain = min(tail / max(head, 1e-12), 2.0)

        window = np.hanning(FFT_SIZE).astype(np.float32)
        freqs = np.fft.rfftfreq(FFT_SIZE, 1.0 / sr)
        low = freqs < 150.0
        mid = (freqs >= 150.0) & (freqs < 2000.0)
        high = freqs >= 2000.0
        ratios, flux = [], []
        previous = None
        previous_sum = 0.0
        for start in range(0, y.size - FFT_SIZE + 1, HOP):
            mag = np.abs(np.fft.rfft(y[start:start + FFT_SIZE] * window))
            total = float(np.sum(mag))
            if total <= 1e-9:
                # Do not treat a silent frame as a valid reference for
                # gain-normalised flux; the next non-silent frame would
                # otherwise divide by a zero baseline.
                previous = None
                previous_sum = 0.0
                continue
            energy = mag * mag
            band_total = float(np.sum(energy))
            ratios.append((float(np.sum(energy[low]) / band_total),
                           float(np.sum(energy[mid]) / band_total),
                           float(np.sum(energy[high]) / band_total)))
            if previous is not None and previous_sum > 1e-9:
                positive = np.maximum(mag - previous, 0.0)
                flux.append(float(min(np.sum(positive) / max(previous_sum, 1e-9), 100.0)))
            previous = mag
            previous_sum = total
        if not ratios:
            return None
        ratios = np.asarray(ratios, dtype=np.float64)
        flux = np.asarray(flux, dtype=np.float64)
        flux_mean = float(flux.mean()) if flux.size else 0.0
        flux_std = float(flux.std()) if flux.size else 0.0
        peak_rate = 0.0
        if flux.size >= 3:
            threshold = flux_mean + flux_std
            peaks = ((flux[1:-1] > threshold)
                     & (flux[1:-1] >= flux[:-2])
                     & (flux[1:-1] >= flux[2:])).sum()
            peak_rate = float(peaks / max(y.size / sr, 1e-9))
        return np.asarray([duration, sustain, *ratios.mean(axis=0),
                           flux_mean, flux_std, peak_rate], dtype=np.float32)
    except Exception:
        return None


def _extract_one(path: str):
    return path, extract(path)


def _load_rows(csv_path: Path):
    rows = []
    for row in csv.DictReader(csv_path.open(newline="")):
        label = row["label"]
        if label in {"__skip__", "Misc/Review", "Other/none"}:
            continue
        path = os.path.abspath(row["path"])
        if os.path.exists(path):
            rows.append((path, int("Loop" in label)))
    return rows


def _score(x: np.ndarray, y: np.ndarray, groups: np.ndarray, seed: int, model):
    pred = np.empty(y.size, dtype=np.int8)
    cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=seed)
    for train, test in cv.split(x, y, groups):
        model.fit(x[train], y[train])
        pred[test] = model.predict(x[test])
    return {
        "accuracy": round(float(100.0 * accuracy_score(y, pred)), 3),
        "macro_f1": round(float(100.0 * f1_score(y, pred, zero_division=0)), 3),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", type=Path,
                    default=Path(__file__).with_name("verified_drums.csv"))
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seeds", type=int, default=5)
    args = ap.parse_args()

    rows = _load_rows(args.labels)
    cached = {}
    if args.cache.exists():
        z = np.load(args.cache, allow_pickle=True)
        if list(z["names"].astype(str)) == FEATURE_NAMES:
            cached = {os.path.abspath(str(p)): z["X"][i]
                      for i, p in enumerate(z["paths"])}
    todo = [path for path, _ in rows if path not in cached]
    if todo:
        with mp.Pool(max(1, args.workers)) as pool:
            for n, (path, value) in enumerate(pool.imap_unordered(_extract_one, todo), 1):
                if value is not None:
                    cached[path] = value
                if n % 100 == 0:
                    print(f"extracted {n}/{len(todo)}", flush=True)
    rows = [(p, y) for p, y in rows if p in cached]
    paths = np.asarray([p for p, _ in rows], dtype=object)
    y = np.asarray([v for _, v in rows], dtype=np.int8)
    x = np.asarray([cached[p] for p in paths], dtype=np.float32)
    groups = np.asarray([os.path.dirname(os.path.dirname(p)) for p in paths], dtype=object)
    args.cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez(args.cache, X=x, paths=paths, names=np.asarray(FEATURE_NAMES, dtype=object),
             version="fft_sidecar_v1")

    arms = {
        "duration_sustain": x[:, :2],
        "fft_sidecar": x[:, 2:],
        "duration_sustain_plus_fft": x,
    }
    results = {name: [] for name in arms}
    for seed in range(args.seeds):
        for name, features in arms.items():
            # A regularized linear probe is deliberately used as the primary
            # result: it exposes whether the sidecar is independently useful,
            # rather than hiding gains in a high-capacity tree.
            model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, random_state=seed))
            results[name].append(_score(features, y, groups, seed, model))
    summary = {
        name: {
            "accuracy": round(float(np.mean([r["accuracy"] for r in values])), 3),
            "macro_f1": round(float(np.mean([r["macro_f1"] for r in values])), 3),
            "per_seed": values,
        }
        for name, values in results.items()
    }
    receipt = {
        "record_type": "slo_fft_sidecar_benchmark",
        "schema_version": "1.0.0",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "protocol": {"split": "StratifiedGroupKFold by two-level collection",
                     "seeds": args.seeds, "folds": 5,
                     "fft_size": FFT_SIZE, "hop": HOP,
                     "band_edges_hz": [150.0, 2000.0],
                     "analysis_view_seconds": 30.0,
                     "promotion_gate_pp": 2.0},
        "inputs": {"labels": str(args.labels.resolve()), "rows": int(len(y)),
                   "loops": int(y.sum()), "one_shots": int((1 - y).sum()),
                   "collections": int(len(set(groups)))},
        "features": FEATURE_NAMES,
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
