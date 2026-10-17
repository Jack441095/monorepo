"""Route handlers for KENN Mix Archive and Reference Library (Milestone E6).

Provides REST endpoints for:
- Listing and fetching producer mixes
- Creating new mixes and recording revisions
- Editing session notes
- Non-destructive deletion of archive records
- Portable export and import
- Grading against stored references with strict tenant isolation
"""

from __future__ import annotations

from typing import Any, Optional
from kenn.core.mix_archive import MixArchiveManager

_default_manager: Optional[MixArchiveManager] = None


def get_archive_manager() -> MixArchiveManager:
    """Return singleton instance of MixArchiveManager."""
    global _default_manager
    if _default_manager is None:
        _default_manager = MixArchiveManager()
    return _default_manager


def handle_list_mixes(
    producer_id: str,
    session_id: Optional[str] = None,
    manager: Optional[MixArchiveManager] = None,
) -> tuple[int, dict[str, Any]]:
    mgr = manager or get_archive_manager()
    clean_producer = str(producer_id or "").strip()
    if not clean_producer:
        return 400, {"error": "producer_id query parameter is required"}
    mixes = mgr.list_mixes(clean_producer, session_id=session_id)
    return 200, {"ok": True, "producer_id": clean_producer, "count": len(mixes), "mixes": mixes}


def handle_get_mix(
    mix_id: str,
    producer_id: str,
    manager: Optional[MixArchiveManager] = None,
) -> tuple[int, dict[str, Any]]:
    mgr = manager or get_archive_manager()
    clean_mix = str(mix_id or "").strip()
    clean_producer = str(producer_id or "").strip()
    if not clean_mix or not clean_producer:
        return 400, {"error": "Both mix_id and producer_id are required"}
    mix = mgr.get_mix(clean_mix, clean_producer)
    if mix is None:
        return 404, {"error": f"Mix '{clean_mix}' not found or access denied"}
    return 200, {"ok": True, "mix": mix}


def handle_add_mix(
    payload: dict[str, Any],
    manager: Optional[MixArchiveManager] = None,
) -> tuple[int, dict[str, Any]]:
    mgr = manager or get_archive_manager()
    producer_id = str(payload.get("producer_id") or "").strip()
    name = str(payload.get("name") or "").strip()
    audio_ref = str(payload.get("audio_ref") or "").strip()

    if not producer_id or not name or not audio_ref:
        return 400, {"error": "producer_id, name, and audio_ref are required"}

    try:
        mix = mgr.add_mix(
            producer_id=producer_id,
            name=name,
            audio_ref=audio_ref,
            tempo=float(payload.get("tempo", 120.0)),
            genre=str(payload.get("genre") or "electronic"),
            target_loudness=float(payload.get("target_loudness", -14.0)),
            session_notes=str(payload.get("session_notes") or ""),
            reference_track_ref=payload.get("reference_track_ref"),
            session_id=payload.get("session_id"),
            initial_grade=payload.get("initial_grade"),
            initial_snapshot=payload.get("initial_snapshot"),
        )
        return 201, {"ok": True, "mix": mix}
    except Exception as exc:
        return 422, {"error": str(exc)}


def handle_update_notes(
    payload: dict[str, Any],
    manager: Optional[MixArchiveManager] = None,
) -> tuple[int, dict[str, Any]]:
    mgr = manager or get_archive_manager()
    mix_id = str(payload.get("mix_id") or "").strip()
    producer_id = str(payload.get("producer_id") or "").strip()
    notes = str(payload.get("session_notes") or "")

    if not mix_id or not producer_id:
        return 400, {"error": "mix_id and producer_id are required"}

    ok = mgr.update_notes(mix_id, producer_id, notes)
    if not ok:
        return 404, {"error": f"Mix '{mix_id}' not found or unauthorized"}
    return 200, {"ok": True, "mix_id": mix_id, "session_notes": notes}


def handle_add_revision(
    payload: dict[str, Any],
    manager: Optional[MixArchiveManager] = None,
) -> tuple[int, dict[str, Any]]:
    mgr = manager or get_archive_manager()
    mix_id = str(payload.get("mix_id") or "").strip()
    producer_id = str(payload.get("producer_id") or "").strip()
    what_changed = str(payload.get("what_changed") or "").strip()

    if not mix_id or not producer_id:
        return 400, {"error": "mix_id and producer_id are required"}

    rev = mgr.add_revision(
        mix_id=mix_id,
        producer_id=producer_id,
        what_changed=what_changed,
        suggestion_applied=payload.get("suggestion_applied"),
        analysis_snapshot=payload.get("analysis_snapshot"),
        measured_grade=payload.get("measured_grade"),
    )
    if rev is None:
        return 404, {"error": f"Mix '{mix_id}' not found or unauthorized"}
    return 201, {"ok": True, "revision": rev}


def handle_delete_mix(
    mix_id: str,
    producer_id: str,
    manager: Optional[MixArchiveManager] = None,
) -> tuple[int, dict[str, Any]]:
    mgr = manager or get_archive_manager()
    clean_mix = str(mix_id or "").strip()
    clean_producer = str(producer_id or "").strip()
    if not clean_mix or not clean_producer:
        return 400, {"error": "mix_id and producer_id are required"}

    ok = mgr.delete_mix(clean_mix, clean_producer)
    if not ok:
        return 404, {"error": f"Mix '{clean_mix}' not found or unauthorized"}
    return 200, {"ok": True, "deleted_mix_id": clean_mix}


def handle_export_archive(
    producer_id: str,
    manager: Optional[MixArchiveManager] = None,
) -> tuple[int, dict[str, Any]]:
    mgr = manager or get_archive_manager()
    clean_producer = str(producer_id or "").strip()
    if not clean_producer:
        return 400, {"error": "producer_id is required for export"}
    data = mgr.export_archive(clean_producer)
    return 200, data


def handle_import_archive(
    producer_id: str,
    payload: dict[str, Any],
    manager: Optional[MixArchiveManager] = None,
) -> tuple[int, dict[str, Any]]:
    mgr = manager or get_archive_manager()
    clean_producer = str(producer_id or "").strip()
    if not clean_producer:
        return 400, {"error": "producer_id is required for import"}
    try:
        imported = mgr.import_archive(clean_producer, payload)
        return 200, {"ok": True, "imported_count": len(imported), "mixes": imported}
    except Exception as exc:
        return 422, {"error": str(exc)}


def handle_grade_against_reference(
    payload: dict[str, Any],
    manager: Optional[MixArchiveManager] = None,
) -> tuple[int, dict[str, Any]]:
    mgr = manager or get_archive_manager()
    ref_mix_id = str(payload.get("reference_mix_id") or "").strip()
    producer_id = str(payload.get("producer_id") or "").strip()
    current_meters = payload.get("current_meters") or {}
    tech_report = payload.get("technical_report")
    request_text = str(payload.get("request_text") or "")

    if not ref_mix_id or not producer_id:
        return 400, {"error": "reference_mix_id and producer_id are required"}

    try:
        result = mgr.grade_against_reference(
            reference_mix_id=ref_mix_id,
            producer_id=producer_id,
            current_meters=current_meters,
            technical_report=tech_report,
            request_text=request_text,
        )
        return 200, {"ok": True, "result": result}
    except PermissionError as exc:
        return 403, {"error": str(exc)}
    except KeyError as exc:
        return 404, {"error": str(exc)}
    except Exception as exc:
        return 422, {"error": str(exc)}
