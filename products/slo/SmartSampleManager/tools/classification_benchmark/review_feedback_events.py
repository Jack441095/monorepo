#!/usr/bin/env python3
"""Append-only typed feedback events for SLO review queues.

These events preserve reviewer intent and provenance without silently becoming
training labels. A later, explicit curation step may promote selected events to
gold data after collection-held-out validation.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any


VERSION = "review_feedback_events_v1"
EVENT_TYPES = {
    "accept_suggestion",
    "correct_class",
    "reject_suggestion",
    "not_in_list",
    "mark_duplicate",
    "mark_not_duplicate",
    "note",
    # Filename candidates are reviewed independently from taxonomy labels. A
    # reviewer may accept the generated candidate, correct it, or reject it;
    # all three remain append-only evidence and never perform a rename.
    "accept_name_candidate",
    "correct_name_candidate",
    "reject_name_candidate",
    # Fused classifier candidates are adjudicated separately from filenames.
    # These events remain review evidence and never become semantic labels by
    # themselves.
    "accept_fused_candidate",
    "correct_fused_candidate",
    "reject_fused_candidate",
}


def _require_text(event: dict[str, Any], key: str) -> str:
    value = event.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _safe_filename(event: dict[str, Any], key: str) -> str:
    value = _require_text(event, key)
    if (len(value) > 255 or value in {".", ".."} or "/" in value
            or "\\" in value or "\n" in value or "\r" in value):
        raise ValueError(f"{key} must be a single safe filename")
    return value


def _optional_sha256(event: dict[str, Any], key: str) -> None:
    if key not in event:
        return
    value = _require_text(event, key).lower()
    if re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"{key} must be a 64-character SHA-256 hex digest")


def validate_event(event: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise ValueError("event must be an object")
    for key in ("event_id", "event_type", "path", "actor", "created_at", "source_plan_sha256"):
        _require_text(event, key)
    _optional_sha256(event, "source_packet_sha256")
    event_type = event["event_type"]
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unsupported event_type: {event_type}")
    path = os.path.abspath(event["path"])
    if path != event["path"]:
        raise ValueError("path must be absolute and normalized")
    _require_text(event, "previous_decision")
    if event_type == "correct_class":
        _require_text(event, "corrected_class")
    if event_type == "not_in_list":
        _require_text(event, "note")
    if event_type == "mark_duplicate":
        canonical = os.path.abspath(_require_text(event, "canonical_path"))
        if canonical == path:
            raise ValueError("canonical_path must differ from duplicate path")
        if canonical != event["canonical_path"]:
            raise ValueError("canonical_path must be absolute and normalized")
    if event_type == "note":
        _require_text(event, "note")
    if event_type == "accept_name_candidate":
        _safe_filename(event, "candidate_filename")
    if event_type == "correct_name_candidate":
        _safe_filename(event, "candidate_filename")
        _safe_filename(event, "corrected_filename")
    if event_type == "reject_name_candidate":
        _safe_filename(event, "candidate_filename")
        _require_text(event, "note")
    if event_type == "accept_fused_candidate":
        _require_text(event, "candidate_label")
    if event_type == "correct_fused_candidate":
        _require_text(event, "candidate_label")
        _require_text(event, "corrected_label")
    if event_type == "reject_fused_candidate":
        _require_text(event, "candidate_label")
        _require_text(event, "note")
    output = dict(event)
    output.update({
        "record_type": "slo_review_feedback_event",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "path": path,
        "promoted_to_gold": False,
    })
    return output


def read_events(log_path: Path) -> list[dict[str, Any]]:
    if not log_path.exists():
        return []
    events = []
    ids: set[str] = set()
    with log_path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                event = validate_event(json.loads(line))
            except (json.JSONDecodeError, ValueError) as exc:
                raise ValueError(f"invalid feedback event at {log_path}:{line_number}: {exc}") from exc
            if event["event_id"] in ids:
                raise ValueError(f"duplicate event_id at {log_path}:{line_number}")
            ids.add(event["event_id"])
            events.append(event)
    return events


def append_event(log_path: Path, event: dict[str, Any]) -> dict[str, Any]:
    normalized = validate_event(event)
    existing = read_events(log_path)
    if any(row["event_id"] == normalized["event_id"] for row in existing):
        raise ValueError(f"event_id already exists: {normalized['event_id']}")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(normalized, sort_keys=True) + "\n")
    return normalized


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--path", required=True)
    parser.add_argument("--event-type", choices=sorted(EVENT_TYPES), required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--source-plan-sha256", required=True)
    parser.add_argument("--previous-decision", required=True)
    parser.add_argument("--corrected-class")
    parser.add_argument("--note")
    parser.add_argument("--canonical-path")
    parser.add_argument("--candidate-filename")
    parser.add_argument("--corrected-filename")
    parser.add_argument("--candidate-label")
    parser.add_argument("--corrected-label")
    parser.add_argument("--event-id", default=lambda: str(uuid.uuid4()))
    args = parser.parse_args()
    event = {
        "event_id": args.event_id if isinstance(args.event_id, str) else args.event_id(),
        "event_type": args.event_type,
        "path": os.path.abspath(args.path),
        "actor": args.actor,
        "created_at": _now(),
        "source_plan_sha256": args.source_plan_sha256,
        "previous_decision": args.previous_decision,
    }
    for key in ("corrected_class", "note", "canonical_path", "candidate_filename",
                "corrected_filename", "candidate_label", "corrected_label"):
        value = getattr(args, key)
        if value is not None:
            event[key] = os.path.abspath(value) if key == "canonical_path" else value
    created = append_event(args.log, event)
    print(json.dumps({"event_id": created["event_id"], "event_type": created["event_type"], "promoted_to_gold": False}, indent=2))


if __name__ == "__main__":
    main()
