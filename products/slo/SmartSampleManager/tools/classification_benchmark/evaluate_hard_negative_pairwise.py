#!/usr/bin/env python3
"""Evaluate a constrained hard-negative pairwise correction arm.

The incumbent nearest-centroid model proposes the top two classes.  A binary
classifier may arbitrate only when that pair is one of the pre-registered
taxonomy boundaries below.  It cannot introduce a third class, override a
rejection decision outside the pair, or create a rename plan.
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

# Chosen from the taxonomy and observed boundary definitions before this run;
# no test-fold labels are used to select pairs.
PRE_REGISTERED_PAIRS = (
    ("Kick", "Bass Hit"),
    ("Bass Hit", "Bass Reese"),
    ("Kick", "Kick Loop"),
    ("Hi-Hat", "Hi-Hat Loop"),
    ("Hi-Hat Loop", "Top Loop"),
    ("Crash", "Hi-Hat"),
    ("Snare", "Rimshot"),
    ("Percussion", "Percussion Loop"),
    ("Drum Loop", "Percussion Loop"),
    ("Foley", "Foley Loop"),
    ("Bass Loop", "Bass Reese"),
    ("Bass Loop", "Bass Hit"),
    ("Chord Loop", "Synth Loop"),
    ("Synth One-Shot", "Pad"),
    ("SFX", "Impact"),
    ("Foley", "Impact"),
)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _centroid_fit(xtr: np.ndarray, ytr: np.ndarray, xte: np.ndarray,
                  classes: list[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler().fit(xtr)
    ztr = scaler.transform(xtr)
    zte = scaler.transform(xte)
    ztr /= np.linalg.norm(ztr, axis=1, keepdims=True) + 1e-9
    zte /= np.linalg.norm(zte, axis=1, keepdims=True) + 1e-9
    centroids = np.vstack([ztr[ytr == c].mean(axis=0) for c in classes])
    centroids /= np.linalg.norm(centroids, axis=1, keepdims=True) + 1e-9
    sims = zte @ centroids.T
    order = np.argsort(-sims, axis=1)
    logits = (sims - sims.max(axis=1, keepdims=True)) * 8.0
    probs = np.exp(logits - logits.max(axis=1, keepdims=True))
    probs /= probs.sum(axis=1, keepdims=True)
    return ztr, zte, order[:, 0].astype(int), order[:, 1].astype(int), probs.max(axis=1)


def _coverage(conf: np.ndarray, correct: np.ndarray, target: float) -> float:
    order = np.argsort(-conf)
    cumulative = np.cumsum(correct[order]) / np.arange(1, len(order) + 1)
    ok = np.where(cumulative >= target)[0]
    return float((ok[-1] + 1) / len(order)) if len(ok) else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=Path,
                    default=SD / "corpus_granularity_relabelled_v1.npz")
    ap.add_argument("--out", type=Path,
                    default=SD / "results_hard_negative_pairwise_granularity_v1.json")
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--splits", type=int, default=5)
    ap.add_argument("--min-examples", type=int, default=5)
    ap.add_argument("--min-collections", type=int, default=5)
    args = ap.parse_args()

    full = _load_module("slo_full_taxonomy_eval", SD / "full_taxonomy_eval.py")
    d = full.load(str(args.corpus))
    inventory = full.eligible_classes(d, args.min_examples, args.min_collections)
    classes = [c for c, info in inventory.items() if info["eligible"]]
    keep = np.isin(d["labels"], classes)
    X = np.asarray(d["X"][keep], dtype=np.float32)
    y = np.asarray(d["labels"][keep]).astype(str)
    groups = np.asarray(d["vendor"][keep]).astype(str)
    classes = list(classes)
    pairs = [tuple(p) for p in PRE_REGISTERED_PAIRS if p[0] in classes and p[1] in classes]
    pair_set = {frozenset(p) for p in pairs}

    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import f1_score
    from sklearn.model_selection import StratifiedGroupKFold

    baseline_rows: list[dict[str, float]] = []
    corrected_rows: list[dict[str, float]] = []
    changed_count = 0
    eligible_pair_count = 0
    for seed in range(args.seeds):
        cv = StratifiedGroupKFold(args.splits, shuffle=True, random_state=seed)
        base_pred = np.empty(len(y), dtype=object)
        corr_pred = np.empty(len(y), dtype=object)
        base_conf = np.zeros(len(y), dtype=float)
        corr_conf = np.zeros(len(y), dtype=float)
        for tr, te in cv.split(X, y, groups=groups):
            ztr, zte, top_a, top_b, top_conf = _centroid_fit(X[tr], y[tr], X[te], classes)
            base_pred[te] = np.asarray(classes, dtype=object)[top_a]
            corr_pred[te] = base_pred[te]
            base_conf[te] = top_conf
            corr_conf[te] = top_conf
            # Fit only on this training fold.  Pair selection itself was fixed
            # before evaluation, so no test-fold labels enter the experiment.
            pair_models: dict[frozenset[str], tuple[Any, tuple[str, str]]] = {}
            for pair in pairs:
                mask = np.isin(y[tr], pair)
                if mask.sum() < 4 or len(set(y[tr][mask])) < 2:
                    continue
                model = LogisticRegression(max_iter=1500, class_weight="balanced", C=1.0)
                model.fit(ztr[mask], y[tr][mask])
                pair_models[frozenset(pair)] = (model, pair)
            eligible_pair_count += len(pair_models)
            for local, (a_index, b_index) in enumerate(zip(top_a, top_b)):
                a, b = classes[int(a_index)], classes[int(b_index)]
                key = frozenset((a, b))
                if key not in pair_models:
                    continue
                model, _ = pair_models[key]
                pair_prob = model.predict_proba(zte[local:local + 1])[0]
                pair_pred = str(model.classes_[int(pair_prob.argmax())])
                if pair_pred != corr_pred[te[local]]:
                    changed_count += 1
                corr_pred[te[local]] = pair_pred
                # Keep confidence conservative: a pair correction cannot be
                # more trusted than both its binary probability and incumbent.
                corr_conf[te[local]] = min(corr_conf[te[local]], float(pair_prob.max()))
        base_correct = (base_pred == y).astype(float)
        corr_correct = (corr_pred == y).astype(float)
        baseline_rows.append({
            "accuracy": float(base_correct.mean()),
            "macro_f1": float(f1_score(y, base_pred.astype(str), average="macro", zero_division=0)),
            "coverage_at_90_precision": _coverage(base_conf, base_correct, 0.90),
            "coverage_at_95_precision": _coverage(base_conf, base_correct, 0.95),
        })
        corrected_rows.append({
            "accuracy": float(corr_correct.mean()),
            "macro_f1": float(f1_score(y, corr_pred.astype(str), average="macro", zero_division=0)),
            "coverage_at_90_precision": _coverage(corr_conf, corr_correct, 0.90),
            "coverage_at_95_precision": _coverage(corr_conf, corr_correct, 0.95),
        })

    def summarise(rows: list[dict[str, float]]) -> dict[str, Any]:
        return {
            "accuracy_mean": float(np.mean([r["accuracy"] for r in rows])),
            "accuracy_sd": float(np.std([r["accuracy"] for r in rows])),
            "macro_f1_mean": float(np.mean([r["macro_f1"] for r in rows])),
            "coverage_at_90_precision_mean": float(np.mean([r["coverage_at_90_precision"] for r in rows])),
            "coverage_at_95_precision_mean": float(np.mean([r["coverage_at_95_precision"] for r in rows])),
            "per_seed": rows,
        }

    base = summarise(baseline_rows)
    corrected = summarise(corrected_rows)
    result = {
        "record_type": "slo_hard_negative_pairwise_eval",
        "schema_version": "1.0.0",
        "method_version": "hard_negative_pairwise_v1",
        "safety": {"read_only": True, "source_audio_modified": False,
                   "production_model_changed": False, "rename_actions": False},
        "protocol": {
            "split": "StratifiedGroupKFold by vendor/collection",
            "seeds": args.seeds, "splits": args.splits,
            "model": "standardised/L2 nearest centroid; pre-registered pairwise LogisticRegression C=1.0 on top-two boundaries",
            "pairs": [list(p) for p in pairs],
            "min_examples": args.min_examples, "min_collections": args.min_collections,
        },
        "corpus": {"path": str(args.corpus.resolve()),
                   "sha256": hashlib.sha256(args.corpus.read_bytes()).hexdigest(),
                   "n_files": int(len(y)), "n_classes": len(classes),
                   "n_collections": int(len(set(groups))), "classes": classes},
        "baseline": base,
        "corrected": corrected,
        "delta": {
            "accuracy_pp": 100.0 * (corrected["accuracy_mean"] - base["accuracy_mean"]),
            "macro_f1_pp": 100.0 * (corrected["macro_f1_mean"] - base["macro_f1_mean"]),
            "coverage_at_95_precision_pp": 100.0 * (corrected["coverage_at_95_precision_mean"] - base["coverage_at_95_precision_mean"]),
        },
        "diagnostics": {"changed_predictions": changed_count,
                        "pair_models_fit_total": eligible_pair_count},
        "decision": "research_only; promote only if accuracy clears +2pp gate and class/rejection gates",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"baseline": base, "corrected": corrected, "delta": result["delta"], "diagnostics": result["diagnostics"]}, indent=2))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
