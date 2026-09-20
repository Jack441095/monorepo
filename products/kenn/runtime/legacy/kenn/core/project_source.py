"""Resolve "the track already uploaded for this project" so an explicit
chat trigger (tool_trigger.py) can re-run a different tool against it
without asking the user to re-upload (Phase 3 of
docs/KENN_HUB_UNIFICATION_PLAN_2026-08-05.md).

Deliberately scoped to the single-file case only: AutoMix-originated
projects hold a STEM SET (multiple files under stem_uploads), a different
shape this resolver does not attempt to collapse into "the" file -- "run an
automix on this" from chat is correspondingly not wired to a trigger yet
(see tool_trigger.py / the plan doc's Phase 3 notes for why).

**Real constraint found live (2026-08-05), not assumed:** mix_reviews'
source WAV is deliberately deleted after analysis
(`review_workflow.py::_cleanup_upload_files`, a genuine privacy/storage
choice, not a bug) -- so a mix-review-sourced project's file is usually
already gone by the time a later chat message could reference it. Checked
before relying on it: `stem_separation_jobs.source_path` has no equivalent
post-success cleanup anywhere in `stem_separation_job_store.py`, so it
reliably persists. Tries mix_reviews first (works in the narrow window
before cleanup runs), falls back to stem_separation_jobs' source_path
(the one that actually persists) -- verified live end-to-end with the
stem-separation-first ordering."""

from __future__ import annotations

from pathlib import Path


def resolve_project_source_audio(project_id: str) -> tuple[bytes, str] | None:
    """Returns (file_bytes, original_filename) for the most recent
    resolvable single-file source under this project, or None if there
    isn't one -- callers must treat None as "fall through to a normal chat
    answer," not an error."""
    if not project_id:
        return None
    try:
        from db import connect
    except ImportError:
        return None

    from_review = _resolve_from_mix_review(project_id, connect)
    if from_review is not None:
        return from_review
    return _resolve_from_stem_separation(project_id, connect)


def _resolve_from_mix_review(project_id: str, connect) -> tuple[bytes, str] | None:
    try:
        from audio_analysis.mix_review.mix_review_config import UPLOAD_ROOT
    except ImportError:
        return None
    with connect() as conn:
        row = conn.execute(
            """SELECT stored_name, original_name FROM mix_reviews
               WHERE project_id = ? ORDER BY created_at DESC LIMIT 1""",
            (project_id,),
        ).fetchone()
    if row is None:
        return None
    stored_name = str(row["stored_name"] or "")
    original_name = str(row["original_name"] or stored_name)
    if not stored_name:
        return None
    path = Path(UPLOAD_ROOT) / stored_name
    if not path.is_file():
        return None
    return path.read_bytes(), original_name


def _resolve_from_stem_separation(project_id: str, connect) -> tuple[bytes, str] | None:
    with connect() as conn:
        row = conn.execute(
            """SELECT source_path, source_filename FROM stem_separation_jobs
               WHERE project_id = ? ORDER BY created_at DESC LIMIT 1""",
            (project_id,),
        ).fetchone()
    if row is None:
        return None
    source_path = str(row["source_path"] or "")
    original_name = str(row["source_filename"] or "")
    if not source_path:
        return None
    path = Path(source_path)
    if not path.is_file():
        return None
    return path.read_bytes(), original_name or path.name
