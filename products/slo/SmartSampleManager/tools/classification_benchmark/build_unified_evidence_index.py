#!/usr/bin/env python3
"""Build a path-independent, evidence-backed SLO index.

The index joins already-produced read-only artefacts by complete-file content
identity.  It intentionally stores no embedding vectors: vectors remain in
their model-versioned NPZ cache and records point to their row indices.  A
record may contain physical measurements, a model suggestion, and aliases, but
none of those fields is promoted to ground truth or a rename action here.

This is a join/index operation, not an audio analyser.  It does not open source
audio, write metadata, rename files, or modify any existing cache.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from audio_evidence_schema import AudioEvidenceRecord, EvidenceClaim, PhysicalMeasurement


VERSION = "unified_evidence_index_v1"
RECORD_TYPE = "slo_audio_evidence_record"


def _absolute(value: str) -> str:
    return os.path.abspath(os.path.expanduser(str(value)))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _load_prediction_rows(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    rows: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid prediction JSON at line {line_no}") from exc
            if not isinstance(row, dict) or not row.get("path"):
                continue
            key = _absolute(str(row["path"]))
            if key in rows:
                raise ValueError(f"duplicate prediction path: {key}")
            rows[key] = row
    return rows


def _load_acoustic(path: Path | None) -> dict[str, dict[str, float]]:
    if path is None:
        return {}
    data = np.load(path, allow_pickle=True)
    required = {"paths", "F", "names"}
    missing = required - set(data.files)
    if missing:
        raise ValueError(f"acoustic cache missing keys: {sorted(missing)}")
    paths = [_absolute(str(value)) for value in data["paths"]]
    matrix = np.asarray(data["F"], dtype=np.float32)
    names = [str(value) for value in data["names"]]
    if matrix.ndim != 2 or matrix.shape[0] != len(paths) or matrix.shape[1] != len(names):
        raise ValueError("acoustic cache paths, matrix, and names do not align")
    if len(paths) != len(set(paths)):
        raise ValueError("acoustic cache contains duplicate paths")
    return {
        path: {name: float(value) for name, value in zip(names, row)
               if np.isfinite(value)}
        for path, row in zip(paths, matrix)
    }


def _unit_for(name: str) -> str:
    if name in {"fundamental_hz", "harmonic_spacing_hz", "beating_rate_hz"}:
        return "Hz"
    if name in {"pitch_drop_cents", "glide_within_100ms_cents"}:
        return "cents"
    if name in {"pitch_drop_rate_cps"}:
        return "cents_per_second"
    if name in {"attack_ms"}:
        return "milliseconds"
    if name in {"decay_seconds"}:
        return "seconds"
    if name in {"onset_density"}:
        return "events_per_second"
    if name in {"partial_count"}:
        return "count"
    return "ratio"


def _form_and_family(label: str) -> tuple[str, str]:
    label = str(label or "").strip()
    lowered = label.lower()
    suffixes = (
        (" Loop", "loop"),
        (" One-Shot", "one-shot"),
        (" Phrase", "phrase"),
        (" Fill", "fill"),
    )
    for suffix, form in suffixes:
        if label.endswith(suffix):
            return label[: -len(suffix)].strip(), form
    if " loop" in lowered:
        return label, "loop"
    return label, "unknown"


def _prediction_claims(row: dict[str, Any] | None) -> tuple[EvidenceClaim, EvidenceClaim, EvidenceClaim, dict[str, Any]]:
    if not row:
        unknown = EvidenceClaim()
        return unknown, unknown, unknown, {}
    label = str(row.get("fused_taxonomy_class") or row.get("full_taxonomy_class") or "").strip()
    if not label:
        unknown = EvidenceClaim()
        return unknown, unknown, unknown, {"prediction_state": "unknown"}
    try:
        confidence = float(row.get("fused_taxonomy_confidence", row.get("full_taxonomy_confidence", 0.0)))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = min(1.0, max(0.0, confidence))
    source = str(row.get("fusion_source") or "full_taxonomy_audio")
    identity = EvidenceClaim(label, confidence, source, "predicted")
    family_value, form_value = _form_and_family(label)
    family = EvidenceClaim(family_value, confidence, source, "predicted")
    form = EvidenceClaim(form_value, confidence if form_value != "unknown" else 0.0,
                         source if form_value != "unknown" else "unknown",
                         "predicted" if form_value != "unknown" else "unknown")
    prediction = {
        "label": label,
        "confidence": confidence,
        "source": source,
        "action": row.get("action"),
        "fusion_reason": row.get("fusion_reason"),
        "full_taxonomy_similarity": row.get("full_taxonomy_similarity"),
        "accepted_at_calibrated_95": row.get("accepted_at_calibrated_95"),
    }
    return identity, family, form, {"prediction": prediction}


def _hash_rows(identity: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = identity.get("rows")
    if not isinstance(rows, list):
        raise ValueError("identity manifest has no rows list")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not row.get("path"):
            continue
        path = _absolute(str(row["path"]))
        content = str(row.get("content_sha256") or "")
        if len(content) != 64:
            raise ValueError(f"invalid content hash for {path}")
        if path in result:
            raise ValueError(f"duplicate identity path: {path}")
        result[path] = {**row, "path": path, "content_sha256": content}
    return result


def _embedding_rows(embedding_index: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for item in embedding_index.get("records", []):
        if not isinstance(item, dict):
            raise ValueError("embedding index record is not an object")
        content = str(item.get("content_sha256") or "")
        paths = [_absolute(str(value)) for value in item.get("paths", [])]
        if len(content) != 64 or not paths:
            raise ValueError("embedding index record requires content hash and paths")
        for path in paths:
            if path in rows:
                raise ValueError(f"embedding index path appears twice: {path}")
            rows[path] = {"content_sha256": content, **item, "paths": paths}
    return rows, {
        "model_version": embedding_index.get("model_version", "unknown"),
        "dimensions": int(embedding_index.get("embedding_dimensions", 0)),
        "cache": embedding_index.get("embedding_cache", {}),
    }


def _metadata(path: str, embedding_info: dict[str, Any], row: dict[str, Any], aliases: list[str]) -> dict[str, Any]:
    source = Path(path)
    return {
        "filename": source.name,
        "extension": source.suffix.lower(),
        "size_bytes": row.get("size_bytes"),
        "aliases": aliases,
        "embedding": {
            "model_version": embedding_info["model_version"],
            "dimensions": embedding_info["dimensions"],
            "row_indices": list(row.get("embedding_row_indices", [])),
            "cache": embedding_info.get("cache", {}),
        },
    }


def build_records(embedding_index: dict[str, Any], identity: dict[str, Any],
                  acoustic: dict[str, dict[str, float]],
                  predictions: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    embedding_paths, embedding_info = _embedding_rows(embedding_index)
    identity_rows = _hash_rows(identity)
    missing_identity = sorted(set(embedding_paths) - set(identity_rows))
    if missing_identity:
        raise ValueError(f"embedding paths missing from identity manifest: {len(missing_identity)}")
    extra_identity = sorted(set(identity_rows) - set(embedding_paths))
    if extra_identity:
        raise ValueError(f"identity manifest contains paths outside embedding index: {len(extra_identity)}")
    unknown_acoustic = sorted(set(acoustic) - set(embedding_paths))
    unknown_predictions = sorted(set(predictions) - set(embedding_paths))

    by_content: dict[str, list[str]] = defaultdict(list)
    for path, item in embedding_paths.items():
        if item["content_sha256"] != identity_rows[path]["content_sha256"]:
            raise ValueError(f"content hash disagreement for {path}")
        by_content[item["content_sha256"]].append(path)

    records: list[dict[str, Any]] = []
    for content_id in sorted(by_content):
        aliases = sorted(by_content[content_id])
        canonical = aliases[0]
        identity_row = identity_rows[canonical]
        source_prediction = predictions.get(canonical)
        # If a prediction exists only for an alias, use it but preserve the
        # canonical content record and expose the source path in provenance.
        prediction_path = canonical
        if source_prediction is None:
            for alias in aliases[1:]:
                if alias in predictions:
                    source_prediction = predictions[alias]
                    prediction_path = alias
                    break
        ident, family, form, prediction_meta = _prediction_claims(source_prediction)
        measurements: dict[str, PhysicalMeasurement] = {}
        acoustic_path = canonical
        values = acoustic.get(acoustic_path)
        if values is None:
            for alias in aliases[1:]:
                if alias in acoustic:
                    values = acoustic[alias]
                    acoustic_path = alias
                    break
        for name, value in (values or {}).items():
            measurements[name] = PhysicalMeasurement(value, _unit_for(name), "physics_v1_1", True)
        item = embedding_paths[canonical]
        metadata = _metadata(canonical, embedding_info, item, aliases)
        metadata["provenance"] = {
            "identity_manifest": "complete_file_sha256",
            "prediction_path": prediction_path if source_prediction else None,
            "acoustic_path": acoustic_path if values else None,
        }
        metadata.update(prediction_meta)
        record = AudioEvidenceRecord(
            content_id=f"sha256:{content_id}",
            source_path=canonical,
            identity=ident,
            family=family,
            form=form,
            measurements=measurements,
            metadata=metadata,
            duplicate_group=f"exact:{content_id}" if len(aliases) > 1 else "",
            model_versions={"evidence_index": VERSION,
                            "embedding": embedding_info["model_version"],
                            "physics": "physics_v1_1" if values else ""},
            legacy={"prediction_present": source_prediction is not None,
                    "acoustic_measurements_present": bool(values)},
        )
        payload = record.as_dict()
        payload["record_type"] = RECORD_TYPE
        records.append(payload)
    summary = {
        "record_type": "slo_unified_evidence_index",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_embedding_paths": len(embedding_paths),
        "n_content_ids": len(records),
        "n_alias_paths": sum(max(0, len(paths) - 1) for paths in by_content.values()),
        "n_exact_duplicate_groups": sum(len(paths) > 1 for paths in by_content.values()),
        "n_with_acoustic_measurements": sum(bool(acoustic.get(path)) for path in embedding_paths),
        "n_with_predictions": sum(path in predictions for path in embedding_paths),
        "n_acoustic_paths_outside_embedding_index": len(unknown_acoustic),
        "n_prediction_paths_outside_embedding_index": len(unknown_predictions),
        "embedding_model_version": embedding_info["model_version"],
        "embedding_dimensions": embedding_info["dimensions"],
        "safety": {
            "read_only": True,
            "source_audio_modified": False,
            "paths_modified": False,
            "metadata_written": False,
            "embedding_values_modified": False,
            "semantic_labels_created": False,
            "rename_actions": False,
            "content_identity_is_complete_file_sha256": True,
        },
    }
    return records, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embedding-index", type=Path, required=True)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--acoustic", type=Path)
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--out", type=Path, required=True,
                        help="JSONL output; one evidence record per content ID")
    parser.add_argument("--summary-out", type=Path)
    args = parser.parse_args()

    embedding_index = json.loads(args.embedding_index.read_text(encoding="utf-8"))
    identity = json.loads(args.identity.read_text(encoding="utf-8"))
    acoustic = _load_acoustic(args.acoustic)
    predictions = _load_prediction_rows(args.predictions)
    records, summary = build_records(embedding_index, identity, acoustic, predictions)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    summary["output"] = str(args.out.resolve())
    summary["input_sha256"] = {
        "embedding_index": hashlib.sha256(args.embedding_index.read_bytes()).hexdigest(),
        "identity": hashlib.sha256(args.identity.read_bytes()).hexdigest(),
        "acoustic": hashlib.sha256(args.acoustic.read_bytes()).hexdigest() if args.acoustic else None,
        "predictions": hashlib.sha256(args.predictions.read_bytes()).hexdigest() if args.predictions else None,
    }
    summary_out = args.summary_out or args.out.with_suffix(args.out.suffix + ".summary.json")
    summary_out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
