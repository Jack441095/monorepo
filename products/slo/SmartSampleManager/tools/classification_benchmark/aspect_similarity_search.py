#!/usr/bin/env python3
"""Aspect-weighted, read-only similarity search over the SLO evidence index.

This mirrors the useful product pattern of exposing independent similarity
dimensions rather than pretending one global class score explains a sound.
It is retrieval only: it never assigns a class, edits metadata, or renames a
file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np


ASPECT_FEATURES = {
    "spectrum": ["spectral_centroid", "spectral_flatness", "spectral_flux",
                 "sub_energy_ratio", "low_energy_ratio", "mid_energy_ratio",
                 "high_energy_ratio", "spectral_purity", "partial_count"],
    "timbre": ["harmonicity", "inharmonicity", "harmonic_density",
               "noise_tonal_ratio", "spectral_purity", "partial_count",
               "beating_depth", "sideband_energy"],
    "pitch": ["fundamental_hz", "pitch_confidence", "pitch_drop_cents",
              "pitch_drop_rate_cps", "glide_within_100ms_cents",
              "beating_rate_hz"],
    "amplitude": ["transient_strength", "attack_ms", "decay_seconds",
                  "sustain_ratio", "attack_to_tail_ratio", "onset_density",
                  "rhythmic_autocorr"],
}


def _normalise(x: np.ndarray, mean: np.ndarray, scale: np.ndarray) -> np.ndarray:
    z = (x - mean) / np.maximum(scale, 1e-8)
    return z / (np.linalg.norm(z, axis=1, keepdims=True) + 1e-9)


def build_index(cache_path: Path) -> dict:
    z = np.load(cache_path, allow_pickle=True)
    names = [str(n) for n in z["names"]]
    position = {name: i for i, name in enumerate(names)}
    raw = np.asarray(z["F"], dtype=np.float32)
    index = {"paths": np.asarray([os.path.abspath(str(p)) for p in z["paths"]], dtype=object),
             "version": str(z["version"]), "cache_sha256": hashlib.sha256(cache_path.read_bytes()).hexdigest()}
    for aspect, feature_names in ASPECT_FEATURES.items():
        cols = [position[name] for name in feature_names]
        values = raw[:, cols]
        index[aspect] = _normalise(values, values.mean(0), values.std(0))
    return index


def search(index: dict, query_path: str, weights: dict[str, float], top_k: int = 20) -> list[dict]:
    query = os.path.abspath(query_path)
    paths = index["paths"]
    matches = np.flatnonzero(paths == query)
    if not len(matches):
        raise ValueError("query path is not present in the evidence index")
    qi = int(matches[0])
    scores = np.zeros(len(paths), dtype=np.float64)
    aspect_scores = {}
    active = {k: float(v) for k, v in weights.items() if float(v) > 0 and k in ASPECT_FEATURES}
    if not active:
        active = {"spectrum": 1.0, "timbre": 1.0, "pitch": 1.0, "amplitude": 1.0}
    total = sum(active.values())
    for aspect, weight in active.items():
        s = index[aspect] @ index[aspect][qi]
        aspect_scores[aspect] = s
        scores += (weight / total) * s
    scores[qi] = -np.inf
    order = np.argsort(-scores)[:top_k]
    return [{"path": str(paths[i]), "overall": float(scores[i]),
             **{aspect: float(aspect_scores[aspect][i]) for aspect in active}}
            for i in order]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--query-path", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--top-k", type=int, default=20)
    ap.add_argument("--spectrum", type=float, default=1.0)
    ap.add_argument("--timbre", type=float, default=1.0)
    ap.add_argument("--pitch", type=float, default=1.0)
    ap.add_argument("--amplitude", type=float, default=1.0)
    args = ap.parse_args()
    index = build_index(args.cache)
    weights = {"spectrum": args.spectrum, "timbre": args.timbre,
               "pitch": args.pitch, "amplitude": args.amplitude}
    rows = search(index, args.query_path, weights, args.top_k)
    payload = {"record_type": "slo_aspect_similarity_search", "schema_version": "1.0.0",
               "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
               "query_path": os.path.abspath(args.query_path), "weights": weights,
               "n_results": len(rows), "results": rows,
               "safety": {"read_only": True, "source_audio_modified": False,
                          "semantic_label_created": False, "rename_actions": False},
               "index": {"version": index["version"], "cache_sha256": index["cache_sha256"]}}
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"query_path": payload["query_path"], "n_results": len(rows),
                      "top_result": rows[0] if rows else None}, indent=2))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

