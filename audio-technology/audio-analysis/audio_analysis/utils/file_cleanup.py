"""Intelligent file cleanup for mix review uploads.

Manages the lifecycle of uploaded audio files:
  - Deletes original uploads immediately after successful analysis
    (the report JSON retains all extracted information)
  - Provides configurable retention for reference audio
  - Can be triggered by agents or run as a maintenance task
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

CLEANUP_POLICY_AFTER_ANALYSIS = "delete_after_analysis"
CLEANUP_POLICY_KEEP_REFERENCE = "keep_reference"
CLEANUP_POLICY_KEEP_ALL = "keep_all"
CLEANUP_POLICY_AGE_BASED = "age_based"


def delete_uploaded_audio(
    review_id: str, *, upload_root: Path, connect_func: Callable[..., object]
) -> bool:
    """Delete the uploaded audio file for a given review.

    Called after a successful analysis. The report JSON retains all
    extracted metrics, so the original upload is no longer needed.

    Returns True if files were removed, False if nothing to delete.
    """
    files_removed = False
    try:
        with connect_func() as conn:
            row = conn.execute(
                "SELECT stored_name FROM mix_reviews WHERE id = ? LIMIT 1",
                (review_id,),
            ).fetchone()

        if not row:
            return False

        stored_name = str(row["stored_name"] or "").strip()
        if stored_name:
            path = upload_root / stored_name
            if path.exists():
                path.unlink()
                files_removed = True
                logger.info("Deleted uploaded audio: %s", path)

        # Also delete associated reference upload
        ref_pattern = f"{review_id}_reference_*"
        for ref_path in upload_root.glob(ref_pattern):
            if ref_path.exists():
                ref_path.unlink()
                files_removed = True
                logger.info("Deleted reference upload: %s", ref_path)

    except Exception as exc:
        logger.warning("Failed to delete uploads for %s: %s", review_id, exc)

    return files_removed


def cleanup_after_analysis(
    review_id: str,
    *,
    upload_root: Path,
    connect_func: Callable,
    keep_reference: bool = False,
) -> dict:
    """Clean up uploaded audio files after a successful analysis.

    This should be called at the end of the analysis workflow, after
    the report JSON has been saved and the summary cache populated.

    Args:
        review_id: The review to clean up after.
        upload_root: Path to the uploads directory.
        connect_func: Database connection factory (e.g. `connect` from db).
        keep_reference: If True, keep the reference audio file.

    Returns:
        Dict with keys: ok, deleted_mix, deleted_reference, errors.
    """
    result = {"ok": True, "deleted_mix": False, "deleted_reference": False, "errors": []}

    try:
        with connect_func() as conn:
            row = conn.execute(
                "SELECT stored_name FROM mix_reviews WHERE id = ? LIMIT 1",
                (review_id,),
            ).fetchone()

        if not row:
            return {"ok": True, "deleted_mix": False, "deleted_reference": False,
                    "errors": [f"Review {review_id} not found in database."]}

        stored_name = str(row["stored_name"] or "").strip()
        if stored_name:
            path = upload_root / stored_name
            if path.exists():
                path.unlink()
                result["deleted_mix"] = True
                logger.info("Deleted upload for %s: %s", review_id, path.name)

        # Reference audio — only delete if not keeping it
        if not keep_reference:
            ref_pattern = f"{review_id}_reference_*"
            for ref_path in upload_root.glob(ref_pattern):
                if ref_path.exists():
                    ref_path.unlink()
                    result["deleted_reference"] = True
                    logger.info("Deleted reference upload for %s: %s", review_id, ref_path.name)

    except Exception as exc:
        logger.exception("Cleanup failed for %s", review_id)
        result["ok"] = False
        result["errors"].append(str(exc))

    return result


def cleanup_all_uploads(
    *,
    upload_root: Path,
    connect_func: Callable,
    policy: str = CLEANUP_POLICY_AFTER_ANALYSIS,
    older_than_days: int = 30,
    dry_run: bool = False,
) -> dict:
    """Clean up uploaded audio files across all reviews.

    Policies:
      - delete_after_analysis: Delete all uploaded audio files (default).
        Reports already contain all data.
      - keep_reference: Delete mix uploads but keep reference files.
      - keep_all: Do not delete anything (safety override).
      - age_based: Delete uploads older than older_than_days.

    Args:
        upload_root: Path to the uploads directory.
        connect_func: Database connection factory.
        policy: Cleanup policy to apply.
        older_than_days: Only relevant for age_based policy.
        dry_run: If True, only report what would be deleted.

    Returns:
        Summary dict with counts and details.
    """
    if policy == CLEANUP_POLICY_KEEP_ALL:
        return {
            "ok": True,
            "policy": policy,
            "deleted_mix": 0,
            "deleted_reference": 0,
            "skipped": 0,
            "errors": [],
            "note": "Policy set to keep_all — nothing deleted.",
        }

    now = datetime.now(timezone.utc)
    deleted_mix = 0
    deleted_reference = 0
    skipped = 0
    errors = []

    try:
        with connect_func() as conn:
            rows = conn.execute(
                "SELECT id, stored_name, created_at FROM mix_reviews ORDER BY created_at ASC"
            ).fetchall()

        for row in rows:
            review_id = str(row["id"] or "").strip()
            stored_name = str(row["stored_name"] or "").strip()

            # Age check for age_based policy
            if policy == CLEANUP_POLICY_AGE_BASED and row["created_at"]:
                try:
                    created = datetime.fromisoformat(str(row["created_at"]))
                    if created > now - timedelta(days=older_than_days):
                        skipped += 1
                        continue
                except (ValueError, TypeError):
                    pass

            # Delete review's uploaded audio
            if stored_name:
                path = upload_root / stored_name
                if path.exists():
                    if not dry_run:
                        try:
                            path.unlink()
                            deleted_mix += 1
                        except OSError as exc:
                            errors.append(f"{review_id}/mix: {exc}")
                    else:
                        deleted_mix += 1

            # Handle reference uploads
            keep_ref = policy == CLEANUP_POLICY_KEEP_REFERENCE
            if not keep_ref:
                ref_pattern = f"{review_id}_reference_*"
                for ref_path in upload_root.glob(ref_pattern):
                    if ref_path.exists():
                        if not dry_run:
                            try:
                                ref_path.unlink()
                                deleted_reference += 1
                            except OSError as exc:
                                errors.append(f"{review_id}/reference: {exc}")
                        else:
                            deleted_reference += 1

    except Exception as exc:
        logger.exception("Bulk cleanup failed")
        return {
            "ok": False,
            "policy": policy,
            "deleted_mix": deleted_mix,
            "deleted_reference": deleted_reference,
            "errors": [str(exc)],
        }

    return {
        "ok": True,
        "policy": policy,
        "dry_run": dry_run,
        "deleted_mix": deleted_mix,
        "deleted_reference": deleted_reference,
        "skipped": skipped,
        "errors": errors,
    }


def cleanup_orphaned_uploads(
    *,
    upload_root: Path,
    connect_func: Callable,
    dry_run: bool = False,
) -> dict:
    """Remove uploaded files that have no matching database record.

    These accumulate from failed uploads that never completed the DB
    insert, or from incomplete cleanup. This is the "deep clean" that
    gets rid of the 9-byte corrupt files.

    Returns a dict with ok, deleted_count, errors.
    """
    deleted = 0
    errors = []

    try:
        with connect_func() as conn:
            known_stored = {
                str(r["stored_name"])
                for r in conn.execute(
                    "SELECT stored_name FROM mix_reviews WHERE stored_name IS NOT NULL"
                ).fetchall()
            }
    except Exception as exc:
        return {"ok": False, "deleted": 0, "errors": [str(exc)]}

    for path in sorted(upload_root.iterdir()):
        if not path.is_file():
            continue

        # A file is orphaned if its name isn't in the known list
        # Known files follow pattern: {review_id}_{original_name}
        in_database = False
        for known in known_stored:
            if path.name == known:
                in_database = True
                break
            # Also check reference patterns: {review_id}_reference_*
            if path.name.startswith("_reference_") and path.name[len("_reference_"):] in known_stored:
                in_database = True
                break

        if not in_database:
            if not dry_run:
                try:
                    path.unlink()
                    deleted += 1
                    logger.info("Deleted orphaned upload: %s", path.name)
                except OSError as exc:
                    errors.append(f"{path.name}: {exc}")
            else:
                deleted += 1

    return {
        "ok": errors == [],
        "dry_run": dry_run,
        "deleted": deleted,
        "errors": errors,
    }


def cleanup_single_review(
    review_id: str,
    *,
    upload_root: Path,
    report_root: Path,
    connect_func: Callable,
    delete_report: bool = False,
    dry_run: bool = False,
) -> dict:
    """Clean up all files for a single review.

    Used by the delete API endpoint and agents.

    Args:
        review_id: The review to clean up.
        upload_root: Uploads directory.
        report_root: Reports directory.
        connect_func: DB connection factory.
        delete_report: If True, also delete the report JSON (default keeps it).
        dry_run: If True, only report what would be deleted.

    Returns:
        Dict with ok, deleted_upload, deleted_report, errors.
    """
    result = {
        "ok": True,
        "deleted_upload": False,
        "deleted_report": False,
        "deleted_reference": False,
        "errors": [],
    }

    try:
        with connect_func() as conn:
            row = conn.execute(
                "SELECT stored_name, report_name FROM mix_reviews WHERE id = ? LIMIT 1",
                (review_id,),
            ).fetchone()

        if not row:
            return {
                "ok": True,
                "deleted_upload": False,
                "deleted_report": False,
                "errors": [f"Review {review_id} not found."],
            }

        stored_name = str(row["stored_name"] or "").strip()
        report_name = str(row["report_name"] or "").strip()

        # Delete uploaded audio
        if stored_name:
            path = upload_root / stored_name
            if path.exists() and not dry_run:
                path.unlink()
                result["deleted_upload"] = True
            elif path.exists():
                result["deleted_upload"] = True

        # Delete reference uploads
        ref_pattern = f"{review_id}_reference_*"
        for ref_path in upload_root.glob(ref_pattern):
            if ref_path.exists() and not dry_run:
                ref_path.unlink()
                result["deleted_reference"] = True
            elif ref_path.exists():
                result["deleted_reference"] = True

        # Delete report (only if requested — usually we keep these)
        if delete_report and report_name:
            path = report_root / report_name
            if path.exists() and not dry_run:
                path.unlink()
                result["deleted_report"] = True
            elif path.exists():
                result["deleted_report"] = True

    except Exception as exc:
        logger.exception("Cleanup failed for %s", review_id)
        result["ok"] = False
        result["errors"].append(str(exc))

    return result


def cleanup_audiogen_exports(
    *,
    audiogen_root: Path,
    dry_run: bool = False,
) -> dict:
    """Delete AudioGen export WAVs and report files after they've been copied to Portfolio.

    AudioGen's `main_render_full_song.py` writes files to `exports/web/`.
    These are temporary artefacts — the rendered WAV is copied to Portfolio
    and the JSON report files are redundant once that's done.

    Args:
        audiogen_root: Path to the LLM_AudioGen directory.
        dry_run: If True, only report what would be deleted.

    Returns:
        Dict with ok, deleted (count), total_bytes_freed, note.
    """
    export_dir = audiogen_root / "exports" / "web"
    if not export_dir.exists():
        return {"ok": True, "deleted": 0, "total_bytes_freed": 0,
                "note": "No export directory found — nothing to clean."}

    deleted = 0
    total_bytes = 0
    errors = []

    for item in sorted(export_dir.iterdir()):
        if not item.is_file():
            continue
        byte_count = item.stat().st_size
        if not dry_run:
            try:
                item.unlink()
                deleted += 1
                total_bytes += byte_count
            except OSError as exc:
                errors.append(f"{item.name}: {exc}")
        else:
            deleted += 1
            total_bytes += byte_count

    return {
        "ok": errors == [],
        "dry_run": dry_run,
        "deleted": deleted,
        "total_bytes_freed": total_bytes,
        "errors": errors,
        "note": "AudioGen export files (WAV + JSON reports). The Portfolio copy is preserved.",
    }


def get_storage_stats(
    *,
    upload_root: Path,
    report_root: Path,
    reference_root: Path,
) -> dict:
    """Get storage usage statistics for all mix review directories.

    Returns dict with file counts, total sizes, and breakdowns.
    """
    stats = {
        "uploads": {"path": str(upload_root), "files": 0, "size_bytes": 0},
        "reports": {"path": str(report_root), "files": 0, "size_bytes": 0},
        "references": {"path": str(reference_root), "files": 0, "size_bytes": 0},
        "orphan_uploads": {"files": 0, "size_bytes": 0},
    }

    for root_key, root_path in [
        ("uploads", upload_root),
        ("reports", report_root),
        ("references", reference_root),
    ]:
        if not root_path.exists():
            continue
        for f in root_path.iterdir():
            if f.is_file():
                stats[root_key]["files"] += 1
                stats[root_key]["size_bytes"] += f.stat().st_size

    return stats
