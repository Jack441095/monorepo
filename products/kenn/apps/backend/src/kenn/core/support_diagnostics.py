"""Redacted support diagnostics for the local KENN service.

The support payload is intentionally an allow-list, not a serializer of
runtime state.  It contains capability and health summaries only; source
audio, project content, personal paths, confirmation tokens, and raw Live
snapshots never cross this boundary.  Change receipts appear only as counts
(by action and outcome, never track names or values) and response times only
as numbers.
"""

from __future__ import annotations

import json
import os
import platform
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kenn.paths import PRODUCT_ROOT


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


def _receipt_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Counts only: what kind of changes were made and how they ended. No targets, values or errors."""
    receipts = [row.get("receipt") for row in rows if isinstance(row, dict) and isinstance(row.get("receipt"), dict)]
    times = sorted(float(r["timestamp"]) for r in receipts if isinstance(r.get("timestamp"), (int, float)))
    return {
        "count": len(receipts),
        "by_action": dict(Counter(str(r.get("action") or "unknown") for r in receipts).most_common(20)),
        "by_status": dict(Counter(str(r.get("status") or "unknown") for r in receipts)),
        "verified": sum(1 for r in receipts if r.get("verified") is True),
        "rolled_back": sum(1 for r in receipts if r.get("rolled_back")),
        "first_at": datetime.fromtimestamp(times[0], timezone.utc).isoformat() if times else None,
        "last_at": datetime.fromtimestamp(times[-1], timezone.utc).isoformat() if times else None,
    }


def _optional(builder: Any, fallback: Any) -> Any:
    try:
        return builder()
    except Exception:
        return fallback


def build_support_diagnostics(
    *,
    live_snapshot: object = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Return an allow-listed diagnostic payload with no sensitive state."""
    root = repo_root.expanduser().resolve() if repo_root else PRODUCT_ROOT
    index_dir = root / "apps" / "backend" / "src" / "kenn" / "data" / "index" / "CURRENT"
    bridge_file = root / "integrations" / "ableton-remote-script" / "KENN_Bridge" / "KENN_Bridge.py"
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
        "knowledge_index_version": _optional(_index_version, None),
        "receipts": _optional(lambda: _receipt_summary(_recent_receipts()), {"count": None}),
        "timings": _optional(_timings, {}),
        "redactions": {
            "excluded_fields": [
                "confirmation_tokens",
                "raw_audio",
                "audio_metadata",
                "personal_paths",
                "project_content",
                "raw_live_snapshot",
                "source_text",
                "track_names",
                "receipt_targets_and_values",
                "request_text",
            ],
            "safe_to_attach_to_support_ticket": True,
        },
        "next_steps": [
            "Attach this file to your report, with what you asked, what you expected and what happened.",
            "For Live issues, run the read-only session probe separately and attach only its redacted receipt.",
            "Never attach confirmation tokens, source audio, project files, or raw paths.",
        ],
    }


def _index_version() -> str | None:
    from kenn.retrieval.index_store import active_version_id

    return active_version_id()


def _recent_receipts() -> list[dict[str, Any]]:
    from kenn.core.live_receipt_journal import MAX_RECEIPTS, list_receipts

    return list_receipts(limit=MAX_RECEIPTS)


def _timings() -> dict[str, Any]:
    from kenn.core import timing_stats

    return timing_stats.summary()


def save_support_diagnostics(payload: dict[str, Any], directory: Path) -> Path:
    """Write one diagnostics file for the tester to attach; returns where it went."""
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = directory / f"kenn-diagnostics-{stamp}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


__all__ = ["SCHEMA", "build_support_diagnostics", "save_support_diagnostics"]
