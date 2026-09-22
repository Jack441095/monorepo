"""Bounded, provenance-aware context for KENN's integrated tools.

The context is a read-only composition of observations.  It does not call
Ableton, write files, launch jobs, or apply Live changes.  Mutation services
consume their own fresh snapshots and remain the authority for writes.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections import OrderedDict, deque
from threading import Lock
from typing import Any, Iterable

from kenn.core.audiogen_artifacts import safe_artifact_metadata
from kenn.core.audio_classification import AudioClassificationError, normalize as normalize_audio_classification
from kenn.core.track_classifier import classify_track_context


SCHEMA = "kenn.session_context.v1"
CONTEXT_BINDING_SCHEMA = "kenn.assistant_context_binding.v1"
MAX_TRACKS = 256
MAX_DEVICES_PER_TRACK = 64
MAX_MATRIX_ENTRIES = 256
MAX_PARAMETERS_PER_DEVICE = 128
MAX_JOBS = 32
MAX_FEEDBACK = 16
MAX_TEXT = 512
MAX_SCENES = 1_024
MAX_LOCATORS = 1_024
MAX_RETURN_TRACKS = 64
MAX_CLIP_SLOTS_PER_TRACK = 256
MAX_SENDS_PER_TRACK = 64
MAX_CONTEXT_AGE_SECONDS = 300.0
MAX_PRODUCER_PREFERENCES = 32
MAX_EPISODIC_OUTCOMES = 64
MAX_AUDIO_CLASSIFICATIONS = 32
MAX_LIVE_CONVERSATION_SESSIONS = 256
MAX_LIVE_EXCHANGES = 10
_LIVE_CONVERSATION_LOCK = Lock()
_LIVE_CONVERSATIONS: OrderedDict[str, dict[str, Any]] = OrderedDict()


def _text(value: Any, limit: int = MAX_TEXT) -> str:
    return str(value or "").strip()[:limit]


def _source_envelope(kind: str, payload: dict[str, Any], *, status: str = "observed") -> dict[str, Any]:
    return {
        "kind": _text(kind, 96),
        "status": _text(status, 64) or "observed",
        "observed_at": time.time(),
        "schema": _text(payload.get("schema"), 128),
    }


def _live_track(track: dict[str, Any]) -> dict[str, Any]:
    devices = [
        {"index": item.get("index"), "name": _text(item.get("name"), 128)}
        for item in (track.get("devices") or [])[:MAX_DEVICES_PER_TRACK]
        if isinstance(item, dict)
    ]
    name = _text(track.get("name"), 128)
    result = {
        "index": track.get("index"),
        "name": name,
        "type": _text(track.get("type"), 64),
        "devices": devices,
        "volume": track.get("volume"),
        "pan": track.get("pan"),
        "muted": bool(track.get("muted", False)),
        "soloed": bool(track.get("soloed", False)),
        "armed": bool(track.get("armed", False)),
        "routing": {
            key: _text(track[key], 128)
            for key in (
                "input_routing_type", "input_routing_channel",
                "output_routing_type", "output_routing_channel",
            )
            if track.get(key) not in (None, "")
        },
        "sends": [
            {
                key: item[key]
                for key in ("index", "return_track_index", "return_track_name", "value")
                if key in item
            }
            for item in (track.get("sends") or [])[:MAX_SENDS_PER_TRACK]
            if isinstance(item, dict)
        ],
        "clip_slots": [
            {
                key: item[key]
                for key in ("index", "name", "has_clip", "is_playing", "is_recording", "length", "color")
                if key in item
            }
            for item in (track.get("clip_slots") or [])[:MAX_CLIP_SLOTS_PER_TRACK]
            if isinstance(item, dict)
        ],
        "arrangement_clips": [
            {
                key: item[key]
                for key in ("index", "name", "length_beats", "start_time_beats")
                if key in item
            }
            for item in (track.get("arrangement_clips") or [])[:MAX_CLIP_SLOTS_PER_TRACK]
            if isinstance(item, dict)
        ],
    }
    if isinstance(track.get("group_track_index"), int) and not isinstance(track.get("group_track_index"), bool):
        result["group_track_index"] = track["group_track_index"]
        group_name = _text(track.get("group_track_name"), 128)
        if group_name:
            result["group_track_name"] = group_name
    for key in ("is_grouped", "is_foldable"):
        if isinstance(track.get(key), bool):
            result[key] = track[key]
    # Ableton exposes these as instantaneous post-fader meter values. Keep
    # them optional and bounded: they are useful evidence for headroom advice,
    # but are not audio-rate peaks, LUFS, true peak, or spectrum data.
    for key in ("output_meter_level", "output_meter_right"):
        value = track.get(key)
        if (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            and 0.0 <= float(value) <= 1.0
        ):
            result[key] = float(value)
    result["classification"] = classify_track_context(
        name,
        track_index=track.get("index") if isinstance(track.get("index"), int) else None,
        track_type=result["type"],
        devices=devices,
    )
    return result


def _safe_mix_review(receipt: dict[str, Any]) -> dict[str, Any]:
    allowed = ("schema", "status", "analysis_version", "input_context", "metrics", "findings", "action_plan", "limitations")
    result = {key: receipt[key] for key in allowed if key in receipt}
    comparison = receipt.get("reference_comparison")
    if isinstance(comparison, dict):
        safe: dict[str, Any] = {
            "comparison_basis": _text(comparison.get("comparison_basis"), 512),
            "lufs_delta_db": comparison.get("lufs_delta_db"),
        }
        for key in ("largest_spectral_difference", "largest_ltas_difference"):
            item = comparison.get(key)
            if isinstance(item, dict):
                safe[key] = {
                    field: item[field]
                    for field in ("band", "center_hz", "low_hz", "high_hz", "delta_db")
                    if field in item and isinstance(item[field], (str, int, float)) and not isinstance(item[field], bool)
                }
        pink_noise = comparison.get("pink_noise_reference")
        if isinstance(pink_noise, dict):
            safe_pink: dict[str, Any] = {
                key: pink_noise[key]
                for key in ("status", "curve", "slope_db_per_octave", "anchor_frequency_hz")
                if key in pink_noise and isinstance(pink_noise[key], (str, int, float)) and not isinstance(pink_noise[key], bool)
            }
            largest_pink = pink_noise.get("largest_deviation")
            if isinstance(largest_pink, dict):
                safe_pink["largest_deviation"] = {
                    field: largest_pink[field]
                    for field in ("center_hz", "measured_relative_db", "pink_expected_relative_db", "deviation_db")
                    if field in largest_pink and isinstance(largest_pink[field], (int, float)) and not isinstance(largest_pink[field], bool)
                }
            if safe_pink:
                safe["pink_noise_reference"] = safe_pink
        result["reference_comparison"] = safe
    return result


def safe_audio_job(job: dict[str, Any]) -> dict[str, Any]:
    allowed = ("schema", "id", "job_id", "status", "kind", "emotion", "bars", "bpm", "key", "artifact", "provenance", "error")
    result = {key: job[key] for key in allowed if key in job}
    artifact = result.get("artifact")
    if not isinstance(artifact, dict) and isinstance(job.get("result"), dict):
        artifact = job["result"].get("artifact")
    if isinstance(artifact, dict):
        result["artifact"] = safe_artifact_metadata(artifact)
    return result


def _safe_automix_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    allowed = (
        "schema", "status", "job_id", "project_id", "engine", "progress", "genre",
        "human_approval", "source", "delivery", "error",
    )
    result = {key: receipt[key] for key in allowed if key in receipt}
    source = result.get("source")
    if isinstance(source, dict):
        result["source"] = {
            key: source[key] for key in ("files", "sha256") if key in source
        }
    return result


def _safe_audio_classification(value: Any) -> dict[str, Any] | None:
    """Accept only completed, contract-valid advisory classifier evidence."""
    if not isinstance(value, dict) or value.get("status") != "completed":
        return None
    try:
        return {"status": "completed", **normalize_audio_classification(value)}
    except AudioClassificationError:
        return None


def _safe_device_matrix(matrix: dict[str, Any] | None) -> dict[str, Any] | None:
    """Keep the read-only capability inventory bounded for planner context."""
    if not isinstance(matrix, dict) or matrix.get("schema") != "kenn.ableton_device_matrix.v1":
        return None
    safe: dict[str, Any] = {
        "schema": "kenn.ableton_device_matrix.v1",
        "status": _text(matrix.get("status"), 64),
        "connected": bool(matrix.get("connected")),
        "transport": _text(matrix.get("transport"), 64),
        "entries": [],
        "observed_families": [_text(item, 128) for item in (matrix.get("observed_families") or [])[:64]],
        "missing_candidate_families": [_text(item, 128) for item in (matrix.get("missing_candidate_families") or [])[:64]],
        "families": {},
        "write_boundary": {
            "report_is_read_only": True,
            "writes_still_require": ["exact identity", "confirmation", "stale check", "readback", "receipt"],
        },
    }
    families = matrix.get("families") if isinstance(matrix.get("families"), dict) else {}
    safe["families"] = {
        _text(name, 128): {
            "qualification": _text(value.get("qualification"), 64),
            "next_control": _text(value.get("next_control"), 256),
        }
        for name, value in list(families.items())[:64]
        if isinstance(value, dict)
    }
    for entry in (matrix.get("entries") or [])[:MAX_MATRIX_ENTRIES]:
        if not isinstance(entry, dict):
            continue
        item: dict[str, Any] = {
            "track_index": entry.get("track_index"),
            "track_name": _text(entry.get("track_name"), 128),
            "device_index": entry.get("device_index"),
            "device_name": _text(entry.get("device_name"), 128),
            "qualification": _text(entry.get("qualification"), 64),
            "next_control": _text(entry.get("next_control"), 256),
        }
        probe = entry.get("parameter_probe") if isinstance(entry.get("parameter_probe"), dict) else None
        if probe is not None:
            parameters = []
            for parameter in (probe.get("parameters") or [])[:MAX_PARAMETERS_PER_DEVICE]:
                if not isinstance(parameter, dict):
                    continue
                parameters.append({
                    key: parameter[key]
                    for key in ("index", "name", "value", "min", "max", "value_display", "readable", "quantized")
                    if key in parameter
                })
            item["parameter_probe"] = {
                "success": bool(probe.get("success")),
                "parameter_count": int(probe.get("parameter_count", len(parameters)) or 0),
                "parameters": parameters,
            }
        safe["entries"].append(item)
    if matrix.get("error"):
        safe["error"] = _text(matrix.get("error"), 512)
    return safe


def _safe_preference(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict) or value.get("schema") != "kenn.producer_preference.v1":
        return None
    key = _text(value.get("key"), 64)
    preference = _text(value.get("value"), 256)
    if not key or not preference or value.get("advisory_only") is not True:
        return None
    return {
        "schema": "kenn.producer_preference.v1",
        "preference_id": _text(value.get("preference_id"), 128),
        "key": key,
        "value": preference,
        "source": "explicit_user_statement",
        "source_turn_id": _text(value.get("source_turn_id"), 128),
        "confidence": "explicit",
        "advisory_only": True,
        "created_at": _text(value.get("created_at"), 64),
    }


def _safe_episode(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict) or value.get("schema") != "kenn.production_episode.v1":
        return None
    verdict = _text(value.get("verdict"), 32)
    if verdict not in {"keep", "revise", "reject"} or value.get("advisory_only") is not True:
        return None
    evidence_refs = []
    for item in (value.get("evidence_refs") or [])[:8]:
        if not isinstance(item, dict):
            continue
        evidence_refs.append({
            key: item[key]
            for key in (
                "step_id", "evidence_schema", "receipt_id", "job_id", "project_id",
                "action_id", "status", "verified", "action", "kind",
            )
            if key in item and isinstance(item[key], (str, int, float, bool, type(None)))
        })
    if not evidence_refs:
        return None
    return {
        "schema": "kenn.production_episode.v1",
        "episode_id": _text(value.get("episode_id"), 128),
        "task_id": _text(value.get("task_id"), 128),
        "goal": _text(value.get("goal"), 1_024),
        "verdict": verdict,
        "comment": _text(value.get("comment"), 1_000),
        "requested_changes": [
            _text(item, 256) for item in (value.get("requested_changes") or [])[:5]
            if isinstance(item, str) and _text(item, 256)
        ],
        "evidence_refs": evidence_refs,
        "advisory_only": True,
        "created_at": _text(value.get("created_at"), 64),
    }


def _fingerprint(context: dict[str, Any]) -> str:
    material = dict(context)
    material.pop("snapshot_fingerprint", None)
    material.pop("observed_at", None)
    material.pop("sources", None)
    encoded = json.dumps(material, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _domain_digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _scoped_entry_digests(items: Any, identity_keys: tuple[str, ...]) -> dict[str, Any]:
    identified: dict[str, list[str]] = {}
    unidentified: list[str] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        digest = _domain_digest(item)
        identity = next((str(item.get(key) or "").strip() for key in identity_keys if str(item.get(key) or "").strip()), "")
        if identity:
            identified.setdefault(identity[:128], []).append(digest)
        else:
            unidentified.append(digest)
    return {
        "identified": {key: sorted(values) for key, values in sorted(identified.items())},
        "unidentified": sorted(unidentified),
    }


def assistant_context_binding(context: dict[str, Any]) -> dict[str, Any]:
    """Create compact domain identities for evidence-scoped task rebinding."""
    live_material = {
        key: context.get(key)
        for key in (
            "transport", "tracks", "devices", "scenes", "return_tracks",
            "master_track", "device_capability_matrix",
        )
    }
    return {
        "schema": CONTEXT_BINDING_SCHEMA,
        "session_id": str(context.get("session_id") or "")[:128],
        "live": _domain_digest(live_material),
        "services": _domain_digest(context.get("service_capabilities")),
        "measurements": _domain_digest(context.get("measurements")),
        "audio_classification": _domain_digest(context.get("audio_classifications")),
        "audition": _domain_digest(context.get("audition_feedback")),
        "profile": _domain_digest({
            "producer_preferences": context.get("producer_preferences"),
            "episodic_outcomes": context.get("episodic_outcomes"),
        }),
        "generation": _scoped_entry_digests(context.get("generated_jobs"), ("job_id", "id")),
        "offline": _scoped_entry_digests(context.get("offline_jobs"), ("job_id", "project_id", "id")),
    }


def build_session_context(
    *,
    snapshot: dict[str, Any] | None = None,
    session_id: str = "",
    plugin_frames: Iterable[dict[str, Any]] = (),
    mix_review_receipts: Iterable[dict[str, Any]] = (),
    audiogen_jobs: Iterable[dict[str, Any]] = (),
    automix_receipts: Iterable[dict[str, Any]] = (),
    audio_classifications: Iterable[dict[str, Any]] = (),
    audition_feedback: Iterable[dict[str, Any]] = (),
    device_matrix: dict[str, Any] | None = None,
    audiogen_available: bool = False,
    offline_render_available: bool = False,
    producer_preferences: Iterable[dict[str, Any]] = (),
    episodic_outcomes: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Compose bounded observations without performing any external action."""
    context: dict[str, Any] = {
        "schema": SCHEMA,
        "session_id": _text(session_id, 128),
        "observed_at": time.time(),
        "snapshot_fingerprint": "",
        "versions": {
            "live_snapshot": "kenn.live_snapshot.v1",
            "world_model": "kenn.session_context.v1",
            "track_context": "kenn.track_context.v1",
            "device_capabilities": "kenn.ableton_device_matrix.v1",
            "mix_review": "kenn.mix_review.local_engine.v1",
            "audio_classification": "kenn.audio_classification.v1",
            "planner": "kenn.deliberative_plan.v1",
        },
        "transport": {},
        "tracks": [],
        "devices": [],
        "scenes": [],
        "locators": [],
        "return_tracks": [],
        "observation_capabilities": {},
        "master_track": None,
        "device_capability_matrix": None,
        "measurements": [],
        "audio_classifications": [],
        "generated_jobs": [],
        "offline_jobs": [],
        "audition_feedback": [],
        "producer_preferences": [],
        "episodic_outcomes": [],
        "service_capabilities": {
            "audiogen_available": audiogen_available is True,
            "offline_render_available": offline_render_available is True,
        },
        "sources": [],
        "available_actions": [],
        "limitations": [],
    }

    if isinstance(snapshot, dict):
        context["transport"] = {
            key: snapshot[key]
            for key in (
                "status", "tempo", "is_playing", "selected_track_index",
                "selected_scene_index", "selected_device_track_index",
                "selected_device_index", "selected_device_name",
                "signature_numerator", "signature_denominator", "root_note", "scale_name",
            )
            if key in snapshot
        }
        context["tracks"] = [_live_track(item) for item in (snapshot.get("tracks") or [])[:MAX_TRACKS] if isinstance(item, dict)]
        context["scenes"] = [
            {"index": item.get("index"), "name": _text(item.get("name"), 128)}
            for item in (snapshot.get("scenes") or [])[:MAX_SCENES]
            if isinstance(item, dict)
        ]
        context["locators"] = [
            {
                "index": item.get("index"),
                "name": _text(item.get("name"), 128),
                "time_beats": item.get("time_beats"),
            }
            for item in (snapshot.get("locators") or [])[:MAX_LOCATORS]
            if isinstance(item, dict) and isinstance(item.get("time_beats"), (int, float))
            and not isinstance(item.get("time_beats"), bool)
        ]
        context["return_tracks"] = [
            {
                "index": item.get("index"),
                "name": _text(item.get("name"), 128),
                "devices": [
                    {"index": device.get("index"), "name": _text(device.get("name"), 128)}
                    for device in (item.get("devices") or [])[:MAX_DEVICES_PER_TRACK]
                    if isinstance(device, dict)
                ],
            }
            for item in (snapshot.get("return_tracks") or [])[:MAX_RETURN_TRACKS]
            if isinstance(item, dict)
        ]
        raw_capabilities = snapshot.get("understanding_capabilities")
        if isinstance(raw_capabilities, dict):
            context["observation_capabilities"] = {
                _text(key, 64): value
                for key, value in list(raw_capabilities.items())[:32]
                if _text(key, 64) and isinstance(value, bool)
            }
        master = snapshot.get("master_track")
        if isinstance(master, dict):
            context["master_track"] = {
                "name": _text(master.get("name"), 128) or "Master",
                "volume": master.get("volume"),
                "pan": master.get("pan"),
                "devices": [
                    {"index": device.get("index"), "name": _text(device.get("name"), 128)}
                    for device in (master.get("devices") or [])[:MAX_DEVICES_PER_TRACK]
                    if isinstance(device, dict)
                ],
            }
        for track in context["tracks"]:
            for device in track["devices"]:
                context["devices"].append({
                    "track_index": track["index"],
                    "track_name": track["name"],
                    **device,
                })
        status = _text(snapshot.get("status"), 64) or "unknown"
        context["sources"].append(_source_envelope("live_snapshot", snapshot, status=status))
        if status == "connected":
            context["available_actions"].extend(["inspect_live", "create_live_proposal"])
        else:
            context["limitations"].append("Live snapshot is not connected; no Live proposal can be trusted.")
    else:
        context["limitations"].append("No Live snapshot was supplied.")

    if audiogen_available is True:
        context["available_actions"].append("create_generation_job")
    else:
        context["limitations"].append("Audio generation job creation is unavailable or unverified.")
    if offline_render_available is True:
        context["available_actions"].append("create_offline_render")
    else:
        context["limitations"].append("Offline render creation is unavailable or unverified.")

    safe_matrix = _safe_device_matrix(device_matrix)
    if safe_matrix is not None:
        context["device_capability_matrix"] = safe_matrix
        context["sources"].append(_source_envelope("live_device_matrix", safe_matrix, status=safe_matrix.get("status", "observed")))
        if safe_matrix.get("connected"):
            context["available_actions"].append("inspect_device_capabilities")
    else:
        context["limitations"].append("No Live device capability matrix was supplied.")

    for frame in list(plugin_frames)[:MAX_JOBS]:
        if not isinstance(frame, dict):
            continue
        measurement = {
            "kind": "plugin_feature_frame",
            "schema": _text(frame.get("schema"), 128),
            "metrics": {key: frame[key] for key in ("peak_dbfs", "rms_dbfs", "stereo_correlation", "stereo_width", "crest_db", "transient_ratio", "clipped_samples", "low_energy", "mid_energy", "high_energy") if key in frame},
            "scope": _text(frame.get("scope"), 64) or "plugin_bus",
            "plugin_state": frame.get("plugin_state", {}),
        }
        # These fields are already bounded by the validated plug-in handoff.
        # Carry them into the explicit context so reasoning clients can see
        # trend/freshness evidence rather than only the latest scalar meters.
        for key in ("spectrum_schema", "spectrum_bands", "pink_noise_reference", "live_window", "freshness"):
            if key in frame and isinstance(frame[key], (dict, list, str, int, float, bool)):
                measurement[key] = frame[key]
        context["measurements"].append(measurement)
        context["sources"].append(_source_envelope("plugin_feature_frame", frame))

    for receipt in list(mix_review_receipts)[:MAX_JOBS]:
        if not isinstance(receipt, dict):
            continue
        context["measurements"].append({"kind": "mix_review", **_safe_mix_review(receipt)})
        context["sources"].append(_source_envelope("mix_review", receipt, status=_text(receipt.get("status"), 64) or "observed"))

    for job in list(audiogen_jobs)[:MAX_JOBS]:
        if not isinstance(job, dict):
            continue
        safe_job = safe_audio_job(job)
        context["generated_jobs"].append(safe_job)
        context["sources"].append(_source_envelope("audiogen_job", job, status=_text(job.get("status"), 64) or "observed"))
        if safe_job.get("status") in {"completed", "success"}:
            context["available_actions"].append("review_generated_asset")

    for receipt in list(automix_receipts)[:MAX_JOBS]:
        if not isinstance(receipt, dict):
            continue
        safe_receipt = _safe_automix_receipt(receipt)
        context["offline_jobs"].append(safe_receipt)
        context["sources"].append(_source_envelope("automix_receipt", receipt, status=_text(receipt.get("status"), 64) or "observed"))
        if safe_receipt.get("status") == "completed":
            context["available_actions"].append("compare_offline_candidate")
        if safe_receipt.get("schema") == "kenn.automix.local_receipt.v1":
            context["available_actions"].append("bind_offline_render")

    for value in list(audio_classifications)[:MAX_AUDIO_CLASSIFICATIONS]:
        classification = _safe_audio_classification(value)
        if classification is None:
            continue
        context["audio_classifications"].append(classification)
        context["sources"].append(_source_envelope(
            "audio_classification", classification, status=classification["out_of_distribution"]["status"],
        ))

    for feedback in list(audition_feedback)[:MAX_FEEDBACK]:
        if not isinstance(feedback, dict):
            continue
        safe_feedback = {
            "schema": _text(feedback.get("schema"), 128),
            "feedback_id": _text(feedback.get("feedback_id"), 128),
            "session_id": _text(feedback.get("session_id"), 128),
            "source_receipt_id": _text(feedback.get("source_receipt_id"), 256),
            "verdict": _text(feedback.get("verdict"), 32),
            "rating": feedback.get("rating"),
            "comment": _text(feedback.get("comment"), 1000),
            "requested_changes": [
                _text(item, 256) for item in (feedback.get("requested_changes") or [])[:5]
                if _text(item, 256)
            ],
            "audition": feedback.get("audition") if isinstance(feedback.get("audition"), dict) else {},
            "created_at": feedback.get("created_at"),
            "advisory_only": True,
        }
        context["audition_feedback"].append(safe_feedback)
        context["sources"].append(_source_envelope("audition_feedback", feedback))
        if safe_feedback["verdict"] == "revise":
            context["available_actions"].append("revise_audition")

    for value in list(producer_preferences)[:MAX_PRODUCER_PREFERENCES]:
        preference = _safe_preference(value)
        if preference is not None:
            context["producer_preferences"].append(preference)
            context["sources"].append(_source_envelope("producer_preference", preference, status="explicit"))

    for value in list(episodic_outcomes)[:MAX_EPISODIC_OUTCOMES]:
        episode = _safe_episode(value)
        if episode is not None:
            context["episodic_outcomes"].append(episode)
            context["sources"].append(_source_envelope("production_episode", episode, status=episode["verdict"]))

    context["available_actions"] = sorted(set(context["available_actions"]))
    context["snapshot_fingerprint"] = _fingerprint(context)
    return context


def validate_session_context(context: Any) -> dict[str, Any]:
    """Validate the structural safety envelope without trusting its claims."""
    if not isinstance(context, dict) or context.get("schema") != SCHEMA:
        return {"ok": False, "errors": [f"Expected {SCHEMA}."]}
    errors: list[str] = []
    for key in ("session_id", "snapshot_fingerprint", "versions", "transport", "tracks", "devices", "scenes", "locators", "return_tracks", "observation_capabilities", "master_track", "service_capabilities", "sources"):
        if key not in context:
            errors.append(f"Missing context field: {key}")
    for key in ("tracks", "devices", "scenes", "locators", "return_tracks", "sources", "measurements", "audio_classifications", "generated_jobs", "offline_jobs", "audition_feedback", "producer_preferences", "episodic_outcomes"):
        if key in context and not isinstance(context[key], list):
            errors.append(f"Context field {key} must be a list.")
    services = context.get("service_capabilities")
    if not isinstance(services, dict) or any(
        not isinstance(services.get(key), bool)
        for key in ("audiogen_available", "offline_render_available")
    ):
        errors.append("Context service_capabilities must contain explicit boolean availability flags.")
    observation_capabilities = context.get("observation_capabilities")
    if not isinstance(observation_capabilities, dict) or any(
        not isinstance(key, str) or not key or len(key) > 64 or not isinstance(value, bool)
        for key, value in observation_capabilities.items()
    ):
        errors.append("Context observation_capabilities must be a bounded boolean map.")
    tracks = context.get("tracks") if isinstance(context.get("tracks"), list) else []
    scenes = context.get("scenes") if isinstance(context.get("scenes"), list) else []
    locators = context.get("locators") if isinstance(context.get("locators"), list) else []
    return_tracks = context.get("return_tracks") if isinstance(context.get("return_tracks"), list) else []
    if len(tracks) > MAX_TRACKS:
        errors.append("Context contains too many tracks.")
    if len(scenes) > MAX_SCENES:
        errors.append("Context contains too many scenes.")
    if len(locators) > MAX_LOCATORS:
        errors.append("Context contains too many locators.")
    if len(return_tracks) > MAX_RETURN_TRACKS:
        errors.append("Context contains too many return tracks.")
    if isinstance(context.get("producer_preferences"), list) and len(context["producer_preferences"]) > MAX_PRODUCER_PREFERENCES:
        errors.append("Context contains too many producer preferences.")
    if isinstance(context.get("episodic_outcomes"), list) and len(context["episodic_outcomes"]) > MAX_EPISODIC_OUTCOMES:
        errors.append("Context contains too many episodic outcomes.")
    if isinstance(context.get("audio_classifications"), list) and len(context["audio_classifications"]) > MAX_AUDIO_CLASSIFICATIONS:
        errors.append("Context contains too many audio classifications.")
    if isinstance(context.get("audio_classifications"), list):
        for position, item in enumerate(context["audio_classifications"], start=1):
            if not isinstance(item, dict) or item.get("status") not in {None, "completed"}:
                errors.append(f"Audio classification {position} is not a completed result.")
                continue
            try:
                normalize_audio_classification(item)
            except AudioClassificationError as exc:
                errors.append(f"Audio classification {position} is invalid: {exc}")
    observed_at = context.get("observed_at")
    if not isinstance(observed_at, (int, float)) or isinstance(observed_at, bool) or not math.isfinite(observed_at):
        errors.append("observed_at must be a Unix timestamp.")
    elif observed_at > time.time() + 5:
        errors.append("observed_at cannot be in the future.")
    elif time.time() - observed_at > MAX_CONTEXT_AGE_SECONDS:
        errors.append("Session context is stale and must be refreshed before planning.")
    if context.get("device_capability_matrix") is not None and not isinstance(context.get("device_capability_matrix"), dict):
        errors.append("device_capability_matrix must be an object or null.")
    if context.get("master_track") is not None and not isinstance(context.get("master_track"), dict):
        errors.append("master_track must be an object or null.")
    if not isinstance(context.get("available_actions"), list):
        errors.append("available_actions must be a list.")
    elif any(not isinstance(item, str) or not item.strip() for item in context["available_actions"]):
        errors.append("available_actions must contain non-empty strings.")
    if not isinstance(context.get("snapshot_fingerprint"), str) or not context.get("snapshot_fingerprint", "").startswith("sha256:"):
        errors.append("snapshot_fingerprint must be a sha256 identifier.")
    return {"ok": not errors, "errors": errors, "schema": SCHEMA}


def refresh_session_context_fingerprint(context: dict[str, Any]) -> dict[str, Any]:
    """Refresh the fingerprint after a caller adds bounded limitations."""
    if isinstance(context, dict) and context.get("schema") == SCHEMA:
        context["snapshot_fingerprint"] = _fingerprint(context)
    return context


def _live_conversation(session_id: str) -> dict[str, Any]:
    key = _text(session_id, 128)
    with _LIVE_CONVERSATION_LOCK:
        state = _LIVE_CONVERSATIONS.get(key)
        if state is None:
            state = {
                "exchanges": deque(maxlen=MAX_LIVE_EXCHANGES),
                "last_track": "",
                "last_device": "",
                "last_parameter": "",
                "last_command": "",
                "last_action": "",
                "last_receipt_id": "",
                "confirmation_status": "none",
                "current_topic": "",
            }
            _LIVE_CONVERSATIONS[key] = state
        _LIVE_CONVERSATIONS.move_to_end(key)
        while len(_LIVE_CONVERSATIONS) > MAX_LIVE_CONVERSATION_SESSIONS:
            _LIVE_CONVERSATIONS.popitem(last=False)
        return state


def preprocess_live_command(command: str, *, session_id: str) -> tuple[str, dict[str, Any]]:
    """Resolve bounded anaphora from the last ten exchanges in one session."""
    original = " ".join(str(command or "").split())
    state = _live_conversation(session_id)
    lower = original.casefold()
    if lower in {"again", "do it again", "same again"} and state["last_command"]:
        return str(state["last_command"]), {"resolution": "repeat_last_action", "original": original}
    if re.fullmatch(r"(?:please\s+)?undo(?:\s+that|\s+it)?[.!]?", lower):
        return "undo", {"resolution": "undo_last_receipt", "original": original}

    resolved = original
    entity = state["last_device"] or state["last_track"]
    if entity and re.search(r"\b(?:it|that)\b", resolved, re.I):
        resolved = re.sub(r"\b(?:it|that)\b", str(entity), resolved, count=1, flags=re.I)
    if state["last_track"] and re.search(r"\b(?:louder|softer|quieter)\b", resolved, re.I):
        known = str(state["last_track"]).casefold() in resolved.casefold()
        if not known:
            resolved = f"{resolved} on {state['last_track']}"
    metadata = {"resolution": "anaphora" if resolved != original else "none", "original": original}
    return resolved, metadata


def record_live_exchange(*, session_id: str, command: str, result: dict[str, Any]) -> None:
    """Store a bounded conversational projection; never store confirmation tokens."""
    if not isinstance(result, dict):
        return
    state = _live_conversation(session_id)
    intent = result.get("intent") if isinstance(result.get("intent"), dict) else {}
    proposal = result.get("proposal") if isinstance(result.get("proposal"), dict) else {}
    receipt = result.get("receipt") if isinstance(result.get("receipt"), dict) else {}
    track = intent.get("track") if isinstance(intent.get("track"), dict) else {}
    device = intent.get("device") if isinstance(intent.get("device"), dict) else {}
    parameter = intent.get("parameter") if isinstance(intent.get("parameter"), dict) else {}
    track_name = str(track.get("name") or proposal.get("track_name") or (receipt.get("target") or {}).get("track_name") or "")
    device_name = str(device.get("name") or proposal.get("device_name") or (receipt.get("target") or {}).get("device_name") or "")
    parameter_name = str(parameter.get("name") or proposal.get("parameter_name") or (receipt.get("target") or {}).get("parameter_name") or "")
    action = str(intent.get("action") or proposal.get("action") or receipt.get("action") or "")
    status = str(result.get("status") or "")
    with _LIVE_CONVERSATION_LOCK:
        if track_name:
            state["last_track"] = track_name[:128]
        if device_name:
            state["last_device"] = device_name[:128]
        if parameter_name:
            state["last_parameter"] = parameter_name[:128]
        if action:
            state["last_action"] = action[:128]
            state["current_topic"] = action[:128]
        if command and status not in {"invalid", "failed", "clarification_required"}:
            state["last_command"] = _text(command, 4000)
        if receipt.get("receipt_id"):
            state["last_receipt_id"] = _text(receipt.get("receipt_id"), 128)
        state["confirmation_status"] = (
            "pending" if status in {"confirmation_required", "requires_confirmation"}
            else "confirmed" if status == "applied"
            else "rejected" if status in {"rejected", "invalid"}
            else state["confirmation_status"]
        )
        state["exchanges"].append({
            "command": _text(command, 4000),
            "status": status[:64],
            "action": action[:128],
            "track": track_name[:128],
            "device": device_name[:128],
            "timestamp": time.time(),
        })


def live_conversation_context(session_id: str) -> dict[str, Any]:
    """Return a copy suitable for diagnostics and tests."""
    state = _live_conversation(session_id)
    with _LIVE_CONVERSATION_LOCK:
        return {**state, "exchanges": list(state["exchanges"])}


__all__ = [
    "CONTEXT_BINDING_SCHEMA", "SCHEMA", "assistant_context_binding", "build_session_context",
    "live_conversation_context", "preprocess_live_command", "record_live_exchange",
    "refresh_session_context_fingerprint", "safe_audio_job", "validate_session_context",
]
