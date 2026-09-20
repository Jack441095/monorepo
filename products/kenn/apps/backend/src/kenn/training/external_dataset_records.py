"""Validation for text-only records derived from external datasets.

This is intentionally separate from KENN's Ableton command-training schema.
It accepts bounded text and provenance only; raw media, hidden reasoning, and
direct Live-control supervision are rejected before a later training job can
see the record.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from .dataset_intake import load_manifest


SCHEMA = "kenn.external_dataset_record.v1"
LANES = frozenset({"knowledge", "perception", "symbolic", "evaluation"})
USE_CLASSES = frozenset({"commercial", "research_only", "evaluation_only", "blocked"})
RECORD_KINDS = frozenset({"caption", "qa", "instruction", "metadata"})
REVIEW_STATUSES = frozenset({"unreviewed", "human_reviewed", "rejected"})
MAX_TEXT_CHARS = 12_000
SUSPICIOUS_MARKERS = (
    ("hidden_reasoning", re.compile(r"<\s*(?:think|analysis|chain[-_ ]of[-_ ]thought)\b", re.IGNORECASE)),
    ("prompt_injection", re.compile(r"\b(?:ignore|disregard|forget)\s+(?:all\s+)?previous instructions\b", re.IGNORECASE)),
    ("host_action_protocol", re.compile(r"(?:osc://|/live/|\bload_item\b|\bset_device_parameter\b)", re.IGNORECASE)),
)


def _text(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    return value.strip() if isinstance(value, str) else ""


def _first_text(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    return item.strip()
    return ""


def prepare_text_record(
    raw: dict[str, Any],
    *,
    dataset_id: str,
    dataset_revision: str,
    hub_url: str,
    declared_license: str,
    use_classification: str,
    lane: str,
    ordinal: int = 0,
) -> dict[str, Any]:
    """Map a common caption/QA row to KENN's text-only record schema.

    This function only maps fields; it does not approve a dataset, retrieve
    media, or infer an Ableton action.  The resulting record must still pass
    :func:`validate_record` and the candidate-registry gate.
    """
    if not isinstance(raw, dict):
        raise ValueError("raw dataset row must be a JSON object")
    dataset_id = dataset_id.strip()
    dataset_revision = dataset_revision.strip()
    hub_url = hub_url.strip()
    declared_license = declared_license.strip()
    use_classification = use_classification.strip()
    lane = lane.strip()
    if not dataset_id or not dataset_revision or not hub_url or not declared_license:
        raise ValueError("dataset_id, dataset_revision, hub_url, and declared_license are required")
    if dataset_revision.lower() in {"main", "master", "latest"} or "pin immutable" in dataset_revision.lower():
        raise ValueError("dataset_revision must be an immutable pinned revision")
    if not hub_url.startswith("https://huggingface.co/datasets/"):
        raise ValueError("hub_url must be a Hugging Face dataset URL")
    source_record_id = _first_text(raw, ("source_record_id", "record_id", "id", "ytid", "source_id"))
    if not source_record_id:
        raise ValueError("raw dataset row must contain a source record id")
    input_text = _first_text(raw, ("input_text", "question", "instruction", "prompt", "input"))
    target_text = _first_text(raw, ("target_text", "answer", "output", "response", "caption", "text"))
    if not input_text and target_text:
        input_text = "Describe or explain the supplied music example."
    if not target_text:
        aspects = raw.get("aspect_list")
        if isinstance(aspects, list):
            labels = [item.strip() for item in aspects if isinstance(item, str) and item.strip()]
            if labels:
                target_text = "Aspects: " + ", ".join(labels)
    if not input_text and target_text:
        input_text = "Describe or explain the supplied music example."
    if not input_text or not target_text:
        raise ValueError("raw dataset row must contain text fields that map to input_text and target_text")
    kind = "caption" if _text(raw, "caption") else "qa" if _text(raw, "question") else "instruction" if _text(raw, "instruction") else "metadata"
    record_id = f"{dataset_id}:{source_record_id}:{ordinal}" if ordinal else f"{dataset_id}:{source_record_id}"
    return {
        "schema": SCHEMA,
        "record_id": record_id,
        "dataset_id": dataset_id,
        "dataset_revision": dataset_revision,
        "hub_url": hub_url,
        "source_record_id": source_record_id,
        "lane": lane,
        "record_kind": kind,
        "input_text": input_text,
        "target_text": target_text,
        "declared_license": declared_license,
        "use_classification": use_classification,
        "external": True,
        "control_supervision": False,
        "source_media_retained": False,
        "review_status": "unreviewed",
        "preparation_method": "text_only_field_mapping",
    }


def validate_record(record: Any, *, manifest: dict[str, Any] | None = None) -> list[str]:
    """Return bounded, non-secret validation errors for one external record."""
    if not isinstance(record, dict):
        return ["record must be a JSON object"]
    identifier = _text(record, "record_id") or "<missing-record-id>"
    errors: list[str] = []
    required = (
        "schema",
        "record_id",
        "dataset_id",
        "dataset_revision",
        "hub_url",
        "source_record_id",
        "lane",
        "record_kind",
        "input_text",
        "target_text",
        "declared_license",
        "use_classification",
        "external",
        "control_supervision",
        "source_media_retained",
        "review_status",
    )
    missing = [key for key in required if key not in record]
    if missing:
        errors.append(f"{identifier}: missing fields: {', '.join(missing)}")
        return errors
    if record.get("schema") != SCHEMA:
        errors.append(f"{identifier}: unsupported schema")
    dataset_id = _text(record, "dataset_id")
    revision = _text(record, "dataset_revision")
    hub_url = _text(record, "hub_url")
    if not dataset_id:
        errors.append(f"{identifier}: dataset_id is required")
    if not revision or revision.lower() in {"main", "master", "latest"}:
        errors.append(f"{identifier}: dataset_revision must be an immutable pinned revision")
    if not hub_url.startswith("https://huggingface.co/datasets/"):
        errors.append(f"{identifier}: hub_url must be a Hugging Face dataset URL")
    if not _text(record, "source_record_id"):
        errors.append(f"{identifier}: source_record_id is required")
    lane = _text(record, "lane")
    if lane not in LANES:
        errors.append(f"{identifier}: unsupported lane {lane!r}")
    kind = _text(record, "record_kind")
    if kind not in RECORD_KINDS:
        errors.append(f"{identifier}: unsupported record_kind {kind!r}")
    for field in ("input_text", "target_text"):
        value = _text(record, field)
        if not value:
            errors.append(f"{identifier}: {field} is required")
        elif len(value) > MAX_TEXT_CHARS:
            errors.append(f"{identifier}: {field} exceeds the {MAX_TEXT_CHARS}-character bound")
        elif any(ord(char) < 32 and char not in "\n\t\r" for char in value):
            errors.append(f"{identifier}: {field} contains a control character")
        for marker_name, pattern in SUSPICIOUS_MARKERS:
            if pattern.search(value):
                errors.append(f"{identifier}: {field} contains {marker_name} material")
    if not _text(record, "declared_license"):
        errors.append(f"{identifier}: declared_license is required")
    use_classification = _text(record, "use_classification")
    if not use_classification:
        errors.append(f"{identifier}: use_classification is required")
    elif use_classification not in USE_CLASSES:
        errors.append(f"{identifier}: unsupported use_classification {use_classification!r}")
    if record.get("external") is not True:
        errors.append(f"{identifier}: external must be true")
    if record.get("control_supervision") is not False:
        errors.append(f"{identifier}: external records cannot provide Ableton control supervision")
    if record.get("source_media_retained") is not False:
        errors.append(f"{identifier}: text-only intake cannot retain source media")
    review_status = _text(record, "review_status")
    if review_status not in REVIEW_STATUSES:
        errors.append(f"{identifier}: unsupported review_status {review_status!r}")
    elif review_status == "rejected":
        errors.append(f"{identifier}: record is marked rejected")
    if manifest is not None and not errors:
        candidates = manifest.get("candidates") or []
        candidate = next((item for item in candidates if isinstance(item, dict) and item.get("id") == dataset_id), None)
        if candidate is None:
            errors.append(f"{identifier}: dataset is not present in the reviewed candidate registry")
        else:
            if candidate.get("hub_url") != hub_url:
                errors.append(f"{identifier}: hub_url does not match the registry")
            if candidate.get("hub_revision") != revision:
                errors.append(f"{identifier}: revision does not match the registry's pinned revision")
            if candidate.get("download_allowed") is not True:
                errors.append(f"{identifier}: dataset is not intake-approved for staging")
            if candidate.get("training_allowed") is not True:
                errors.append(f"{identifier}: dataset is not approved for training")
    return errors


def audit_records(records: list[Any], *, manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    """Audit records and return a report containing ids/errors, never raw text."""
    errors: list[str] = []
    record_ids: set[str] = set()
    lane_counts: Counter[str] = Counter()
    accepted = 0
    for record in records:
        if isinstance(record, dict):
            record_id = _text(record, "record_id")
            if record_id:
                if record_id in record_ids:
                    errors.append(f"{record_id}: duplicate record_id")
                record_ids.add(record_id)
            lane = _text(record, "lane")
            if lane:
                lane_counts[lane] += 1
        record_errors = validate_record(record, manifest=manifest)
        if record_errors:
            errors.extend(record_errors)
        else:
            accepted += 1
    return {
        "schema": "kenn.external_dataset_audit.v1",
        "record_count": len(records),
        "accepted_count": accepted,
        "rejected_count": len(records) - accepted,
        "lanes": dict(sorted(lane_counts.items())),
        "control_supervision_allowed": False,
        "raw_media_retained": False,
        "errors": errors,
        "ok": not errors,
    }
