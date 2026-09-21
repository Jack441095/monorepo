"""Bounded contracts for AudioGen artifacts exposed to KENN.

AudioGen is an adjacent creative subsystem.  KENN must be able to understand
its outputs without importing the generator or trusting arbitrary job fields.
This module therefore only validates metadata and returns a small allowlisted
summary.  It never opens, copies, deletes, or imports an artifact.
"""

from __future__ import annotations

import math
import re
from typing import Any


SCHEMA = "kenn.audiogen_artifact.v1"
_SHA256 = re.compile(r"^(?:sha256:)?[0-9a-fA-F]{64}$")
_KINDS = {"audio", "wav", "midi", "stems", "stems_zip", "report"}
_MIDI_KINDS = {"midi", "midi_file"}
MAX_MIDI_NOTES = 4096
MAX_MIDI_LENGTH = 4096.0
_MIDI_LIMITS = {
    "lowest_note": (0, 127),
    "highest_note": (0, 127),
    "note_count": (0, 10_000_000),
    "bars": (0, 1_000_000),
}


def _bounded_text(value: Any, limit: int = 256) -> str:
    return str(value or "").strip()[:limit]


def _number(value: Any, field: str, errors: list[str], *, integer: bool = False) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        errors.append(f"{field} must be numeric.")
        return None
    try:
        parsed = int(value) if integer else float(value)
    except (TypeError, ValueError):
        errors.append(f"{field} must be numeric.")
        return None
    if not math.isfinite(float(parsed)):
        errors.append(f"{field} must be finite.")
        return None
    return parsed


def _normalized_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    """Flatten the producer shapes used by AudioGen artifact records."""
    normalized = dict(artifact)
    metadata = artifact.get("metadata")
    if isinstance(metadata, dict):
        for key in ("note_count", "lowest_note", "highest_note", "bars", "length_beats", "bpm", "key"):
            if key not in normalized and key in metadata:
                normalized[key] = metadata[key]
    if not normalized.get("sha256") and normalized.get("content_hash"):
        normalized["sha256"] = normalized["content_hash"]
    return normalized


def _raw_midi_notes(artifact: dict[str, Any]) -> Any:
    if isinstance(artifact.get("notes"), list):
        return artifact.get("notes")
    metadata = artifact.get("metadata")
    if isinstance(metadata, dict) and isinstance(metadata.get("notes"), list):
        return metadata.get("notes")
    return None


def safe_generation_context(value: Any) -> dict[str, Any] | None:
    """Allowlist the server-owned Live context attached to a MIDI artifact."""
    if not isinstance(value, dict) or value.get("schema") != "kenn.audiogen_live_context.v1":
        return None
    target = value.get("target") if isinstance(value.get("target"), dict) else {}
    try:
        track_index = int(target.get("track_index"))
        live_bpm = float(value.get("live_tempo_bpm"))
    except (TypeError, ValueError):
        return None
    if track_index < 0 or not math.isfinite(live_bpm) or not 20.0 <= live_bpm <= 999.0:
        return None
    source_bpm = value.get("source_tempo_bpm")
    if source_bpm is not None:
        try:
            source_bpm = float(source_bpm)
        except (TypeError, ValueError):
            source_bpm = None
        if source_bpm is not None and (not math.isfinite(source_bpm) or not 20.0 <= source_bpm <= 999.0):
            source_bpm = None
    relationship = str(value.get("tempo_relationship", "unknown"))
    if relationship not in {"match", "different", "unknown"}:
        relationship = "unknown"
    limitations = value.get("limitations") if isinstance(value.get("limitations"), list) else []
    limitations = [str(item)[:256] for item in limitations[:3] if str(item).strip()]
    selected = value.get("selected_track_index")
    try:
        selected = int(selected) if selected is not None else None
    except (TypeError, ValueError):
        selected = None
    time_signature = value.get("time_signature") if isinstance(value.get("time_signature"), dict) else None
    if time_signature:
        try:
            ts_numerator = int(time_signature.get("numerator"))
            ts_denominator = int(time_signature.get("denominator"))
        except (TypeError, ValueError):
            time_signature = None
        if time_signature and (not 1 <= ts_numerator <= 32 or not 1 <= ts_denominator <= 64):
            time_signature = None
    live_key = value.get("live_key") if isinstance(value.get("live_key"), dict) else None
    if live_key:
        try:
            live_root = int(live_key.get("root_note")) if live_key.get("root_note") is not None else None
        except (TypeError, ValueError):
            live_root = None
        live_scale = str(live_key.get("scale_name") or "")[:64] or None
        if live_root is not None and not 0 <= live_root <= 11:
            live_root = None
        live_key = {"root_note": live_root, "scale_name": live_scale}
    key_relationship = str(value.get("key_relationship", "unknown"))
    if key_relationship not in {"unknown", "not_compared", "match", "different"}:
        key_relationship = "unknown"
    result = {
        "schema": "kenn.audiogen_live_context.v1",
        "target": {"track_index": track_index, "track_name": str(target.get("track_name", ""))[:256]},
        "live_tempo_bpm": live_bpm,
        "source_tempo_bpm": source_bpm,
        "tempo_relationship": relationship,
        "timing_basis": "symbolic MIDI positions are expressed in beats; Live project tempo governs playback",
        "timing_action": "preserve_symbolic_beats",
        "adaptation": "none_required",
        "selected_track_index": selected,
        "time_signature": time_signature,
        "live_key": live_key,
        "source_key": str(value.get("source_key") or "")[:64] or None,
        "key_relationship": key_relationship,
        "limitations": limitations,
    }
    revision = value.get("revision") if isinstance(value.get("revision"), dict) else None
    if revision and revision.get("schema") == "kenn.audition_revision_brief.v1" and revision.get("advisory_only") is True:
        listener = revision.get("listener") if isinstance(revision.get("listener"), dict) else {}
        baseline = revision.get("baseline") if isinstance(revision.get("baseline"), dict) else {}
        result["revision"] = {
            "schema": "kenn.audition_revision_brief.v1",
            "feedback_id": str(revision.get("feedback_id", ""))[:128],
            "source_receipt_id": str(revision.get("source_receipt_id", ""))[:256],
            "listener": {
                "verdict": "revise",
                "rating": listener.get("rating"),
                "comment": str(listener.get("comment", ""))[:1000],
                "requested_changes": [str(item)[:256] for item in (listener.get("requested_changes") or [])[:5]],
            },
            "baseline": {
                "audition_receipt_id": str(baseline.get("audition_receipt_id", ""))[:256],
                "clip_fingerprint": str(baseline.get("clip_fingerprint", ""))[:128],
                "clip_length": baseline.get("clip_length"),
            },
            "advisory_only": True,
        }
        comparison = revision.get("comparison") if isinstance(revision.get("comparison"), dict) else None
        if comparison and comparison.get("schema") == "kenn.audiogen_audio_comparison.v1":
            deltas = comparison.get("metric_deltas") if isinstance(comparison.get("metric_deltas"), dict) else {}
            result["revision"]["comparison"] = {
                "schema": "kenn.audiogen_audio_comparison.v1",
                "source_a": {
                    "reference": str((comparison.get("source_a") or {}).get("reference", ""))[:512]
                    if isinstance(comparison.get("source_a"), dict) else "",
                    "input_hash": str((comparison.get("source_a") or {}).get("input_hash", ""))[:128]
                    if isinstance(comparison.get("source_a"), dict) else "",
                },
                "source_b": {
                    "reference": str((comparison.get("source_b") or {}).get("reference", ""))[:512]
                    if isinstance(comparison.get("source_b"), dict) else "",
                    "input_hash": str((comparison.get("source_b") or {}).get("input_hash", ""))[:128]
                    if isinstance(comparison.get("source_b"), dict) else "",
                },
                "metric_deltas": {
                    str(key)[:64]: value for key, value in list(deltas.items())[:32]
                    if isinstance(value, dict)
                },
                "advisory_only": True,
            }
    return result


def _canonical_midi_notes(raw_notes: Any) -> tuple[list[dict[str, Any]], list[str]]:
    if raw_notes is None:
        return [], []
    if not isinstance(raw_notes, list):
        return [], ["MIDI notes must be a list."]
    if len(raw_notes) > MAX_MIDI_NOTES:
        return [], [f"MIDI notes may contain at most {MAX_MIDI_NOTES} entries."]
    errors: list[str] = []
    notes: list[dict[str, Any]] = []
    for offset, item in enumerate(raw_notes):
        if not isinstance(item, dict):
            errors.append(f"MIDI note {offset} must be an object.")
            continue
        try:
            pitch = int(item["pitch"])
            start_time = float(item["start_time"])
            duration = float(item["duration"])
            velocity = int(item["velocity"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"MIDI note {offset} has invalid fields.")
            continue
        if not 0 <= pitch <= 127:
            errors.append(f"MIDI note {offset} pitch must be between 0 and 127.")
            continue
        if not math.isfinite(start_time) or start_time < 0:
            errors.append(f"MIDI note {offset} start_time must be finite and non-negative.")
            continue
        if not math.isfinite(duration) or duration <= 0:
            errors.append(f"MIDI note {offset} duration must be finite and greater than zero.")
            continue
        if not 1 <= velocity <= 127:
            errors.append(f"MIDI note {offset} velocity must be between 1 and 127.")
            continue
        notes.append({
            "pitch": pitch,
            "start_time": start_time,
            "duration": duration,
            "velocity": velocity,
            "mute": bool(item.get("mute", False)),
        })
    notes.sort(key=lambda item: (
        item["pitch"], item["start_time"], item["duration"], item["velocity"], item["mute"]
    ))
    return notes, errors


def midi_preview_metadata(artifact: Any) -> dict[str, Any]:
    """Return a bounded symbolic preview without rendering or playing audio."""
    if not isinstance(artifact, dict):
        return {
            "schema": "kenn.audiogen_midi_preview.v1",
            "status": "unavailable",
            "limitations": ["No MIDI artifact metadata was supplied."],
        }
    normalized = _normalized_artifact(artifact)
    notes, note_errors = _canonical_midi_notes(_raw_midi_notes(normalized))
    if note_errors or not notes:
        return {
            "schema": "kenn.audiogen_midi_preview.v1",
            "status": "unavailable",
            "limitations": note_errors[:3] or ["The artifact contains no previewable MIDI notes."],
        }
    try:
        length_beats = float(normalized.get("length_beats"))
    except (TypeError, ValueError):
        length_beats = 0.0
    try:
        bars = float(normalized.get("bars"))
    except (TypeError, ValueError):
        bars = 0.0
    if not math.isfinite(bars) or bars <= 0:
        bars = length_beats / 4.0 if length_beats > 0 else 0.0
    durations = [float(note["duration"]) for note in notes]
    velocities = [int(note["velocity"]) for note in notes]
    onsets = sorted({float(note["start_time"]) for note in notes})
    histogram = [0] * 12
    for note in notes:
        histogram[int(note["pitch"]) % 12] += 1
    preview_notes = sorted(notes, key=lambda item: (item["start_time"], item["pitch"]))[:64]
    return {
        "schema": "kenn.audiogen_midi_preview.v1",
        "status": "ready",
        "audition": {
            "status": "not_rendered",
            "available": False,
            "limitation": "This is a symbolic MIDI preview; KENN has not rendered or played audio.",
        },
        "note_count": len(notes),
        "bar_count": bars,
        "length_beats": length_beats,
        "note_density_per_bar": round(len(notes) / bars, 4) if bars > 0 else None,
        "pitch_range": {"lowest": min(note["pitch"] for note in notes), "highest": max(note["pitch"] for note in notes)},
        "pitch_class_histogram": histogram,
        "velocity_range": {"minimum": min(velocities), "maximum": max(velocities)},
        "duration_beats": {
            "minimum": min(durations),
            "maximum": max(durations),
            "mean": round(sum(durations) / len(durations), 6),
        },
        "onset_count": len(onsets),
        "first_events": preview_notes,
        "truncated": len(notes) > len(preview_notes),
    }


def validate_artifact_metadata(artifact: Any) -> dict[str, Any]:
    """Validate an untrusted AudioGen artifact metadata object.

    Missing optional metadata is reported as a warning.  Invalid values are
    errors and must prevent downstream import until a producer supplies a
    corrected, verifiable record.
    """
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(artifact, dict):
        return {"ok": False, "schema": SCHEMA, "kind": "unknown", "errors": ["Artifact metadata must be an object."], "warnings": []}

    artifact = _normalized_artifact(artifact)
    kind = _bounded_text(artifact.get("kind"), 64).lower()
    if kind not in _KINDS and kind not in _MIDI_KINDS:
        errors.append("Artifact kind is missing or unsupported.")

    sha256 = _bounded_text(artifact.get("sha256"), 128)
    if sha256 and not _SHA256.fullmatch(sha256):
        errors.append("sha256 must be a 64-character hexadecimal digest.")
    elif not sha256:
        warnings.append("Artifact has no content digest yet.")

    if kind in _MIDI_KINDS:
        for field, (minimum, maximum) in _MIDI_LIMITS.items():
            parsed = _number(artifact.get(field), field, errors, integer=True)
            if parsed is None:
                warnings.append(f"MIDI metadata does not include {field}.")
                continue
            if not minimum <= parsed <= maximum:
                errors.append(f"{field} must be between {minimum} and {maximum}.")

        lowest = artifact.get("lowest_note")
        highest = artifact.get("highest_note")
        if lowest is not None and highest is not None:
            try:
                if int(lowest) > int(highest):
                    errors.append("lowest_note cannot exceed highest_note.")
            except (TypeError, ValueError):
                pass

        bpm = _number(artifact.get("bpm"), "bpm", errors)
        if bpm is None:
            warnings.append("MIDI metadata does not include bpm.")
        elif not 20.0 <= bpm <= 400.0:
            errors.append("bpm must be between 20 and 400.")

        if not _bounded_text(artifact.get("key"), 64):
            warnings.append("MIDI metadata does not include key.")

        length_beats = _number(artifact.get("length_beats"), "length_beats", errors)
        if length_beats is None:
            warnings.append("MIDI metadata does not include length_beats.")
        elif not 0.0 < float(length_beats) <= MAX_MIDI_LENGTH:
            errors.append(f"length_beats must be greater than 0 and at most {MAX_MIDI_LENGTH}.")

        raw_notes = _raw_midi_notes(artifact)
        notes, note_errors = _canonical_midi_notes(raw_notes)
        errors.extend(note_errors)
        if raw_notes is not None and not notes and not note_errors:
            warnings.append("MIDI artifact contains no note events.")
        note_count = artifact.get("note_count")
        if raw_notes is not None and note_count is not None:
            try:
                if int(note_count) != len(notes):
                    errors.append("note_count does not match the supplied MIDI note events.")
            except (TypeError, ValueError):
                pass
        if length_beats is not None and not note_errors:
            for offset, note in enumerate(notes):
                if note["start_time"] + note["duration"] > float(length_beats) + 1e-9:
                    errors.append(f"MIDI note {offset} extends beyond length_beats.")

    return {
        "ok": not errors,
        "schema": SCHEMA,
        "kind": kind or "unknown",
        "errors": errors,
        "warnings": warnings,
    }


def safe_artifact_metadata(artifact: Any) -> dict[str, Any]:
    """Return the allowlisted artifact fields safe for session context."""
    if not isinstance(artifact, dict):
        return {"validation": validate_artifact_metadata(artifact)}

    artifact = _normalized_artifact(artifact)
    fields = (
        "artifact_id",
        "kind",
        "media_type",
        "sha256",
        "producer",
        "producer_version",
        "note_count",
        "lowest_note",
        "highest_note",
        "bars",
        "length_beats",
        "bpm",
        "key",
    )
    result = {key: artifact[key] for key in fields if key in artifact}
    context = safe_generation_context(artifact.get("generation_context"))
    if context:
        result["generation_context"] = context
    if _bounded_text(artifact.get("kind"), 64).lower() in _MIDI_KINDS:
        result["preview"] = midi_preview_metadata(artifact)
    notes, note_errors = _canonical_midi_notes(_raw_midi_notes(artifact))
    if notes and not note_errors and len(notes) <= MAX_MIDI_NOTES:
        result["notes"] = notes
    result["validation"] = validate_artifact_metadata(artifact)
    return result


def midi_import_payload(artifact: Any) -> dict[str, Any]:
    """Return the only AudioGen data allowed to enter the Live proposal path.

    This is deliberately stricter than metadata inspection: importing requires
    a completed, digest-bound MIDI artifact with explicit clip length and
    bounded note events.  It never reads a producer path or opens a MIDI file.
    """
    if not isinstance(artifact, dict):
        return {"ok": False, "errors": ["MIDI artifact metadata is unavailable."], "warnings": []}
    normalized = _normalized_artifact(artifact)
    validation = validate_artifact_metadata(normalized)
    errors = list(validation.get("errors", []))
    warnings = list(validation.get("warnings", []))
    kind = _bounded_text(normalized.get("kind"), 64).lower()
    if kind not in _MIDI_KINDS:
        errors.append("Only MIDI artifacts can be proposed for Live MIDI clip import.")
    digest = _bounded_text(normalized.get("sha256"), 128).lower()
    if digest and not digest.startswith("sha256:"):
        digest = "sha256:" + digest
    if not digest:
        errors.append("MIDI clip import requires a content digest.")
    artifact_id = _bounded_text(normalized.get("artifact_id"), 256)
    try:
        length_beats = float(normalized.get("length_beats"))
    except (TypeError, ValueError):
        length_beats = 0.0
    notes, note_errors = _canonical_midi_notes(_raw_midi_notes(normalized))
    errors.extend(note_errors)
    if not notes:
        errors.append("MIDI clip import requires at least one note event.")
    if not math.isfinite(length_beats) or not 0.0 < length_beats <= MAX_MIDI_LENGTH:
        errors.append(f"MIDI clip import requires length_beats between 0 and {MAX_MIDI_LENGTH}.")
    for offset, note in enumerate(notes):
        if note["start_time"] + note["duration"] > length_beats + 1e-9:
            errors.append(f"MIDI note {offset} extends beyond length_beats.")
    result = {
        "ok": not errors and validation.get("ok") is True,
        "artifact_id": artifact_id,
        "source_artifact_sha256": digest,
        "length": length_beats,
        "notes": notes,
        "validation": validation,
        "errors": errors,
        "warnings": warnings,
    }
    context = safe_generation_context(normalized.get("generation_context"))
    if context:
        result["generation_context"] = context
    return result


__all__ = ["SCHEMA", "midi_import_payload", "midi_preview_metadata", "safe_artifact_metadata", "safe_generation_context", "validate_artifact_metadata"]
