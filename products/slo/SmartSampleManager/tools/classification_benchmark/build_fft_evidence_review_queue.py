#!/usr/bin/env python3
"""Attach FFT evidence to a label-free review queue.

This is deliberately a *review artifact*, not a classifier or training-set
builder.  It resolves GPU receipt paths against the local content inventory,
computes the shipped 2048/512 FFT sidecar for the highest-priority uncertain
rows, and records conservative form-of-signal hints.  Hints are evidence-only:
``semantic_label`` always remains ``None`` and no rename or model action is
created.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path
from typing import Any


VERSION = "fft_evidence_review_queue_v1"
SD = Path(__file__).resolve().parent


def _load_fft_extractor():
    path = SD / "fft_sidecar_benchmark.py"
    spec = importlib.util.spec_from_file_location("slo_fft_sidecar", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load FFT sidecar extractor")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_packet(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if path.suffix.lower() == ".jsonl":
        lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                 if line.strip()]
        if not lines:
            raise ValueError("receipt is empty")
        header, rows = lines[0], lines[1:]
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("receipt must be an object")
        header, rows = payload, payload.get("rows", [])
    if not isinstance(rows, list):
        raise ValueError("receipt rows must be a list")
    safety = header.get("safety") or {}
    if not safety.get("read_only") or safety.get("semantic_labels_created") or safety.get("rename_actions"):
        raise ValueError("receipt is not a read-only, label-free receipt")
    clean = [row for row in rows if isinstance(row, dict) and row.get("path")]
    if any(row.get("semantic_label") is not None for row in clean):
        raise ValueError("receipt contains semantic labels")
    return header, clean


def _priority(row: dict[str, Any]) -> float:
    """Rank uncertainty without treating uncalibrated scores as probabilities."""
    if "model_agreement" in row:
        margins = [float(row[key]) for key in ("model_a_margin", "model_b_margin")
                   if isinstance(row.get(key), (int, float)) and math.isfinite(float(row[key]))]
        margin = sum(margins) / len(margins) if margins else 1.0
        view = row.get("evidence") or {}
        views = [float((view.get(name) or {}).get("view_agreement"))
                 for name in ("model_a", "model_b")
                 if isinstance((view.get(name) or {}).get("view_agreement"), (int, float))]
        return (0.65 * (0.0 if row.get("model_agreement") else 1.0)
                + 0.20 * (row.get("model_a_status") != row.get("model_b_status"))
                + 0.10 * (1.0 - min(views or [1.0]))
                + 0.05 * max(0.0, min(1.0, (0.08 - margin) / 0.08)))
    agreement = float(row.get("view_agreement", 1.0))
    margin = float(row.get("margin", 1.0))
    return 0.65 * (1.0 - agreement) + 0.35 * max(0.0, min(1.0, (0.08 - margin) / 0.08))


def _inventory_index(path: Path) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    files = payload.get("files") if isinstance(payload, dict) else None
    if not isinstance(files, list):
        raise ValueError("inventory must contain a files list")
    by_hash: dict[str, list[dict[str, Any]]] = {}
    by_path: dict[str, dict[str, Any]] = {}
    for item in files:
        if not isinstance(item, dict) or not item.get("path"):
            continue
        item_path = str(item["path"])
        by_path[item_path] = item
        digest = str(item.get("sha256") or item.get("content_sha256") or "").lower()
        if digest:
            by_hash.setdefault(digest, []).append(item)
    return by_hash, by_path


def _resolve(row: dict[str, Any], by_hash: dict[str, list[dict[str, Any]]],
             by_path: dict[str, dict[str, Any]]) -> Path | None:
    digest = str(row.get("content_sha256") or "").lower()
    for item in by_hash.get(digest, []):
        candidate = Path(str(item["path"]))
        if candidate.exists() and bool(item.get("readable", True)):
            return candidate
    direct = Path(str(row["path"]))
    if direct.exists():
        return direct
    item = by_path.get(str(row["path"]))
    if item:
        candidate = Path(str(item["path"]))
        if candidate.exists() and bool(item.get("readable", True)):
            return candidate
    # GPU receipts use /mnt/data/slo_training/... while the inventory keeps the
    # same path relative to the local sample_pack_testing root.  Resolve by
    # suffix only after the content hash, never by a basename guess.
    marker = "/sample_pack_testing/"
    raw = str(row["path"])
    if marker in raw:
        suffix = raw.split(marker, 1)[1]
        for item_path, item in by_path.items():
            if item_path.endswith(marker + suffix):
                candidate = Path(item_path)
                if candidate.exists() and bool(item.get("readable", True)):
                    return candidate
    return None


def _lanes(features: dict[str, float]) -> list[str]:
    duration = features["duration_s"]
    sustain = features["sustain_ratio"]
    peak_rate = features["flux_peak_rate"]
    lanes: list[str] = []
    # These are intentionally broad, explainable evidence gates.  They are
    # not semantic labels and are never promoted automatically.
    if duration >= 1.5 and sustain >= 0.55 and 1.0 <= peak_rate <= 12.0:
        lanes.append("loop_temporal_evidence")
    if duration <= 2.0 and (features["flux_std"] >= 0.08 or peak_rate >= 8.0):
        lanes.append("transient_temporal_evidence")
    if features["high_band_ratio"] >= 0.65:
        lanes.append("bright_spectral_evidence")
    return lanes


def build_queue(receipt: Path, inventory: Path, out: Path, limit: int = 500) -> dict[str, Any]:
    header, rows = _read_packet(receipt)
    if limit < 0:
        raise ValueError("limit must be non-negative")
    by_hash, by_path = _inventory_index(inventory)
    candidates = [row for row in rows if row.get("status") == "review" and row.get("error") is None]
    n_source_review_candidates_total = len(candidates)
    candidates.sort(key=lambda row: (-_priority(row), str(row["path"])))
    candidates = candidates[:limit]
    fft = _load_fft_extractor()
    output_rows: list[dict[str, Any]] = []
    computed = unresolved = 0
    for row in candidates:
        item = dict(row)
        item["semantic_label"] = None
        item["review_priority"] = round(_priority(row), 6)
        local = _resolve(row, by_hash, by_path)
        if local is None:
            item["fft_status"] = "unresolved_local_audio"
            item["fft_evidence"] = None
            item["fft_candidate_lanes"] = []
            unresolved += 1
        else:
            values = fft.extract(str(local))
            if values is None:
                item["fft_status"] = "decode_or_short_audio"
                item["fft_evidence"] = None
                item["fft_candidate_lanes"] = []
                unresolved += 1
            else:
                evidence = {name: round(float(value), 7)
                            for name, value in zip(fft.FEATURE_NAMES, values)}
                item["fft_status"] = "computed"
                item["fft_local_path"] = str(local)
                item["fft_evidence"] = evidence
                item["fft_candidate_lanes"] = _lanes(evidence)
                computed += 1
        output_rows.append(item)
    payload = {
        "record_type": "slo_fft_evidence_review_queue",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "source_receipt": str(receipt.resolve()),
        "source_method_version": header.get("method_version"),
        "inventory": str(inventory.resolve()),
        "n_source_review_candidates_total": n_source_review_candidates_total,
        "n_source_review_candidates": len(candidates),
        "n_queued": len(output_rows),
        "n_fft_computed": computed,
        "n_fft_unresolved": unresolved,
        "features": list(fft.FEATURE_NAMES),
        "safety": {
            "read_only": True,
            "ground_truth_read": False,
            "semantic_labels_created": False,
            "training_data_created": False,
            "rename_actions": False,
            "human_approval_required": True,
            "fft_lanes_are_evidence_only": True,
        },
        "rows": output_rows,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()
    payload = build_queue(args.receipt, args.inventory, args.out, args.limit)
    print(json.dumps({"out": str(args.out),
                      "n_source_review_candidates_total": payload["n_source_review_candidates_total"],
                      "n_queued": payload["n_queued"],
                      "n_fft_computed": payload["n_fft_computed"],
                      "n_fft_unresolved": payload["n_fft_unresolved"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
