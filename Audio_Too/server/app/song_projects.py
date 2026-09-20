"""Shared song-lifecycle Project entity.

Deliberately separate from the CRM `projects` table (a business/client
engagement, which can span many songs) -- see
docs/KENN_HUB_UNIFICATION_PLAN_2026-08-05.md Phase 2. A song_project is the
one thing AutoMix, Mix Review, and stem-separation should all be able to
point at for a single song, whether or not a CRM engagement exists yet.

Table is created by business/app/migrations/018_song_projects.sql, applied
via db.init_db() before any of this module's functions run.
"""

from __future__ import annotations

from uuid import uuid4

from db import connect, now


def create_project(title: str = "") -> dict:
    """Mint a fresh song_project row and return it."""
    project_id = f"kenn-{uuid4().hex[:10]}"
    timestamp = now()
    with connect() as conn:
        conn.execute(
            """INSERT INTO song_projects (id, title, crm_project_id, created_at, updated_at)
               VALUES (?, ?, NULL, ?, ?)""",
            (project_id, title, timestamp, timestamp),
        )
        conn.commit()
    return {
        "id": project_id,
        "title": title,
        "crm_project_id": None,
        "reference_track_id": None,
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def get_project(project_id: str) -> dict | None:
    if not project_id:
        return None
    with connect() as conn:
        row = conn.execute(
            "SELECT id, title, crm_project_id, reference_track_id, created_at, updated_at "
            "FROM song_projects WHERE id = ?",
            (project_id,),
        ).fetchone()
    if row is None:
        return None
    return dict(row)


def link_to_crm(project_id: str, crm_project_id: str) -> bool:
    """Attach an existing song_project to a CRM client engagement.
    Returns False if project_id doesn't exist (caller should create it
    first via create_project(), not silently no-op)."""
    with connect() as conn:
        cursor = conn.execute(
            "UPDATE song_projects SET crm_project_id = ?, updated_at = ? WHERE id = ?",
            (crm_project_id, now(), project_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def set_reference_track(project_id: str, reference_track_id: str) -> bool:
    """Remember which saved reference track (mix_references.id) this
    project is being mixed against (D1.7,
    docs/KENN_FUTURE_PLAN.md Phase 1). Only ever called when a review
    explicitly selects a saved reference for a project that doesn't have
    one yet -- see review_workflow.py::save_review() -- so it doesn't
    silently overwrite an intentional later choice. Returns False if
    project_id doesn't exist."""
    with connect() as conn:
        cursor = conn.execute(
            "UPDATE song_projects SET reference_track_id = ?, updated_at = ? WHERE id = ?",
            (reference_track_id, now(), project_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def record_revision_request(project_id: str, feedback_text: str) -> int | None:
    """Remember a mix-revision request against a song_project (D2.2,
    docs/KENN_FUTURE_PLAN.md Phase 2 "Mix Memory" storage half). Called
    whenever a revision is actually queued (business/app/ableton_bridge.py
    ::_handle_mix_revision), not on every chat message -- only real
    accepted requests, not idle conversation. No-ops on an empty
    project_id or feedback_text (nothing to remember). Returns the new
    row's id (so a later listening-checkpoint reply can record whether
    the user kept it, §13.6.2) -- None if nothing was recorded."""
    if not project_id or not feedback_text.strip():
        return None
    with connect() as conn:
        cursor = conn.execute(
            """INSERT INTO project_revision_history (project_id, feedback_text, created_at)
               VALUES (?, ?, ?)""",
            (project_id, feedback_text.strip(), now()),
        )
        conn.commit()
        return cursor.lastrowid


def record_revision_outcome(revision_id: int, outcome: str) -> bool:
    """Record whether a past revision request was kept or reverted
    (§13.6.2, fed by D2.4's listening-checkpoint accept/reject reply).
    Returns False if revision_id doesn't exist."""
    if not revision_id or outcome not in {"kept", "reverted"}:
        return False
    with connect() as conn:
        cursor = conn.execute(
            "UPDATE project_revision_history SET outcome = ? WHERE id = ?",
            (outcome, revision_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def get_revision_history(project_id: str, limit: int = 5) -> list[dict]:
    """Return the most recent revision requests for a project, newest
    first. Empty list for a project with no history yet."""
    if not project_id:
        return []
    with connect() as conn:
        rows = conn.execute(
            """SELECT id, feedback_text, created_at, outcome FROM project_revision_history
               WHERE project_id = ? ORDER BY created_at DESC LIMIT ?""",
            (project_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]
