"""Characterisation of the MCP intent router in ``kenn.core.mcp_facade``.

``_dispatch`` used to be a single 1900-line if/elif chain that held every MCP
tool body inline, so an intent's routing, its argument refusals, and its return
shape were all one edit away from each other.  These tests were written against
that chain *before* it was split into per-family handler modules, which is the
only reason the split could be treated as a pure move: for all 72 advertised
intents they pin which KENN endpoints get called, which arguments are refused,
and with which message.

``OUTCOMES`` is captured, not derived.  If an intent genuinely needs to change,
update the table in the same commit and say why in that intent's test.

``OUTCOMES`` alone only proves argument validation: most intents refuse an empty
call before they reach KENN, so a wrong handler that also refused would pass it.
``ROUTES`` is the half that proves routing -- the same 72 intents called with
arguments good enough to get past the guards, pinning which endpoints each one
reaches.  Both tables are load-bearing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from kenn.core.assistant_coordinator import AssistantCoordinator
from kenn.core.assistant_task_memory import AssistantTaskStore
from kenn.core.mcp import HANDLERS
from kenn.core.mcp_facade import TOOLS, KennMCPFacade, KennTransportError


ADVERTISED = [tool["name"] for tool in TOOLS]

CONTEXT_READ = [
    "GET /api/ableton/osc/session",
    "GET /api/ableton/device-matrix",
    "GET /api/audiogen/status",
    "GET /api/ableton/audition-feedback",
]
"""What a session-scoped ``kenn_context`` costs: snapshot, matrix, queue, feedback."""


class RecordingHTTP:
    """Minimal KENN stand-in that records every request it is handed.

    Deliberately shape-agnostic: this file characterises the router, so it pins
    which endpoints an intent reaches rather than what KENN would answer.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.requests: list[tuple[str, str, dict]] = []

    def get(self, path: str, query: dict | None = None) -> dict:
        self.calls.append(("GET", path))
        self.requests.append(("GET", path, dict(query or {})))
        if path == "/api/ableton/osc/session":
            return {
                "status": "connected",
                "tracks": [{"index": 0, "name": "1-Audio", "devices": [{"index": 0, "name": "Glue Compressor"}]}],
            }
        if path == "/api/ableton/osc/device-parameters":
            return {
                "success": True,
                "device_name": "Glue Compressor",
                "parameters": [{"index": 0, "name": "Attack", "value": 3.0, "min": 0.0, "max": 6.0}],
            }
        return {"ok": True}

    def post(self, path: str, payload: dict) -> dict:
        self.calls.append(("POST", path))
        self.requests.append(("POST", path, dict(payload or {})))
        return {"ok": True, "status": "confirmation_required", "changed": False, "proposal": {"id": "probe"}}


def _facade(db_path: Path, client: RecordingHTTP, **kwargs) -> KennMCPFacade:
    coordinator = AssistantCoordinator(AssistantTaskStore(db_path))
    return KennMCPFacade(client, coordinator=coordinator, **kwargs)


def _observed(tmp_path: Path, name: str, args: dict[str, Any], **kwargs) -> dict[str, Any]:
    """Call one intent and describe what it did, without pinning payload values."""
    client = RecordingHTTP()
    facade = _facade(tmp_path / f"{name}.sqlite3", client, **kwargs)
    try:
        result = facade._dispatch(name, args)
    except Exception as exc:  # the router's refusals are part of the behaviour
        outcome: dict[str, Any] = {"error": f"{type(exc).__name__}: {exc}"}
    else:
        outcome = {"keys": sorted(result) if isinstance(result, dict) else sorted(vars(result))}
    return {"calls": [f"{method} {path}" for method, path in client.calls], **outcome}


def _route(tmp_path: Path, name: str, args: dict[str, Any], **kwargs) -> dict[str, Any]:
    """Like ``_observed``, but only report the endpoints and whether it refused.

    Return shapes owned by another module (the profile store, the outcome store)
    are deliberately not pinned here; routing and refusal are this file's job.
    """
    observed = _observed(tmp_path, name, args, **kwargs)
    return {"calls": observed["calls"], "refused": "error" in observed}


def _payload_of(tmp_path: Path, name: str, args: dict[str, Any]) -> dict:
    """Return the single POST body an intent sent, for payload-level routing pins."""
    client = RecordingHTTP()
    facade = _facade(tmp_path / f"{name}-payload.sqlite3", client)
    try:
        facade._dispatch(name, args)
    except Exception:
        pass
    assert len(client.requests) == 1, client.requests
    method, _path, payload = client.requests[0]
    assert method == "POST", client.requests
    return payload


# Every advertised intent called with no arguments: what it reaches, what it
# refuses, and the shape of what it returns when the empty call is legal.
OUTCOMES: dict[str, dict[str, Any]] = {
    "analyze_sample_library_entry": {"calls": [], "error": "ValueError: sample_id is required"},
    "apply_live_proposal": {"calls": [], "error": "ValueError: proposal must be a non-empty object"},
    "ask_audio_engineering_question": {"calls": [], "error": "ValueError: question is required"},
    "audiogen_artifact": {"calls": [], "error": "ValueError: job_id is required"},
    "audition_feedback": {"calls": ["GET /api/ableton/audition-feedback"], "keys": ["ok"]},
    "bind_assistant_automix_job": {
        "calls": [], "error": "ValueError: task_id, step_id, session_id, and job_id are required",
    },
    "clear_producer_profile": {
        "calls": [],
        "keys": ["advisory_only", "cleared", "live_mutation_authorized", "ok", "schema"],
    },
    "clip_warp_pitch_proposal": {"calls": [], "error": "ValueError: session_id is required"},
    "compare_audiogen_audio_candidates": {"calls": [], "error": "ValueError: source_a and source_b are required"},
    "compare_live_devices": {
        "calls": [], "error": "ValueError: left_track_index must be a non-negative integer",
    },
    "compare_realtime_mix_review": {
        "calls": [], "error": "ValueError: review_id and plugin_session_id are required",
    },
    "create_audition_revision_brief": {
        "calls": [], "error": "ValueError: session_id and feedback_id are required",
    },
    "create_clip_audition_from_receipt": {
        "calls": [], "error": "ValueError: session_id and receipt are required",
    },
    "create_clip_audition_proposal": {
        "calls": [], "error": "ValueError: session_id and track_name are required",
    },
    "create_live_proposal": {"calls": [], "error": "ValueError: command is required"},
    "create_live_recipe_proposal": {"calls": [], "error": "ValueError: session_id is required"},
    "create_midi_clip_from_artifact": {"calls": [], "error": "ValueError: job_id and session_id are required"},
    "create_midi_clip_proposal": {"calls": [], "error": "ValueError: session_id is required"},
    "create_mix_review_recipe_proposal": {
        "calls": [], "error": "ValueError: review_id and session_id are required",
    },
    "duplicate_clip_proposal": {"calls": [], "error": "ValueError: session_id is required"},
    "duplicate_loop_proposal": {"calls": [], "error": "ValueError: session_id is required"},
    "find_similar_samples": {"calls": [], "error": "ValueError: sample_id is required"},
    "forget_producer_preference": {
        "calls": [],
        "keys": ["advisory_only", "live_mutation_authorized", "ok", "schema"],
    },
    "generate_audiogen_audio_candidate": {"calls": [], "error": "ValueError: prompt is required"},
    "generate_audiogen_midi_proposal": {
        "calls": [], "error": "ValueError: session_id and track_name are required",
    },
    "generate_audiogen_midi_revision_proposal": {
        "calls": [], "error": "ValueError: session_id and feedback_id are required",
    },
    "import_sample_to_live": {
        "calls": [], "error": "ValueError: sample_id, session_id, and track_name are required",
    },
    "kenn_capabilities": {"calls": ["GET /api/ableton/capabilities"], "keys": ["ok"]},
    "kenn_context": {
        "calls": ["GET /api/ableton/osc/session", "GET /api/ableton/device-matrix", "GET /api/audiogen/status"],
        "keys": [
            "audio_classifications", "audition_feedback", "available_actions", "device_capability_matrix",
            "devices", "episodic_outcomes", "generated_jobs", "limitations", "locators", "master_track",
            "measurements", "observation_capabilities", "observed_at", "offline_jobs", "producer_preferences",
            "return_tracks", "scenes", "schema", "service_capabilities", "session_id", "snapshot_fingerprint",
            "sources", "tracks", "transport", "versions",
        ],
    },
    "kenn_context_delta": {"calls": [], "error": "ValueError: session_id is required"},
    "kenn_generate_midi_pattern": {
        "calls": [], "keys": ["note_count", "notes", "ok", "pattern_type"],
    },
    "kenn_search_knowledge": {"calls": [], "keys": ["ok", "query", "results"]},
    "kenn_session_doctor": {
        "calls": ["GET /api/ableton/osc/session"],
        "keys": [
            "issues", "issues_found", "ok", "remediation_batch", "remediation_execution", "summary", "track_count",
        ],
    },
    "kenn_session_intelligence": {
        "calls": ["GET /api/ableton/osc/session", "GET /api/ableton/device-matrix", "GET /api/audiogen/status"],
        "keys": [
            "arrangement", "audio_classifications", "audio_evidence", "capability_state", "expires_at",
            "explanation_sections", "freshness", "limitations", "mixdown_coach", "mutation_authorized",
            "observed_at", "project_intent", "project_memory", "realtime_mix_comparison", "retrieval",
            "schema", "session_observations", "snapshot", "status", "track_roles",
        ],
    },
    "launch_clip_proposal": {"calls": [], "error": "ValueError: session_id is required"},
    "launch_scene_proposal": {"calls": [], "error": "ValueError: session_id is required"},
    "live_arrangement_analysis": {"calls": [], "error": "ValueError: session_id is required"},
    "live_clip_slot": {"calls": [], "error": "ValueError: track_index must be a non-negative integer"},
    "live_device_matrix": {"calls": ["GET /api/ableton/device-matrix"], "keys": ["ok"]},
    "live_devices": {"calls": [], "error": "ValueError: track_index must be a non-negative integer"},
    "live_midi_clip": {"calls": [], "error": "ValueError: track_index must be a non-negative integer"},
    "live_parameter_display": {"calls": [], "error": "ValueError: track_index must be a non-negative integer"},
    "live_parameter_profile": {"calls": [], "error": "ValueError: track_index must be a non-negative integer"},
    "live_parameters": {"calls": [], "error": "ValueError: track_index must be a non-negative integer"},
    "live_plugin_review": {"calls": [], "error": "ValueError: session_id is required"},
    "live_receipts": {"calls": ["GET /api/ableton/receipts"], "keys": ["ok"]},
    "live_snapshot": {"calls": ["GET /api/ableton/osc/session"], "keys": ["status", "tracks"]},
    "mix_review_recommendations": {"calls": [], "error": "ValueError: review_id is required"},
    "plan_assistant_goal": {"calls": [], "error": "ValueError: goal and session_id are required"},
    "plan_assistant_task": {"calls": [], "error": "ValueError: goal and session_id are required"},
    "producer_profile": {
        "calls": [],
        "keys": ["advisory_only", "live_mutation_authorized", "memory", "ok", "schema", "scope", "session_id"],
    },
    "queue_assistant_audiogen_job": {
        "calls": [], "error": "ValueError: task_id, step_id, and session_id are required",
    },
    "realtime_mix_recommendations": {"calls": [], "error": "ValueError: session_id is required"},
    "realtime_session_review": {"calls": ["GET /api/realtime-session-review"], "keys": ["ok"]},
    "record_assistant_live_receipt": {
        "calls": [], "error": "ValueError: task_id, step_id, session_id, and receipt_id are required",
    },
    "record_assistant_observation": {
        "calls": [], "error": "ValueError: task_id, step_id, and session_id are required",
    },
    "record_assistant_user_response": {
        "calls": [], "error": "ValueError: task_id, step_id, session_id, and response are required",
    },
    "record_audition_feedback": {
        "calls": [], "error": "ValueError: session_id, receipt, and verdict are required",
    },
    "record_diagnostic_test_result": {"calls": [], "error": "ValueError: result must be an object"},
    "record_producer_preference": {"calls": [], "keys": ["errors", "ok"]},
    "record_supervised_session_outcome": {
        "calls": [], "error": "ValueError: outcome must be a privacy-safe session outcome object",
    },
    "refresh_assistant_audiogen_job": {
        "calls": [], "error": "ValueError: task_id, step_id, session_id, and job_id are required",
    },
    "refresh_assistant_automix_job": {
        "calls": [], "error": "ValueError: task_id, step_id, session_id, and job_id are required",
    },
    "rename_clip_proposal": {"calls": [], "error": "ValueError: session_id is required"},
    "replan_assistant_task": {"calls": [], "error": "ValueError: task_id and session_id are required"},
    "resume_assistant_task": {"calls": [], "error": "ValueError: task_id and session_id are required"},
    "search_sample_library": {"calls": [], "error": "ValueError: query is required"},
    "start_assistant_task": {"calls": [], "error": "ValueError: plan and session_id are required"},
    "start_production_diagnosis": {"calls": [], "error": "ValueError: goal and session_id are required"},
    "supervised_session_outcome_summary": {
        "calls": [],
        "keys": [
            "advisory_only", "counts", "invalid_sample_count", "limitations", "live_mutation_authorized",
            "mean_latency_ms", "privacy", "reviewable_miss_count", "root_cause_label_rate",
            "root_cause_labeled_miss_count", "sample_count", "schema", "valid_sample_count",
        ],
    },
    "undo_live_receipt": {"calls": [], "error": "ValueError: receipt must be a non-empty object"},
    "update_midi_clip_proposal": {"calls": [], "error": "ValueError: session_id is required"},
}


SUPERVISED_OUTCOME = {
    "schema": "kenn.session_outcome.v1",
    "session_bucket": "sha256:" + f"{1:064x}",
    "project_bucket": "sha256:" + f"{2:064x}",
    "tester_bucket": "sha256:" + f"{3:064x}",
    "intent_class": "analysis",
    "context_freshness": "fresh",
    "evidence_classes": ["live_snapshot"],
    "lifecycle_outcome": "completed",
    "user_verdict": "keep",
    "reason_codes": [],
    "root_cause": None,
    "latency_ms": {"retrieval": 1, "generation": 1, "validation": 1, "execution": 1, "readback": 1},
    "contains_raw_prompt": False,
    "contains_audio": False,
}

APPLIED_RECEIPT = {
    "schema": "kenn.ableton_midi_clip_receipt.v1",
    "status": "applied",
    "verified": True,
    "receipt_id": "receipt-1",
    "target": {"track_index": 0, "track_name": "1-Audio", "clip_slot_index": 0},
}

TASK = {"task_id": "task-1", "step_id": "step-1", "session_id": "route"}

# The same 72 intents as OUTCOMES, called with arguments good enough to clear the
# guards.  This is the half that proves routing: which endpoints each intent
# reaches, and whether it refused at all.  ``refused: False`` matters as much as
# the endpoint list -- it proves the arguments reached the handler body.
#
# Intents with no KENN endpoint of their own (local search, the pattern
# generator, the stores) still carry a ``calls`` list, usually empty, and
# ``refused: False`` is the load-bearing part for them.
ROUTES: list[tuple[str, str, dict[str, Any], dict[str, Any]]] = [
    # Session, plug-in, and Mix Review reads.
    ("live_snapshot", "detail", {"detail": "understanding"},
     {"calls": ["GET /api/ableton/osc/session"], "refused": False}),
    ("live_plugin_review", "session", {"session_id": "route"},
     {"calls": ["GET /api/plugin-live-review"], "refused": False}),
    ("realtime_session_review", "focus", {"plugin_session_id": "p-1", "focus": "kick"},
     {"calls": ["GET /api/realtime-session-review"], "refused": False}),
    ("live_arrangement_analysis", "session", {"session_id": "route"},
     {"calls": [
         "GET /api/ableton/osc/session", "GET /api/audiogen/status", "GET /api/ableton/audition-feedback",
     ], "refused": False}),
    ("realtime_mix_recommendations", "session", {"session_id": "route"},
     {"calls": ["GET /api/plugin-live-review"], "refused": False}),
    ("compare_realtime_mix_review", "both ids", {"review_id": "r-1", "plugin_session_id": "p-1"},
     {"calls": ["GET /api/mix-review-status", "GET /api/plugin-live-review"], "refused": False}),
    ("mix_review_recommendations", "review", {"review_id": "r-1"},
     {"calls": ["GET /api/mix-review-status"], "refused": False}),

    # Exact read-only Live reads.
    ("live_midi_clip", "indices", {"track_index": 0, "clip_slot_index": 0},
     {"calls": ["GET /api/ableton/osc/midi-clip"], "refused": False}),
    ("live_clip_slot", "indices", {"track_index": 0, "clip_slot_index": 0},
     {"calls": ["GET /api/ableton/osc/clip-slot"], "refused": False}),
    ("live_devices", "track", {"track_index": 0},
     {"calls": ["GET /api/ableton/osc/session"], "refused": False}),
    ("live_parameters", "device", {"track_index": 0, "device_index": 0},
     {"calls": ["GET /api/ableton/osc/device-parameters"], "refused": False}),
    ("live_parameter_display", "parameter", {"track_index": 0, "device_index": 0, "parameter_index": 0},
     {"calls": ["GET /api/ableton/osc/device-parameter-value-string"], "refused": False}),
    ("live_parameter_profile", "parameter", {"track_index": 0, "device_index": 0, "parameter_index": 0},
     {"calls": [
         "GET /api/ableton/osc/device-parameters", "GET /api/ableton/osc/device-parameter-value-string",
     ], "refused": False}),
    ("compare_live_devices", "both sides", {
        "left_track_index": 0, "left_device_index": 0, "right_track_index": 0, "right_device_index": 0,
    }, {"calls": [
        "GET /api/ableton/osc/session",
        "GET /api/ableton/osc/device-parameters",
        "GET /api/ableton/osc/device-parameters",
    ], "refused": False}),
    ("kenn_capabilities", "no args", {},
     {"calls": ["GET /api/ableton/capabilities"], "refused": False}),
    ("live_device_matrix", "matrix off", {"include_parameters": False},
     {"calls": ["GET /api/ableton/device-matrix"], "refused": False}),

    # Proposal-only calls.  The eight that share POST /api/ableton/command are
    # pinned at the payload level further down.
    ("duplicate_clip_proposal", "session", {"session_id": "route"},
     {"calls": ["POST /api/ableton/clip-duplication/proposal"], "refused": False}),
    ("rename_clip_proposal", "session", {"session_id": "route"},
     {"calls": ["POST /api/ableton/clip-rename/proposal"], "refused": False}),
    ("create_live_proposal", "command", {"command": "set the fader", "session_id": "route"},
     {"calls": ["POST /api/ableton/command"], "refused": False}),
    ("create_live_recipe_proposal", "one step", {"session_id": "route", "steps": [{"kind": "inspect"}]},
     {"calls": ["POST /api/ableton/command"], "refused": False}),
    ("create_mix_review_recipe_proposal", "review and step", {
        "review_id": "r-1", "session_id": "route", "steps": [{"kind": "inspect"}],
    }, {"calls": ["POST /api/ableton/command"], "refused": False}),
    ("launch_clip_proposal", "session", {"session_id": "route"},
     {"calls": ["POST /api/ableton/command"], "refused": False}),
    ("launch_scene_proposal", "scene", {"session_id": "route", "scene_name": "Intro"},
     {"calls": ["POST /api/ableton/command"], "refused": False}),
    ("clip_warp_pitch_proposal", "session", {"session_id": "route"},
     {"calls": ["POST /api/ableton/command"], "refused": False}),
    ("duplicate_loop_proposal", "session", {"session_id": "route"},
     {"calls": ["POST /api/ableton/command"], "refused": False}),
    ("create_midi_clip_proposal", "session", {"session_id": "route"},
     {"calls": ["POST /api/ableton/midi-clip/proposal"], "refused": False}),
    ("update_midi_clip_proposal", "session", {"session_id": "route"},
     {"calls": ["POST /api/ableton/midi-clip/update-proposal"], "refused": False}),

    # The identity-bound write path and the journal it undoes against.
    ("apply_live_proposal", "full confirmation", {
        "proposal": {"id": "p-1"}, "confirm_token": "t-1", "session_id": "route", "idempotency_key": "k-1",
    }, {"calls": ["POST /api/ableton/command"], "refused": False}),
    ("undo_live_receipt", "receipt", {"receipt": {"receipt_id": "receipt-1"}, "session_id": "route"},
     {"calls": ["POST /api/ableton/osc/undo"], "refused": False}),
    ("live_receipts", "bounded", {"session_id": "route", "limit": 5},
     {"calls": ["GET /api/ableton/receipts"], "refused": False}),

    # Audition loop.
    ("create_clip_audition_proposal", "track", {"session_id": "route", "track_name": "1-Audio"},
     {"calls": ["POST /api/ableton/clip-audition/proposal"], "refused": False}),
    ("create_clip_audition_from_receipt", "applied receipt", {"session_id": "route", "receipt": APPLIED_RECEIPT},
     {"calls": ["POST /api/ableton/clip-audition/proposal"], "refused": False}),
    ("record_audition_feedback", "verdict", {
        "session_id": "route", "receipt": {"receipt_id": "receipt-1"}, "verdict": "keep",
    }, {"calls": ["POST /api/ableton/audition-feedback"], "refused": False}),
    ("audition_feedback", "bounded", {"session_id": "route", "limit": 5},
     {"calls": ["GET /api/ableton/audition-feedback"], "refused": False}),
    ("create_audition_revision_brief", "feedback id", {"session_id": "route", "feedback_id": "f-1"},
     {"calls": ["GET /api/ableton/audition-feedback"], "refused": True}),

    # Sample library.
    ("search_sample_library", "query", {"query": "kick"},
     {"calls": [], "refused": False}),
    ("analyze_sample_library_entry", "sample", {"sample_id": "s-1"},
     {"calls": [], "refused": False}),
    ("find_similar_samples", "sample and candidates", {"sample_id": "s-1", "candidate_query": "snare"},
     {"calls": [], "refused": False}),
    ("import_sample_to_live", "full target", {
        "sample_id": "s-1", "session_id": "route", "track_name": "1-Audio",
    }, {"calls": ["POST /api/ableton/sample-import/proposal"], "refused": False}),

    # Offline AudioGen and AutoMix.
    ("audiogen_artifact", "job", {"job_id": "j-1"},
     {"calls": ["GET /api/audiogen/job"], "refused": False}),
    ("queue_assistant_audiogen_job", "task", {**TASK},
     {"calls": ["POST /api/audiogen/render-song"], "refused": False}),
    ("refresh_assistant_audiogen_job", "task and job", {**TASK, "job_id": "j-1"},
     {"calls": ["GET /api/audiogen/job"], "refused": False}),
    ("bind_assistant_automix_job", "task and job", {**TASK, "job_id": "j-1"},
     {"calls": ["GET /api/automix-status"], "refused": False}),
    ("refresh_assistant_automix_job", "task and job", {**TASK, "job_id": "j-1"},
     {"calls": ["GET /api/automix-status"], "refused": False}),
    ("generate_audiogen_audio_candidate", "prompt", {"prompt": "a warm pad"},
     {"calls": ["POST /api/audiogen/generate"], "refused": False}),
    ("compare_audiogen_audio_candidates", "two sources", {"source_a": "a.wav", "source_b": "b.wav"},
     {"calls": ["POST /api/audiogen/audio-compare"], "refused": False}),
    ("create_midi_clip_from_artifact", "job and session", {"job_id": "j-1", "session_id": "route"},
     {"calls": ["GET /api/audiogen/job"], "refused": False}),
    ("generate_audiogen_midi_revision_proposal", "feedback and seed", {
        "session_id": "route", "feedback_id": "f-1", "seed": 7,
    }, {"calls": ["GET /api/ableton/audition-feedback"], "refused": True}),
    ("generate_audiogen_midi_proposal", "track", {"session_id": "route", "track_name": "1-Audio"},
     {"calls": ["POST /api/audiogen/midi-proposal"], "refused": False}),

    # Grounded retrieval and the local pattern generator.
    ("ask_audio_engineering_question", "question", {"question": "how should I compress a bass?"},
     {"calls": ["POST /api/knowledge/ask"], "refused": False}),
    ("kenn_search_knowledge", "query", {"query": "compressor", "limit": 1},
     {"calls": [], "refused": False}),
    ("kenn_generate_midi_pattern", "drums", {"pattern_type": "drums", "bars": 1, "genre": "trap"},
     {"calls": [], "refused": False}),

    # Canonical context and the briefings derived from it.
    ("kenn_context", "session", {"session_id": "route"},
     {"calls": CONTEXT_READ, "refused": False}),
    ("kenn_context_delta", "session", {"session_id": "route"},
     {"calls": CONTEXT_READ, "refused": False}),
    ("kenn_session_intelligence", "session", {"session_id": "route"},
     {"calls": CONTEXT_READ, "refused": False}),
    ("kenn_session_doctor", "session", {"session_id": "route"},
     {"calls": ["GET /api/ableton/osc/session"], "refused": False}),

    # Producer preferences and session outcomes.
    ("producer_profile", "session", {"session_id": "route"},
     {"calls": [], "refused": False}),
    ("record_producer_preference", "preference", {
        "session_id": "route", "key": "creative_direction", "value": "minimal",
    }, {"calls": [], "refused": False}),
    ("forget_producer_preference", "preference", {"session_id": "route", "key": "creative_direction"},
     {"calls": [], "refused": False}),
    ("clear_producer_profile", "session", {"session_id": "route"},
     {"calls": [], "refused": False}),
    ("record_supervised_session_outcome", "outcome", {"outcome": SUPERVISED_OUTCOME},
     {"calls": [], "refused": False}),
    ("supervised_session_outcome_summary", "bounded", {"limit": 5},
     {"calls": [], "refused": False}),

    # Diagnosis loop.  record_diagnostic_test_result needs a loop that already
    # exists, so it gets its own two-step test below.
    ("start_production_diagnosis", "goal", {
        "goal": "Help the kick and bass coexist without losing their weight.", "session_id": "route",
    }, {"calls": CONTEXT_READ, "refused": False}),

    # Assistant planning and the task ledger.
    ("plan_assistant_goal", "diagnostic goal", {
        "goal": "Help the kick and bass coexist without losing their weight.", "session_id": "route",
    }, {"calls": CONTEXT_READ, "refused": False}),
    ("plan_assistant_task", "goal", {"goal": "Summarise the session", "session_id": "route"},
     {"calls": CONTEXT_READ, "refused": False}),
    ("start_assistant_task", "plan", {"plan": {"goal": "g", "steps": []}, "session_id": "route"},
     {"calls": CONTEXT_READ, "refused": False}),
    ("resume_assistant_task", "task", {"task_id": "task-1", "session_id": "route"},
     {"calls": CONTEXT_READ, "refused": False}),
    ("replan_assistant_task", "missing task", {"task_id": "task-1", "session_id": "route"},
     {"calls": [], "refused": False}),
    ("record_assistant_observation", "task", TASK,
     {"calls": CONTEXT_READ, "refused": False}),
    ("record_assistant_user_response", "task and response", {**TASK, "response": "keep it"},
     {"calls": CONTEXT_READ, "refused": False}),
    ("record_assistant_live_receipt", "task and receipt", {**TASK, "receipt_id": "receipt-1"},
     {"calls": ["GET /api/ableton/receipts"], "refused": False}),
]

# Eight intents POST to the same command gateway.  Their payloads are the only
# thing telling them apart, so a crossed route shows up here and nowhere else.
COMMAND_GATEWAY_PAYLOADS: list[tuple[str, str, dict[str, Any], dict[str, Any]]] = [
    ("create_live_proposal", {"command": "set the fader", "session_id": "route"}, {
        "command": "set the fader", "session_id": "route",
    }),
    ("create_live_recipe_proposal", {"session_id": "route", "steps": [{"kind": "inspect"}]}, {
        "command": "MCP supervised Live recipe", "recipe_steps": [{"kind": "inspect"}],
    }),
    ("create_mix_review_recipe_proposal", {
        "review_id": "r-1", "session_id": "route", "steps": [{"kind": "inspect"}],
    }, {
        "command": "Mix Review evidence-bound Live recipe", "mix_review_id": "r-1",
        "recipe_steps": [{"kind": "inspect"}],
    }),
    ("launch_clip_proposal", {"session_id": "route", "track_index": 0, "clip_slot_index": 0}, {
        "command": "propose clip launch track 0 slot 0", "proposal_action": "launch_clip",
    }),
    ("launch_scene_proposal", {"session_id": "route", "scene_name": "Intro"}, {
        "command": "propose create scene Intro", "proposal_action": "create_scene",
    }),
    ("clip_warp_pitch_proposal", {"session_id": "route"}, {
        "command": "propose clip warp pitch track None slot None", "proposal_action": "set_clip_warp_pitch",
    }),
    ("duplicate_loop_proposal", {"session_id": "route"}, {
        "command": "propose duplicate loop track None slot None", "proposal_action": "duplicate_loop",
    }),
    ("apply_live_proposal", {
        "proposal": {"id": "p-1"}, "confirm_token": "t-1", "session_id": "route", "idempotency_key": "k-1",
    }, {"command": "apply confirmed KENN Live proposal", "confirm_token": "t-1", "idempotency_key": "k-1"}),
]


def test_the_outcome_table_covers_every_advertised_intent_exactly_once() -> None:
    assert sorted(OUTCOMES) == sorted(ADVERTISED)
    assert len(ADVERTISED) == len(set(ADVERTISED))


def test_every_advertised_intent_has_a_handler_and_no_handler_is_orphaned() -> None:
    # An intent added to TOOLS without a handler would reach the facade as an
    # "Unknown KENN MCP tool" refusal at runtime; a handler left behind after an
    # intent is renamed would be unreachable dead code.
    assert set(HANDLERS) == set(ADVERTISED)


def test_every_intent_reaches_the_same_endpoints_and_refusals_as_before(tmp_path) -> None:
    drifted: dict[str, Any] = {}
    for name, expected in OUTCOMES.items():
        observed = _observed(tmp_path, name, {})
        if observed != expected:
            drifted[name] = {"expected": expected, "observed": observed}
    assert drifted == {}


def test_the_route_table_covers_every_advertised_intent_but_the_one_that_needs_a_stored_loop() -> None:
    # record_diagnostic_test_result is the single intent that cannot be routed
    # from a table row: it needs a loop already in the ledger.
    covered = {intent for intent, _label, _args, _expected in ROUTES}
    assert set(ADVERTISED) - covered == {"record_diagnostic_test_result"}
    assert not covered - set(ADVERTISED)


def test_valid_arguments_reach_the_endpoints_each_intent_owns(tmp_path) -> None:
    """The routing half of the characterisation.

    A handler swapped for another that also refuses would survive ``OUTCOMES``;
    it cannot survive this, because each intent's argument set only reaches its
    own endpoints.
    """
    drifted: dict[str, Any] = {}
    for intent, label, args, expected in ROUTES:
        observed = _route(tmp_path / intent, intent, args)
        if observed != expected:
            drifted[f"{intent} ({label})"] = {"expected": expected, "observed": observed}
    assert drifted == {}


def test_the_command_gateway_intents_keep_their_own_payloads(tmp_path) -> None:
    # create_live_proposal, the two recipe proposals, the three ``propose ...``
    # verbs, and apply_live_proposal all POST to /api/ableton/command.  Nothing
    # about the route distinguishes them, so the command string and the
    # proposal_action tag are what a crossed route would break.
    for intent, args, expected in COMMAND_GATEWAY_PAYLOADS:
        payload = _payload_of(tmp_path, intent, args)
        for key, value in expected.items():
            assert payload.get(key) == value, f"{intent} sent {key}={payload.get(key)!r}, expected {value!r}"


def test_record_diagnostic_test_result_reads_the_stored_loop_before_the_context(tmp_path) -> None:
    # The only intent that cannot be routed from a table row: it needs a loop that
    # start_production_diagnosis put in the ledger, so it gets its own two-step
    # test.  Reaching CONTEXT_READ is the routing claim -- the handler reloads the
    # loop, re-reads the session, and only then advances the hypothesis.
    client = RecordingHTTP()
    facade = _facade(tmp_path / "diagnostic-loop.sqlite3", client)
    started = facade._dispatch("start_production_diagnosis", {
        "goal": "Help the kick and bass coexist without losing their weight.",
        "session_id": "route",
    })

    client.calls.clear()
    recorded = facade._dispatch("record_diagnostic_test_result", {
        "loop_id": started["loop"]["loop_id"],
        "result": {
            "schema": "kenn.diagnostic_test_result.v1",
            "hypothesis_id": started["loop"]["active_hypothesis_id"],
            "verdict": "contradicts",
            "source": "user_observation",
            "observation": "Muting each sustained part did not clear the low mids.",
            "source_turn_id": "turn-1",
        },
    })

    assert [f"{method} {path}" for method, path in client.calls] == CONTEXT_READ
    assert recorded["schema"] == "kenn.production_diagnosis.v1"
    assert recorded["continuation_ready"] is True
    assert recorded["execution_authorized"] is False


def test_kenn_generate_midi_pattern_refuses_an_unknown_pattern_type(tmp_path) -> None:
    # The generator picks between three branches inside one handler; an unknown
    # type must still be named back rather than silently defaulted.
    facade = _facade(tmp_path / "pattern.sqlite3", RecordingHTTP())

    with pytest.raises(ValueError, match=r"^Unknown pattern_type: sitar$"):
        facade._dispatch("kenn_generate_midi_pattern", {"pattern_type": "sitar"})


def test_unknown_intent_is_refused_and_named(tmp_path) -> None:
    facade = _facade(tmp_path / "unknown.sqlite3", RecordingHTTP())

    with pytest.raises(ValueError, match=r"^Unknown KENN MCP tool: not_a_kenn_tool$"):
        facade._dispatch("not_a_kenn_tool", {})


def test_intent_lookup_is_exact_so_near_miss_names_are_never_dispatched(tmp_path) -> None:
    # A prefix, a case change, or a stray space must not reach a real handler.
    facade = _facade(tmp_path / "near-miss.sqlite3", RecordingHTTP())
    for name in ("kenn_context ", "Kenn_Context", "kenn", "", "live_snapshot_v2"):
        with pytest.raises(ValueError, match="Unknown KENN MCP tool"):
            facade._dispatch(name, {})


def test_kenn_context_delta_does_not_shadow_kenn_context(tmp_path) -> None:
    # The two intents share a prefix; each must keep its own schema rather than
    # whichever check the router happens to reach first.
    delta = _observed(tmp_path, "kenn_context_delta", {"session_id": "precedence"})
    context = _observed(tmp_path, "kenn_context", {"session_id": "precedence"})

    # A session-scoped context read also pulls that session's audition feedback.
    assert delta["calls"] == [
        "GET /api/ableton/osc/session",
        "GET /api/ableton/device-matrix",
        "GET /api/audiogen/status",
        "GET /api/ableton/audition-feedback",
    ]
    assert delta["keys"] == [
        "advisory_only", "delta", "live_mutation_authorized", "read_only", "schema", "session_id",
        "snapshot_fingerprint",
    ]
    assert context["keys"] != delta["keys"]


def test_bind_and_refresh_automix_job_share_one_handler(tmp_path) -> None:
    # One dispatch block covers both names, so the two must not drift apart.
    args = {"task_id": "t-1", "step_id": "s-1", "session_id": "precedence", "job_id": "j-1"}
    assert _observed(tmp_path, "bind_assistant_automix_job", args) == _observed(
        tmp_path, "refresh_assistant_automix_job", args,
    )


def test_plan_assistant_goal_tries_the_diagnostic_workflow_before_the_model(tmp_path) -> None:
    # Both branches answer the same intent, so the order is the behaviour: a
    # causal-diagnosis goal must be handled locally and never reach the planner.
    planner_calls: list[str] = []
    diagnostic = _observed(
        tmp_path,
        "plan_assistant_goal",
        {"goal": "Help the kick and bass coexist without losing their weight.", "session_id": "precedence"},
        planner=lambda prompt: planner_calls.append(prompt) or "must not run",
    )

    assert diagnostic["calls"] == [
        "GET /api/ableton/osc/session",
        "GET /api/ableton/device-matrix",
        "GET /api/audiogen/status",
        "GET /api/ableton/audition-feedback",
    ]
    assert diagnostic["keys"] == ["execution_authorized", "loop", "next_plan", "ok", "schema", "workflow"]
    assert planner_calls == []


def test_live_arrangement_analysis_reuses_the_context_read_instead_of_a_second_snapshot(tmp_path) -> None:
    # live_arrangement_analysis and live_snapshot both read the session. The
    # analysis must keep routing through kenn_context with the device matrix
    # turned off, rather than picking up the topology-only snapshot read or
    # walking the device inventory itself.
    observed = _observed(tmp_path, "live_arrangement_analysis", {"session_id": "precedence"})

    assert observed["calls"] == [
        "GET /api/ableton/osc/session",
        "GET /api/audiogen/status",
        "GET /api/ableton/audition-feedback",
    ]
    assert observed["keys"] == [
        "advisory_only", "limitations", "locators", "mutation_authorized", "repetition_candidates", "schema",
        "sections", "source_fingerprint", "status", "suggestions", "timeline_sections", "timeline_transitions",
        "transitions",
    ]


def test_transport_failures_stay_retryable_except_for_the_two_mutation_intents(tmp_path) -> None:
    class Broken(RecordingHTTP):
        def get(self, path: str, query: dict | None = None) -> dict:
            raise KennTransportError("connection refused")

        def post(self, path: str, payload: dict) -> dict:
            raise KennTransportError("connection refused")

    # Arguments have to be valid enough to reach KENN: a refusal raised before
    # the request would be an ordinary ValueError, not a transport failure.
    cases = (
        ("live_snapshot", {}, True),
        ("apply_live_proposal", {
            "proposal": {"id": "p-1"}, "confirm_token": "token", "session_id": "s", "idempotency_key": "k",
        }, False),
        ("undo_live_receipt", {"receipt": {"receipt_id": "r-1"}, "session_id": "s"}, False),
    )
    facade = _facade(tmp_path / "broken.sqlite3", Broken())
    for name, arguments, retry_allowed in cases:
        response = facade._tool_call(7, name, arguments)
        payload = json.loads(response["result"]["content"][0]["text"])
        assert response["result"]["isError"] is True
        assert payload["error_kind"] == "transport_uncertain"
        assert payload["retry_allowed"] is retry_allowed
        assert payload["recovery_tools"] == ["live_receipts", "live_snapshot"]