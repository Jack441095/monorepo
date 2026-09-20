"""Licence-aware intake checks for external training datasets.

The manifest is deliberately a registry of candidates, not a downloader.  An
external dataset must pass provenance and use-policy checks before another
pipeline is allowed to stage it.  In particular, third-party data can never
become direct Ableton-control supervision through this module.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_MANIFEST = Path(__file__).with_name("huggingface_dataset_candidates.json")
SCHEMA = "kenn.huggingface_dataset_manifest.v1"
LANES = frozenset({"knowledge", "perception", "symbolic", "evaluation"})
USE_CLASSES = frozenset({"commercial", "research_only", "evaluation_only", "blocked"})
STATUSES = frozenset({"candidate", "approved_research", "approved_commercial", "evaluation_only", "blocked"})


class DatasetManifestError(ValueError):
    """Raised when the external dataset registry violates the intake policy."""


def _text(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    return value.strip() if isinstance(value, str) else ""


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    """Load and validate a candidate manifest without touching external state."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetManifestError(f"Cannot read dataset manifest {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DatasetManifestError("Dataset manifest must be a JSON object.")
    if payload.get("schema") != SCHEMA:
        raise DatasetManifestError(f"Unsupported dataset manifest schema: {payload.get('schema')!r}")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise DatasetManifestError("Dataset manifest candidates must be an array.")
    validate_candidates(candidates)
    return payload


def validate_candidates(candidates: list[Any]) -> None:
    """Enforce the no-download/no-control policy for registry entries."""
    seen: set[str] = set()
    required = (
        "id",
        "hub_url",
        "hub_revision",
        "lane",
        "source_kinds",
        "declared_license",
        "underlying_terms",
        "use_classification",
        "status",
        "external",
        "download_allowed",
        "training_allowed",
    )
    for position, candidate in enumerate(candidates, start=1):
        if not isinstance(candidate, dict):
            raise DatasetManifestError(f"Candidate {position} must be a JSON object.")
        missing = [key for key in required if key not in candidate]
        if missing:
            raise DatasetManifestError(f"Candidate {position} is missing fields: {', '.join(missing)}")
        identifier = _text(candidate, "id")
        if not identifier:
            raise DatasetManifestError(f"Candidate {position} has an empty id.")
        if identifier in seen:
            raise DatasetManifestError(f"Duplicate dataset candidate id: {identifier}")
        seen.add(identifier)
        hub_url = _text(candidate, "hub_url")
        if not hub_url.startswith("https://huggingface.co/datasets/"):
            raise DatasetManifestError(f"{identifier}: hub_url must be a Hugging Face dataset URL.")
        if not _text(candidate, "hub_revision"):
            raise DatasetManifestError(f"{identifier}: hub_revision is required; do not use an implicit latest revision.")
        lane = _text(candidate, "lane")
        if lane not in LANES:
            raise DatasetManifestError(f"{identifier}: unsupported lane {lane!r}.")
        source_kinds = candidate.get("source_kinds")
        if not isinstance(source_kinds, list) or not source_kinds or not all(isinstance(item, str) and item.strip() for item in source_kinds):
            raise DatasetManifestError(f"{identifier}: source_kinds must be a non-empty string array.")
        for key in ("declared_license", "underlying_terms"):
            if not _text(candidate, key):
                raise DatasetManifestError(f"{identifier}: {key} must be explicit; unknown terms are blocked.")
        use_classification = _text(candidate, "use_classification")
        if use_classification not in USE_CLASSES:
            raise DatasetManifestError(f"{identifier}: unsupported use classification {use_classification!r}.")
        status = _text(candidate, "status")
        if status not in STATUSES:
            raise DatasetManifestError(f"{identifier}: unsupported status {status!r}.")
        if candidate.get("external") is not True:
            raise DatasetManifestError(f"{identifier}: external candidates must set external=true.")
        if candidate.get("download_allowed") is not False:
            raise DatasetManifestError(f"{identifier}: downloads remain disabled until a separate intake approval.")
        if candidate.get("training_allowed") is not False:
            raise DatasetManifestError(f"{identifier}: training remains disabled until a separate intake approval.")
        if lane == "evaluation" and use_classification != "evaluation_only":
            raise DatasetManifestError(f"{identifier}: evaluation lane must be evaluation_only.")
        if use_classification == "blocked" and status != "blocked":
            raise DatasetManifestError(f"{identifier}: blocked use must have blocked status.")
        # External data is never accepted as the direct command-control lane.
        if lane == "knowledge" and candidate.get("control_supervision") is True:
            raise DatasetManifestError(f"{identifier}: knowledge data cannot provide Ableton control supervision.")


def audit_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a bounded summary suitable for CI or a human review packet."""
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise DatasetManifestError("Dataset manifest candidates must be an array.")
    validate_candidates(candidates)
    lane_counts = Counter(_text(row, "lane") for row in candidates)
    use_counts = Counter(_text(row, "use_classification") for row in candidates)
    status_counts = Counter(_text(row, "status") for row in candidates)
    return {
        "schema": "kenn.huggingface_dataset_audit.v1",
        "candidate_count": len(candidates),
        "external_count": sum(row.get("external") is True for row in candidates),
        "download_allowed_count": sum(row.get("download_allowed") is True for row in candidates),
        "training_allowed_count": sum(row.get("training_allowed") is True for row in candidates),
        "lanes": dict(sorted(lane_counts.items())),
        "use_classifications": dict(sorted(use_counts.items())),
        "statuses": dict(sorted(status_counts.items())),
        "control_supervision_allowed": False,
        "source_revision_policy": "pin an immutable Hub revision before any staging",
    }

