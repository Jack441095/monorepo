#!/usr/bin/env python3
"""Audit class-conditional precision gates under collection-held-out folds.

This is an audit, not an approval command.  It tests whether a class can have
its own conservative confidence threshold while maintaining 95% precision on
every repeated vendor-held-out seed.  No production model, rename plan, or
source file is changed.
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


def _load_full():
    spec = importlib.util.spec_from_file_location("slo_full_taxonomy_eval", SD / "full_taxonomy_eval.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _gate(conf: np.ndarray, correct: np.ndarray, target: float) -> dict[str, Any]:
    if len(conf) == 0:
        return {"n_candidates": 0, "n_accepted": 0, "precision": None, "threshold": 1.0, "coverage": 0.0}
    order = np.argsort(-conf)
    c = correct[order]
    cumulative = np.cumsum(c) / np.arange(1, len(c) + 1)
    ok = np.where(cumulative >= target)[0]
    if not len(ok):
        return {"n_candidates": int(len(conf)), "n_accepted": 0, "precision": 0.0, "threshold": 1.0, "coverage": 0.0}
    k = int(ok[-1] + 1)
    return {"n_candidates": int(len(conf)), "n_accepted": k,
            "precision": float(c[:k].mean()), "threshold": float(conf[order][k - 1]),
            "coverage": float(k / len(conf))}


def _fixed_gate(conf: np.ndarray, correct: np.ndarray, threshold: float) -> dict[str, Any]:
    accepted = conf >= threshold
    n = int(accepted.sum())
    precision = float(correct[accepted].mean()) if n else 0.0
    return {"n_candidates": int(len(conf)), "n_accepted": n,
            "precision": precision, "threshold": float(threshold),
            "coverage": float(n / len(conf)) if len(conf) else 0.0}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=Path,
                    default=SD / "corpus_granularity_relabelled_v1.npz")
    ap.add_argument("--out", type=Path,
                    default=SD / "results_class_conditional_gates_granularity_v1.json")
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--splits", type=int, default=5)
    ap.add_argument("--min-examples", type=int, default=5)
    ap.add_argument("--min-collections", type=int, default=5)
    ap.add_argument("--min-accepted", type=int, default=20,
                    help="minimum accepted rows required for a candidate class")
    args = ap.parse_args()

    full = _load_full()
    d = full.load(str(args.corpus))
    inventory = full.eligible_classes(d, args.min_examples, args.min_collections)
    classes = [c for c, info in inventory.items() if info["eligible"]]
    keep = np.isin(d["labels"], classes)
    X = np.asarray(d["X"][keep], dtype=np.float32)
    y = np.asarray(d["labels"][keep]).astype(str)
    groups = np.asarray(d["vendor"][keep]).astype(str)
    classes = list(classes)
    from sklearn.model_selection import StratifiedGroupKFold
    import incumbent_receipt as incumbent

    seed_rows: list[dict[str, Any]] = []
    by_class_seed: dict[str, list[dict[str, Any]]] = {c: [] for c in classes}
    raw_by_class_seed: dict[str, list[tuple[np.ndarray, np.ndarray]]] = {c: [] for c in classes}
    for seed in range(args.seeds):
        cv = StratifiedGroupKFold(args.splits, shuffle=True, random_state=seed)
        pred = np.empty(len(y), dtype=object)
        conf = np.zeros(len(y), dtype=float)
        for tr, te in cv.split(X, y, groups=groups):
            if set(groups[tr]) & set(groups[te]):
                raise AssertionError("collection leakage")
            p, c = incumbent.centroid_fit_predict(X[tr], y[tr], X[te], classes)
            pred[te], conf[te] = p, c
        correct = (pred == y).astype(float)
        for cls in classes:
            m = pred == cls
            g = _gate(conf[m], correct[m], 0.95)
            g["seed"] = seed
            g["class"] = cls
            by_class_seed[cls].append(g)
            raw_by_class_seed[cls].append((conf[m].copy(), correct[m].copy()))
        seed_rows.append({
            "seed": seed,
            "accuracy": float(correct.mean()),
            "n_predictions": int(len(pred)),
        })

    class_results: dict[str, Any] = {}
    candidates: list[str] = []
    for cls in classes:
        per_seed = by_class_seed[cls]
        # A threshold must survive every seed, so take the highest threshold
        # that any seed required.  This is intentionally conservative.
        threshold = max(float(r["threshold"]) for r in per_seed)
        seed_eval = [
            _fixed_gate(conf, correct, threshold)
            | {"seed": seed}
            for seed, (conf, correct) in enumerate(raw_by_class_seed[cls])
        ]
        accepted_counts = [int(r["n_accepted"]) for r in seed_eval]
        robust = all(int(r["n_accepted"]) >= args.min_accepted and
                     float(r["precision"]) >= 0.95 for r in seed_eval)
        class_results[cls] = {
            "conservative_threshold": threshold,
            "min_seed_accepted": min(accepted_counts) if accepted_counts else 0,
            "max_seed_accepted": max(accepted_counts) if accepted_counts else 0,
            "robust_candidate": bool(robust),
            "per_seed": seed_eval,
            "per_seed_individual_gates": per_seed,
        }
        if robust:
            candidates.append(cls)

    payload = {
        "record_type": "slo_class_conditional_gate_audit",
        "schema_version": "1.0.0",
        "method_version": "class_conditional_gates_v1",
        "safety": {"read_only": True, "source_audio_modified": False,
                   "production_model_changed": False, "rename_actions": False,
                   "approval_granted": False},
        "protocol": {
            "split": "StratifiedGroupKFold by vendor/collection",
            "seeds": args.seeds, "splits": args.splits,
            "target_precision": 0.95,
            "threshold_policy": "maximum per-seed class threshold",
            "min_accepted_per_seed": args.min_accepted,
            "min_examples": args.min_examples, "min_collections": args.min_collections,
        },
        "corpus": {"path": str(args.corpus.resolve()),
                   "sha256": hashlib.sha256(args.corpus.read_bytes()).hexdigest(),
                   "n_files": int(len(y)), "n_classes": len(classes),
                   "n_collections": int(len(set(groups))), "classes": classes},
        "seed_summary": seed_rows,
        "classes": class_results,
        "robust_candidate_classes": candidates,
        "decision": "audit_only; candidate classes still require new-domain validation and explicit owner approval before auto-action",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"robust_candidate_classes": candidates,
                      "n_classes": len(classes),
                      "n_files": len(y)}, indent=2))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
