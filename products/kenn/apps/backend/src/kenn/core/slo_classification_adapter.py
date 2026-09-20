"""Read-only presentation adapter for SLO's local classification cache.

SLO remains the classification owner.  This module deliberately exposes only
presentation-safe fields and opens SQLite with ``mode=ro`` so KENN cannot
create, migrate, or mutate the cache.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

SCHEMA = "kenn.slo-classifications/v1"
DEFAULT_LIMIT = 100
MAX_LIMIT = 500
CURRENT_TAXONOMY_VERSION = 5

_SELECT = """
SELECT path, category, subcategory, secondary_tags, tag_confidence,
       tag_source, tag_user_overridden, winning_evidence,
       classification_model_version, taxonomy_version
FROM sample_cache
ORDER BY path
"""


class SloClassificationUnavailable(RuntimeError):
    """Raised when the read-only SLO cache cannot be queried safely."""


def configured_cache_path() -> Path:
    override = os.environ.get("SLO_CLASSIFICATION_DB", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "Application Support" / "SmartSampleManager" / "sample_cache.sqlite3"


def _opaque_id(path: str) -> str:
    return hashlib.sha256(path.encode("utf-8", errors="surrogatepass")).hexdigest()[:24]


def _tags(value: Any) -> list[str]:
    if value is None:
        return []
    return [part.strip() for part in str(value).split("|") if part.strip()]


def _confidence(value: Any) -> float:
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _evidence_label(tag_source: str, winning_evidence: str) -> str:
    if tag_source == "user" or winning_evidence == "USER_OVERRIDE":
        return "user override"
    if tag_source == "ml_ood":
        return "OOD abstention"
    if tag_source == "physics" or winning_evidence == "PHYSICS":
        return "physical acoustics"
    if tag_source == "ml_v3":
        return "audio model"
    return {
        "EMBEDDED_METADATA": "metadata-assisted",
        "FILENAME": "filename heuristic",
        "FOLDER": "folder heuristic",
        "DSP": "audio-only",
    }.get(winning_evidence, "not run" if tag_source == "unclassified" else "unknown")


def _uncertainty_reason(tag_source: str, winning_evidence: str, confidence: float) -> str | None:
    if tag_source == "user" or winning_evidence == "USER_OVERRIDE":
        return None
    if tag_source == "unclassified":
        return "not analysed"
    if tag_source == "ml_ood":
        return "outside the known audio domain"
    if confidence < 0.5:
        return "weak evidence agreement"
    if winning_evidence in {"FILENAME", "FOLDER"}:
        return "name or folder evidence only"
    if confidence < 0.75:
        return "mixed evidence"
    return None


def _row_to_item(row: sqlite3.Row) -> dict[str, Any]:
    path = str(row["path"] or "")
    category = str(row["category"] or "")
    subcategory = str(row["subcategory"] or "")
    instrument_fallback = ""
    source = str(row["tag_source"] or "unclassified")
    evidence = str(row["winning_evidence"] or "UNKNOWN")
    confidence = _confidence(row["tag_confidence"])
    taxonomy_version = int(row["taxonomy_version"] or 0)
    user_overridden = bool(row["tag_user_overridden"])
    stale = not user_overridden and 0 < taxonomy_version < CURRENT_TAXONOMY_VERSION
    missing = source == "unclassified" or taxonomy_version == 0
    review_required = source == "ml_ood" or stale or missing

    if source == "ml_ood":
        primary_label = "Needs review"
    else:
        primary_label = subcategory or category or instrument_fallback or "Unclassified"

    return {
        "id": _opaque_id(path),
        "display_name": Path(path).name or "Unnamed sample",
        "category": category,
        "subcategory": subcategory,
        "tags": _tags(row["secondary_tags"]),
        "confidence": confidence,
        "primary_label": primary_label,
        "review_required": review_required,
        "uncertainty_reason": _uncertainty_reason(source, evidence, confidence),
        "evidence_source": _evidence_label(source, evidence),
        "winning_evidence": evidence,
        "model_version": int(row["classification_model_version"] or 0),
        "taxonomy_version": taxonomy_version,
        "user_overridden": user_overridden,
        "classification_state": "missing" if missing else "stale" if stale else "ready",
    }


def _read_rows(cache_path: Path) -> list[sqlite3.Row]:
    if not cache_path.is_file():
        raise SloClassificationUnavailable("SLO classification cache is not available.")
    uri = f"file:{quote(str(cache_path), safe='/')}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=1.0)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA query_only = ON")
            return list(connection.execute(_SELECT))
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise SloClassificationUnavailable("SLO classification cache could not be read.") from exc


def _matches(item: dict[str, Any], query: str, category: str, needs_review: bool | None) -> bool:
    if category and item["category"].casefold() != category.casefold():
        return False
    if needs_review is not None and item["review_required"] is not needs_review:
        return False
    if query:
        haystack: Iterable[str] = (
            item["display_name"], item["primary_label"], item["category"],
            item["subcategory"], *item["tags"],
        )
        if query.casefold() not in " ".join(haystack).casefold():
            return False
    return True


def list_classifications(
    *, cache_path: Path | None = None, query: str = "", category: str = "",
    needs_review: bool | None = None, limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    safe_limit = min(MAX_LIMIT, max(1, int(limit)))
    all_items = [_row_to_item(row) for row in _read_rows(cache_path or configured_cache_path())]
    filtered = [item for item in all_items if _matches(item, query, category, needs_review)]
    items = filtered[:safe_limit]
    return {
        "schema": SCHEMA,
        "status": "ready",
        "items": items,
        "summary": {
            "total": len(filtered),
            "returned": len(items),
            "needs_review": sum(bool(item["review_required"]) for item in filtered),
            "stale": sum(item["classification_state"] == "stale" for item in filtered),
        },
    }


def get_classification(sample_id: str, *, cache_path: Path | None = None) -> dict[str, Any] | None:
    if not sample_id or len(sample_id) != 24:
        return None
    for row in _read_rows(cache_path or configured_cache_path()):
        item = _row_to_item(row)
        if item["id"] == sample_id:
            return {"schema": SCHEMA, "status": "ready", "item": item}
    return None
