#!/usr/bin/env python3
"""Nested collection-held-out recalibration of current auto-action gates."""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import numpy as np


def gate_for_class(conf, pred, correct, cls, target, min_n):
    mask = pred == cls
    if int(mask.sum()) < min_n:
        return None
    scores = conf[mask]
    ok = correct[mask]
    order = np.argsort(-scores)
    cumulative = np.cumsum(ok[order]) / np.arange(1, len(order) + 1)
    valid = np.flatnonzero(cumulative >= target)
    valid = valid[valid + 1 >= min_n]
    if not len(valid):
        return None
    k = int(valid[-1]) + 1
    return {"threshold": float(scores[order[k - 1]]), "calibration_n": k,
            "calibration_precision": float(cumulative[k - 1])}


def load_rows(manifest_path: Path) -> tuple[list[dict], bool]:
    """Load either a labelled manifest or a completed validation receipt.

    Returns rows normalized to ``path``, ``label`` and ``vendor`` plus a flag
    indicating validation-receipt mode.  Candidate classes in a validation
    receipt are metadata for selecting the gate heads; human labels remain the
    evaluation truth and may intentionally be outside those classes.
    """
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    validation_receipt_mode = (
        isinstance(manifest_payload, dict)
        and manifest_payload.get("record_type") == "slo_class_conditional_gate_validation"
    )
    if validation_receipt_mode:
        receipt_rows = manifest_payload.get("rows")
        if not isinstance(receipt_rows, list) or not receipt_rows:
            raise ValueError("validation receipt has no rows")
        rows = []
        for row in receipt_rows:
            human_label = str(row.get("human_label", "")).strip()
            vendor = str(row.get("vendor", "")).strip()
            candidate_class = str(row.get("candidate_class", "")).strip()
            if (not human_label or human_label == "__skip__" or not vendor
                    or not candidate_class):
                raise ValueError("validation receipt row is missing label, vendor, or candidate class")
            rows.append({"path": row.get("path"), "label": human_label,
                         "vendor": vendor, "candidate_class": candidate_class})
    elif isinstance(manifest_payload, dict):
        rows = manifest_payload.get("rows")
        if not isinstance(rows, list):
            raise ValueError("manifest must contain a rows array")
    elif isinstance(manifest_payload, list):
        rows = manifest_payload
    else:
        raise ValueError("manifest must be an object or array")

    if not rows:
        raise ValueError("manifest has no rows")
    for row in rows:
        if (not isinstance(row, dict) or not row.get("path")
                or not row.get("label") or not row.get("vendor")):
            raise ValueError("manifest row is missing path, label, or vendor")
    return rows, validation_receipt_mode


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--splits", type=int, default=5)
    ap.add_argument("--target", type=float, default=0.90)
    ap.add_argument("--min-n", type=int, default=20)
    args = ap.parse_args()
    from sklearn.model_selection import GroupKFold, StratifiedGroupKFold
    from incumbent_receipt import centroid_fit_predict

    z = np.load(args.corpus, allow_pickle=True)
    by_path = {os.path.abspath(str(p)): i for i, p in enumerate(z["paths"])}
    rows, validation_receipt_mode = load_rows(args.manifest)
    paths = [os.path.abspath(str(r["path"])) for r in rows]
    missing_paths = [path for path in paths if path not in by_path]
    if missing_paths:
        raise ValueError(f"corpus is missing {len(missing_paths)} manifest paths")
    idx = [by_path[p] for p in paths]
    X = np.asarray(z["emb"], dtype=np.float32)[idx]
    y = np.asarray([str(r["label"]) for r in rows], dtype=object)
    g = np.asarray([str(r["vendor"]) for r in rows], dtype=object)
    if validation_receipt_mode:
        candidate = np.asarray([str(r["candidate_class"]) for r in rows], dtype=object)
        inventory = {c: (int((candidate == c).sum()), int(len(set(g[candidate == c]))))
                     for c in sorted(set(candidate))}
    else:
        inventory = {c: (int((y == c).sum()), int(len(set(g[y == c])))) for c in sorted(set(y))}
    classes = [c for c, (n, ng) in inventory.items() if n >= 5 and ng >= 5]
    if not classes:
        raise ValueError("no classes meet the minimum count/vendor requirement")
    if not validation_receipt_mode:
        keep = np.isin(y, classes)
        X, y, g = X[keep], y[keep], g[keep]
    all_results = []
    for target in (args.target, 0.95):
        total_auto = total_correct = total_rows = 0
        class_counts = {c: [0, 0] for c in classes}
        per_seed = []
        for seed in range(args.seeds):
            pred = np.empty(len(y), dtype=object); conf = np.zeros(len(y)); auto = np.zeros(len(y), dtype=bool)
            if validation_receipt_mode:
                # A validation receipt may intentionally contain a small
                # number of labels outside the candidate classes (a negative
                # example). GroupKFold preserves collection holdout without
                # dropping that evidence merely because it is rare.
                outer = GroupKFold(args.splits)
                outer_splits = outer.split(X, y, groups=g)
                outer_protocol = "GroupKFold by vendor/collection"
            else:
                outer = StratifiedGroupKFold(args.splits, shuffle=True, random_state=seed)
                outer_splits = outer.split(X, y, groups=g)
                outer_protocol = "StratifiedGroupKFold by vendor/collection"
            for tr, te in outer_splits:
                fit_mask = np.isin(y[tr], classes)
                fit_indices = tr[fit_mask]
                if len(fit_indices) < args.min_n:
                    raise ValueError("outer training fold has too few supported-class rows")
                inner = StratifiedGroupKFold(3, shuffle=True, random_state=seed + 1000)
                cal_pred = np.empty(len(fit_indices), dtype=object); cal_conf = np.zeros(len(fit_indices))
                for itr, iva in inner.split(X[fit_indices], y[fit_indices], groups=g[fit_indices]):
                    if set(g[fit_indices][itr]) & set(g[fit_indices][iva]):
                        raise AssertionError("inner collection leakage")
                    p, c = centroid_fit_predict(X[fit_indices][itr], y[fit_indices][itr],
                                                X[fit_indices][iva], classes)
                    cal_pred[iva], cal_conf[iva] = p, c
                cal_correct = (cal_pred == y[fit_indices]).astype(float)
                gates = {c: gate_for_class(cal_conf, cal_pred, cal_correct, c, target, args.min_n)
                         for c in classes}
                p, c = centroid_fit_predict(X[fit_indices], y[fit_indices], X[te], classes)
                pred[te], conf[te] = p, c
                auto[te] = np.asarray([gates.get(label) is not None and score >= gates[label]["threshold"]
                                        for label, score in zip(p, c)], dtype=bool)
            ok = (pred == y)
            n = int(auto.sum()); cor = int((auto & ok).sum())
            total_auto += n; total_correct += cor; total_rows += len(y)
            for c in classes:
                m = auto & (pred == c)
                class_counts[c][0] += int(m.sum()); class_counts[c][1] += int((m & ok).sum())
            per_seed.append({"auto_n": n, "auto_precision": 100 * cor / max(n, 1),
                             "auto_share": 100 * n / len(y)})
        all_results.append({"target_precision": target, "auto_n": total_auto,
                            "auto_precision": 100 * total_correct / max(total_auto, 1),
                            "auto_share": 100 * total_auto / max(total_rows, 1),
                            "per_seed": per_seed,
                            "by_class": {c: {"n": n, "precision": 100 * cor / max(n, 1)}
                                         for c, (n, cor) in class_counts.items() if n}})
        print(all_results[-1], flush=True)
    payload = {
        "record_type": "slo_current_class_gate_recalibration",
        "schema_version": "1.0.0", "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "protocol": {"outer_split": outer_protocol,
                     "inner_calibration": "three-fold StratifiedGroupKFold by vendor/collection",
                     "seeds": args.seeds, "splits": args.splits,
                     "minimum_calibration_predictions_per_class": args.min_n},
        "inventory": {"n_rows": int(len(y)), "n_classes": len(classes),
                      "n_collections": int(len(set(g))),
                      "candidate_classes": classes,
                      "out_of_scope_human_labels": sorted(
                          set(str(label) for label in y if label not in classes)),
                      "n_out_of_scope_human_labels": int(sum(label not in classes for label in y)),
                      "validation_receipt_mode": validation_receipt_mode},
        "results": all_results,
        "decision": "research audit only; no policy mutation or rename approval",
        "safety": {"read_only": True, "source_audio_modified": False,
                   "production_model_changed": False, "rename_actions": False},
    }
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
