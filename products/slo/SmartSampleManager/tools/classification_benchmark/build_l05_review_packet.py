#!/usr/bin/env python3
"""Build a fail-closed SLO L-05 human-review packet.

The command only reads manifests and CSV evidence.  It never decodes, copies,
hashes, relabels, or modifies audio.  The blind packet intentionally excludes
the current and proposed labels; those remain in a separate key for an
independent reviewer/adjudicator.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path


PACKET_FIELDS = (
    "review_id",
    "source_path",
    "source_sha256",
    "vendor_id",
    "pack_id",
    "audio_format",
    "duration_seconds",
    "reviewer_1_id",
    "reviewer_1_label",
    "reviewer_1_status",
    "reviewer_1_ambiguity_reason",
    "reviewer_1_notes",
    "reviewer_2_id",
    "reviewer_2_label",
    "reviewer_2_status",
    "reviewer_2_ambiguity_reason",
    "reviewer_2_notes",
    "adjudicated_label",
    "adjudication_status",
    "adjudication_notes",
)

BLIND_FIELDS = (
    "review_id",
    "source_path",
    "source_sha256",
    "vendor_id",
    "pack_id",
    "audio_format",
    "duration_seconds",
)

KEY_FIELDS = (
    "review_id",
    "source_path",
    "source_sha256",
    "vendor_id",
    "pack_id",
    "expected_subcategory",
    "label_authority",
    "label_confidence",
    "predicted_class",
    "confidence",
    "selection_reason",
    "source_family",
    "ood",
)


def _read_json(path: Path) -> list[dict]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read manifest {path}: {exc}") from exc
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise RuntimeError("manifest must contain a list of objects")
    return value


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    except OSError as exc:
        raise RuntimeError(f"cannot read CSV {path}: {exc}") from exc


def _norm(value: object) -> str:
    return os.path.normcase(os.path.normpath(str(value)))


def _manifest_identity(row: dict) -> tuple[str, str, str]:
    source_path = row.get("source_path") or row.get("full_evidence_relpath")
    relative_path = row.get("local_relative_path") or row.get("relative_path")
    filename = row.get("filename") or row.get("original_filename")
    return (
        _norm(source_path) if source_path else "",
        _norm(relative_path) if relative_path else "",
        _norm(filename) if filename else "",
    )


def _index_manifest(manifest: list[dict]) -> dict[str, list[dict]]:
    index: dict[str, list[dict]] = {}
    for row in manifest:
        for value in _manifest_identity(row):
            if value:
                index.setdefault(value, []).append(row)
    return index


def _resolve_row(candidate: dict[str, str], index: dict[str, list[dict]]) -> dict:
    values = (
        candidate.get("source_path"),
        candidate.get("relative_path"),
        candidate.get("filename"),
    )
    matches: list[dict] = []
    for value in values:
        if not value:
            continue
        for row in index.get(_norm(value), []):
            if row not in matches:
                matches.append(row)
    if not matches:
        raise RuntimeError(
            "review evidence row does not resolve to the declared manifest: "
            f"{candidate.get('filename') or candidate.get('relative_path')!r}"
        )
    if len(matches) > 1:
        raise RuntimeError(
            "review evidence identity is ambiguous; add a path identity: "
            f"{candidate.get('filename') or candidate.get('relative_path')!r}"
        )
    return matches[0]


def _source_path(row: dict) -> str:
    value = row.get("source_path") or row.get("full_evidence_relpath")
    if not value:
        value = row.get("local_relative_path") or row.get("relative_path")
    if not value:
        raise RuntimeError(f"manifest row has no source path: {row!r}")
    return str(value)


def _source_sha(row: dict) -> str:
    value = row.get("source_sha256") or row.get("sha256")
    if not value:
        raise RuntimeError(f"manifest row has no source SHA-256: {_source_path(row)}")
    return str(value)


def _selection(candidate: dict[str, str], row: dict) -> str:
    if candidate.get("selection_reason"):
        return candidate["selection_reason"]
    if row.get("ood") or row.get("expected_subcategory") == "OOD":
        return "OOD failure or near-neighbour negative"
    if candidate.get("predicted_class") or candidate.get("proposed_class"):
        return "known-set classifier conflict or low-confidence review candidate"
    return "targeted classification review candidate"


def _make_rows(
    manifest: list[dict],
    owner_queue: list[dict[str, str]],
    error_database: list[dict[str, str]],
) -> tuple[list[dict], list[dict]]:
    index = _index_manifest(manifest)
    selected: dict[str, tuple[dict, dict[str, str]]] = {}
    candidates = []
    for row in owner_queue:
        candidates.append((row, "owner_review_queue"))
    for row in error_database:
        candidates.append((row, "error_database"))

    for candidate, source in candidates:
        manifest_row = _resolve_row(candidate, index)
        source_path = _source_path(manifest_row)
        source_sha = _source_sha(manifest_row)
        identity = source_sha.lower()
        if identity in selected:
            existing, key = selected[identity]
            key["selection_reason"] = (
                f"{key['selection_reason']}; also selected by {source}"
            )
            continue
        key = {
            "review_id": f"slo-l05-{len(selected) + 1:04d}",
            "source_path": source_path,
            "source_sha256": source_sha,
            "vendor_id": str(manifest_row.get("vendor_id", "")),
            "pack_id": str(manifest_row.get("pack_id", "")),
            "expected_subcategory": str(manifest_row.get("expected_subcategory", "")),
            "label_authority": str(manifest_row.get("label_authority", "")),
            "label_confidence": str(manifest_row.get("label_confidence", "")),
            "predicted_class": str(candidate.get("predicted_class") or candidate.get("proposed_class") or ""),
            "confidence": str(candidate.get("confidence") or ""),
            "selection_reason": _selection(candidate, manifest_row),
            "source_family": str(manifest_row.get("source_family", "")),
            "ood": str(bool(manifest_row.get("ood") or manifest_row.get("expected_subcategory") == "OOD")).lower(),
        }
        packet = {
            "review_id": key["review_id"],
            "source_path": source_path,
            "source_sha256": source_sha,
            "vendor_id": str(manifest_row.get("vendor_id", "")),
            "pack_id": str(manifest_row.get("pack_id", "")),
            "audio_format": str(manifest_row.get("audio_format", "")),
            "duration_seconds": str(manifest_row.get("duration_seconds", "")),
            **{field: "" for field in PACKET_FIELDS if field not in {
                "review_id", "source_path", "source_sha256", "vendor_id",
                "pack_id", "audio_format", "duration_seconds",
            }},
        }
        selected[identity] = (packet, key)

    packets = [item[0] for item in selected.values()]
    keys = [item[1] for item in selected.values()]
    return packets, keys


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict]) -> None:
    if path.exists():
        raise RuntimeError(f"refusing to overwrite existing output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_packet(
    manifest_path: Path,
    owner_queue_path: Path,
    error_database_path: Path,
    output_dir: Path,
) -> dict:
    manifest = _read_json(manifest_path)
    packets, keys = _make_rows(
        manifest,
        _read_csv(owner_queue_path),
        _read_csv(error_database_path),
    )
    if not packets:
        raise RuntimeError("no review candidates resolved from the supplied evidence")

    _write_csv(output_dir / "blind_review_packet.csv", BLIND_FIELDS, packets)
    _write_csv(output_dir / "review_results_template.csv", PACKET_FIELDS, packets)
    _write_csv(output_dir / "review_packet_key.csv", KEY_FIELDS, keys)
    return {
        "status": "READY_FOR_HUMAN_REVIEW",
        "candidate_count": len(packets),
        "blind_packet": str(output_dir / "blind_review_packet.csv"),
        "results_template": str(output_dir / "review_results_template.csv"),
        "key": str(output_dir / "review_packet_key.csv"),
        "audio_mutated": False,
        "production_model_changed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--owner-review-queue", type=Path, required=True)
    parser.add_argument("--error-database", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = build_packet(
            args.manifest,
            args.owner_review_queue,
            args.error_database,
            args.output_dir,
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
