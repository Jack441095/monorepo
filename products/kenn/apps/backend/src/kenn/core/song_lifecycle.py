"""Song-lifecycle project resolution shared by the server and route modules.

We keep this beside the server instead of inside it so ``server.py``,
``routes/audio_handler.py`` and ``routes/upload_handler.py`` resolve the same
Project id from one copy. The storage owners stay where they were: session
memory owns the remembered project, ``song_projects`` owns the row, the mix
outputs directory owns the evidence file. This module only reads them, so a
wrong answer degrades to "standalone, no linkage" (the pre-existing empty
project_id behaviour) rather than a failed upload.

``song_projects`` is optional, same as in ``server.py``: KENN starts without
it and these helpers return "" / None until it is importable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kenn.core.session_memory import get_remembered_automix_project, remember_automix_project
from kenn.paths import PRODUCT_ROOT

try:
    import song_projects
except ImportError:  # pragma: no cover - optional subsystem
    song_projects = None

WEBSITE_ROOT = PRODUCT_ROOT / "packages" / "website"


def resolve_session_project(session_id: str) -> str:
    """The shared song-lifecycle Project id for this KENN chat session
    (docs/KENN_HUB_UNIFICATION_PLAN_2026-08-05.md Phase 2) -- reuses the
    session's already-remembered project if one exists (same storage
    `remember_automix_project`/`get_remembered_automix_project` already use
    for conversational AutoMix revision), otherwise mints a fresh
    `song_projects` row and remembers it so the NEXT upload/review/
    revision in this same conversation resolves to the same project.
    Returns "" if song_projects/session tracking is unavailable or no
    session_id was supplied -- callers already handle an empty project_id
    as "standalone, no linkage" (the pre-existing behaviour)."""
    if not session_id or not song_projects:
        return ""
    existing = get_remembered_automix_project(session_id)
    if existing:
        return existing
    project = song_projects.create_project()
    remember_automix_project(session_id, project["id"])
    return project["id"]


def read_match_evidence(project_id: str) -> dict[str, Any] | None:
    """Read a completed AutoMix job's persisted match_evidence.json (D2.3,
    docs/KENN_FUTURE_PLAN.md Phase 2) for the proactive completion card --
    same file automix_worker.py writes and automix_routes.py's
    /api/automix/match-evidence/<project_id> route already serves, read
    directly here since KENN's server already runs in the same process/
    filesystem as business/app (see the WEBSITE_ROOT sys.path wiring
    above). Returns None if there's no evidence file (e.g. no reference
    track was used for this render) -- not every completion has one."""
    if not project_id:
        return None
    try:
        from kenn.core import path_safety

        mix_output_root = WEBSITE_ROOT.parent / "data" / "mix_outputs"
        evidence_path = path_safety.safe_child(mix_output_root, project_id) / "match_evidence.json"
        if not evidence_path.is_file():
            return None
        return json.loads(evidence_path.read_text(encoding="utf-8"))
    except Exception:
        return None
