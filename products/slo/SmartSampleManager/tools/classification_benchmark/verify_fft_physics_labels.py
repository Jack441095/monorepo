#!/usr/bin/env python3
"""Fail-closed verification for the candidate-hidden FFT/physics label CSV.

This validates reviewer output without promoting it: ids, absolute paths and
content hashes must still match the blinded receipt; labels must belong to the
frozen taxonomy or an explicit escape hatch; and required escape notes cannot
be empty.  The output is a receipt only and never changes the training corpus
or filesystem.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


METHOD_VERSION = "verify_fft_physics_labels_v1"
RECORD_TYPE = "slo_fft_physics_label_manifest"
ALLOWED_LABELS = {
    "Bass Hit", "Bass Loop", "Bass Reese", "Chord Loop", "Clap", "Crash",
    "Drum Loop", "Foley", "Foley Loop", "Hi-Hat", "Hi-Hat Loop", "Impact",
    "Kick", "Kick Loop", "Other/none", "Pad", "Percussion",
    "Percussion Loop", "Rimshot", "Riser", "SFX", "Snare", "Synth Loop",
    "Synth One-Shot", "Top Loop", "Vocal Loop", "Vocal One-Shot",
    "Weather/Nature Atmos", "Unknown", "Not in list", "Not enough info",
    "Taxonomy gap", "__skip__",
}
NOTE_REQUIRED = {"Unknown", "Not in list", "Taxonomy gap"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _manifest(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("record_type") != RECORD_TYPE:
        raise ValueError("manifest is not an FFT/physics label receipt")
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("manifest has no rows")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("manifest row is not an object")
        row_id = str(row.get("id", "")).strip()
        file_path = str(row.get("path", "")).strip()
        expected = str(row.get("content_sha256", "")).strip().lower()
        if not row_id or not file_path or not expected:
            raise ValueError("manifest row requires id, path and content_sha256")
        absolute = str(Path(file_path).expanduser().resolve())
        if row_id in seen:
            raise ValueError(f"duplicate manifest id: {row_id}")
        seen.add(row_id)
        out.append({"id": row_id, "path": absolute, "content_sha256": expected})
    return out


def verify_labels(manifest_path: Path, labels_path: Path,
                  require_complete: bool = False,
                  check_audio_hash: bool = True) -> dict[str, Any]:
    expected = _manifest(manifest_path)
    by_id = {row["id"]: row for row in expected}
    with labels_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or [])
        required = {"id", "path", "label", "note", "not_in_list_label"}
        if not required.issubset(fields):
            raise ValueError(f"labels CSV is missing columns: {sorted(required - fields)}")
        # Candidate values are never valid reviewer output.  Rejecting them
        # here catches accidental export of the source queue or evidence JSON.
        forbidden = {name for name in fields if any(token in name.lower()
                    for token in ("candidate", "prediction", "probability", "physics", "fft"))}
        if forbidden:
            raise ValueError(f"labels CSV contains candidate/evidence fields: {sorted(forbidden)}")
        rows = list(reader)

    seen: set[str] = set()
    accepted: list[dict[str, str]] = []
    failures: list[dict[str, str]] = []
    hash_cache: dict[str, str] = {}
    for number, row in enumerate(rows, 2):
        row_id = str(row.get("id", "")).strip()
        file_path = str(Path(str(row.get("path", "")).strip()).expanduser().resolve())
        label = str(row.get("label", "")).strip()
        reason = ""
        target = by_id.get(row_id)
        if not target:
            reason = "id_not_in_manifest"
        elif row_id in seen:
            reason = "duplicate_id"
        elif file_path != target["path"]:
            reason = "path_mismatch"
        elif label and label not in ALLOWED_LABELS:
            reason = "label_not_in_frozen_taxonomy"
        elif label in NOTE_REQUIRED and not (str(row.get("note", "")).strip()
                                              or str(row.get("not_in_list_label", "")).strip()):
            reason = "required_escape_note_missing"
        elif check_audio_hash and target:
            audio = Path(target["path"])
            if not audio.is_file():
                reason = "audio_missing"
            else:
                actual = hash_cache.setdefault(target["path"], _sha256(audio))
                if actual != target["content_sha256"]:
                    reason = "content_hash_mismatch"
        if reason:
            failures.append({"line": str(number), "id": row_id, "reason": reason})
            continue
        # Mark the identity as consumed even when the reviewer left it blank;
        # otherwise two blank rows for one id could evade duplicate detection.
        seen.add(row_id)
        if label:
            accepted.append({"id": row_id, "path": file_path, "label": label})

    unlabeled = sorted(set(by_id) - seen)
    if require_complete and unlabeled:
        failures.append({"line": "", "id": "", "reason": "incomplete_review"})
    return {
        "record_type": "slo_fft_physics_label_verification",
        "schema_version": "1.0.0",
        "method_version": METHOD_VERSION,
        "source_manifest": str(manifest_path.resolve()),
        "source_labels": str(labels_path.resolve()),
        "summary": {
            "manifest_rows": len(expected),
            "csv_rows": len(rows),
            "accepted_labeled_rows": len(accepted),
            "unlabeled_rows": len(unlabeled),
            "failure_count": len(failures),
        },
        "decision": "verified_review_only" if not failures else "rejected_fail_closed",
        "safety": {
            "audio_modified": False,
            "training_corpus_modified": False,
            "model_changed": False,
            "rename_actions": False,
            "candidate_values_accepted": False,
        },
        "unlabeled_ids": unlabeled,
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--skip-audio-hash", action="store_true",
                        help="only for offline schema tests; production runs should hash audio")
    args = parser.parse_args(argv)
    try:
        receipt = verify_labels(args.manifest, args.labels,
                                require_complete=args.require_complete,
                                check_audio_hash=not args.skip_audio_hash)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL CLOSED: {exc}")
        return 2
    if args.out.exists():
        print(f"FAIL CLOSED: refusing to overwrite {args.out}")
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt["summary"], indent=2, sort_keys=True))
    print(f"decision: {receipt['decision']}")
    return 0 if not receipt["failures"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
