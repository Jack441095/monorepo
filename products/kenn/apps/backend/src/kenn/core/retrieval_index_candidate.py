"""Read-only qualification for a staged retrieval-index candidate.

This deliberately does not call ``promote_index`` or write pointer files.  It
is the gate used before a manually reviewed candidate may be promoted by a
separate, explicitly authorized release operation.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from kenn.retrieval.index_store import IndexValidationError, VERSIONS_DIRNAME, validate_version


SCHEMA = "kenn.retrieval_index_candidate_inspection.v1"
_VERSION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
OFFICIAL_MANUAL_EVIDENCE_CLASS = "official_ableton_manual"


def candidate_version_dir(candidate_root: Path) -> Path:
    """Resolve only CURRENT; a candidate must never silently fall back."""
    try:
        version_id = (candidate_root / "CURRENT").read_text(encoding="ascii").strip()
    except OSError as exc:
        raise IndexValidationError("Candidate has no readable CURRENT pointer.") from exc
    if not _VERSION_RE.fullmatch(version_id):
        raise IndexValidationError("Candidate CURRENT pointer is invalid.")
    version_dir = candidate_root / VERSIONS_DIRNAME / version_id
    manifest = validate_version(version_dir)
    if manifest.get("version_id") != version_id:
        raise IndexValidationError("Candidate manifest version does not match CURRENT.")
    return version_dir


def _manifest_sha256(version_dir: Path) -> str:
    return hashlib.sha256((version_dir / "manifest.json").read_bytes()).hexdigest()


def inspect_candidate(
    candidate_root: Path,
    *,
    expected_manual_sha256: str,
    expected_manual_filename: str = "live12-manual-en.pdf",
) -> dict[str, Any]:
    """Return an auditable, non-mutating verdict for a staged candidate."""
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "candidate_root": str(candidate_root),
        "promotion_eligible": False,
        "status": "rejected",
        "errors": [],
    }
    if not re.fullmatch(r"[0-9a-f]{64}", expected_manual_sha256.lower()):
        report["errors"].append("Expected manual SHA-256 must be 64 hexadecimal characters.")
        return report

    try:
        version_dir = candidate_version_dir(candidate_root)
        manifest = validate_version(version_dir)
        chunks = [
            json.loads(line)
            for line in (version_dir / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError, IndexValidationError) as exc:
        report["errors"].append(str(exc))
        return report

    report.update(
        {
            "version_id": version_dir.name,
            "content_sha256": manifest.get("content_sha256"),
            "manifest_sha256": _manifest_sha256(version_dir),
            "chunk_count": len(chunks),
        }
    )
    build = manifest.get("build")
    source_manifest = build.get("source_manifest") if isinstance(build, dict) else None
    sources = source_manifest.get("sources") if isinstance(source_manifest, dict) else None
    if not isinstance(sources, list):
        report["errors"].append("Candidate has no build source manifest.")
        return report

    matching_sources = [
        source for source in sources
        if isinstance(source, dict)
        and str(source.get("kind") or "") == "manual"
        and Path(str(source.get("path") or "")).name == expected_manual_filename
    ]
    expected_sha = expected_manual_sha256.lower()
    matching_sources = [
        source for source in matching_sources
        if str(source.get("sha256") or "").lower() == expected_sha
    ]
    if len(matching_sources) != 1:
        report["errors"].append("Candidate source manifest does not bind exactly one expected manual.")
        return report

    manual_source = str(matching_sources[0]["path"])
    official_chunk_count = sum(
        1
        for chunk in chunks
        if isinstance(chunk, dict)
        and str(chunk.get("evidence_class") or "") == OFFICIAL_MANUAL_EVIDENCE_CLASS
        and str(chunk.get("kind") or "") == "manual"
        # build_index stores a repository-relative source in the manifest but
        # the compact retrieval chunk stores its basename.  Compare the latter
        # to the already hash-bound manifest source, rather than requiring two
        # different storage representations to be byte-identical.
        and Path(str(chunk.get("source") or "")).name == Path(manual_source).name
    )
    report.update(
        {
            "manual_source": manual_source,
            "manual_sha256": expected_sha,
            "official_manual_chunk_count": official_chunk_count,
        }
    )
    if official_chunk_count <= 0:
        report["errors"].append("Candidate has no official-manual chunks bound to the expected manual.")
        return report

    report.update({"status": "verified", "promotion_eligible": True})
    return report
