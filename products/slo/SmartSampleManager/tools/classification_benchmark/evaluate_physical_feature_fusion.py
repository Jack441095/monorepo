#!/usr/bin/env python3
"""Evaluate physical waveform features as a controlled fusion arm.

This is a research-only experiment.  It reads the corrected labelled corpus,
extracts the versioned physical definition-card measurements, and compares
embedding-only nearest-centroid inference with embedding plus acoustic
features under the canonical collection-held-out protocol.  No semantic label
is inferred from a card and no production model or source file is changed.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import time
from pathlib import Path
from typing import Any

import numpy as np

SD = Path(__file__).resolve().parent
FEATURE_VERSION = "definition_card_v1"

# These are physical measurements, not semantic predictions.  Values that are
# absent for a source (for example pitch or stereo correlation) are imputed
# from the training fold only.
FEATURE_PATHS = (
    ("source", "analysis_duration_seconds"),
    ("signal", "rms_dbfs"),
    ("signal", "peak_dbfs"),
    ("signal", "crest_factor"),
    ("signal", "clipped_fraction"),
    ("signal", "leading_silence_seconds"),
    ("signal", "trailing_silence_seconds"),
    ("spectrum", "spectral_centroid_hz"),
    ("spectrum", "spectral_rolloff_hz"),
    ("spectrum", "spectral_flatness"),
    ("spectrum", "zero_crossing_rate"),
    ("spectrum", "low_band_energy_ratio"),
    ("spectrum", "high_band_energy_ratio"),
    ("spectrum", "harmonic_energy_ratio"),
    ("temporal", "onset_count"),
    ("temporal", "onset_density_per_second"),
    ("temporal", "estimated_tempo_bpm"),
    ("temporal", "periodicity_seconds"),
    ("temporal", "periodicity_strength"),
    ("pitch", "median_f0_hz"),
    ("pitch", "voiced_frame_fraction"),
    ("spatial", "stereo_correlation"),
)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _cards_for(paths: list[str], out: Path, corpus_sha256: str) -> dict[str, Any]:
    if out.exists():
        payload = json.loads(out.read_text(encoding="utf-8"))
        if (payload.get("feature_version") == FEATURE_VERSION and
                payload.get("corpus_sha256") == corpus_sha256 and
                payload.get("n_requested") == len(paths)):
            return payload
    cards_mod = _load_module("slo_audio_definition_card", SD / "audio_definition_card.py")
    cards: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for path in paths:
        try:
            cards.append(cards_mod.analyse_file(path))
        except Exception as exc:
            errors.append({"path": path, "error": str(exc)})
    if errors:
        raise SystemExit(f"FAIL CLOSED: {len(errors)} definition-card extraction errors")
    payload = {
        "record_type": "slo_physical_feature_cards",
        "schema_version": "1.0.0",
        "feature_version": FEATURE_VERSION,
        "corpus_sha256": corpus_sha256,
        "n_requested": len(paths),
        "n_cards": len(cards),
        "n_errors": 0,
        "cards": cards,
        "safety": {"read_only": True, "source_audio_modified": False,
                   "semantic_labels_created": False, "rename_actions": False},
    }
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def _vector(card: dict[str, Any]) -> list[float]:
    values: list[float] = []
    for section, key in FEATURE_PATHS:
        value = card.get(section, {}).get(key)
        try:
            value = float(value) if value is not None else float("nan")
        except (TypeError, ValueError):
            value = float("nan")
        values.append(value)
    return values


def _normalise_rows(x: np.ndarray, train: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    median = np.nanmedian(train, axis=0)
    median[~np.isfinite(median)] = 0.0
    train = np.where(np.isfinite(train), train, median)
    x = np.where(np.isfinite(x), x, median)
    mean = train.mean(axis=0)
    scale = train.std(axis=0)
    scale[scale < 1e-9] = 1.0
    return (x - mean) / scale, (train - mean) / scale


def _predict(xtr: np.ndarray, ytr: np.ndarray, xte: np.ndarray,
             classes: list[str]) -> tuple[np.ndarray, np.ndarray]:
    ztr = xtr / (np.linalg.norm(xtr, axis=1, keepdims=True) + 1e-9)
    zte = xte / (np.linalg.norm(xte, axis=1, keepdims=True) + 1e-9)
    centroids = np.vstack([ztr[ytr == c].mean(axis=0) for c in classes])
    centroids /= np.linalg.norm(centroids, axis=1, keepdims=True) + 1e-9
    sims = zte @ centroids.T
    logits = (sims - sims.max(axis=1, keepdims=True)) * 8.0
    probs = np.exp(logits - logits.max(axis=1, keepdims=True))
    probs /= probs.sum(axis=1, keepdims=True)
    return np.asarray(classes)[sims.argmax(axis=1)], probs.max(axis=1)


def _coverage(conf: np.ndarray, correct: np.ndarray, target: float) -> float:
    order = np.argsort(-conf)
    cumulative = np.cumsum(correct[order]) / np.arange(1, len(order) + 1)
    ok = np.where(cumulative >= target)[0]
    return float((ok[-1] + 1) / len(order)) if len(ok) else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=Path,
                    default=SD / "corpus_granularity_relabelled_v1.npz")
    ap.add_argument("--cards", type=Path,
                    default=SD / "results_physical_feature_cards_granularity_v1.json")
    ap.add_argument("--out", type=Path,
                    default=SD / "results_physical_feature_fusion_granularity_v1.json")
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--splits", type=int, default=5)
    ap.add_argument("--min-examples", type=int, default=5)
    ap.add_argument("--min-collections", type=int, default=5)
    args = ap.parse_args()

    corpus_sha = hashlib.sha256(args.corpus.read_bytes()).hexdigest()
    full = _load_module("slo_full_taxonomy_eval", SD / "full_taxonomy_eval.py")
    d = full.load(str(args.corpus))
    cards_payload = _cards_for([str(p) for p in d["paths"]], args.cards, corpus_sha)
    cards_by_path = {str(c["path"]): c for c in cards_payload["cards"]}
    if set(d["paths"]) != set(cards_by_path):
        raise SystemExit("FAIL CLOSED: definition cards do not cover corpus paths")
    acoustic = np.asarray([_vector(cards_by_path[str(p)]) for p in d["paths"]], dtype=float)

    inventory = full.eligible_classes(d, args.min_examples, args.min_collections)
    classes = [c for c, info in inventory.items() if info["eligible"]]
    keep = np.isin(d["labels"], classes)
    Xemb = np.asarray(d["X"][keep], dtype=np.float32)
    Xac = acoustic[keep]
    y = np.asarray(d["labels"][keep]).astype(str)
    groups = np.asarray(d["vendor"][keep]).astype(str)
    classes = list(classes)

    from sklearn.metrics import f1_score
    from sklearn.model_selection import StratifiedGroupKFold

    weights = (0.0, 0.25, 0.5, 1.0)
    per_arm: dict[str, list[dict[str, float]]] = {f"acoustic_weight_{w:g}": [] for w in weights}
    for seed in range(args.seeds):
        cv = StratifiedGroupKFold(args.splits, shuffle=True, random_state=seed)
        oof: dict[str, np.ndarray] = {
            f"acoustic_weight_{w:g}": np.empty(len(y), dtype=object) for w in weights
        }
        confs: dict[str, np.ndarray] = {
            f"acoustic_weight_{w:g}": np.zeros(len(y), dtype=float) for w in weights
        }
        for tr, te in cv.split(Xemb, y, groups=groups):
            zemb_te, zemb_tr = _normalise_rows(Xemb[te], Xemb[tr])
            zac_te, zac_tr = _normalise_rows(Xac[te], Xac[tr])
            for w in weights:
                key = f"acoustic_weight_{w:g}"
                if w == 0.0:
                    train_x, test_x = zemb_tr, zemb_te
                else:
                    train_x = np.hstack([zemb_tr, w * zac_tr])
                    test_x = np.hstack([zemb_te, w * zac_te])
                pred, conf = _predict(train_x, y[tr], test_x, classes)
                oof[key][te] = pred
                confs[key][te] = conf
        for w in weights:
            key = f"acoustic_weight_{w:g}"
            correct = (oof[key] == y).astype(float)
            per_arm[key].append({
                "accuracy": float(correct.mean()),
                "macro_f1": float(f1_score(y, oof[key].astype(str), average="macro", zero_division=0)),
                "coverage_at_90_precision": _coverage(confs[key], correct, 0.90),
                "coverage_at_95_precision": _coverage(confs[key], correct, 0.95),
            })

    results: dict[str, Any] = {}
    for key, rows in per_arm.items():
        results[key] = {
            "acoustic_weight": float(key.rsplit("_", 1)[1]),
            "accuracy_mean": float(np.mean([r["accuracy"] for r in rows])),
            "accuracy_sd": float(np.std([r["accuracy"] for r in rows])),
            "macro_f1_mean": float(np.mean([r["macro_f1"] for r in rows])),
            "coverage_at_90_precision_mean": float(np.mean([r["coverage_at_90_precision"] for r in rows])),
            "coverage_at_95_precision_mean": float(np.mean([r["coverage_at_95_precision"] for r in rows])),
            "per_seed": rows,
        }
    base = results["acoustic_weight_0"]
    for result in results.values():
        result["delta_accuracy_pp_vs_embedding_only"] = 100.0 * (result["accuracy_mean"] - base["accuracy_mean"])

    payload = {
        "record_type": "slo_physical_feature_fusion_eval",
        "schema_version": "1.0.0",
        "method_version": "physical_feature_fusion_v1",
        "safety": {"read_only": True, "source_audio_modified": False,
                   "production_model_changed": False, "rename_actions": False},
        "protocol": {
            "split": "StratifiedGroupKFold by vendor/collection",
            "seeds": args.seeds, "splits": args.splits,
            "min_examples": args.min_examples,
            "min_collections": args.min_collections,
            "feature_version": FEATURE_VERSION,
            "fusion": "standardise each block on train fold, L2 normalise rows, concatenate acoustic block with stated weight, nearest centroid",
            "weights": list(weights),
        },
        "corpus": {"path": str(args.corpus.resolve()), "sha256": corpus_sha,
                   "n_rows": int(len(y)), "n_classes": len(classes),
                   "n_collections": int(len(set(groups))), "classes": classes},
        "acoustic_features": [f"{section}.{key}" for section, key in FEATURE_PATHS],
        "definition_cards": {"path": str(args.cards.resolve()), "n_cards": cards_payload["n_cards"], "n_errors": cards_payload["n_errors"]},
        "results": results,
        "decision": "research_only; no promotion unless an arm clears the pre-registered +2pp accuracy gate and class/rejection gates",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: {m: v for m, v in r.items() if m.endswith("mean") or m.startswith("delta_")} for k, r in results.items()}, indent=2))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
