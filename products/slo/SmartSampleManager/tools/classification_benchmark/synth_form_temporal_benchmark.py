#!/usr/bin/env python3
"""Tune a narrowly scoped temporal/form evidence block for synth samples."""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import numpy as np


FEATURE_SETS = {
    "temporal": ["attack_ms", "decay_seconds", "sustain_ratio",
                 "attack_to_tail_ratio", "onset_density", "transient_strength",
                 "rhythmic_autocorr"],
    "pitch_and_shape": ["fundamental_hz", "pitch_confidence", "harmonicity",
                         "spectral_purity", "partial_count", "beating_rate_hz",
                         "beating_depth"],
    "temporal_plus_shape": ["attack_ms", "decay_seconds", "sustain_ratio",
                            "attack_to_tail_ratio", "onset_density",
                            "transient_strength", "rhythmic_autocorr",
                            "fundamental_hz", "pitch_confidence", "harmonicity",
                            "spectral_purity", "partial_count", "beating_rate_hz",
                            "beating_depth"],
}


def predict(xtr, ytr, xte, classes):
    mean = xtr.mean(0)
    scale = xtr.std(0)
    scale[scale < 1e-6] = 1.0
    a = (xtr - mean) / scale
    b = (xte - mean) / scale
    a /= np.linalg.norm(a, axis=1, keepdims=True) + 1e-9
    b /= np.linalg.norm(b, axis=1, keepdims=True) + 1e-9
    c = np.asarray([a[ytr == cls].mean(0) for cls in classes])
    c /= np.linalg.norm(c, axis=1, keepdims=True) + 1e-9
    return np.asarray(classes, dtype=object)[(b @ c.T).argmax(1)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--waveform-cache", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--splits", type=int, default=5)
    args = ap.parse_args()
    from sklearn.model_selection import StratifiedGroupKFold

    z = np.load(args.corpus, allow_pickle=True)
    by_path = {os.path.abspath(str(p)): i for i, p in enumerate(z["paths"])}
    rows = json.loads(args.manifest.read_text(encoding="utf-8"))["rows"]
    paths = [os.path.abspath(str(r["path"])) for r in rows]
    indices = [by_path[p] for p in paths]
    emb = np.asarray(z["emb"], dtype=np.float32)[indices]
    labels = np.asarray([str(r["label"]) for r in rows], dtype=object)
    groups = np.asarray([str(r["vendor"]) for r in rows], dtype=object)
    target = np.isin(labels, ["Synth Loop", "Synth One-Shot"])
    wcache = np.load(args.waveform_cache, allow_pickle=True)
    names = [str(n) for n in wcache["names"]]
    position = {n: i for i, n in enumerate(names)}
    wf = {os.path.abspath(str(p)): wcache["F"][i]
          for i, p in enumerate(wcache["paths"])}
    target &= np.asarray([p in wf for p in paths])
    x = emb[target]
    w = np.asarray([wf[p] for p in np.asarray(paths)[target]], dtype=np.float32)
    y = labels[target]
    g = groups[target]
    classes = ["Synth Loop", "Synth One-Shot"]
    weights = [0.10, 0.25, 0.50, 1.0, 2.0, 4.0]
    results = {}
    for set_name, feature_names in FEATURE_SETS.items():
        idx = [position[n] for n in feature_names]
        block = w[:, idx]
        for weight in weights:
            accs = []
            for seed in range(args.seeds):
                pred = np.empty(len(y), dtype=object)
                cv = StratifiedGroupKFold(args.splits, shuffle=True, random_state=seed)
                for tr, te in cv.split(x, y, groups=g):
                    if set(g[tr]) & set(g[te]):
                        raise AssertionError("collection leakage")
                    pred[te] = predict(np.hstack([x[tr], weight * block[tr]]), y[tr],
                                       np.hstack([x[te], weight * block[te]]), classes)
                accs.append(100.0 * float((pred == y).mean()))
            key = f"{set_name}_weight_{weight:g}"
            results[key] = {"feature_names": feature_names, "weight": weight,
                            "accuracy": round(float(np.mean(accs)), 3),
                            "accuracy_sd": round(float(np.std(accs)), 3),
                            "per_seed": [round(float(v), 3) for v in accs]}
            print(key, results[key], flush=True)
    base = max(results.values(), key=lambda r: r["accuracy"])
    payload = {
        "record_type": "slo_synth_form_temporal_benchmark",
        "schema_version": "1.0.0", "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "protocol": {"split": "StratifiedGroupKFold by vendor/collection",
                     "seeds": args.seeds, "splits": args.splits,
                     "pair": classes, "decision_gate_pp": 2.0},
        "inventory": {"n_rows": int(len(y)), "n_collections": int(len(set(g))),
                      "counts": {c: int((y == c).sum()) for c in classes}},
        "results": results,
        "best_temporal_arm": base,
        "decision": "research evidence only; no production policy or rename actions",
        "safety": {"read_only": True, "source_audio_modified": False,
                   "production_model_changed": False, "rename_actions": False},
    }
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

