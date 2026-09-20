"""Explicit, atomic promotion of a qualified staged retrieval-index candidate."""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from kenn.core.retrieval_index_candidate import candidate_version_dir, inspect_candidate
from kenn.retrieval.index_store import (
    CURRENT_FILENAME,
    PREVIOUS_FILENAME,
    VERSIONS_DIRNAME,
    IndexValidationError,
    active_version_dir,
    promotion_lock,
    validate_version,
)


def _write_pointer(index_root: Path, filename: str, version_id: str) -> None:
    temporary = index_root / f".{filename}.{os.getpid()}.tmp"
    try:
        temporary.write_text(f"{version_id}\n", encoding="ascii")
        os.replace(temporary, index_root / filename)
    finally:
        temporary.unlink(missing_ok=True)


def promote_candidate(
    candidate_root: Path,
    target_root: Path,
    *,
    expected_manual_sha256: str,
    expected_manual_filename: str = "live12-manual-en.pdf",
    apply: bool = False,
) -> dict[str, Any]:
    """Qualify then atomically promote a candidate only when ``apply`` is true.

    No versions are pruned.  The prior target version remains available through
    PREVIOUS, so a rollback can be performed without a rebuild.
    """
    preflight = inspect_candidate(
        candidate_root,
        expected_manual_sha256=expected_manual_sha256,
        expected_manual_filename=expected_manual_filename,
    )
    report: dict[str, Any] = {
        "schema": "kenn.retrieval_index_candidate_promotion.v1",
        "preflight": preflight,
        "target_root": str(target_root),
        "applied": False,
    }
    if not preflight["promotion_eligible"]:
        report.update({"status": "preflight_rejected", "errors": ["Candidate did not pass preflight."]})
        return report
    if candidate_root.resolve() == target_root.resolve():
        report.update({"status": "rejected", "errors": ["Candidate and target roots must differ."]})
        return report

    candidate_version = candidate_version_dir(candidate_root)
    candidate_manifest = validate_version(candidate_version)
    target_current = active_version_dir(target_root)
    report.update(
        {
            "candidate_version_id": candidate_version.name,
            "target_current_version_id": target_current.name if target_current else None,
            "would_set_current_version_id": candidate_version.name,
        }
    )
    if not apply:
        report["status"] = "dry_run_verified"
        return report

    target_root.mkdir(parents=True, exist_ok=True)
    target_versions = target_root / VERSIONS_DIRNAME
    target_version = target_versions / candidate_version.name
    with promotion_lock(target_root):
        prior = active_version_dir(target_root)
        target_versions.mkdir(parents=True, exist_ok=True)
        if target_version.exists():
            existing = validate_version(target_version)
            if existing.get("content_sha256") != candidate_manifest.get("content_sha256"):
                raise IndexValidationError("Target already has this version ID with different content.")
        else:
            staging = target_versions / f".staging-{candidate_version.name}-{os.getpid()}"
            shutil.rmtree(staging, ignore_errors=True)
            try:
                shutil.copytree(candidate_version, staging)
                copied = validate_version(staging)
                if copied.get("content_sha256") != candidate_manifest.get("content_sha256"):
                    raise IndexValidationError("Copied candidate content hash differs from source.")
                staging.rename(target_version)
            except Exception:
                shutil.rmtree(staging, ignore_errors=True)
                raise
        if prior is not None and prior.name != candidate_version.name:
            _write_pointer(target_root, PREVIOUS_FILENAME, prior.name)
        _write_pointer(target_root, CURRENT_FILENAME, candidate_version.name)
    report.update({"status": "promoted", "applied": True})
    return report
