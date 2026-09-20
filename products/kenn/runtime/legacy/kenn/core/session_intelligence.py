"""Read-only, provenance-preserving musical context for KENN advice.

``kenn.session_context.v1`` is deliberately complete enough for a planner.
This module turns that bounded source into a smaller, explainable briefing for
advice and retrieval.  It never polls Ableton, invokes a model, stores user
content, or grants an action authority.  A Live write must still start from a
fresh ``kenn.session_context.v1`` snapshot and use the normal proposal path.
"""

from __future__ import annotations

import math
import time
from typing import Any, Iterable

from kenn.core.arrangement_analysis import analyze_arrangement_context
from kenn.core.audio_classification import AudioClassificationError, normalize as normalize_audio_classification
from kenn.core.session_context import MAX_CONTEXT_AGE_SECONDS, validate_session_context


SCHEMA = "kenn.session_intelligence.v1"
MAX_TRACK_ROLES = 128
MAX_AUDIO_EVIDENCE = 16
MAX_RETRIEVAL_SOURCES = 12
MAX_RETRIEVAL_SOURCE_ID = 256
MAX_TEXT = 256

_ALLOWED_EVIDENCE_CLASSES = frozenset({
    "official_ableton_manual", "reference_document", "manual_reference",
    "curated_kenn_note", "youtube_transcript", "session_measurement", "specialist_inference",
})


def _text(value: Any, limit: int = MAX_TEXT) -> str:
    return str(value or "").strip()[:limit]


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _safe_project_intent(value: Any) -> dict[str, Any]:
    """Keep only explicit, current-turn project intent; do not persist it."""
    if not isinstance(value, dict):
        return {"declared": False, "genre": "", "goal": "", "references": []}
    references = [
        _text(item, 128) for item in (value.get("references") or [])[:5]
        if isinstance(item, str) and _text(item, 128)
    ]
    genre = _text(value.get("genre"), 96)
    goal = _text(value.get("goal"), 512)
    return {
        "declared": bool(genre or goal or references),
        "genre": genre,
        "goal": goal,
        "references": references,
        "source": "explicit_current_turn" if (genre or goal or references) else "none",
        "advisory_only": True,
    }


def _safe_retrieval_sources(values: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    safe: list[dict[str, str]] = []
    entries = values if isinstance(values, (list, tuple)) else ()
    for value in entries[:MAX_RETRIEVAL_SOURCES]:
        if not isinstance(value, dict):
            continue
        evidence_class = _text(value.get("evidence_class"), 64)
        source_id = _text(value.get("source_id") or value.get("id") or value.get("path"), MAX_RETRIEVAL_SOURCE_ID)
        if evidence_class not in _ALLOWED_EVIDENCE_CLASSES or not source_id:
            continue
        item = {"source_id": source_id, "evidence_class": evidence_class}
        title = _text(value.get("title") or value.get("label"), 160)
        if title:
            item["title"] = title
        safe.append(item)
    return safe


def retrieval_sources_from_cache(values: Any) -> list[dict[str, str]]:
    """Extract provenance from KENN's own cached retrieval tuples.

    The cache holds ``(score, chunk)`` pairs created by the retrieval layer.
    Only source identifiers and declared evidence classes escape this boundary;
    chunk text, query text, scores, and paths remain private.
    """
    candidates: list[dict[str, Any]] = []
    for item in values if isinstance(values, list) else []:
        if not isinstance(item, (list, tuple)) or len(item) != 2 or not isinstance(item[1], dict):
            continue
        chunk = item[1]
        candidates.append({
            "source_id": chunk.get("source"),
            "title": chunk.get("title"),
            "evidence_class": chunk.get("evidence_class") or (
                "curated_kenn_note" if chunk.get("kind") == "note" else "manual_reference"
            ),
        })
    return _safe_retrieval_sources(candidates)


def _track_roles(context: dict[str, Any]) -> list[dict[str, Any]]:
    roles: list[dict[str, Any]] = []
    for track in (context.get("tracks") or [])[:MAX_TRACK_ROLES]:
        if not isinstance(track, dict):
            continue
        classification = track.get("classification") if isinstance(track.get("classification"), dict) else {}
        role = _text(classification.get("role"), 64) or "unknown"
        confidence = _text(classification.get("confidence_band"), 32) or "unknown"
        role_entry = {
            "track_index": track.get("index"),
            "track_name": _text(track.get("name"), 128),
            "role": role,
            "confidence_band": confidence,
            "evidence_class": "specialist_inference",
            "source": "track_context_heuristic",
            "user_confirmed": False,
            "advisory_only": True,
        }
        for key in ("output_meter_level", "output_meter_right"):
            value = _number(track.get(key))
            if value is not None and 0.0 <= value <= 1.0:
                role_entry[key] = value
        if any(key in role_entry for key in ("output_meter_level", "output_meter_right")):
            role_entry["meter_scope"] = "instantaneous_post_fader"
        roles.append(role_entry)
    return roles


def _audio_classification_evidence(context: dict[str, Any]) -> list[dict[str, Any]]:
    """Expose validated classifier output without turning it into certainty."""
    evidence: list[dict[str, Any]] = []
    for raw in (context.get("audio_classifications") or [])[:MAX_AUDIO_EVIDENCE]:
        try:
            classification = normalize_audio_classification(raw)
        except AudioClassificationError:
            continue
        predictions = lambda value: [
            {"label": _text(item.get("label"), 96), "probability": _number(item.get("probability"))}
            for item in (value or [])[:3]
            if isinstance(item, dict) and _number(item.get("probability")) is not None
        ]
        ood = classification["out_of_distribution"]
        evidence.append({
            "kind": "audio_classification",
            "evidence_class": "specialist_inference",
            "audio_sha256": classification["audio_sha256"],
            "model_id": classification["model_id"],
            "inference_version": classification["inference_version"],
            "selected_label": classification["selected_label"],
            "selected_source": classification["selected_source"],
            "confidence_band": classification["confidence_band"],
            "out_of_distribution": {
                "status": ood["status"],
                "score": ood["score"],
            },
            "audio_only": predictions(classification["audio_only"]),
            "metadata_assisted": predictions(classification["metadata_assisted"]),
            "limitations": [
                "This is advisory classifier output, not proof of the audio source, track role, or musical quality.",
                "Metadata-assisted predictions may use filenames or folders; audio-only predictions are the blind-audio stream.",
                "Unknown or out-of-distribution output must remain unresolved until a producer or stronger evidence confirms it.",
            ],
            "advisory_only": True,
            "live_mutation_authorized": False,
        })
    return evidence


def _audio_evidence(context: dict[str, Any], reference_comparison: Any) -> list[dict[str, Any]]:
    def pink_noise_evidence(comparison: dict[str, Any]) -> dict[str, Any] | None:
        reference = comparison.get("pink_noise_reference")
        largest = reference.get("largest_deviation") if isinstance(reference, dict) else None
        if not isinstance(largest, dict):
            return None
        frequency = _number(largest.get("center_hz"))
        deviation = _number(largest.get("deviation_db"))
        if frequency is None or deviation is None:
            return None
        return {
            "kind": "pink_noise_shape",
            "evidence_class": "session_measurement",
            "largest_deviation": {"center_hz": frequency, "deviation_db": deviation},
            "curve": _text(reference.get("curve"), 128),
            "anchor_frequency_hz": _number(reference.get("anchor_frequency_hz")),
            "limitations": [
                "This is a broad spectral-shape reference, not a universal mix target or quality score.",
                "It does not identify a Live track, arrangement choice, room problem, or processing cause.",
                "Level-match and listen before making any tonal change.",
            ],
        }

    evidence: list[dict[str, Any]] = []
    for measurement in (context.get("measurements") or [])[:MAX_AUDIO_EVIDENCE]:
        if not isinstance(measurement, dict):
            continue
        kind = _text(measurement.get("kind"), 64)
        metrics = measurement.get("metrics") if isinstance(measurement.get("metrics"), dict) else {}
        numeric_metrics = {
            _text(key, 96): number
            for key, value in list(metrics.items())[:32]
            if (number := _number(value)) is not None
        }
        if kind and numeric_metrics:
            evidence.append({
                "kind": kind,
                "evidence_class": "session_measurement",
                "metrics": numeric_metrics,
                "limitations": ["Measurements describe their captured audio scope, not an unobserved Live cause."],
            })
        trusted_comparison = measurement.get("reference_comparison")
        if isinstance(trusted_comparison, dict):
            largest = trusted_comparison.get("largest_ltas_difference")
            if isinstance(largest, dict):
                frequency = _number(largest.get("center_hz"))
                delta = _number(largest.get("delta_db"))
                if frequency is not None and delta is not None:
                    evidence.append({
                        "kind": "uploaded_reference_ltas",
                        "evidence_class": "session_measurement",
                        "largest_difference": {"center_hz": frequency, "delta_db": delta},
                        "comparison_basis": _text(trusted_comparison.get("comparison_basis"), 512),
                        "limitations": [
                            "Measured against the uploaded reference after normalisation around 1 kHz.",
                            "It is a listening target, not an automatic or universal EQ instruction.",
                        ],
                    })
            pink = pink_noise_evidence(trusted_comparison)
            if pink is not None:
                evidence.append(pink)
        if kind == "plugin_feature_frame":
            pink = pink_noise_evidence(measurement)
            if pink is not None:
                evidence.append(pink)
    if isinstance(reference_comparison, dict):
        largest = reference_comparison.get("largest_ltas_difference")
        if isinstance(largest, dict):
            frequency = _number(largest.get("center_hz"))
            delta = _number(largest.get("delta_db"))
            if frequency is not None and delta is not None:
                evidence.append({
                    "kind": "uploaded_reference_ltas",
                    "evidence_class": "session_measurement",
                    "largest_difference": {"center_hz": frequency, "delta_db": delta},
                    "comparison_basis": _text(reference_comparison.get("comparison_basis"), 512),
                    "limitations": [
                        "Measured against the uploaded reference after normalisation around 1 kHz.",
                        "It is a listening target, not an automatic or universal EQ instruction.",
                    ],
                })
        pink = pink_noise_evidence(reference_comparison)
        if pink is not None:
            evidence.append(pink)
    return evidence[:MAX_AUDIO_EVIDENCE]


def _mixdown_coach_from_context(context: dict[str, Any]) -> dict[str, Any] | None:
    """Build listening guidance only from a completed stored mix receipt.

    A Live snapshot, declared genre, or arbitrary caller payload must never
    manufacture a whole-mix target. The receipt has already been bounded by
    ``build_session_context`` and contains measurement metadata, not audio.
    """
    for measurement in context.get("measurements") or []:
        if not isinstance(measurement, dict):
            continue
        if measurement.get("schema") != "kenn.mix_review.reference_comparison.v1":
            continue
        if measurement.get("status") != "completed":
            continue
        comparison = measurement.get("reference_comparison")
        if not isinstance(comparison, dict):
            continue
        from kenn.core.mixdown_coach import build_mixdown_coach
        return build_mixdown_coach({"reference_comparison": comparison})
    return None


def _project_memory(context: dict[str, Any]) -> dict[str, Any]:
    """Expose only explicit preferences and reviewed outcome summaries."""
    preferences = []
    for item in (context.get("producer_preferences") or [])[:32]:
        if not isinstance(item, dict) or item.get("source") != "explicit_user_statement":
            continue
        key, value = _text(item.get("key"), 64), _text(item.get("value"), 256)
        if key and value:
            preferences.append({"key": key, "value": value, "source": "explicit_user_statement"})
    outcomes = []
    for item in (context.get("episodic_outcomes") or [])[:16]:
        if not isinstance(item, dict):
            continue
        verdict = _text(item.get("verdict"), 32)
        if verdict in {"keep", "revise", "reject"}:
            outcomes.append({
                "episode_id": _text(item.get("episode_id"), 128),
                "verdict": verdict,
                "requested_changes": [
                    _text(change, 256) for change in (item.get("requested_changes") or [])[:5]
                    if isinstance(change, str) and _text(change, 256)
                ],
                "source": "reviewed_production_episode",
            })
    return {
        "scope": "session_scoped",
        "session_id": _text(context.get("session_id"), 128),
        "explicit_preferences": preferences,
        "reviewed_outcomes": outcomes,
        "editable": True,
        "advisory_only": True,
        "limitations": [
            "Only explicit preferences and reviewed outcomes appear here; KENN does not infer durable preferences from a single answer.",
            "Memory is session-scoped and can be inspected or cleared by the producer.",
        ],
    }


def _session_observations(context: dict[str, Any]) -> dict[str, Any]:
    """Summarise only observed routing, sends, clips, and selection facts.

    This is intentionally a compact briefing rather than a second full
    snapshot.  It gives an explanation/planner enough context to say what
    KENN actually observed, while detailed identity remains in the bound
    session context and all writes still require a fresh proposal.
    """
    tracks = [item for item in (context.get("tracks") or []) if isinstance(item, dict)]
    scenes = [item for item in (context.get("scenes") or []) if isinstance(item, dict)]
    returns = [item for item in (context.get("return_tracks") or []) if isinstance(item, dict)]
    locators = [item for item in (context.get("locators") or []) if isinstance(item, dict)]
    observation_capabilities = context.get("observation_capabilities") if isinstance(context.get("observation_capabilities"), dict) else {}
    transport = context.get("transport") if isinstance(context.get("transport"), dict) else {}
    selected_track_index = transport.get("selected_track_index")
    selected_scene_index = transport.get("selected_scene_index")
    selected_device_track_index = transport.get("selected_device_track_index")
    selected_device_index = transport.get("selected_device_index")
    selected_track = next((item for item in tracks if item.get("index") == selected_track_index), None)
    selected_scene = next((item for item in scenes if item.get("index") == selected_scene_index), None)
    selected_device_track = next((item for item in tracks if item.get("index") == selected_device_track_index), None)
    selected_device = None
    if isinstance(selected_device_track, dict) and isinstance(selected_device_index, int):
        devices = selected_device_track.get("devices") or []
        if 0 <= selected_device_index < len(devices):
            device = devices[selected_device_index]
            selected_device = {
                "track_index": selected_device_track.get("index"),
                "track_name": _text(selected_device_track.get("name"), 128),
                "device_index": selected_device_index,
                "name": _text(device.get("name") if isinstance(device, dict) else device, 128),
            }
    routed_tracks = []
    active_sends = []
    track_meter_observations = []
    clip_count = 0
    arrangement_clip_count = 0
    group_memberships = []
    for track in tracks[:MAX_TRACK_ROLES]:
        meter = {}
        for key in ("output_meter_level", "output_meter_right"):
            value = _number(track.get(key))
            if value is not None and 0.0 <= value <= 1.0:
                meter[key] = value
        if meter:
            track_meter_observations.append({
                "track_index": track.get("index"),
                "track_name": _text(track.get("name"), 128),
                **meter,
                "scope": "instantaneous_post_fader",
                "advisory_only": True,
            })
        group_track_index = track.get("group_track_index")
        if isinstance(group_track_index, int) and not isinstance(group_track_index, bool):
            membership = {
                "track_index": track.get("index"),
                "track_name": _text(track.get("name"), 128),
                "group_track_index": group_track_index,
                "evidence_class": "observed_session_fact",
                "confidence": "observed_group_membership",
            }
            group_track_name = _text(track.get("group_track_name"), 128)
            if group_track_name:
                membership["group_track_name"] = group_track_name
            group_memberships.append(membership)
        routing = track.get("routing") if isinstance(track.get("routing"), dict) else {}
        if routing:
            routed_tracks.append({
                "track_index": track.get("index"), "track_name": _text(track.get("name"), 128),
                "routing": {key: _text(value, 128) for key, value in routing.items() if _text(value, 128)},
            })
        for send in (track.get("sends") or [])[:32]:
            if not isinstance(send, dict) or _number(send.get("value")) is None:
                continue
            if float(_number(send.get("value")) or 0.0) > 0.0:
                active_sends.append({
                    "track_index": track.get("index"), "track_name": _text(track.get("name"), 128),
                    "return_track_index": send.get("return_track_index"),
                    "return_track_name": _text(send.get("return_track_name"), 128),
                    "value": _number(send.get("value")),
                })
        clip_count += sum(1 for slot in (track.get("clip_slots") or []) if isinstance(slot, dict) and slot.get("has_clip") is True)
        arrangement_clip_count += sum(1 for clip in (track.get("arrangement_clips") or []) if isinstance(clip, dict))
    return {
        "selected_track": (
            {"index": selected_track.get("index"), "name": _text(selected_track.get("name"), 128)}
            if isinstance(selected_track, dict) else None
        ),
        "selected_scene": (
            {"index": selected_scene.get("index"), "name": _text(selected_scene.get("name"), 128)}
            if isinstance(selected_scene, dict) else None
        ),
        "selected_device": selected_device,
        "return_tracks": [
            {"index": item.get("index"), "name": _text(item.get("name"), 128), "device_count": len(item.get("devices") or [])}
            for item in returns[:64]
        ],
        "locators": [
            {"index": item.get("index"), "name": _text(item.get("name"), 128), "time_beats": _number(item.get("time_beats"))}
            for item in locators[:64] if _number(item.get("time_beats")) is not None
        ],
        "routed_tracks": routed_tracks[:MAX_TRACK_ROLES],
        "active_sends": active_sends[:128],
        "track_meter_observations": track_meter_observations[:MAX_TRACK_ROLES],
        "session_clip_count": clip_count,
        "arrangement_clip_count": arrangement_clip_count,
        "group_memberships": group_memberships[:MAX_TRACK_ROLES],
        "observation_capabilities": {
            _text(key, 64): value
            for key, value in observation_capabilities.items()
            if _text(key, 64) and isinstance(value, bool)
        },
        "source": "fresh_live_snapshot",
        "advisory_only": True,
    }


def build_session_intelligence(
    context: dict[str, Any],
    *,
    project_intent: dict[str, Any] | None = None,
    retrieval_sources: Iterable[dict[str, Any]] = (),
    reference_comparison: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create an advisory briefing from a validated current session context.

    The result is safe to show to a producer or give to an explanation model.
    It is intentionally *not* acceptable as Live mutation input.
    """
    validation = validate_session_context(context)
    context_comparison = context.get("realtime_mix_comparison") if isinstance(context, dict) else None
    effective_comparison = (
        reference_comparison
        if isinstance(reference_comparison, dict)
        else context_comparison
        if isinstance(context_comparison, dict)
        else None
    )
    observed_at = context.get("observed_at") if isinstance(context, dict) else None
    now = time.time()
    fresh = validation["ok"] is True
    limitations: list[str] = [
        "Read-only intelligence only; Live writes require a new proposal from a fresh session context.",
        "Creative suggestions are alternatives, not measured facts or automatic changes.",
    ]
    if not fresh:
        limitations.append("The source session context is invalid or stale; no current-session claim is available.")
    if isinstance(context, dict):
        limitations.extend(_text(item, 256) for item in (context.get("limitations") or [])[:16] if _text(item, 256))

    result: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "current" if fresh else "unavailable",
        "observed_at": observed_at if isinstance(observed_at, (int, float)) else None,
        "expires_at": (float(observed_at) + MAX_CONTEXT_AGE_SECONDS) if isinstance(observed_at, (int, float)) else None,
        "freshness": {
            "is_current": fresh,
            "age_seconds": round(max(0.0, now - float(observed_at)), 3) if isinstance(observed_at, (int, float)) else None,
            "source_schema": context.get("schema") if isinstance(context, dict) else "",
            "source_fingerprint": _text(context.get("snapshot_fingerprint"), 96) if isinstance(context, dict) else "",
        },
        "project_intent": _safe_project_intent(project_intent),
        "snapshot": {},
        "track_roles": [],
        "audio_classifications": [],
        "audio_evidence": [],
        "mixdown_coach": None,
        "realtime_mix_comparison": effective_comparison,
        "arrangement": {},
        "session_observations": {},
        "project_memory": {},
        "retrieval": _safe_retrieval_sources(retrieval_sources),
        "capability_state": {"available_actions": [], "read_only": True},
        "limitations": list(dict.fromkeys(limitations)),
        "mutation_authorized": False,
    }
    if not fresh:
        result["errors"] = list(validation.get("errors") or [])[:16]
        return result

    transport = context.get("transport") if isinstance(context.get("transport"), dict) else {}
    result["snapshot"] = {
        "session_id": _text(context.get("session_id"), 128),
        "fingerprint": _text(context.get("snapshot_fingerprint"), 96),
        "transport": {
            key: transport[key]
            for key in ("status", "tempo", "is_playing", "selected_track_index", "selected_scene_index", "selected_device_track_index", "selected_device_index", "selected_device_name", "signature_numerator", "signature_denominator", "root_note", "scale_name")
            if key in transport
        },
        "track_count": len(context.get("tracks") or []),
        "scene_count": len(context.get("scenes") or []),
        "return_track_count": len(context.get("return_tracks") or []),
    }
    result["track_roles"] = _track_roles(context)
    result["audio_classifications"] = _audio_classification_evidence(context)
    result["audio_evidence"] = _audio_evidence(context, effective_comparison)
    result["mixdown_coach"] = _mixdown_coach_from_context(context)
    result["arrangement"] = analyze_arrangement_context(context)
    result["session_observations"] = _session_observations(context)
    result["project_memory"] = _project_memory(context)
    result["capability_state"] = {
        "available_actions": list(context.get("available_actions") or []),
        "read_only": True,
        "write_prerequisites": ["fresh snapshot", "exact target identity", "explicit confirmation", "readback", "receipt"],
    }
    return result


def explanation_sections(brief: dict[str, Any]) -> list[dict[str, str]]:
    """Return display-safe provenance labels without generating advice."""
    if not isinstance(brief, dict) or brief.get("schema") != SCHEMA:
        return []
    sections: list[dict[str, str]] = []
    if brief.get("snapshot"):
        sections.append({"kind": "observed_session_fact", "label": "Observed in the current Live snapshot"})
    if brief.get("audio_evidence"):
        sections.append({"kind": "audio_measurement", "label": "Measured from supplied audio or a captured meter"})
    coach = brief.get("mixdown_coach") if isinstance(brief.get("mixdown_coach"), dict) else {}
    if coach.get("status") == "ready":
        sections.append({"kind": "measurement_guided_listening", "label": "Listening checks based on a supplied-reference measurement"})
    comparison = brief.get("realtime_mix_comparison") if isinstance(brief.get("realtime_mix_comparison"), dict) else {}
    if comparison.get("comparison_available") is True:
        sections.append({"kind": "realtime_mix_comparison", "label": "Directional comparison of the current plugin bus with an uploaded render"})
    if brief.get("track_roles"):
        sections.append({"kind": "specialist_inference", "label": "Inferred role; confirm or correct it"})
    if brief.get("audio_classifications"):
        sections.append({"kind": "audio_classification", "label": "Advisory audio-classifier evidence"})
    for source in brief.get("retrieval") or []:
        if isinstance(source, dict) and source.get("evidence_class") == "official_ableton_manual":
            sections.append({"kind": "official_technical_reference", "label": "Grounded in the authorized Ableton manual"})
            break
    if any(
        isinstance(source, dict) and source.get("evidence_class") == "youtube_transcript"
        for source in brief.get("retrieval") or []
    ):
        sections.append({"kind": "producer_technique_reference", "label": "Based on reviewed producer technique; treat as advisory"})
    if brief.get("project_intent", {}).get("declared"):
        sections.append({"kind": "producer_intent", "label": "Based on your declared project intent"})
    memory = brief.get("project_memory") if isinstance(brief.get("project_memory"), dict) else {}
    if memory.get("explicit_preferences") or memory.get("reviewed_outcomes"):
        sections.append({"kind": "explicit_project_memory", "label": "Based on editable, explicit project memory"})
    return sections


__all__ = ["SCHEMA", "build_session_intelligence", "explanation_sections", "retrieval_sources_from_cache"]
