#!/usr/bin/env python3
"""Add research-only periodicity/FFT form evidence to an existing review queue.

The model is fit from the verified by-ear corpus solely as a research probe,
then applied to the label-free FFT queue.  Every output row remains review-only:
the script never emits a semantic class, mutates audio, or authorizes a rename.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import multiprocessing as mp
import os
import time
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


SD = Path(__file__).resolve().parent
PERIODICITY_NAMES = ("dur", "sustain", "ac_peak", "ac_ratio", "recur", "onsets", "tempo_conf")
MAX_PERIODICITY_SECONDS = 30.0


def _module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SD / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _periodicity_one(path: str):
    # librosa's tempogram is quadratic in frame count.  Bound review-time
    # work so an unusually long recording cannot stall the whole queue; it is
    # reported as unresolved evidence rather than truncated or relabelled.
    try:
        import soundfile as sf
        info = sf.info(path)
        if info.samplerate <= 0 or info.frames / info.samplerate > MAX_PERIODICITY_SECONDS:
            return path, None
    except Exception:
        return path, None
    module = _module("loop_periodicity_worker", "loop_periodicity.py")
    return path, module.features(path)


def _candidate_rows(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("record_type") != "slo_fft_evidence_review_queue":
        raise ValueError("candidate queue is not an FFT evidence review receipt")
    safety = payload.get("safety") or {}
    if (not safety.get("read_only") or safety.get("semantic_labels_created")
            or safety.get("rename_actions") or safety.get("auto_action_allowed")):
        raise ValueError("candidate queue is not review-only")
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("candidate queue has no rows")
    return rows


def _fft_matrix(rows: list[dict], names: list[str]) -> tuple[np.ndarray, list[dict]]:
    values, kept = [], []
    for row in rows:
        evidence = row.get("fft_evidence")
        if row.get("fft_status") != "computed" or not isinstance(evidence, dict):
            continue
        try:
            vector = np.asarray([float(evidence[name]) for name in names], dtype=np.float32)
        except (KeyError, TypeError, ValueError):
            continue
        if not np.isfinite(vector).all():
            continue
        values.append(vector)
        kept.append(row)
    if not values:
        raise ValueError("candidate queue has no finite computed FFT evidence")
    return np.asarray(values, dtype=np.float32), kept


def _fit_training(labels: Path, periodicity_cache: Path, fft_cache: Path, workers: int):
    benchmark = _module("periodicity_fft_loop_benchmark", "periodicity_fft_loop_benchmark.py")
    training_rows = benchmark._rows(labels)
    paths = [path for path, _ in training_rows]
    requested_count = len(paths)
    y = np.asarray([label for _, label in training_rows], dtype=np.int8)
    periodicity = benchmark._load_periodicity(periodicity_cache, paths)
    # Training is read-only and should not spawn an extractor for a known
    # undecodable row.  Align to the existing sidecar cache instead; the
    # benchmark receipt records the excluded count explicitly.
    z = np.load(fft_cache, allow_pickle=True)
    fft_names = [str(name) for name in z["names"]]
    expected_names = [str(name) for name in _module(
        "fft_names_training", "fft_sidecar_benchmark.py").FEATURE_NAMES]
    if fft_names != expected_names:
        raise ValueError("training FFT cache feature names do not match sidecar")
    by_path = {os.path.abspath(str(path)): i for i, path in enumerate(z["paths"])}
    keep = np.asarray([path in by_path for path in paths], dtype=bool)
    paths, y, periodicity = ([value[keep] if isinstance(value, np.ndarray)
                               else [item for item, use in zip(value, keep) if use]
                               for value in (paths, y, periodicity)])
    fft = np.asarray([z["X"][by_path[path]] for path in paths], dtype=np.float32)
    if not np.isfinite(fft).all(axis=1).all():
        finite = np.isfinite(fft).all(axis=1)
        paths, y, periodicity, fft = ([value[finite] if isinstance(value, np.ndarray)
                                       else [item for item, use in zip(value, finite) if use]
                                       for value in (paths, y, periodicity, fft)])
    valid = np.isfinite(periodicity).all(axis=1) & np.isfinite(fft).all(axis=1)
    X = np.hstack([periodicity[valid], fft[valid, 2:]])
    y = y[valid]
    model = make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=3000, class_weight="balanced", random_state=0),
    )
    model.fit(X, y)
    return model, benchmark, int(valid.sum()), int(requested_count - valid.sum())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-queue", type=Path, required=True)
    parser.add_argument("--labels", type=Path, default=SD / "verified_drums.csv")
    parser.add_argument("--periodicity-cache", type=Path,
                        default=SD / "loop_periodicity_feats.npz")
    parser.add_argument("--training-fft-cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--confidence-threshold", type=float, default=0.98)
    args = parser.parse_args()
    if not 0.5 < args.confidence_threshold < 1.0:
        raise ValueError("confidence threshold must be between 0.5 and 1.0")

    source_rows = _candidate_rows(args.candidate_queue)
    fft_module = _module("fft_sidecar_benchmark", "fft_sidecar_benchmark.py")
    fft_names = list(fft_module.FEATURE_NAMES)
    candidate_fft, candidate_rows = _fft_matrix(source_rows, fft_names)
    local_paths = [os.path.abspath(str(row.get("fft_local_path") or row.get("path") or ""))
                   for row in candidate_rows]
    usable = [path for path in local_paths if path and os.path.exists(path)]
    periodicity: dict[str, np.ndarray] = {}
    with mp.Pool(max(1, args.workers)) as pool:
        for path, values in pool.imap_unordered(_periodicity_one, usable):
            if values is not None and np.isfinite(values).all():
                periodicity[path] = np.asarray(values, dtype=np.float32)

    model, benchmark, training_rows, training_excluded = _fit_training(
        args.labels, args.periodicity_cache, args.training_fft_cache, args.workers)
    feature_rows, feature_fft, unresolved = [], [], 0
    for row, path, fft_values in zip(candidate_rows, local_paths, candidate_fft):
        values = periodicity.get(path)
        if values is None:
            unresolved += 1
            continue
        # loop_periodicity.features returns the historical nine-column vector;
        # keep the same seven named columns as the training specialist.
        selected = values[[0, 1, 2, 4, 5, 7, 8]]
        feature_rows.append(row)
        feature_fft.append(np.hstack([selected, fft_values[2:]]))
    if not feature_rows:
        raise ValueError("no candidate files had usable periodicity evidence")

    X = np.asarray(feature_fft, dtype=np.float32)
    probabilities = model.predict_proba(X)
    loop_index = int(np.flatnonzero(model.classes_ == 1)[0])
    loop_probability = probabilities[:, loop_index]
    confidence = probabilities.max(axis=1)
    output_rows = []
    for row, loop_prob, conf in zip(feature_rows, loop_probability, confidence):
        form = "loop_temporal_evidence" if loop_prob >= 0.5 else "transient_temporal_evidence"
        route = "high_confidence_review" if conf >= args.confidence_threshold else "review"
        output_rows.append({
            "path": row.get("path"),
            "content_sha256": row.get("content_sha256"),
            "fft_local_path": row.get("fft_local_path"),
            "semantic_label": None,
            "form_evidence": form,
            "loop_probability": round(float(loop_prob), 6),
            "confidence": round(float(conf), 6),
            "route": route,
            "source_fft_status": row.get("fft_status"),
            "source_review_priority": row.get("review_priority"),
        })

    high = sum(row["route"] == "high_confidence_review" for row in output_rows)
    receipt = {
        "record_type": "slo_periodicity_fft_review_queue",
        "schema_version": "1.0.0",
        "method_version": "periodicity_fft_review_queue_v1",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source_queue": str(args.candidate_queue.resolve()),
        "protocol": {
            "training_model": "standardized balanced logistic regression",
            "training_labels": "verified by-ear corpus; research probe only",
            "confidence_threshold": args.confidence_threshold,
            "max_periodicity_seconds": MAX_PERIODICITY_SECONDS,
            "high_confidence_route": "review only; no automatic action",
        },
        "inputs": {
            "source_candidates": len(source_rows),
            "fft_computed_candidates": len(candidate_rows),
            "periodicity_resolved_candidates": len(feature_rows),
            "periodicity_unresolved": unresolved,
            "training_rows": training_rows,
            "training_excluded": training_excluded,
        },
        "features": {"periodicity": list(PERIODICITY_NAMES), "fft_sidecar": fft_names},
        "summary": {
            "n_rows": len(output_rows),
            "n_high_confidence_review": high,
            "n_standard_review": len(output_rows) - high,
            "semantic_labels_created": 0,
        },
        "rows": output_rows,
        "decision": "review evidence only; no semantic labels, production weights, or rename actions",
        "safety": {
            "read_only": True,
            "source_audio_modified": False,
            "semantic_labels_created": False,
            "production_model_changed": False,
            "rename_actions": False,
            "auto_action_allowed": False,
            "human_approval_required": True,
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"summary": receipt["summary"], "inputs": receipt["inputs"]}, indent=2))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
