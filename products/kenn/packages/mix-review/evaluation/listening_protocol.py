"""Metadata-only gate for rights-cleared blind Mix Review listening."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


SCHEMA = "kenn.mix_review.listening_manifest.v1"
PRODUCT_STATUSES = {"awaiting_owner_approval", "ready_for_review", "completed"}


def _has_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_timezone_aware_timestamp(value: Any) -> bool:
    if not _has_text(value):
        return False
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _outside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return True
    return False


def evaluate_manifest_readiness(manifest: dict[str, Any], *, product_root: Path) -> dict[str, Any]:
    """Validate only manifest metadata; never opens a case or audio file."""
    errors: list[str] = []
    if manifest.get("schema") != SCHEMA:
        errors.append("schema must be kenn.mix_review.listening_manifest.v1")
    if manifest.get("status") not in PRODUCT_STATUSES:
        errors.append("status is not a recognised listening-manifest state")
    rights = manifest.get("rights") if isinstance(manifest.get("rights"), dict) else {}
    if rights.get("rights_cleared") is not True:
        errors.append("rights_cleared must be true")
    if rights.get("owner_approved") is not True:
        errors.append("owner_approved must be true")
    if not _has_text(rights.get("consent_reference")):
        errors.append("consent_reference is required")
    source_root = manifest.get("source_root")
    if manifest.get("status") != "awaiting_owner_approval":
        for field in ("approval_reference", "approved_by"):
            if not _has_text(rights.get(field)):
                errors.append(f"{field} is required once review is ready")
        if not _has_text(rights.get("reviewed_at")):
            errors.append("reviewed_at is required once review is ready")
        elif not _is_timezone_aware_timestamp(rights.get("reviewed_at")):
            errors.append("reviewed_at must be an ISO-8601 timestamp with timezone")
        protocol = manifest.get("protocol") if isinstance(manifest.get("protocol"), dict) else {}
        if protocol.get("audio_opening_authorized") is not True:
            errors.append("audio_opening_authorized must be true once review is ready")
        if not _has_text(protocol.get("plan_hash")):
            errors.append("plan_hash is required once review is ready")
        if not source_root:
            errors.append("source_root is required once review is ready")
        else:
            source = Path(str(source_root)).expanduser()
            if not source.is_absolute():
                errors.append("source_root must be absolute and external")
            elif not _outside(source, product_root):
                errors.append("source_root must be outside the product checkout")
    cases = manifest.get("cases") if isinstance(manifest.get("cases"), list) else []
    case_ids = [item.get("case_id") for item in cases if isinstance(item, dict)]
    if len(case_ids) != len(cases) or any(not str(case_id).strip() for case_id in case_ids):
        errors.append("every case requires a case_id")
    if len(set(case_ids)) != len(case_ids):
        errors.append("case_id values must be unique")
    ready = not errors and manifest.get("status") == "ready_for_review" and bool(cases)
    return {
        "schema": "kenn.mix_review.listening_readiness.v1",
        "ready_for_execution": ready,
        "case_count": len(cases),
        "errors": errors,
        "audio_opened": False,
    }


def load_manifest(path: Path, *, product_root: Path) -> dict[str, Any]:
    """Load and gate a JSON manifest without traversing its source_root."""
    manifest = json.loads(path.read_text(encoding="utf-8"))
    readiness = evaluate_manifest_readiness(manifest, product_root=product_root)
    return {"manifest": manifest, "readiness": readiness}
