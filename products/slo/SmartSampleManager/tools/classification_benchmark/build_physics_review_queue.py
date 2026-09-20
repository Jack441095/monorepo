#!/usr/bin/env python3
"""Attach bounded multi-window FFT physics evidence to a review queue."""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import time
from pathlib import Path

import numpy as np


SD = Path(__file__).resolve().parent
MAX_PHYSICS_SECONDS = 120.0
PHYSICS_NAMES = (
    "full_transient", "full_decay_s", "full_low_energy", "full_hf_density",
    "full_onset_rate", "third_onset_cv", "rhythm_ac_peak", "rhythm_ac_lag",
    "repetition_score", "silence_frac",
)


def _physics_one(path: str):
    try:
        import soundfile as sf
        info = sf.info(path)
        if info.samplerate <= 0 or info.frames / info.samplerate > MAX_PHYSICS_SECONDS:
            return path, None
    except Exception:
        return path, None
    import mw_features
    return path, mw_features.extract(path)


def _read_queue(path: Path) -> tuple[dict, list[dict]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("record_type") not in {"slo_fft_evidence_review_queue", "slo_periodicity_fft_review_queue"}:
        raise ValueError("input is not an FFT/periodicity review queue")
    safety = payload.get("safety") or {}
    if (not safety.get("read_only") or safety.get("semantic_labels_created")
            or safety.get("rename_actions") or safety.get("auto_action_allowed")):
        raise ValueError("input queue is not review-only")
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("input queue has no rows")
    return payload, rows


def _physics_lanes(evidence: dict[str, float]) -> list[str]:
    lanes = []
    if (evidence["repetition_score"] >= 0.08
            and evidence["third_onset_cv"] <= 0.9
            and evidence["full_decay_s"] >= 0.25):
        lanes.append("repeating_temporal_evidence")
    if evidence["full_transient"] >= 2.0 and evidence["full_decay_s"] <= 0.35:
        lanes.append("transient_decay_evidence")
    if evidence["full_hf_density"] >= 0.35:
        lanes.append("high_frequency_evidence")
    return lanes


def build_queue(source: Path, out: Path, workers: int = 4,
                limit: int | None = None) -> dict:
    payload, rows = _read_queue(source)
    if limit is not None:
        rows = rows[:limit]
    candidates = []
    for row in rows:
        local = row.get("fft_local_path") or row.get("path")
        if local and os.path.exists(local):
            candidates.append((row, os.path.abspath(str(local))))
    found: dict[str, np.ndarray] = {}
    with mp.Pool(max(1, workers)) as pool:
        for path, values in pool.imap_unordered(_physics_one, [p for _, p in candidates]):
            if values is not None and np.isfinite(values).all():
                found[path] = np.asarray(values, dtype=np.float32)

    source_names = None
    # mw_features.NAMES is imported only in workers; this keeps the parent
    # lightweight and makes the cache contract explicit.
    import mw_features
    source_names = list(mw_features.NAMES)
    indices = [source_names.index(name) for name in PHYSICS_NAMES]
    output_rows = []
    unresolved = 0
    for row, path in candidates:
        item = dict(row)
        item["semantic_label"] = None
        values = found.get(path)
        if values is None:
            item["physics_status"] = "unresolved_long_or_decode"
            item["physics_evidence"] = None
            item["physics_candidate_lanes"] = []
            unresolved += 1
            output_rows.append(item)
            continue
        evidence = {name: round(float(values[index]), 7)
                    for name, index in zip(PHYSICS_NAMES, indices)}
        item["physics_status"] = "computed"
        item["physics_evidence"] = evidence
        item["physics_candidate_lanes"] = _physics_lanes(evidence)
        output_rows.append(item)

    computed = len(output_rows) - unresolved
    result = {
        "record_type": "slo_physics_review_queue",
        "schema_version": "1.0.0",
        "method_version": "physics_review_queue_v1",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source_queue": str(source.resolve()),
        "max_physics_seconds": MAX_PHYSICS_SECONDS,
        "n_source_rows": len(rows), "n_candidates": len(candidates),
        "n_physics_computed": computed, "n_physics_unresolved": unresolved,
        "features": list(PHYSICS_NAMES), "rows": output_rows,
        "safety": {
            "read_only": True, "ground_truth_read": False,
            "semantic_labels_created": False, "training_data_created": False,
            "source_audio_modified": False, "rename_actions": False,
            "auto_action_allowed": False, "human_approval_required": True,
            "physics_lanes_are_evidence_only": True,
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-queue", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    result = build_queue(args.source_queue, args.out, args.workers, args.limit)
    print(json.dumps({key: result[key] for key in (
        "n_source_rows", "n_candidates", "n_physics_computed", "n_physics_unresolved")}, indent=2))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
