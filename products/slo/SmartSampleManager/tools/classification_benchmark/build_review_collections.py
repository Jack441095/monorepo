#!/usr/bin/env python3
"""Export immutable, action-specific review collections from a rename plan.

The classifier plan remains the source of truth for decisions. This tool only
reshapes it into product-facing queues and joins existing review evidence by
exact source path. It never promotes a suggestion, creates a label, or applies
a rename.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any


VERSION = "review_collections_v1"
COLLECTIONS = ("auto_rename", "suggest", "review", "never_act")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at {path}:{line_number}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"expected object at {path}:{line_number}")
            rows.append(row)
    return rows


def _decision_action(row: dict[str, Any]) -> str:
    decision = row.get("decision")
    if not isinstance(decision, dict) or not isinstance(decision.get("action"), str):
        raise ValueError(f"row has no decision.action: {row.get('path', '<missing>')}")
    action = decision["action"]
    if action not in COLLECTIONS:
        raise ValueError(f"unsupported decision action {action!r} for {row.get('path')}")
    return action


def _facet_summary(card: dict[str, Any] | None) -> dict[str, Any] | None:
    if not card:
        return None
    source = card.get("source", {})
    signal = card.get("signal", {})
    spectrum = card.get("spectrum", {})
    temporal = card.get("temporal", {})
    pitch = card.get("pitch", {})
    spatial = card.get("spatial", {})
    return {
        "duration_seconds": source.get("analysis_duration_seconds"),
        "sample_rate_hz": source.get("sample_rate_hz"),
        "rms_dbfs": signal.get("rms_dbfs"),
        "peak_dbfs": signal.get("peak_dbfs"),
        "clipped_fraction": signal.get("clipped_fraction"),
        "spectral_centroid_hz": spectrum.get("spectral_centroid_hz"),
        "low_band_energy_ratio": spectrum.get("low_band_energy_ratio"),
        "high_band_energy_ratio": spectrum.get("high_band_energy_ratio"),
        "harmonic_energy_ratio": spectrum.get("harmonic_energy_ratio"),
        "onset_density_per_second": temporal.get("onset_density_per_second"),
        "estimated_tempo_bpm": temporal.get("estimated_tempo_bpm"),
        "periodicity_strength": temporal.get("periodicity_strength"),
        "form_hint": temporal.get("form_hint"),
        "form_hint_confidence": temporal.get("form_hint_confidence"),
        "median_f0_hz": pitch.get("median_f0_hz"),
        "voiced_frame_fraction": pitch.get("voiced_frame_fraction"),
        "stereo_correlation": spatial.get("stereo_correlation"),
        "heuristic_tags": card.get("heuristic_tags", []),
        "uncertainty_reasons": card.get("uncertainty_reasons", []),
    }


def build_collections(plan_path: Path, evidence_path: Path | None = None) -> dict[str, Any]:
    records = _read_jsonl(plan_path)
    if not records or records[0].get("record_type") != "slo_rename_plan":
        raise ValueError("plan must begin with an slo_rename_plan header")
    header = records[0]
    rows = records[1:]
    evidence: dict[str, dict[str, Any]] = {}
    evidence_errors = []
    if evidence_path is not None:
        evidence_records = _read_jsonl(evidence_path)
        if not evidence_records or evidence_records[0].get("record_type") != "slo_review_evidence_packet":
            raise ValueError("evidence must begin with an slo_review_evidence_packet header")
        for row in evidence_records[1:]:
            path = row.get("path")
            if not isinstance(path, str) or path in evidence:
                evidence_errors.append({"path": path, "error": "duplicate or missing evidence path"})
            else:
                evidence[os.path.abspath(path)] = row

    seen: set[str] = set()
    collections = {name: [] for name in COLLECTIONS}
    errors = list(evidence_errors)
    for row in rows:
        path = row.get("path")
        if not isinstance(path, str):
            errors.append({"path": path, "error": "missing source path"})
            continue
        abs_path = os.path.abspath(path)
        if abs_path in seen:
            errors.append({"path": abs_path, "error": "duplicate plan path"})
            continue
        seen.add(abs_path)
        action = _decision_action(row)
        decision = row["decision"]
        packet = evidence.get(abs_path)
        prediction = packet.get("prediction", {}) if packet else {}
        card = packet.get("definition_card") if packet else None
        item = {
            "path": abs_path,
            "destination": row.get("destination"),
            "action": action,
            "predicted_class": row.get("full_taxonomy_class", prediction.get("class")),
            "filename_class": row.get("filename_class", prediction.get("filename_class")),
            "confidence": row.get("full_taxonomy_confidence", prediction.get("confidence")),
            "similarity": row.get("full_taxonomy_similarity", prediction.get("similarity")),
            "reason": decision.get("reason"),
            "policy_version": decision.get("policy_version"),
            "requires_approval": bool(decision.get("requires_approval", True)),
            "applied": bool(row.get("applied", False)),
            "approved": bool(row.get("approved", False)),
            "review_evidence": {
                "nearest_labelled_reference": packet.get("nearest_labelled_reference") if packet else None,
                "aspect_similarity_to_reference": packet.get("aspect_similarity_to_reference") if packet else None,
                "facets": _facet_summary(card),
            } if packet else None,
        }
        collections[action].append(item)

    for values in collections.values():
        values.sort(key=lambda item: item["path"])
    return {
        "record_type": "slo_review_collections",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "source_plan": str(plan_path.resolve()),
        "source_plan_sha256": _sha256(plan_path),
        "source_evidence": str(evidence_path.resolve()) if evidence_path else None,
        "source_evidence_sha256": _sha256(evidence_path) if evidence_path else None,
        "model": header.get("model"),
        "collections": collections,
        "summary": {name: len(values) for name, values in collections.items()},
        "n_plan_rows": len(rows),
        "n_joined_evidence": sum(item["review_evidence"] is not None
                                  for values in collections.values() for item in values),
        "errors": errors,
        "safety": {
            "read_only": True,
            "source_audio_modified": False,
            "labels_created": False,
            "rename_plan_applied": False,
            "suggestions_promoted": False,
            "evidence_is_not_label_transfer": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = build_collections(args.plan, args.evidence)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"summary": result["summary"], "joined_evidence": result["n_joined_evidence"], "errors": len(result["errors"])}, indent=2))


if __name__ == "__main__":
    main()
