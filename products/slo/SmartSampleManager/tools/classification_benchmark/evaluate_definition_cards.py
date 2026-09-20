#!/usr/bin/env python3
"""Evaluate physical definition-card features against the frozen incumbent.

The experiment uses existing human-labelled corpus rows and the same
collection-held-out protocol as the incumbent. It is deliberately separate
from production inference: no labels are created, no source audio is changed,
and no rename plan is generated.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import time
from pathlib import Path

import numpy as np


SD = Path(__file__).resolve().parent
DEFAULT_CORPUS = SD / "corpus_v3.npz"
DEFAULT_OUT = SD / "results_definition_card_eval_v1.json"
DEFAULT_CACHE = SD / "definition_cards_corpus_v3_v1.json"


def _load_definition_module():
    path = SD / "audio_definition_card.py"
    spec = importlib.util.spec_from_file_location("audio_definition_card", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


FEATURE_KEYS = (
    ("signal", "rms_dbfs"), ("signal", "peak_dbfs"),
    ("signal", "crest_factor"), ("signal", "clipped_fraction"),
    ("signal", "leading_silence_seconds"), ("signal", "trailing_silence_seconds"),
    ("spectrum", "spectral_centroid_hz"), ("spectrum", "spectral_rolloff_hz"),
    ("spectrum", "spectral_flatness"), ("spectrum", "zero_crossing_rate"),
    ("spectrum", "low_band_energy_ratio"), ("spectrum", "high_band_energy_ratio"),
    ("spectrum", "harmonic_energy_ratio"), ("temporal", "onset_count"),
    ("temporal", "onset_density_per_second"), ("temporal", "estimated_tempo_bpm"),
    ("temporal", "periodicity_seconds"), ("temporal", "periodicity_strength"),
    ("temporal", "form_hint_confidence"), ("pitch", "median_f0_hz"),
    ("pitch", "voiced_frame_fraction"), ("spatial", "stereo_correlation"),
)


def _vector(card: dict) -> list[float]:
    out = []
    for section, key in FEATURE_KEYS:
        value = card.get(section, {}).get(key)
        try:
            out.append(float(value) if value is not None and np.isfinite(float(value)) else np.nan)
        except (TypeError, ValueError):
            out.append(np.nan)
    return out


def _load_groups(paths: list[str]) -> np.ndarray:
    """Use the production collection parser, not corpus source labels."""
    import sample_library_inventory as inventory

    groups = []
    for path in paths:
        attrs = inventory.attribute(path)
        groups.append(str(attrs[1]))
    return np.asarray(groups)


def _eligible(labels: np.ndarray, groups: np.ndarray, min_examples: int,
              min_collections: int) -> list[str]:
    classes = []
    for cls in sorted(set(labels)):
        mask = labels == cls
        if int(mask.sum()) >= min_examples and len(set(groups[mask])) >= min_collections:
            classes.append(cls)
    return classes


def _impute(train: np.ndarray, test: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    med = np.nanmedian(train, axis=0)
    med[~np.isfinite(med)] = 0.0
    a, b = train.copy(), test.copy()
    ai = np.where(~np.isfinite(a)); bi = np.where(~np.isfinite(b))
    a[ai] = med[ai[1]]; b[bi] = med[bi[1]]
    return a, b


def _run_arm(X: np.ndarray, y: np.ndarray, groups: np.ndarray, classes: list[str],
             seeds: int, splits: int) -> dict:
    from sklearn.metrics import f1_score
    from sklearn.model_selection import StratifiedGroupKFold
    import incumbent_receipt as incumbent

    accuracies, f1s, cov90, cov95 = [], [], [], []
    for seed in range(seeds):
        pred = np.empty(len(y), dtype=object)
        conf = np.zeros(len(y), dtype=float)
        cv = StratifiedGroupKFold(n_splits=splits, shuffle=True, random_state=seed)
        for tr, te in cv.split(X, y, groups=groups):
            assert not (set(groups[tr]) & set(groups[te]))
            Xtr, Xte = _impute(X[tr], X[te])
            p, c = incumbent.centroid_fit_predict(Xtr, y[tr], Xte, classes)
            pred[te], conf[te] = p, c
        correct = (pred == y).astype(float)
        accuracies.append(100.0 * float(correct.mean()))
        f1s.append(100.0 * float(f1_score(y, pred.astype(str), average="macro", zero_division=0)))
        cov90.append(incumbent.coverage_at(conf, correct, 0.90))
        cov95.append(incumbent.coverage_at(conf, correct, 0.95))
    return {
        "accuracy_mean": round(float(np.mean(accuracies)), 2),
        "accuracy_sd": round(float(np.std(accuracies)), 2),
        "per_seed_accuracy": [round(float(x), 2) for x in accuracies],
        "macro_f1": round(float(np.mean(f1s)), 2),
        "coverage_at_90_precision": round(float(np.mean(cov90)), 1),
        "coverage_at_95_precision": round(float(np.mean(cov95)), 1),
    }


def _load_cards(paths: list[str], cache: Path, analyser) -> tuple[list[dict], list[int]]:
    if cache.exists():
        payload = json.loads(cache.read_text(encoding="utf-8"))
        if payload.get("paths") == paths and payload.get("feature_version") == analyser.FEATURE_VERSION:
            return payload["cards"], payload.get("errors", [])
    cards, errors = [], []
    for index, path in enumerate(paths):
        try:
            cards.append(analyser.analyse_file(path))
        except Exception as exc:
            cards.append(None)
            errors.append({"index": index, "path": path, "error": str(exc)})
    cache.write_text(json.dumps({
        "record_type": "slo_audio_definition_card_cache",
        "feature_version": analyser.FEATURE_VERSION,
        "paths": paths, "cards": cards, "errors": errors,
    }, indent=2) + "\n", encoding="utf-8")
    return cards, errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--seeds", type=int, default=4)
    parser.add_argument("--splits", type=int, default=5)
    parser.add_argument("--min-examples", type=int, default=5)
    parser.add_argument("--min-collections", type=int, default=5)
    args = parser.parse_args()

    z = np.load(args.corpus, allow_pickle=True)
    paths = [os.path.abspath(str(p)) for p in z["paths"]]
    labels = np.asarray(z["labels"]).astype(str)
    embeddings = np.asarray(z["emb"], dtype=np.float32)
    groups = _load_groups(paths)
    classes = _eligible(labels, groups, args.min_examples, args.min_collections)
    keep = np.isin(labels, classes)

    analyser = _load_definition_module()
    cards, errors = _load_cards(paths, args.cache, analyser)
    valid = np.asarray([card is not None for card in cards]) & keep
    physical = np.asarray([_vector(card) if card is not None else [np.nan] * len(FEATURE_KEYS)
                           for card in cards], dtype=np.float32)
    y, g = labels[valid], groups[valid]
    audio, physical = embeddings[valid], physical[valid]
    results = {
        "physical_definition_features": _run_arm(physical, y, g, classes, args.seeds, args.splits),
        "frozen_audio_embedding": _run_arm(audio, y, g, classes, args.seeds, args.splits),
        "audio_plus_definition_features": _run_arm(
            np.hstack([audio, physical]), y, g, classes, args.seeds, args.splits
        ),
    }
    payload = {
        "record_type": "slo_definition_card_eval",
        "schema_version": "1.0.0",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "protocol": {
            "split": "StratifiedGroupKFold by collection",
            "seeds": args.seeds, "splits": args.splits,
            "min_examples": args.min_examples,
            "min_collections": args.min_collections,
        },
        "identity": {
            "corpus": str(args.corpus.resolve()),
            "n_corpus_rows": len(paths), "n_evaluated": int(valid.sum()),
            "n_card_errors": len(errors), "n_classes": len(classes),
            "classes": classes,
            "path_hash": hashlib.sha256("\n".join(paths).encode()).hexdigest(),
            "definition_feature_version": analyser.FEATURE_VERSION,
        },
        "results": results,
        "feature_names": [f"{section}.{key}" for section, key in FEATURE_KEYS],
        "safety": {
            "source_audio_modified": False,
            "labels_created": False,
            "production_classifier_changed": False,
            "rename_plan_applied": False,
        },
        "interpretation": "Promote physical fields only if the combined arm improves the frozen audio arm on identical grouped folds; otherwise keep them as explanation and policy signals.",
    }
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"n_evaluated": int(valid.sum()), "n_classes": len(classes), "errors": len(errors), "results": results}, indent=2))


if __name__ == "__main__":
    main()
