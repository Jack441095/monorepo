"""Redacted support diagnostics for the local KENN service.

The support payload is intentionally an allow-list, not a serializer of
runtime state.  It contains capability and health summaries only; source
audio, project content, personal paths, confirmation tokens, and raw Live
snapshots never cross this boundary.
"""

from __future__ import annotations

import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = "kenn.support_diagnostics.v1"


def _live_summary(snapshot: object) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        return {
            "status": "not_queried",
            "snapshot_available": False,
            "track_count": None,
        }
    status = str(snapshot.get("status") or "unknown")
    if status not in {"connected", "offline", "dispatched", "unknown"}:
        status = "unknown"
    tracks = snapshot.get("tracks")
    return {
        "status": status,
        "snapshot_available": status == "connected",
        "track_count": len(tracks) if isinstance(tracks, list) else None,
    }


def build_support_diagnostics(
    *,
    live_snapshot: object = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Return an allow-listed diagnostic payload with no sensitive state."""
    root = repo_root.expanduser().resolve() if repo_root else Path(__file__).resolve().parents[3]
    index_dir = root / "source" / "kenn" / "data" / "index" / "CURRENT"
    bridge_file = root / "source" / "remote_script" / "KENN_Bridge" / "KENN_Bridge.py"
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "service": "kenn",
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.system(),
            "architecture": platform.machine(),
        },
        "checks": {
            # CURRENT is a pointer *file* (holding a version id), not a
            # directory -- .is_dir() here always returned False, even with
            # a genuinely available index (2026-09-06 beta-sprint P0 audit
            # found this; the existing test only exercised an empty
            # tmp_path repo_root, where either check trivially returns
            # False, so it never caught the real bug).
            "knowledge_index_available": index_dir.exists(),
            "remote_script_source_available": bridge_file.is_file(),
            "audio_retained_by_diagnostics": False,
            "project_content_included": False,
        },
        "features": {
            "retrieval_chat": True,
            "pcm_wav_analysis": True,
            "ableton_read_only_snapshot": True,
            "ableton_track_transport_writes": True,
            "ableton_device_write_qualification": "external_gate",
            "auto_mode": False,
            "llm_rewrite_enabled": os.environ.get("AUDIO_TOO_LLM_ENABLED", "0") == "1",
        },
        "ableton": _live_summary(live_snapshot),
        "redactions": {
            "excluded_fields": [
                "confirmation_tokens",
                "raw_audio",
                "audio_metadata",
                "personal_paths",
                "project_content",
                "raw_live_snapshot",
                "source_text",
            ],
            "safe_to_attach_to_support_ticket": True,
        },
        "next_steps": [
            "Attach the sanitized request ID and this payload to a support report.",
            "For Live issues, run the read-only session probe separately and attach only its redacted receipt.",
            "Never attach confirmation tokens, source audio, project files, or raw paths.",
        ],
    }


__all__ = ["SCHEMA", "build_support_diagnostics"]
