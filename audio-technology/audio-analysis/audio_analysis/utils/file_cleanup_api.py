"""File cleanup API for mix review uploads and AudioGen exports.

Re-exported through :mod:`audio_analysis_tool.mix_review` so existing
imports continue to work. Agents may import this module directly.
"""

from __future__ import annotations

from pathlib import Path

from audio_analysis.utils.file_cleanup import (
    CLEANUP_POLICY_AFTER_ANALYSIS,
    CLEANUP_POLICY_AGE_BASED,
    cleanup_all_uploads as _file_cleanup_all_uploads,
    cleanup_orphaned_uploads as _file_cleanup_orphaned_uploads,
    cleanup_single_review as _file_cleanup_single_review,
    cleanup_audiogen_exports as _file_cleanup_audiogen_exports,
    get_storage_stats as _file_get_storage_stats,
)
from audio_analysis.mix_review.review_workflow import set_auto_delete_uploads as _set_auto_delete_uploads

BUSINESS_ROOT = Path(__file__).resolve().parent.parent


def set_auto_delete_uploads(enabled: bool) -> None:
    """Toggle automatic deletion of uploaded audio after analysis.

    When enabled (default True), the original upload is deleted as soon as
    analysis completes and the report JSON is saved. The report retains all
    extracted metrics; the audio is not needed again.

    Agents can use this if they need to temporarily keep uploads, for
    example during batch ingestion where re-analysis may be beneficial.
    """
    _set_auto_delete_uploads(enabled)


def cleanup_orphaned_uploads(
    *,
    upload_root: Path,
    connect_func: callable,
    dry_run: bool = True,
) -> dict:
    """Remove uploaded files that have no matching database record.

    This gets rid of the accumulated 9-byte corrupt files from failed
    uploads. In dry-run mode (default), it reports what would be deleted
    without actually removing anything.

    Args:
        upload_root: Uploads directory.
        connect_func: Database connection factory.
        dry_run: If True, only report what would be deleted.

    Returns:
        Dict with ok, dry_run, deleted (count), errors.
    """
    return _file_cleanup_orphaned_uploads(
        upload_root=upload_root,
        connect_func=connect_func,
        dry_run=dry_run,
    )


def cleanup_old_uploads(
    *,
    upload_root: Path,
    connect_func: callable,
    days: int = 30,
    dry_run: bool = True,
) -> dict:
    """Delete uploaded audio files older than the specified number of days.

    The report JSONs are NOT deleted — only the original audio uploads.

    Args:
        upload_root: Uploads directory.
        connect_func: Database connection factory.
        days: Delete uploads older than this many days.
        dry_run: If True, only report what would be deleted.

    Returns:
        Summary dict with counts of deleted files.
    """
    return _file_cleanup_all_uploads(
        upload_root=upload_root,
        connect_func=connect_func,
        policy=CLEANUP_POLICY_AGE_BASED,
        older_than_days=days,
        dry_run=dry_run,
    )


def cleanup_all_uploads(
    *,
    upload_root: Path,
    connect_func: callable,
    dry_run: bool = True,
) -> dict:
    """Delete ALL uploaded audio files across every review.

    WARNING: This removes the original audio for all reviews. The report
    JSONs (metrics, flags, analysis) are preserved. Use this when you
    want to reclaim disk space after confirming all analyses are complete.

    Args:
        upload_root: Uploads directory.
        connect_func: Database connection factory.
        dry_run: If True, only report what would be deleted.

    Returns:
        Summary dict with counts of deleted files.
    """
    return _file_cleanup_all_uploads(
        upload_root=upload_root,
        connect_func=connect_func,
        policy=CLEANUP_POLICY_AFTER_ANALYSIS,
        dry_run=dry_run,
    )


def cleanup_single_review(
    review_id: str,
    *,
    upload_root: Path,
    report_root: Path,
    connect_func: callable,
    delete_report: bool = False,
    dry_run: bool = True,
) -> dict:
    """Delete all files associated with a single review.

    Removes uploaded audio, reference files, and optionally the report JSON.
    Use this from the agent when a review needs to be fully purged.

    Args:
        review_id: The review to delete.
        upload_root: Uploads directory.
        report_root: Reports directory.
        connect_func: Database connection factory.
        delete_report: If True, also delete the report JSON.
        dry_run: If True, only report what would be deleted.

    Returns:
        Dict with ok, deleted_upload, deleted_report, errors.
    """
    return _file_cleanup_single_review(
        review_id,
        upload_root=upload_root,
        report_root=report_root,
        connect_func=connect_func,
        delete_report=delete_report,
        dry_run=dry_run,
    )


def cleanup_audiogen_exports(
    *,
    audiogen_root: Path,
    dry_run: bool = True,
) -> dict:
    """Delete AudioGen export files (WAVs + JSON reports) from ``exports/web/``.

    AudioGen writes render outputs to ``LLM_AudioGen/exports/web/`` during
    full-song rendering. These files are copied to Portfolio/audio after
    generation, so the exports become stale duplicates.

    Args:
        audiogen_root: Path to the LLM_AudioGen directory.
        dry_run: If True, only report what would be deleted.

    Returns:
        Dict with ok, deleted (count), total_bytes_freed, note.
    """
    return _file_cleanup_audiogen_exports(
        audiogen_root=audiogen_root,
        dry_run=dry_run,
    )


def get_storage_stats(
    *,
    upload_root: Path,
    report_root: Path,
    reference_root: Path,
) -> dict:
    """Get storage usage statistics for all audio-related directories.

    Args:
        upload_root: Uploads directory.
        report_root: Reports directory.
        reference_root: References directory.

    Returns:
        Dict with per-directory file counts and sizes.
    """
    return _file_get_storage_stats(
        upload_root=upload_root,
        report_root=report_root,
        reference_root=reference_root,
    )
