"""Dependency-free MCP facade for KENN's Ableton companion.

The facade intentionally talks to KENN over localhost HTTP instead of opening
its own AbletonOSC socket. This keeps the companion as the single owner of the
fixed AbletonOSC reply port and makes the existing proposal/readback boundary
the only path toward Live.

This module implements the small MCP JSON-RPC surface needed by stdio clients:
``initialize``, ``ping``, ``tools/list``, and ``tools/call``. Reads and
proposal creation are available to every client. Mutations are available only
through KENN's existing exact-proposal confirmation boundary; the facade never
opens an AbletonOSC socket or accepts a raw Live command.
"""

from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

from kenn.core.assistant_coordinator import AssistantCoordinator
from kenn.core.assistant_profile_memory import AssistantProfileStore, PREFERENCE_KEYS
from kenn.core.assistant_task_memory import AssistantTaskStore
from kenn.core.audiogen_artifacts import midi_import_payload
from kenn.core.audition_revision import build_audition_revision_brief
from kenn.core.diagnostic_loop import next_diagnostic_plan, record_diagnostic_result, start_diagnostic_loop
from kenn.core.diagnostic_loop_store import DiagnosticLoopStore
from kenn.core.diagnostic_framework import plan_for as diagnostic_plan_for
from kenn.core.deliberative_planner import deliberative_preflight_plan, run_shadow_sketch
from kenn.core.evidence import MAX_PLUGIN_CONTEXT_AGE_SECONDS
from kenn.core.realtime_mix_comparison import build_realtime_mix_comparison
from kenn.core.arrangement_analysis import analyze_arrangement_context
from kenn.core.session_context import build_session_context, refresh_session_context_fingerprint, safe_audio_job
from kenn.core.session_intelligence import build_session_intelligence, explanation_sections, retrieval_sources_from_cache
from kenn.core.session_outcome_contract import SCHEMA as SESSION_OUTCOME_SCHEMA
from kenn.core.session_outcome_store import SessionOutcomeStore
from kenn.core.session_world_model import SessionWorldModel


MCP_PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "kenn-live"
SERVER_VERSION = "0.1.0"


class KennTransportError(RuntimeError):
    """A companion request did not complete; a mutation may be ambiguous."""


_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


_NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirect())


def open_loopback_companion(request: urllib.request.Request, *, timeout: float):
    return _NO_REDIRECT_OPENER.open(request, timeout=timeout)


def validate_companion_base_url(value: str) -> str:
    """Accept only an uncredentialed loopback HTTP origin."""
    candidate = str(value or "").strip().rstrip("/")
    parsed = urllib.parse.urlsplit(candidate)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in _LOOPBACK_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("KENN companion URL must be an uncredentialed loopback HTTP origin.")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("KENN companion URL has an invalid port.") from exc
    return candidate


TOOLS: list[dict[str, Any]] = [
    {
        "name": "live_snapshot",
        "description": "Read the current KENN/Ableton Live session snapshot. 'understanding' adds read-only routing, sends, clip inventory, return tracks, and selection evidence. This tool never writes.",
        "inputSchema": {
            "type": "object",
            "properties": {"detail": {"type": "string", "enum": ["topology", "full", "understanding"], "default": "topology"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "live_plugin_review",
        "description": "Read the latest validated KENN Mix Assistant plug-in bus review for one session, including bounded realtime trend and freshness evidence. This tool never requests a capture, writes to Live, or attributes a bus finding to a track/device.",
        "inputSchema": {
            "type": "object",
            "properties": {"session_id": {"type": "string", "minLength": 1, "maxLength": 128}},
            "required": ["session_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "realtime_session_review",
        "description": "Read one coherent, scope-labelled review of the cached Ableton session, Mixing Doctor advisories, project-health findings, and optional validated plug-in bus evidence. This tool never polls or writes to Live, requests capture, or attributes bus findings to a track/device.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "plugin_session_id": {"type": "string", "maxLength": 128, "description": "Optional explicit KENN Mix Assistant plug-in session id. No capture is requested."},
                "focus": {"type": "string", "maxLength": 512, "description": "Optional advice focus used to retrieve relevant manual/transcript guidance. No Live mutation or capture is requested."},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "live_arrangement_analysis",
        "description": "Build a bounded, read-only arrangement briefing from the current Live session, including observed locators, timeline clip density, and cautious structural suggestions. It never measures audio quality or writes to Live.",
        "inputSchema": {
            "type": "object",
            "properties": {"session_id": {"type": "string", "minLength": 1, "maxLength": 128}},
            "required": ["session_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "realtime_mix_recommendations",
        "description": "Turn the latest validated current KENN Mix Assistant plug-in bus snapshot into read-only listening checks for peak headroom, clipping, mono compatibility, width, and spectral shape. This tool never requests a capture, writes to Live, attributes a finding to a track/device, or applies EQ.",
        "inputSchema": {
            "type": "object",
            "properties": {"session_id": {"type": "string", "minLength": 1, "maxLength": 128}},
            "required": ["session_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "compare_realtime_mix_review",
        "description": "Compare the latest validated KENN plug-in bus measurements with one uploaded/rendered Mix Review. Results are scope-labelled and advisory only; this tool never requests a capture, infers a responsible Live track/device, or applies a mix change.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "review_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "plugin_session_id": {"type": "string", "minLength": 1, "maxLength": 128},
            },
            "required": ["review_id", "plugin_session_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "live_midi_clip",
        "description": "Read one exact Ableton MIDI clip slot, including clip identity, length, and bounded notes. This tool never writes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "track_index": {"type": "integer", "minimum": 0},
                "clip_slot_index": {"type": "integer", "minimum": 0},
            },
            "required": ["track_index", "clip_slot_index"],
            "additionalProperties": False,
        },
    },
    {
        "name": "live_clip_slot",
        "description": "Read one exact Ableton Session View clip slot for either MIDI or audio, including name, type, length, and bounded MIDI notes when available. Audio bytes are not returned. This tool never writes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "track_index": {"type": "integer", "minimum": 0},
                "clip_slot_index": {"type": "integer", "minimum": 0},
            },
            "required": ["track_index", "clip_slot_index"],
            "additionalProperties": False,
        },
    },
    {
        "name": "duplicate_clip_proposal",
        "description": "Create a confirmation-only proposal to duplicate one exact existing MIDI or audio Session View clip into an explicitly empty slot. KENN verifies both track identities, reads the result back, and never replaces an existing target.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "source_track_index": {"type": "integer", "minimum": 0},
                "source_track_name": {"type": "string", "minLength": 1, "maxLength": 256},
                "source_clip_slot_index": {"type": "integer", "minimum": 0},
                "target_track_index": {"type": "integer", "minimum": 0},
                "target_track_name": {"type": "string", "minLength": 1, "maxLength": 256},
                "target_clip_slot_index": {"type": "integer", "minimum": 0},
            },
            "required": ["session_id", "source_track_index", "source_track_name", "source_clip_slot_index", "target_track_index", "target_track_name", "target_clip_slot_index"],
            "additionalProperties": False,
        },
    },
    {
        "name": "rename_clip_proposal",
        "description": "Create a confirmation-only proposal to rename one exact existing Ableton Session View clip. KENN checks the current clip identity and never writes during proposal creation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "track_index": {"type": "integer", "minimum": 0},
                "track_name": {"type": "string", "minLength": 1, "maxLength": 256},
                "clip_slot_index": {"type": "integer", "minimum": 0},
                "new_name": {"type": "string", "minLength": 1, "maxLength": 128},
            },
            "required": ["session_id", "track_index", "track_name", "clip_slot_index", "new_name"],
            "additionalProperties": False,
        },
    },
    {
        "name": "launch_clip_proposal",
        "description": "Create a confirmation-only proposal to launch or stop a Session View clip. KENN returns an exact proposal requiring user confirmation before firing.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "track_index": {"type": "integer", "minimum": 0},
                "clip_slot_index": {"type": "integer", "minimum": 0},
                "stop": {"type": "boolean", "default": False},
            },
            "required": ["session_id", "track_index", "clip_slot_index"],
            "additionalProperties": False,
        },
    },
    {
        "name": "launch_scene_proposal",
        "description": "Create a confirmation-only proposal to create and trigger a new Session View scene. KENN returns an exact proposal requiring user confirmation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "scene_name": {"type": "string", "maxLength": 128},
            },
            "required": ["session_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "clip_warp_pitch_proposal",
        "description": "Create a confirmation-only proposal to adjust audio clip warp mode or pitch transposition. Requires explicit confirmation token.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "track_index": {"type": "integer", "minimum": 0},
                "clip_slot_index": {"type": "integer", "minimum": 0},
                "warp_mode": {"type": "integer", "minimum": 0, "maximum": 6},
                "pitch_coarse": {"type": "integer", "minimum": -48, "maximum": 48},
            },
            "required": ["session_id", "track_index", "clip_slot_index"],
            "additionalProperties": False,
        },
    },
    {
        "name": "duplicate_loop_proposal",
        "description": "Create a confirmation-only proposal to duplicate loop markers and content in an arrangement or session clip.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "track_index": {"type": "integer", "minimum": 0},
                "clip_slot_index": {"type": "integer", "minimum": 0},
            },
            "required": ["session_id", "track_index", "clip_slot_index"],
            "additionalProperties": False,
        },
    },
    {
        "name": "live_devices",
        "description": "List exact device identities on one visible Live track. This tool never writes.",
        "inputSchema": {
            "type": "object",
            "properties": {"track_index": {"type": "integer", "minimum": 0}},
            "required": ["track_index"],
            "additionalProperties": False,
        },
    },
    {
        "name": "live_parameters",
        "description": "Read exact device parameter names, raw values, ranges, and quantization metadata.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "track_index": {"type": "integer", "minimum": 0},
                "device_index": {"type": "integer", "minimum": 0},
            },
            "required": ["track_index", "device_index"],
            "additionalProperties": False,
        },
    },
    {
        "name": "live_parameter_display",
        "description": "Read Ableton's displayed value string for one exact parameter.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "track_index": {"type": "integer", "minimum": 0},
                "device_index": {"type": "integer", "minimum": 0},
                "parameter_index": {"type": "integer", "minimum": 0},
            },
            "required": ["track_index", "device_index", "parameter_index"],
            "additionalProperties": False,
        },
    },
    {
        "name": "live_parameter_profile",
        "description": "Read one exact Live parameter's raw value, range, quantization, and Ableton-displayed value string. This tool never writes and is the required evidence path before interpreting a user-facing unit.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "track_index": {"type": "integer", "minimum": 0},
                "device_index": {"type": "integer", "minimum": 0},
                "parameter_index": {"type": "integer", "minimum": 0},
            },
            "required": ["track_index", "device_index", "parameter_index"],
            "additionalProperties": False,
        },
    },
    {
        "name": "compare_live_devices",
        "description": "Compare two exact current Ableton Live devices by matched parameter name and raw value. This is a read-only diagnostic comparison, not an audible quality verdict and never a mutation proposal.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "left_track_index": {"type": "integer", "minimum": 0},
                "left_device_index": {"type": "integer", "minimum": 0},
                "right_track_index": {"type": "integer", "minimum": 0},
                "right_device_index": {"type": "integer", "minimum": 0},
            },
            "required": ["left_track_index", "left_device_index", "right_track_index", "right_device_index"],
            "additionalProperties": False,
        },
    },
    {
        "name": "create_live_proposal",
        "description": "Ask KENN to create a confirmation-only Live proposal, including bounded track and return-track creation, track controls, audio/MIDI-track creation, device work, qualified Hybrid Reverb/Echo Dry/Wet setup, clip/scene actions, and evidence-backed parameter changes. It never applies the proposal.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "minLength": 1},
                "session_id": {"type": "string", "minLength": 1},
                "assistant_task_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "assistant_step_id": {"type": "string", "minLength": 1, "maxLength": 64},
            },
            "required": ["command"],
            "additionalProperties": False,
        },
    },
    {
        "name": "create_live_recipe_proposal",
        "description": "Create a confirmation-only 1–3 step typed Live recipe. Every step is resolved against the fresh session and the recipe is never applied by this tool.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "steps": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 3,
                    "items": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": ["set_volume", "set_pan", "set_mute", "set_solo", "set_arm", "rename_track", "transport_play", "transport_stop", "set_device_parameter"]},
                            "track_index": {"type": "integer", "minimum": 0},
                            "track_name": {"type": "string", "maxLength": 256},
                            "device_index": {"type": "integer", "minimum": 0},
                            "device_name": {"type": "string", "maxLength": 128},
                            "parameter_index": {"type": "integer", "minimum": 0},
                            "parameter": {"type": "string", "maxLength": 256},
                            "parameter_name": {"type": "string", "maxLength": 256},
                            "value": {},
                            "unit": {"type": "string", "maxLength": 32},
                        },
                        "required": ["action"],
                        "additionalProperties": False,
                    },
                },
                "reason": {"type": "string", "maxLength": 512},
                "session_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "assistant_task_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "assistant_step_id": {"type": "string", "minLength": 1, "maxLength": 64},
            },
            "required": ["steps", "session_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "create_mix_review_recipe_proposal",
        "description": "Create a confirmation-only typed Live recipe linked to one measured Mix Review. The review is fetched by KENN and attached as immutable evidence; this tool never infers a Live target from audio findings.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "review_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "session_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "reason": {"type": "string", "maxLength": 512},
                "steps": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 3,
                    "items": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": ["set_volume", "set_pan", "set_mute", "set_solo", "set_arm", "rename_track", "transport_play", "transport_stop", "set_device_parameter"]},
                            "track_index": {"type": "integer", "minimum": 0},
                            "track_name": {"type": "string", "maxLength": 256},
                            "device_index": {"type": "integer", "minimum": 0},
                            "device_name": {"type": "string", "maxLength": 128},
                            "parameter_index": {"type": "integer", "minimum": 0},
                            "parameter": {"type": "string", "maxLength": 256},
                            "parameter_name": {"type": "string", "maxLength": 256},
                            "value": {},
                            "unit": {"type": "string", "maxLength": 32},
                        },
                        "required": ["action"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["review_id", "session_id", "steps"],
            "additionalProperties": False,
        },
    },
    {
        "name": "apply_live_proposal",
        "description": "Apply one exact KENN Live proposal after explicit confirmation. KENN verifies identity, stale state, readback, and replay protection.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "proposal": {"type": "object"},
                "confirm_token": {"type": "string", "minLength": 1},
                "session_id": {"type": "string", "minLength": 1},
                "idempotency_key": {"type": "string", "minLength": 1},
                "assistant_task_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "assistant_step_id": {"type": "string", "minLength": 1, "maxLength": 64},
            },
            "required": ["proposal", "confirm_token", "session_id", "idempotency_key"],
            "additionalProperties": False,
        },
    },
    {
        "name": "create_clip_audition_proposal",
        "description": "Create a confirmation-only proposal to audition one exact existing MIDI clip. It never starts playback; apply_live_proposal is required, and playback is verified by Live readback.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "track_index": {"type": "integer", "minimum": 0},
                "track_name": {"type": "string", "minLength": 1, "maxLength": 256},
                "clip_slot_index": {"type": "integer", "minimum": 0},
                "source_receipt_id": {"type": "string", "maxLength": 256},
            },
            "required": ["session_id", "track_index", "track_name", "clip_slot_index"],
            "additionalProperties": False,
        },
    },
    {
        "name": "create_clip_audition_from_receipt",
        "description": "Create a confirmation-only audition proposal from a verified MIDI-clip creation receipt. KENN derives the exact track and slot from the receipt; the tool never starts playback.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "receipt": {"type": "object"},
            },
            "required": ["session_id", "receipt"],
            "additionalProperties": False,
        },
    },
    {
        "name": "record_audition_feedback",
        "description": "Record a bounded keep/revise/reject listener response against one verified applied audition receipt. This is advisory evidence only and never changes Live.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "receipt": {"type": "object"},
                "verdict": {"type": "string", "enum": ["keep", "revise", "reject"]},
                "rating": {"type": "integer", "minimum": 1, "maximum": 5},
                "comment": {"type": "string", "maxLength": 1000},
                "requested_changes": {"type": "array", "maxItems": 5, "items": {"type": "string", "maxLength": 256}},
            },
            "required": ["session_id", "receipt", "verdict"],
            "additionalProperties": False,
        },
    },
    {
        "name": "audition_feedback",
        "description": "Read bounded listener feedback for a KENN session. This tool never writes or changes Live.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "maxLength": 128},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "create_audition_revision_brief",
        "description": "Build a bounded, proposal-only revision brief from one revise verdict. It preserves the exact audition target and receipt provenance and never calls AudioGen or changes Live.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "feedback_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "comparison": {"type": "object"},
            },
            "required": ["session_id", "feedback_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "undo_live_receipt",
        "description": "Create an identity-bound inverse for a verified KENN receipt, or apply that inverse when its exact proposal and confirmation token are supplied.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "receipt": {"type": "object"},
                "proposal": {"type": "object"},
                "confirm_token": {"type": "string", "minLength": 1},
                "session_id": {"type": "string", "minLength": 1},
                "idempotency_key": {"type": "string", "minLength": 1},
            },
            "required": ["receipt", "session_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "live_receipts",
        "description": "Read KENN's bounded redacted receipt journal for recovery after an uncertain request. This tool never writes and never exposes confirmation tokens.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 20},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "kenn_capabilities",
        "description": "Read KENN's current backend and safety capabilities. This tool never writes.",
        "inputSchema": {"type": "object", "additionalProperties": False},
    },
    {
        "name": "live_device_matrix",
        "description": "Read the exact devices and, optionally, their current Live parameter profiles across the session. This is an inventory only; qualification labels never grant write permission.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "include_parameters": {"type": "boolean", "default": True},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "kenn_context",
        "description": "Build a bounded, read-only KENN planning context from the current Live snapshot, including track-role evidence, exact device identities, and the optional device capability matrix. This tool never writes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "maxLength": 128},
                "plugin_session_id": {"type": "string", "maxLength": 128, "description": "Optional explicit session id for the already-captured Mix Assistant plug-in review."},
                "mix_review_id": {"type": "string", "maxLength": 128},
                "automix_job_id": {"type": "string", "maxLength": 128},
                "audiogen_job_id": {"type": "string", "maxLength": 128},
                "include_device_matrix": {"type": "boolean", "default": True},
                "include_device_parameters": {"type": "boolean", "default": False},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "kenn_context_delta",
        "description": "Compare the current bounded Live context with the previous read for this session and return semantic changes. The first call initializes the read-only world model; this tool never writes or authorizes Live changes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "plugin_session_id": {"type": "string", "maxLength": 128, "description": "Optional explicit session id for the already-captured Mix Assistant plug-in review."},
                "mix_review_id": {"type": "string", "maxLength": 128},
                "automix_job_id": {"type": "string", "maxLength": 128},
                "audiogen_job_id": {"type": "string", "maxLength": 128},
                "include_device_matrix": {"type": "boolean", "default": True},
                "include_device_parameters": {"type": "boolean", "default": False},
            },
            "required": ["session_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "kenn_session_intelligence",
        "description": "Build KENN's compact, read-only musical briefing from a fresh Live context. It distinguishes observed session facts, audio measurements, inferred roles, declared intent, and grounded retrieval sources. It never writes or authorizes Live changes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "maxLength": 128},
                "plugin_session_id": {"type": "string", "maxLength": 128, "description": "Optional explicit session id for the already-captured Mix Assistant plug-in review."},
                "mix_review_id": {"type": "string", "maxLength": 128},
                "automix_job_id": {"type": "string", "maxLength": 128},
                "audiogen_job_id": {"type": "string", "maxLength": 128},
                "include_device_matrix": {"type": "boolean", "default": True},
                "include_device_parameters": {"type": "boolean", "default": False},
                "genre": {"type": "string", "maxLength": 96},
                "goal": {"type": "string", "maxLength": 512},
                "references": {"type": "array", "maxItems": 5, "items": {"type": "string", "maxLength": 128}},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "producer_profile",
        "description": "Read KENN's editable, session-scoped producer preferences and reviewed production outcomes. This tool never writes or changes Live.",
        "inputSchema": {
            "type": "object",
            "properties": {"session_id": {"type": "string", "minLength": 1, "maxLength": 128}},
            "required": ["session_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "record_producer_preference",
        "description": "Store one explicit, editable producer preference for this KENN session. It changes profile metadata only, never Ableton Live.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "key": {"type": "string", "enum": sorted(PREFERENCE_KEYS)},
                "value": {"type": "string", "minLength": 1, "maxLength": 256},
                "source_turn_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "user_statement": {"type": "string", "minLength": 1, "maxLength": 2048},
            },
            "required": ["session_id", "key", "value", "source_turn_id", "user_statement"],
            "additionalProperties": False,
        },
    },
    {
        "name": "forget_producer_preference",
        "description": "Forget one explicit producer preference for this KENN session. It changes profile metadata only, never Ableton Live.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "key": {"type": "string", "enum": sorted(PREFERENCE_KEYS)},
            },
            "required": ["session_id", "key"],
            "additionalProperties": False,
        },
    },
    {
        "name": "clear_producer_profile",
        "description": "Clear all editable producer preferences and reviewed outcomes for this KENN session. It never deletes Live data, receipts, audio, or project files.",
        "inputSchema": {
            "type": "object",
            "properties": {"session_id": {"type": "string", "minLength": 1, "maxLength": 128}},
            "required": ["session_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "record_supervised_session_outcome",
        "description": "Record one privacy-safe, category-only supervised-session outcome for KENN evaluation. It rejects prompts, audio, paths, names, and identities; it never changes Ableton Live.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "outcome": {
                    "type": "object",
                    "properties": {
                        "schema": {"type": "string", "const": "kenn.session_outcome.v1"},
                        "session_bucket": {"type": "string", "minLength": 71, "maxLength": 71},
                        "project_bucket": {"type": "string", "minLength": 71, "maxLength": 71},
                        "tester_bucket": {"type": "string", "minLength": 71, "maxLength": 71},
                        "intent_class": {"type": "string"},
                        "context_freshness": {"type": "string"},
                        "evidence_classes": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                        "lifecycle_outcome": {"type": "string"},
                        "user_verdict": {"type": "string"},
                        "reason_codes": {"type": "array", "items": {"type": "string", "maxLength": 80}},
                        "root_cause": {"type": ["string", "null"]},
                        "latency_ms": {"type": "object"},
                        "contains_raw_prompt": {"type": "boolean", "const": False},
                        "contains_audio": {"type": "boolean", "const": False},
                    },
                    "required": ["schema", "session_bucket", "project_bucket", "tester_bucket", "intent_class", "context_freshness", "evidence_classes", "lifecycle_outcome", "user_verdict", "reason_codes", "root_cause", "latency_ms", "contains_raw_prompt", "contains_audio"],
                    "additionalProperties": False,
                },
            },
            "required": ["outcome"],
            "additionalProperties": False,
        },
    },
    {
        "name": "supervised_session_outcome_summary",
        "description": "Return a bounded aggregate of privacy-safe supervised-session outcomes, including root-cause coverage and stage latency. It never returns individual records, prompts, audio, paths, or identities, and never changes Ableton Live.",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}},
            "additionalProperties": False,
        },
    },
    {
        "name": "start_production_diagnosis",
        "description": "Start a bounded, evidence-first diagnosis of a production or mix symptom against the fresh Ableton session. Returns one hypothesis and one read-only listening/test instruction at a time; it never changes Live.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "goal": {"type": "string", "minLength": 1, "maxLength": 1024},
                "session_id": {"type": "string", "minLength": 1, "maxLength": 128},
            },
            "required": ["goal", "session_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "record_diagnostic_test_result",
        "description": "Record one explicit producer observation for the server-persisted active diagnosis hypothesis, then return the next bounded assistant step from a fresh session read. Caller-supplied loop state, measurements, and receipts are not trusted; this tool never changes Live and rejects stale continuations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "loop": {"type": "object"},
                "loop_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "result": {
                    "type": "object",
                    "properties": {
                        "schema": {"type": "string", "const": "kenn.diagnostic_test_result.v1"},
                        "hypothesis_id": {"type": "string", "minLength": 1, "maxLength": 64},
                        "verdict": {"type": "string", "enum": ["supports", "contradicts", "inconclusive"]},
                        "source": {"type": "string", "enum": ["user_observation", "measurement", "verified_receipt"]},
                        "observation": {"type": "string", "maxLength": 1000},
                        "source_turn_id": {"type": "string", "maxLength": 128},
                        "evidence": {"type": "object"},
                    },
                    "required": ["schema", "hypothesis_id", "verdict", "source"],
                    "additionalProperties": False,
                },
            },
            "required": ["result"],
            "anyOf": [{"required": ["loop_id"]}, {"required": ["loop"]}],
            "additionalProperties": False,
        },
    },
    {
        "name": "plan_assistant_goal",
        "description": "Route a producer goal through KENN's evidence-first diagnostic workflow when a supported symptom is recognized; otherwise create a validated local-planner task. This is the preferred assistant entry point and never changes Live or authorizes execution.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "goal": {"type": "string", "minLength": 1, "maxLength": 1024},
                "session_id": {"type": "string", "minLength": 1, "maxLength": 128},
            },
            "required": ["goal", "session_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "plan_assistant_task",
        "description": "Build a fresh context-bound assistant plan with KENN's deterministic safety preflight and configured local planner, persist it, and return only the next safe step. This never changes Ableton Live or authorizes execution.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "goal": {"type": "string", "minLength": 1, "maxLength": 1024},
                "session_id": {"type": "string", "minLength": 1, "maxLength": 128},
            },
            "required": ["goal", "session_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "start_assistant_task",
        "description": "Persist one strictly validated, context-bound deliberative plan and return only its next safe step. This records assistant state but never changes Ableton Live.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "plan": {"type": "object"},
                "session_id": {"type": "string", "minLength": 1, "maxLength": 128},
            },
            "required": ["plan", "session_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "resume_assistant_task",
        "description": "Resume one persisted assistant task against a fresh Ableton session context. Changed state produces a replan directive rather than continuing stale work.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "session_id": {"type": "string", "minLength": 1, "maxLength": 128},
            },
            "required": ["task_id", "session_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "replan_assistant_task",
        "description": "Replace a stale or clarified assistant task with a fresh context-bound plan while preserving task lineage. Pending confirmations and jobs cannot be abandoned by this tool, and it never changes Live.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "session_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "follow_up": {"type": "string", "minLength": 1, "maxLength": 1000},
            },
            "required": ["task_id", "session_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "record_assistant_observation",
        "description": "Complete the current inspection step using a fresh context fetched by KENN itself, then return the next safe step. Caller-supplied observation claims are not accepted.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "step_id": {"type": "string", "minLength": 1, "maxLength": 64},
                "session_id": {"type": "string", "minLength": 1, "maxLength": 128},
            },
            "required": ["task_id", "step_id", "session_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "record_assistant_user_response",
        "description": "Record the producer's explicit response for the current clarification step and return the next safe step. This changes assistant memory only, never Live.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "step_id": {"type": "string", "minLength": 1, "maxLength": 64},
                "session_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "response": {"type": "string", "minLength": 1, "maxLength": 1000},
            },
            "required": ["task_id", "step_id", "session_id", "response"],
            "additionalProperties": False,
        },
    },
    {
        "name": "record_assistant_live_receipt",
        "description": "Resolve a Live receipt by ID from KENN's session-scoped journal and use it as task evidence. Caller-supplied receipt objects are never trusted.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "step_id": {"type": "string", "minLength": 1, "maxLength": 64},
                "session_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "receipt_id": {"type": "string", "minLength": 1, "maxLength": 128},
            },
            "required": ["task_id", "step_id", "session_id", "receipt_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "mix_review_recommendations",
        "description": "Read measured Mix Review findings and action-plan guidance for one review, ranked most severe/confident first with duplicates merged and a plain-language summary. An optional plugin_session_id adds the latest already-captured realtime plug-in bus evidence as a separate advisory. This tool never writes, requests a capture, or infers which Live track or device caused a finding.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "review_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "genre": {"type": "string", "maxLength": 64, "description": "Optional, explicitly known genre (e.g. 'hip_hop') to attach one advisory reference-target note. Never inferred from the audio; never changes a measured finding."},
                "plugin_session_id": {"type": "string", "maxLength": 128, "description": "Optional explicit session id for the latest already-captured, validated realtime Mix Assistant plug-in review. No capture is requested and no Live target is inferred."},
            },
            "required": ["review_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "search_sample_library",
        "description": "Search the user's approved local sample library by keyword/tag (e.g. 'dark 808 kick'). Filenames and folder structure only -- no audio is analyzed or hashed. This is a library reference, not a measured or generated result. This tool itself never imports anything into Live -- use import_sample_to_live for a confirmation-only import proposal.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 256},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "analyze_sample_library_entry",
        "description": "Real, on-demand BPM and key-pitch-class estimate for one sample already returned by search_sample_library (by its id). This decodes the actual audio, unlike the filename-only search -- it is measured evidence, bounded to one file, and abstains honestly (no dependency, unreadable file, too short, no stable tempo) rather than guessing. Reports a pitch class only, never a major/minor key.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sample_id": {"type": "string", "minLength": 1, "maxLength": 64},
            },
            "required": ["sample_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "find_similar_samples",
        "description": "Find samples acoustically similar to one already returned by search_sample_library (by its id), using a real 512D audio embedding (PANNs Cnn10, MIT/CC BY 4.0 licensed) -- not filename matching. Bounded: only ranks a small keyword-filtered candidate pool (never the whole library) and abstains honestly if the optional embedding dependencies are unavailable or the target can't be embedded.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sample_id": {"type": "string", "minLength": 1, "maxLength": 64},
                "candidate_query": {"type": "string", "maxLength": 256, "description": "Keyword query used to build the bounded candidate pool (e.g. the same tag as the target, like 'kick'). Required so this never scans the whole library."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": ["sample_id", "candidate_query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "import_sample_to_live",
        "description": "Create a confirmation-only proposal to import one sample (from search_sample_library, by its id) into one exact, empty Live clip slot. Never applies the change itself -- it only prepares the proposal; a separate explicit confirmation is required before anything is written to Live, and an existing clip in the target slot is never replaced.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sample_id": {"type": "string", "minLength": 1, "maxLength": 64},
                "session_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "track_index": {"type": "integer", "minimum": 0},
                "track_name": {"type": "string", "minLength": 1, "maxLength": 256},
                "clip_slot_index": {"type": "integer", "minimum": 0},
            },
            "required": ["sample_id", "session_id", "track_index", "track_name", "clip_slot_index"],
            "additionalProperties": False,
        },
    },
    {
        "name": "ask_audio_engineering_question",
        "description": "Ask a general audio-engineering/mixing/Ableton-device knowledge question. Retrieval-grounded and deterministic (no LLM, no Ableton/AudioGen mutation dispatch); abstains honestly on out-of-scope or weakly-matched questions instead of guessing. This tool itself never writes Live state; it can include an already-captured realtime plug-in bus review and an explicit stored Mix Review plus a scope-labelled comparison, with no capture or Live target inference.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "minLength": 1, "maxLength": 2000},
                "session_id": {"type": "string", "maxLength": 128, "description": "Optional. When the question names one instrument role (e.g. 'why is my vocal getting masked'), the answer cites the real matching track(s) and their current device list from a fresh, read-only Live snapshot. Omit for a purely general-knowledge answer."},
                "plugin_session_id": {"type": "string", "maxLength": 128, "description": "Optional. Include the latest already-captured, read-only Mix Assistant plug-in bus evidence for this session. No capture is requested and no track/device cause is inferred."},
                "mix_review_id": {"type": "string", "maxLength": 128, "description": "Optional. Include one explicit stored uploaded/rendered Mix Review and, when plugin_session_id is also supplied, a scope-labelled realtime-versus-uploaded comparison. No audio is retained and no Live target is inferred."},
            },
            "required": ["question"],
            "additionalProperties": False,
        },
    },
    {
        "name": "audiogen_artifact",
        "description": "Inspect one AudioGen job's bounded, validated artifact metadata. This tool never generates, imports, or writes to Live.",
        "inputSchema": {
            "type": "object",
            "properties": {"job_id": {"type": "string", "minLength": 1, "maxLength": 128}},
            "required": ["job_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "queue_assistant_audiogen_job",
        "description": "Queue one offline AudioGen render for the active assistant generation step and bind its server-issued job ID. This never changes Ableton Live.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "step_id": {"type": "string", "minLength": 1, "maxLength": 64},
                "session_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "emotion": {"type": "string", "maxLength": 64},
                "bars": {"type": "integer", "minimum": 1, "maximum": 24},
                "candidates": {"type": "integer", "minimum": 1, "maximum": 4},
            },
            "required": ["task_id", "step_id", "session_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "refresh_assistant_audiogen_job",
        "description": "Fetch one bound AudioGen job from KENN and update the active assistant step from its real queued, running, completed, or failed status. Caller-supplied job results are not accepted.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "step_id": {"type": "string", "minLength": 1, "maxLength": 64},
                "session_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "job_id": {"type": "string", "minLength": 1, "maxLength": 128},
            },
            "required": ["task_id", "step_id", "session_id", "job_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "bind_assistant_automix_job",
        "description": "Bind one already-created AutoMix job to the active assistant offline-render step using status fetched from KENN. This never starts AutoMix, uploads files, or changes Ableton Live.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "step_id": {"type": "string", "minLength": 1, "maxLength": 64},
                "session_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "job_id": {"type": "string", "minLength": 1, "maxLength": 128},
            },
            "required": ["task_id", "step_id", "session_id", "job_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "refresh_assistant_automix_job",
        "description": "Fetch one previously bound AutoMix job from KENN and update the assistant offline-render step from its real queued, running, completed, or failed status. This never starts AutoMix or changes Ableton Live.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "step_id": {"type": "string", "minLength": 1, "maxLength": 64},
                "session_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "job_id": {"type": "string", "minLength": 1, "maxLength": 128},
            },
            "required": ["task_id", "step_id", "session_id", "job_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "generate_audiogen_audio_candidate",
        "description": "Generate one offline AudioGen WAV candidate and return a local listen URL plus safe artifact metadata. This does not call Ableton or change Live.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "minLength": 1, "maxLength": 512},
                "emotion": {"type": "string", "maxLength": 64},
                "bars": {"type": "integer", "minimum": 1, "maximum": 24},
            },
            "required": ["prompt"],
            "additionalProperties": False,
        },
    },
    {
        "name": "compare_audiogen_audio_candidates",
        "description": "Compare two KENN-served AudioGen WAV candidates using bounded deterministic measurements. This returns technical deltas for revision planning, not a musical quality verdict, and never changes Live.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_a": {"type": "string", "minLength": 1, "maxLength": 512},
                "source_b": {"type": "string", "minLength": 1, "maxLength": 512},
            },
            "required": ["source_a", "source_b"],
            "additionalProperties": False,
        },
    },
    {
        "name": "create_midi_clip_from_artifact",
        "description": "Create a confirmation-only Live MIDI clip proposal from a completed, digest-bound AudioGen MIDI artifact. It never applies the change or opens a producer file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "session_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "track_index": {"type": "integer", "minimum": 0},
                "track_name": {"type": "string", "maxLength": 256},
                "clip_slot_index": {"type": "integer", "minimum": 0},
            },
            "required": ["job_id", "session_id", "track_index", "track_name", "clip_slot_index"],
            "additionalProperties": False,
        },
    },
    {
        "name": "generate_audiogen_midi_proposal",
        "description": "Ask the configured local AudioGen producer for symbolic MIDI events and turn them into a confirmation-only Live MIDI proposal. It never applies the Live change.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "track_index": {"type": "integer", "minimum": 0},
                "track_name": {"type": "string", "maxLength": 256},
                "clip_slot_index": {"type": "integer", "minimum": 0},
                "emotion": {"type": "string", "maxLength": 64},
                "bars": {"type": "integer", "minimum": 1, "maximum": 24},
                "seed": {"type": "string", "maxLength": 128},
            },
            "required": ["session_id", "track_index", "track_name", "clip_slot_index"],
            "additionalProperties": False,
        },
    },
    {
        "name": "generate_audiogen_midi_revision_proposal",
        "description": "Use one server-verified listener revision brief to generate a new AudioGen MIDI candidate at the same exact Live target. The result remains proposal-only, can be bound to an active assistant revision step, and must be confirmed separately.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "feedback_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "emotion": {"type": "string", "maxLength": 64},
                "bars": {"type": "integer", "minimum": 1, "maximum": 24},
                "seed": {"type": "integer"},
                "comparison": {"type": "object"},
                "assistant_task_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "assistant_step_id": {"type": "string", "minLength": 1, "maxLength": 64},
            },
            "required": ["session_id", "feedback_id", "seed"],
            "additionalProperties": False,
        },
    },
    {
        "name": "create_midi_clip_proposal",
        "description": "Create a confirmation-only proposal for a validated note list in one exact empty Ableton MIDI clip slot. It never applies the change.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "track_index": {"type": "integer", "minimum": 0},
                "track_name": {"type": "string", "maxLength": 256},
                "clip_slot_index": {"type": "integer", "minimum": 0},
                "length": {"type": "number", "exclusiveMinimum": 0, "maximum": 4096},
                "notes": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 4096,
                    "items": {
                        "type": "object",
                        "properties": {
                            "pitch": {"type": "integer", "minimum": 0, "maximum": 127},
                            "start_time": {"type": "number", "minimum": 0},
                            "duration": {"type": "number", "exclusiveMinimum": 0},
                            "velocity": {"type": "integer", "minimum": 1, "maximum": 127},
                            "mute": {"type": "boolean"},
                        },
                        "required": ["pitch", "start_time", "duration", "velocity"],
                        "additionalProperties": False,
                    },
                },
                "source_artifact_sha256": {"type": "string", "maxLength": 128},
                "source_artifact_id": {"type": "string", "maxLength": 256},
            },
            "required": ["session_id", "track_index", "track_name", "clip_slot_index", "length", "notes"],
            "additionalProperties": False,
        },
    },
    {
        "name": "update_midi_clip_proposal",
        "description": "Create a confirmation-only proposal to replace the complete note set of one exact existing MIDI clip. The current notes and clip identity are bound, readback is required, and the resulting receipt supports identity-checked undo.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "track_index": {"type": "integer", "minimum": 0},
                "track_name": {"type": "string", "maxLength": 256},
                "clip_slot_index": {"type": "integer", "minimum": 0},
                "notes": {
                    "type": "array",
                    "maxItems": 4096,
                    "items": {
                        "type": "object",
                        "properties": {
                            "pitch": {"type": "integer", "minimum": 0, "maximum": 127},
                            "start_time": {"type": "number", "minimum": 0},
                            "duration": {"type": "number", "exclusiveMinimum": 0},
                            "velocity": {"type": "integer", "minimum": 1, "maximum": 127},
                            "mute": {"type": "boolean"},
                        },
                        "required": ["pitch", "start_time", "duration", "velocity"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["session_id", "track_index", "track_name", "clip_slot_index", "notes"],
            "additionalProperties": False,
        },
    },
    {
        "name": "kenn_session_doctor",
        "description": "Diagnose session headroom, phase correlation, and low-end mud across all Live tracks, returning a prioritized report and autonomous non-destructive remediation batch.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "auto_remediate": {"type": "boolean", "default": False},
                "session_id": {"type": "string", "default": "doctor_session"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "kenn_generate_midi_pattern",
        "description": "Generate scale-aware chord progressions, Euclidean rhythms, or Drum Rack patterns ready to be inserted via create_midi_clip_proposal.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern_type": {"type": "string", "enum": ["chords", "euclidean", "drums"]},
                "root": {"type": "string", "default": "C"},
                "scale": {"type": "string", "default": "minor"},
                "progression": {"type": "string", "default": "pop_i_v_vi_iv"},
                "genre": {"type": "string", "default": "trap"},
                "bars": {"type": "integer", "default": 2},
                "hits": {"type": "integer", "default": 5},
                "steps": {"type": "integer", "default": 8},
                "pitch": {"type": "integer", "default": 36},
            },
            "required": ["pattern_type"],
            "additionalProperties": False,
        },
    },
    {
        "name": "kenn_search_knowledge",
        "description": "Semantic hybrid search across KENN's complete audio engineering knowledge base (389 notes + Ableton Live 12 manual).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 3},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
]


def _realtime_context_is_current(live_context: dict[str, Any]) -> bool:
    """Return whether retained plug-in context is fresh enough for advice."""
    freshness = live_context.get("freshness")
    if not isinstance(freshness, dict):
        return True
    current = freshness.get("current_for_diagnosis")
    if current is False:
        return False
    if current is True:
        return True
    age = freshness.get("age_seconds", live_context.get("age_seconds"))
    return not (
        isinstance(age, (int, float))
        and not isinstance(age, bool)
        and float(age) > MAX_PLUGIN_CONTEXT_AGE_SECONDS
    )


def _realtime_mix_recommendation(live_context: dict[str, Any]) -> Any | None:
    """Convert the realtime spectral observation into advisory guidance.

    Keep this separate from uploaded-render findings: a realtime bus snapshot
    has a different scope and cannot identify a responsible Live track/device.
    The companion has already validated the shape, trend, and freshness; this
    helper only formats the bounded spectral measurement for the recommendation
    list.  ``_realtime_mix_recommendations`` adds the other validated bus
    warnings while retaining this single-item helper for callers that only need
    the spectral finding.
    """
    from kenn.project_analysis import Recommendation

    # The handoff is retained longer than it is diagnostically current so a
    # client can inspect bounded history/recovery state.  Never phrase an old
    # bus snapshot as a current mix recommendation.
    if not _realtime_context_is_current(live_context):
        return None

    reference = live_context.get("pink_noise_reference")
    latest = reference.get("largest_deviation") if isinstance(reference, dict) else None
    window = live_context.get("live_window")
    shape = window.get("pink_noise_shape") if isinstance(window, dict) else None
    median = shape.get("largest_median_deviation") if isinstance(shape, dict) else None
    source = median if isinstance(median, dict) else latest
    if not isinstance(source, dict):
        return None
    frequency = source.get("center_hz")
    deviation_key = "median_deviation_db" if source is median else "deviation_db"
    deviation = source.get(deviation_key)
    if (
        isinstance(frequency, bool) or not isinstance(frequency, (int, float)) or float(frequency) <= 0
        or isinstance(deviation, bool) or not isinstance(deviation, (int, float))
        or not math.isfinite(float(frequency)) or not math.isfinite(float(deviation))
        or abs(float(deviation)) < 1.5
    ):
        return None
    direction = "above" if float(deviation) > 0 else "below"
    trend = str(window.get("status") or "insufficient") if isinstance(window, dict) else "insufficient"
    sample_count = window.get("sample_count") if isinstance(window, dict) else None
    window_note = f" across {int(sample_count)} recent frames" if isinstance(sample_count, int) and sample_count > 1 else ""
    return Recommendation(
        title=f"Realtime bus: inspect around {float(frequency):.0f} Hz",
        category="realtime_mix",
        severity="info",
        confidence=0.78,
        description=(
            f"The validated Mix Assistant plug-in bus is about {abs(float(deviation)):.1f} dB "
            f"{direction} the explicit pink-noise-style baseline around {float(frequency):.0f} Hz"
            f"{window_note}; the recent trend is {trend}."
        ),
        reason=(
            "This is a broad, uncalibrated realtime bus observation, not a track-level diagnosis, "
            "a universal target, or proof that an EQ change is needed."
        ),
        suggestedAction=(
            "Level-match and listen to the full arrangement, then audition likely source changes one at a time; "
            "do not apply automatic master EQ from this bus measurement."
        ),
        requiresConfirmation=False,
    )


def _realtime_mix_recommendations(live_context: dict[str, Any]) -> list[Any]:
    """Promote every validated current bus warning into advisory guidance.

    These findings deliberately remain bus-scoped.  They are useful for the
    assistant's next listening check, but none identifies a responsible track
    or device and none is eligible for automatic Live mutation.
    """
    from kenn.project_analysis import Recommendation

    if not _realtime_context_is_current(live_context):
        return []

    metrics = live_context
    recommendations: list[Any] = []
    peak = metrics.get("peak_dbfs")
    if isinstance(peak, (int, float)) and not isinstance(peak, bool) and float(peak) > -0.3:
        recommendations.append(Recommendation(
            title="Realtime bus: limited peak headroom",
            category="realtime_mix",
            severity="warning",
            confidence=0.95,
            description=(
                f"The current validated bus peak is {float(peak):.1f} dBFS, within 0.3 dB of full scale."
            ),
            reason=(
                "The plug-in reports a momentary bus peak, not calibrated loudness or true peak; this is a reason to listen and inspect the gain/limiter chain."
            ),
            suggestedAction=(
                "Check source gain and limiting at matched loudness, then confirm export headroom; do not lower the master automatically."
            ),
            requiresConfirmation=False,
        ))

    clipped = metrics.get("clipped_samples")
    if isinstance(clipped, (int, float)) and not isinstance(clipped, bool) and float(clipped) > 0:
        recommendations.append(Recommendation(
            title="Realtime bus: recent clipping",
            category="realtime_mix",
            severity="warning",
            confidence=0.98,
            description=(
                f"The latest validated bus block contains {int(float(clipped))} sample(s) at digital full scale."
            ),
            reason="The handoff records a recent clipped-sample count directly from the plug-in bus snapshot.",
            suggestedAction="Locate the gain or limiter stage causing the peak, audition the unclipped path, and recheck the full arrangement.",
            requiresConfirmation=False,
        ))

    correlation = metrics.get("stereo_correlation")
    if isinstance(correlation, (int, float)) and not isinstance(correlation, bool) and float(correlation) < 0.0:
        recommendations.append(Recommendation(
            title="Realtime bus: mono-compatibility risk",
            category="realtime_mix",
            severity="warning",
            confidence=0.88,
            description=f"The current validated bus stereo correlation is {float(correlation):.2f}, below zero.",
            reason="Negative correlation can indicate phase interaction that deserves an audible mono check, but it is not proof of a fault.",
            suggestedAction="Audition the arrangement in mono and compare the affected elements before changing width or polarity.",
            requiresConfirmation=False,
        ))

    width = metrics.get("stereo_width")
    if isinstance(width, (int, float)) and not isinstance(width, bool) and float(width) > 0.75:
        recommendations.append(Recommendation(
            title="Realtime bus: wide side energy",
            category="realtime_mix",
            severity="info",
            confidence=0.76,
            description=f"The current validated bus stereo-width estimate is {float(width):.2f}, above the broad 0.75 review threshold.",
            reason="Width is a stylistic choice; a broad bus estimate cannot identify which source contributes the side energy.",
            suggestedAction="Compare the mix against a level-matched reference and audition mono playback before narrowing anything.",
            requiresConfirmation=False,
        ))

    spectral = _realtime_mix_recommendation(live_context)
    if spectral is not None:
        recommendations.append(spectral)
    return recommendations


class KennHTTPClient:
    """Small standard-library HTTP client used by the stdio facade."""

    def __init__(
        self, base_url: str = "http://127.0.0.1:8090", timeout: float = 15.0,
        opener: Callable[..., Any] = open_loopback_companion,
    ):
        self.base_url = validate_companion_base_url(base_url)
        self.timeout = max(0.1, float(timeout))
        self._opener = opener

    def get(self, path: str, query: dict[str, Any] | None = None) -> dict[str, Any]:
        url = self.base_url + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        request = urllib.request.Request(url, method="GET")
        return self._open(request)

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        return self._open(request)

    def _open(self, request: urllib.request.Request) -> dict[str, Any]:
        try:
            with self._opener(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8"))
            except Exception:
                payload = {"error": str(exc)}
            payload.setdefault("http_status", exc.code)
            return payload
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            raise KennTransportError(
                "KENN companion request did not complete; mutation state may be uncertain. "
                "Do not retry an apply or undo request. Inspect live_receipts and live_snapshot first."
            ) from exc


class KennMCPFacade:
    """Handle MCP JSON-RPC messages using an injected KENN HTTP client."""

    def __init__(
        self,
        client: KennHTTPClient | Any,
        coordinator: AssistantCoordinator | None = None,
        *,
        diagnostic_store: DiagnosticLoopStore | None = None,
        session_outcome_store: SessionOutcomeStore | None = None,
        planner: Callable[[str], str] | None = None,
        planner_provider: str = "ollama",
        planner_id: str = "configured-local",
    ):
        self.client = client
        self.coordinator = coordinator or AssistantCoordinator(AssistantTaskStore())
        self.diagnostic_store = diagnostic_store or DiagnosticLoopStore(self.coordinator.store.db_path)
        self.profile_store = AssistantProfileStore(self.coordinator.store.db_path)
        self.session_outcome_store = session_outcome_store or SessionOutcomeStore(self.coordinator.store.db_path)
        self.planner = planner
        self.planner_provider = str(planner_provider or "unknown")[:128]
        self.planner_id = str(planner_id or "unknown")[:128]
        self._world_models: dict[str, SessionWorldModel] = {}
        self._max_world_models = 32

    def handle_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(message, dict):
            return self._error(None, -32600, "Invalid JSON-RPC message.")
        method = message.get("method")
        request_id = message.get("id")
        if method == "notifications/initialized" or method == "notifications/cancelled":
            return None
        if method == "ping":
            return self._result(request_id, {})
        if method == "initialize":
            return self._result(
                request_id,
                {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                    "instructions": "KENN exposes exact Live reads, proposal creation, explicitly confirmed proposal apply, and identity-bound receipt undo. It has no raw OSC or arbitrary execution tool.",
                },
            )
        if method == "tools/list":
            return self._result(request_id, {"tools": TOOLS})
        if method == "tools/call":
            params = message.get("params") if isinstance(message.get("params"), dict) else {}
            return self._tool_call(request_id, str(params.get("name", "")), params.get("arguments"))
        if request_id is None:
            return None
        return self._error(request_id, -32601, f"Method not found: {method}")

    def _tool_call(self, request_id: Any, name: str, arguments: Any) -> dict[str, Any]:
        args = arguments if isinstance(arguments, dict) else {}
        try:
            result = self._dispatch(name, args)
            return self._result(request_id, {"content": [{"type": "text", "text": json.dumps(result, indent=2, sort_keys=True)}], "isError": False})
        except KennTransportError as exc:
            is_mutation = name in {"apply_live_proposal", "undo_live_receipt"}
            error = {
                "ok": False,
                "error": str(exc),
                "tool": name,
                "error_kind": "transport_uncertain",
                "retry_allowed": not is_mutation,
                "recovery_tools": ["live_receipts", "live_snapshot"],
            }
            return self._result(request_id, {"content": [{"type": "text", "text": json.dumps(error, indent=2, sort_keys=True)}], "isError": True})
        except Exception as exc:
            error = {"ok": False, "error": str(exc), "tool": name}
            return self._result(request_id, {"content": [{"type": "text", "text": json.dumps(error, indent=2, sort_keys=True)}], "isError": True})

    def _dispatch(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name == "live_snapshot":
            detail = str(args.get("detail", "topology"))
            if detail not in {"topology", "full", "understanding"}:
                raise ValueError("detail must be 'topology', 'full', or 'understanding'")
            return self.client.get("/api/ableton/osc/session", {"detail": detail})
        if name == "live_plugin_review":
            session_id = str(args.get("session_id", "")).strip()[:128]
            if not session_id:
                raise ValueError("session_id is required")
            result = self.client.get("/api/plugin-live-review", {"session_id": session_id})
            if not isinstance(result, dict):
                raise ValueError("KENN returned an invalid plug-in review response")
            # Preserve the endpoint's explicit missing/expired distinction so
            # a reasoning client cannot mistake an unavailable frame for a
            # zero-valued measurement or stale session state.
            return result
        if name == "realtime_session_review":
            plugin_session_id = str(args.get("plugin_session_id", "")).strip()[:128]
            focus = str(args.get("focus", "")).strip()[:512]
            query = {}
            if plugin_session_id:
                query["plugin_session_id"] = plugin_session_id
            if focus:
                query["focus"] = focus
            result = self.client.get("/api/realtime-session-review", query)
            if not isinstance(result, dict):
                raise ValueError("KENN returned an invalid realtime session review response")
            return result
        if name == "live_arrangement_analysis":
            session_id = str(args.get("session_id", "")).strip()[:128]
            if not session_id:
                raise ValueError("session_id is required")
            context = self._dispatch(
                "kenn_context",
                {
                    "session_id": session_id,
                    "include_device_matrix": False,
                    "include_device_parameters": False,
                },
            )
            return analyze_arrangement_context(context)
        if name == "realtime_mix_recommendations":
            session_id = str(args.get("session_id", "")).strip()[:128]
            if not session_id:
                raise ValueError("session_id is required")
            result = self.client.get("/api/plugin-live-review", {"session_id": session_id})
            if not isinstance(result, dict):
                raise ValueError("KENN returned an invalid plug-in review response")
            context = result.get("live_context")
            recommendations = _realtime_mix_recommendations(context) if isinstance(context, dict) else []
            limitations = [
                "Realtime findings are validated plug-in bus observations, not track-level diagnoses.",
                "No responsible Live track/device is inferred and no automatic master EQ or other mutation is authorized.",
            ]
            if isinstance(context, dict) and not _realtime_context_is_current(context):
                limitations.append("The retained plug-in context is stale_or_unknown for current diagnosis; recommendations are withheld.")
            if result.get("ok") is not True:
                return {
                    "ok": False,
                    "schema": "kenn.realtime_mix_recommendations.v1",
                    "session_id": session_id,
                    "recommendations": [],
                    "recommendations_available": False,
                    "advisory_only": True,
                    "capture_requested": False,
                    "error": result.get("error") or "No validated realtime plug-in review was available.",
                    "limitations": limitations,
                }
            return {
                "ok": True,
                "schema": "kenn.realtime_mix_recommendations.v1",
                "session_id": session_id,
                "scope": "plugin_bus",
                "recommendations": [item.payload() for item in recommendations],
                "recommendations_available": bool(recommendations),
                "advisory_only": True,
                "capture_requested": False,
                "freshness": context.get("freshness") if isinstance(context, dict) else None,
                "live_context": context,
                "limitations": limitations,
            }
        if name == "compare_realtime_mix_review":
            review_id = str(args.get("review_id", "")).strip()[:128]
            plugin_session_id = str(args.get("plugin_session_id", "")).strip()[:128]
            if not review_id or not plugin_session_id:
                raise ValueError("review_id and plugin_session_id are required")
            review_result = self.client.get("/api/mix-review-status", {"id": review_id})
            review = review_result.get("review") if isinstance(review_result, dict) else None
            plugin_result = self.client.get("/api/plugin-live-review", {"session_id": plugin_session_id})
            live_context = plugin_result.get("live_context") if isinstance(plugin_result, dict) else None
            comparison = build_realtime_mix_comparison(
                review,
                live_context,
                review_id=review_id,
                plugin_session_id=plugin_session_id,
            )
            if not isinstance(review, dict):
                comparison.update({"ok": False, "error": review_result.get("error", "Mix Review was not found.")})
            elif not isinstance(live_context, dict):
                comparison.update({"ok": False, "error": plugin_result.get("error", "No realtime plug-in context was available.")})
            return comparison
        if name == "live_midi_clip":
            track_index = self._index(args, "track_index")
            clip_slot_index = self._index(args, "clip_slot_index")
            return self.client.get(
                "/api/ableton/osc/midi-clip",
                {"track_index": track_index, "clip_slot_index": clip_slot_index},
            )
        if name == "live_clip_slot":
            track_index = self._index(args, "track_index")
            clip_slot_index = self._index(args, "clip_slot_index")
            return self.client.get(
                "/api/ableton/osc/clip-slot",
                {"track_index": track_index, "clip_slot_index": clip_slot_index},
            )
        if name == "duplicate_clip_proposal":
            session_id = str(args.get("session_id", "")).strip()[:128]
            if not session_id:
                raise ValueError("session_id is required")
            result = self.client.post(
                "/api/ableton/clip-duplication/proposal",
                {
                    "session_id": session_id,
                    "source_track_index": args.get("source_track_index"),
                    "source_track_name": str(args.get("source_track_name", ""))[:256],
                    "source_clip_slot_index": args.get("source_clip_slot_index"),
                    "target_track_index": args.get("target_track_index"),
                    "target_track_name": str(args.get("target_track_name", ""))[:256],
                    "target_clip_slot_index": args.get("target_clip_slot_index"),
                },
            )
            if result.get("receipt") or result.get("changed") is True:
                raise RuntimeError("KENN returned a mutation from a clip duplication proposal-only MCP call")
            return result
        if name == "rename_clip_proposal":
            session_id = str(args.get("session_id", "")).strip()[:128]
            if not session_id:
                raise ValueError("session_id is required")
            result = self.client.post(
                "/api/ableton/clip-rename/proposal",
                {
                    "session_id": session_id,
                    "track_index": args.get("track_index"),
                    "track_name": str(args.get("track_name", ""))[:256],
                    "clip_slot_index": args.get("clip_slot_index"),
                    "new_name": str(args.get("new_name", ""))[:128],
                },
            )
            if result.get("receipt") or result.get("changed") is True:
                raise RuntimeError("KENN returned a mutation from a clip rename proposal-only MCP call")
            return result
        if name == "live_devices":
            track_index = self._index(args, "track_index")
            snapshot = self.client.get("/api/ableton/osc/session", {"detail": "topology"})
            tracks = [item for item in snapshot.get("tracks", []) if isinstance(item, dict)]
            track = next((item for item in tracks if int(item.get("index", -1)) == track_index), None)
            if track is None:
                raise ValueError(f"track_index {track_index} is not present in the current Live snapshot")
            return {
                "status": snapshot.get("status"),
                "track_index": track_index,
                "track_name": track.get("name", ""),
                "devices": track.get("devices", []),
            }
        if name == "live_parameters":
            track_index = self._index(args, "track_index")
            device_index = self._index(args, "device_index")
            return self.client.get("/api/ableton/osc/device-parameters", {"track_index": track_index, "device_index": device_index})
        if name == "live_parameter_display":
            track_index = self._index(args, "track_index")
            device_index = self._index(args, "device_index")
            parameter_index = self._index(args, "parameter_index")
            return self.client.get(
                "/api/ableton/osc/device-parameter-value-string",
                {"track_index": track_index, "device_index": device_index, "parameter_index": parameter_index},
            )
        if name == "live_parameter_profile":
            track_index = self._index(args, "track_index")
            device_index = self._index(args, "device_index")
            parameter_index = self._index(args, "parameter_index")
            info = self.client.get(
                "/api/ableton/osc/device-parameters",
                {"track_index": track_index, "device_index": device_index},
            )
            parameters = info.get("parameters", []) if isinstance(info, dict) else []
            parameter = next(
                (
                    item for item in parameters
                    if isinstance(item, dict) and int(item.get("index", -1)) == parameter_index
                ),
                None,
            )
            if parameter is None and 0 <= parameter_index < len(parameters):
                parameter = parameters[parameter_index]
            if not isinstance(parameter, dict):
                raise ValueError(f"parameter_index {parameter_index} is not present on the current Live device")
            display = self.client.get(
                "/api/ableton/osc/device-parameter-value-string",
                {
                    "track_index": track_index,
                    "device_index": device_index,
                    "parameter_index": parameter_index,
                },
            )
            return {
                "success": bool(info.get("success")) if isinstance(info, dict) else False,
                "track_index": track_index,
                "device_index": device_index,
                "device_name": info.get("device_name", "") if isinstance(info, dict) else "",
                "parameter": parameter,
                "display": display,
                "display_available": bool(isinstance(display, dict) and display.get("success")),
            }
        if name == "compare_live_devices":
            coordinates = {
                "left": (self._index(args, "left_track_index"), self._index(args, "left_device_index")),
                "right": (self._index(args, "right_track_index"), self._index(args, "right_device_index")),
            }
            snapshot = self.client.get("/api/ableton/osc/session", {"detail": "topology"})
            if not isinstance(snapshot, dict) or snapshot.get("status") != "connected":
                return {
                    "ok": False,
                    "schema": "kenn.live_device_comparison.v1",
                    "status": "offline",
                    "error": "The current Live topology is not connected; device comparison is unavailable.",
                    "read_only": True,
                    "mutation_authorized": False,
                }

            def exact_identity(track_index: int, device_index: int) -> dict[str, Any]:
                tracks = [item for item in snapshot.get("tracks", []) if isinstance(item, dict)]
                track = next((item for item in tracks if int(item.get("index", -1)) == track_index), None)
                if track is None:
                    raise ValueError(f"track_index {track_index} is not present in the current Live snapshot")
                devices = [item for item in track.get("devices", []) if isinstance(item, dict)]
                device = next((item for item in devices if int(item.get("index", -1)) == device_index), None)
                if device is None:
                    raise ValueError(f"device_index {device_index} is not present on track_index {track_index}")
                return {
                    "track_index": track_index,
                    "track_name": str(track.get("name", ""))[:128],
                    "device_index": device_index,
                    "device_name": str(device.get("name", ""))[:128],
                }

            identities = {side: exact_identity(*pair) for side, pair in coordinates.items()}
            parameter_sets: dict[str, dict[str, Any]] = {}
            for side, identity in identities.items():
                info = self.client.get(
                    "/api/ableton/osc/device-parameters",
                    {"track_index": identity["track_index"], "device_index": identity["device_index"]},
                )
                if not isinstance(info, dict) or info.get("success") is not True:
                    raise ValueError(f"Could not read parameters for the {side} device")
                if str(info.get("device_name", "")) != identity["device_name"]:
                    raise ValueError(f"The {side} device identity changed during comparison")
                parameter_sets[side] = info

            def keyed_parameters(values: Any) -> dict[tuple[str, int], dict[str, Any]]:
                seen: dict[str, int] = {}
                result: dict[tuple[str, int], dict[str, Any]] = {}
                for item in values if isinstance(values, list) else []:
                    if not isinstance(item, dict):
                        continue
                    parameter_name = str(item.get("name", "")).strip()
                    if not parameter_name:
                        continue
                    normalized = parameter_name.casefold()
                    occurrence = seen.get(normalized, 0)
                    seen[normalized] = occurrence + 1
                    result[(normalized, occurrence)] = item
                return result

            left_parameters = keyed_parameters(parameter_sets["left"].get("parameters"))
            right_parameters = keyed_parameters(parameter_sets["right"].get("parameters"))
            rows: list[dict[str, Any]] = []
            keys = list(left_parameters) + [key for key in right_parameters if key not in left_parameters]
            for key in keys:
                left = left_parameters.get(key)
                right = right_parameters.get(key)
                row: dict[str, Any] = {
                    "name": (left or right).get("name", ""),
                    "matched": left is not None and right is not None,
                }
                if left is not None:
                    row["left"] = {field: left[field] for field in ("index", "value", "min", "max", "quantized") if field in left}
                if right is not None:
                    row["right"] = {field: right[field] for field in ("index", "value", "min", "max", "quantized") if field in right}
                left_value = left.get("value") if left else None
                right_value = right.get("value") if right else None
                if (
                    isinstance(left_value, (int, float)) and not isinstance(left_value, bool)
                    and math.isfinite(float(left_value))
                    and isinstance(right_value, (int, float)) and not isinstance(right_value, bool)
                    and math.isfinite(float(right_value))
                ):
                    row["delta_right_minus_left"] = round(float(right_value) - float(left_value), 6)
                rows.append(row)
            differing = sum(
                1 for row in rows
                if row.get("matched") is True and row.get("delta_right_minus_left") not in (None, 0.0)
            )
            return {
                "ok": True,
                "schema": "kenn.live_device_comparison.v1",
                "status": "complete",
                "left": identities["left"],
                "right": identities["right"],
                "matched_parameter_count": sum(1 for row in rows if row.get("matched") is True),
                "differing_parameter_count": differing,
                "parameters": rows[:128],
                "comparison_basis": "Matched parameter names and current raw Live values; display units may differ and are not inferred here.",
                "limitations": [
                    "This reports current parameter metadata and raw values, not an audible preference or sonic quality verdict.",
                    "Unmatched parameters are shown separately; KENN does not invent equivalence between different controls.",
                    "A comparison never authorizes a Live write; any change requires a separate exact proposal, confirmation, stale check, and readback.",
                ],
                "read_only": True,
                "mutation_authorized": False,
            }
        if name == "create_live_proposal":
            command = str(args.get("command", "")).strip()
            if not command:
                raise ValueError("command is required")
            session_id = str(args.get("session_id", "mcp-proposal")).strip() or "mcp-proposal"
            self._assistant_binding_ids(args)
            result = self.client.post("/api/ableton/command", {"session_id": session_id, "command": command})
            # A proposal call must never be allowed to return an applied receipt.
            if result.get("receipt") or result.get("changed") is True:
                raise RuntimeError("KENN returned a mutation from a proposal-only MCP call")
            binding = self._bind_assistant_proposal(args=args, result=result, session_id=session_id)
            if binding is not None:
                result = {**result, "assistant_task": binding}
            return result
        if name == "create_live_recipe_proposal":
            session_id = str(args.get("session_id", "")).strip()[:128]
            steps = args.get("steps")
            self._assistant_binding_ids(args)
            if not session_id:
                raise ValueError("session_id is required")
            if not isinstance(steps, list) or not 1 <= len(steps) <= 3:
                raise ValueError("steps must contain between 1 and 3 typed actions")
            if any(not isinstance(step, dict) for step in steps):
                raise ValueError("every recipe step must be an object")
            payload = {
                "session_id": session_id,
                "command": str(args.get("reason", "MCP supervised Live recipe"))[:512],
                "recipe_steps": steps,
            }
            result = self.client.post("/api/ableton/command", payload)
            if result.get("receipt") or result.get("changed") is True:
                raise RuntimeError("KENN returned a mutation from a recipe proposal-only MCP call")
            binding = self._bind_assistant_proposal(args=args, result=result, session_id=session_id)
            if binding is not None:
                result = {**result, "assistant_task": binding}
            return result
        if name == "create_mix_review_recipe_proposal":
            review_id = str(args.get("review_id", "")).strip()[:128]
            session_id = str(args.get("session_id", "")).strip()[:128]
            steps = args.get("steps")
            if not review_id or not session_id:
                raise ValueError("review_id and session_id are required")
            if not isinstance(steps, list) or not 1 <= len(steps) <= 3:
                raise ValueError("steps must contain between 1 and 3 typed actions")
            if any(not isinstance(step, dict) for step in steps):
                raise ValueError("every recipe step must be an object")
            result = self.client.post(
                "/api/ableton/command",
                {
                    "session_id": session_id,
                    "command": str(args.get("reason", "Mix Review evidence-bound Live recipe"))[:512],
                    "mix_review_id": review_id,
                    "recipe_steps": steps,
                },
            )
            if result.get("receipt") or result.get("changed") is True:
                raise RuntimeError("KENN returned a mutation from a Mix Review recipe proposal-only MCP call")
            return result
        if name == "apply_live_proposal":
            proposal = args.get("proposal")
            if not isinstance(proposal, dict) or not proposal:
                raise ValueError("proposal must be a non-empty object")
            confirm_token = str(args.get("confirm_token", "")).strip()
            session_id = str(args.get("session_id", "")).strip()
            idempotency_key = str(args.get("idempotency_key", "")).strip()
            task_id, step_id = self._assistant_binding_ids(args)
            if not confirm_token or not session_id or not idempotency_key:
                raise ValueError("confirm_token, session_id, and idempotency_key are required")
            result = self.client.post(
                "/api/ableton/command",
                {
                    "command": "apply confirmed KENN Live proposal",
                    "session_id": session_id,
                    "proposal": proposal,
                    "confirm_token": confirm_token,
                    "idempotency_key": idempotency_key,
                },
            )
            # The command gateway's public response uses ``status`` and
            # ``changed`` as its authoritative outcome fields, but older and
            # test HTTP clients may omit the convenience ``ok`` boolean.
            # Normalize it here so assistant trajectories have one stable
            # contract for both successful applies and replay rejection.
            if isinstance(result, dict) and "ok" not in result:
                result = {
                    **result,
                    "ok": result.get("status") == "applied" and result.get("changed") is True,
                }
            if task_id and step_id:
                receipt = result.get("receipt") if isinstance(result.get("receipt"), dict) else None
                if receipt is None:
                    binding = {"ok": False, "errors": ["Applied response did not include a typed receipt."]}
                else:
                    try:
                        binding = self.coordinator.record_evidence(
                            task_id=task_id,
                            step_id=step_id,
                            evidence=receipt,
                            context=self._assistant_context(session_id),
                        )
                    except Exception as exc:
                        # The Live result is already known. Never obscure its
                        # receipt because optional assistant bookkeeping failed.
                        binding = {
                            "ok": False,
                            "error_kind": "assistant_sync_failed",
                            "errors": [f"{type(exc).__name__}: {exc}"],
                            "recovery_tool": "record_assistant_live_receipt",
                        }
                result = {**result, "assistant_task": binding}
            return result
        if name == "create_clip_audition_proposal":
            session_id = str(args.get("session_id", "")).strip()[:128]
            track_name = str(args.get("track_name", "")).strip()[:256]
            if not session_id or not track_name:
                raise ValueError("session_id and track_name are required")
            result = self.client.post(
                "/api/ableton/clip-audition/proposal",
                {
                    "session_id": session_id,
                    "track_index": args.get("track_index"),
                    "track_name": track_name,
                    "clip_slot_index": args.get("clip_slot_index"),
                    "source_receipt_id": str(args.get("source_receipt_id", ""))[:256],
                },
            )
            if result.get("receipt") or result.get("changed") is True:
                raise RuntimeError("KENN returned a mutation from a clip audition proposal-only MCP call")
            return result
        if name == "create_clip_audition_from_receipt":
            session_id = str(args.get("session_id", "")).strip()[:128]
            receipt = args.get("receipt")
            if not session_id or not isinstance(receipt, dict):
                raise ValueError("session_id and receipt are required")
            if receipt.get("schema") != "kenn.ableton_midi_clip_receipt.v1" or receipt.get("status") != "applied" or receipt.get("verified") is not True:
                raise ValueError("receipt must be a verified applied MIDI clip receipt")
            target = receipt.get("target") if isinstance(receipt.get("target"), dict) else {}
            if any(key not in target for key in ("track_index", "track_name", "clip_slot_index")):
                raise ValueError("receipt does not contain a complete exact MIDI clip target")
            result = self.client.post(
                "/api/ableton/clip-audition/proposal",
                {
                    "session_id": session_id,
                    "track_index": target["track_index"],
                    "track_name": str(target["track_name"])[:256],
                    "clip_slot_index": target["clip_slot_index"],
                    "source_receipt_id": str(receipt.get("receipt_id", ""))[:256],
                },
            )
            if result.get("receipt") or result.get("changed") is True:
                raise RuntimeError("KENN returned a mutation from a receipt-derived audition proposal-only MCP call")
            return {**result, "source_receipt_id": str(receipt.get("receipt_id", ""))[:256]}
        if name == "record_audition_feedback":
            session_id = str(args.get("session_id", "")).strip()[:128]
            receipt = args.get("receipt")
            verdict = str(args.get("verdict", "")).strip()[:32]
            if not session_id or not isinstance(receipt, dict) or not verdict:
                raise ValueError("session_id, receipt, and verdict are required")
            result = self.client.post(
                "/api/ableton/audition-feedback",
                {
                    "session_id": session_id,
                    "receipt": receipt,
                    "verdict": verdict,
                    "rating": args.get("rating"),
                    "comment": str(args.get("comment", ""))[:1000],
                    "requested_changes": args.get("requested_changes"),
                },
            )
            if result.get("receipt") or result.get("changed") is True:
                raise RuntimeError("KENN returned a mutation from an advisory audition-feedback call")
            return result
        if name == "audition_feedback":
            session_id = str(args.get("session_id", "")).strip()[:128]
            try:
                limit = int(args.get("limit", 20))
            except (TypeError, ValueError):
                raise ValueError("limit must be an integer between 1 and 100") from None
            if not 1 <= limit <= 100:
                raise ValueError("limit must be an integer between 1 and 100")
            return self.client.get(
                "/api/ableton/audition-feedback",
                {"session_id": session_id, "limit": limit},
            )
        if name == "create_audition_revision_brief":
            session_id = str(args.get("session_id", "")).strip()[:128]
            feedback_id = str(args.get("feedback_id", "")).strip()[:128]
            if not session_id or not feedback_id:
                raise ValueError("session_id and feedback_id are required")
            result = self.client.get(
                "/api/ableton/audition-feedback",
                {"session_id": session_id, "limit": 100},
            )
            items = result.get("feedback", []) if isinstance(result, dict) else []
            feedback = next(
                (
                    item for item in items
                    if isinstance(item, dict) and str(item.get("feedback_id", "")) == feedback_id
                ),
                None,
            )
            if feedback is None:
                raise ValueError("feedback_id was not found in the requested session")
            return build_audition_revision_brief(feedback, comparison=args.get("comparison"))
        if name == "undo_live_receipt":
            receipt = args.get("receipt")
            if not isinstance(receipt, dict) or not receipt:
                raise ValueError("receipt must be a non-empty object")
            session_id = str(args.get("session_id", "")).strip()
            if not session_id:
                raise ValueError("session_id is required")
            proposal = args.get("proposal")
            if proposal is None:
                result = self.client.post(
                    "/api/ableton/osc/undo",
                    {"receipt": receipt, "session_id": session_id},
                )
                if result.get("ok") and isinstance(result.get("proposal"), dict):
                    return {
                        **result,
                        "status": "confirmation_required",
                        "changed": False,
                        "confirmation_required": True,
                    }
                return result
            if not isinstance(proposal, dict) or not proposal:
                raise ValueError("proposal must be a non-empty object when applying an undo")
            confirm_token = str(args.get("confirm_token", "")).strip()
            idempotency_key = str(args.get("idempotency_key", "")).strip()
            if not confirm_token or not idempotency_key:
                raise ValueError("confirm_token and idempotency_key are required when applying an undo")
            result = self.client.post(
                "/api/ableton/osc/undo",
                {
                    "receipt": receipt,
                    "proposal": proposal,
                    "session_id": session_id,
                    "confirm_token": confirm_token,
                    "idempotency_key": idempotency_key,
                },
            )
            if result.get("ok"):
                return {**result, "status": "applied", "changed": True}
            return {**result, "status": "failed", "changed": False}
        if name == "live_receipts":
            session_id = str(args.get("session_id", "")).strip()
            try:
                limit = int(args.get("limit", 20))
            except (TypeError, ValueError):
                raise ValueError("limit must be an integer between 1 and 200") from None
            if not 1 <= limit <= 200:
                raise ValueError("limit must be an integer between 1 and 200")
            return self.client.get(
                "/api/ableton/receipts",
                {"session_id": session_id, "limit": limit},
            )
        if name == "kenn_capabilities":
            return self.client.get("/api/ableton/capabilities")
        if name == "live_device_matrix":
            include_parameters = args.get("include_parameters", True)
            if not isinstance(include_parameters, bool):
                raise ValueError("include_parameters must be boolean")
            return self.client.get(
                "/api/ableton/device-matrix",
                {"parameters": "1" if include_parameters else "0"},
            )
        if name == "search_sample_library":
            query = str(args.get("query", "")).strip()[:256]
            if not query:
                raise ValueError("query is required")
            limit = args.get("limit", 10)
            try:
                limit = max(1, min(50, int(limit)))
            except (TypeError, ValueError):
                limit = 10
            from kenn.core.sample_library import library_root, scan_sample_library, search_samples

            root = library_root()
            if root is None:
                return {
                    "ok": False,
                    "query": query,
                    "results": [],
                    "error": "No sample library is configured (KENN_SAMPLE_LIBRARY_ROOT is unset or not a directory).",
                }
            entries = scan_sample_library(root)
            results = search_samples(entries, query, limit=limit)
            return {
                "ok": True,
                "query": query,
                "results": [entry.payload() for entry in results],
                "total_indexed": len(entries),
                "advisory_only": True,
                "live_import_available": True,
                "live_import_notes": "Use import_sample_to_live for a confirmation-only proposal. Reliability depends on the sample's folder already being registered as a Place in Ableton (Live > Preferences > Library); a large, deeply-nested library is not yet reliably fast/correct to search.",
            }
        if name == "analyze_sample_library_entry":
            sample_id = str(args.get("sample_id", "")).strip()[:64]
            if not sample_id:
                raise ValueError("sample_id is required")
            from kenn.core.sample_library import (
                analyze_sample_audio,
                library_root,
                resolve_sample,
                scan_sample_library,
            )

            root = library_root()
            if root is None:
                return {
                    "ok": False,
                    "sample_id": sample_id,
                    "error": "No sample library is configured (KENN_SAMPLE_LIBRARY_ROOT is unset or not a directory).",
                }
            entries = scan_sample_library(root)
            entry = resolve_sample(entries, sample_id)
            if entry is None:
                return {
                    "ok": False,
                    "sample_id": sample_id,
                    "error": "No sample with that id was found in the configured library (run search_sample_library first).",
                }
            result, abstain_reason = analyze_sample_audio(root / entry.relative_path)
            if result is None:
                return {
                    "ok": False,
                    "sample_id": sample_id,
                    "filename": entry.filename,
                    "error": f"Analysis abstained: {abstain_reason}.",
                }
            return {
                "ok": True,
                "sample_id": sample_id,
                "filename": entry.filename,
                "measured": True,
                **result,
            }
        if name == "find_similar_samples":
            sample_id = str(args.get("sample_id", "")).strip()[:64]
            candidate_query = str(args.get("candidate_query", "")).strip()[:256]
            if not sample_id:
                raise ValueError("sample_id is required")
            if not candidate_query:
                raise ValueError("candidate_query is required")
            limit = args.get("limit", 10)
            try:
                limit = max(1, min(20, int(limit)))
            except (TypeError, ValueError):
                limit = 10
            from kenn.core.sample_embeddings import rank_by_similarity
            from kenn.core.sample_library import library_root, resolve_sample, scan_sample_library, search_samples

            root = library_root()
            if root is None:
                return {
                    "ok": False,
                    "sample_id": sample_id,
                    "error": "No sample library is configured (KENN_SAMPLE_LIBRARY_ROOT is unset or not a directory).",
                }
            entries = scan_sample_library(root)
            target = resolve_sample(entries, sample_id)
            if target is None:
                return {
                    "ok": False,
                    "sample_id": sample_id,
                    "error": "No sample with that id was found in the configured library (run search_sample_library first).",
                }
            candidates = [
                (entry.id, root / entry.relative_path)
                for entry in search_samples(entries, candidate_query, limit=25)
            ]
            ranked, reason = rank_by_similarity(root / target.relative_path, candidates, limit=limit)
            if ranked is None:
                return {
                    "ok": False,
                    "sample_id": sample_id,
                    "error": f"Similarity search abstained: {reason}.",
                }
            by_id = {entry.id: entry for entry in entries}
            results = []
            for item in ranked:
                entry = by_id.get(item["sample_id"])
                if entry is None:
                    continue
                results.append({**entry.payload(), "similarity": item["similarity"]})
            return {
                "ok": True,
                "sample_id": sample_id,
                "measured": True,
                "candidate_pool_size": len(candidates),
                "results": results,
                "advisory_only": True,
                "live_import_available": True,
                "live_import_notes": "Use import_sample_to_live for a confirmation-only proposal. Reliability depends on the sample's folder already being registered as a Place in Ableton (Live > Preferences > Library); a large, deeply-nested library is not yet reliably fast/correct to search.",
            }
        if name == "import_sample_to_live":
            sample_id = str(args.get("sample_id", "")).strip()[:64]
            session_id = str(args.get("session_id", "")).strip()[:128]
            track_name = str(args.get("track_name", "")).strip()[:256]
            if not sample_id or not session_id or not track_name:
                raise ValueError("sample_id, session_id, and track_name are required")
            payload = {
                "session_id": session_id,
                "track_index": args.get("track_index"),
                "track_name": track_name,
                "clip_slot_index": args.get("clip_slot_index"),
                "sample_id": sample_id,
            }
            result = self.client.post("/api/ableton/sample-import/proposal", payload)
            if result.get("receipt") or result.get("changed") is True:
                raise RuntimeError("KENN returned a mutation from a proposal-only MCP call")
            return result
        if name == "ask_audio_engineering_question":
            question = str(args.get("question", "")).strip()[:2000]
            if not question:
                raise ValueError("question is required")
            session_id = str(args.get("session_id", "")).strip()[:128]
            plugin_session_id = str(args.get("plugin_session_id", "")).strip()[:128]
            mix_review_id = str(args.get("mix_review_id", "")).strip()[:128]
            request_payload = {"question": question, "session_id": session_id}
            if plugin_session_id:
                request_payload["plugin_session_id"] = plugin_session_id
            if mix_review_id:
                request_payload["mix_review_id"] = mix_review_id
            result = self.client.post("/api/knowledge/ask", request_payload)
            response = {
                "ok": bool(result.get("ok")),
                "question": question,
                "answer": result.get("answer", ""),
                "found": bool(result.get("found")),
                "weak_match": bool(result.get("weak_match")),
                "confidence": result.get("confidence", "low"),
                "sources": result.get("sources", []),
            }
            if result.get("session_evidence"):
                response["session_evidence"] = result["session_evidence"]
            if result.get("plugin_evidence"):
                response["plugin_evidence"] = result["plugin_evidence"]
            if result.get("mix_review_evidence"):
                response["mix_review_evidence"] = result["mix_review_evidence"]
            if result.get("realtime_mix_comparison"):
                response["realtime_mix_comparison"] = result["realtime_mix_comparison"]
            return response
        if name == "audiogen_artifact":
            job_id = str(args.get("job_id", "")).strip()[:128]
            if not job_id:
                raise ValueError("job_id is required")
            response = self.client.get("/api/audiogen/job", {"id": job_id})
            job = response.get("job") if isinstance(response, dict) else None
            if not isinstance(job, dict):
                return {
                    "schema": "kenn.audiogen_artifact_inspection.v1",
                    "job_id": job_id,
                    "status": "unavailable",
                    "artifact": None,
                    "ready_for_review": False,
                    "available_actions": [],
                    "limitations": ["AudioGen job was not available."],
                }
            safe_job = safe_audio_job(job)
            artifact = safe_job.get("artifact") if isinstance(safe_job.get("artifact"), dict) else None
            validation = artifact.get("validation") if isinstance(artifact, dict) else None
            ready = bool(
                str(safe_job.get("status", "")).lower() in {"completed", "success", "complete"}
                and isinstance(validation, dict)
                and validation.get("ok") is True
            )
            limitations: list[str] = []
            if artifact is None:
                limitations.append("The job has no inspectable artifact metadata yet.")
            if not ready:
                limitations.append("Artifact is not ready for audition or Live import.")
            else:
                limitations.append("Use create_midi_clip_from_artifact to create a confirmation-only Live proposal; applying it still requires explicit confirmation and readback.")
            return {
                "schema": "kenn.audiogen_artifact_inspection.v1",
                "job_id": job_id,
                "status": safe_job.get("status", "unknown"),
                "artifact": artifact,
                "ready_for_review": ready,
                "available_actions": [],
                "limitations": limitations,
            }
        if name == "queue_assistant_audiogen_job":
            task_id = str(args.get("task_id", "")).strip()[:128]
            step_id = str(args.get("step_id", "")).strip()[:64]
            session_id = str(args.get("session_id", "")).strip()[:128]
            if not task_id or not step_id or not session_id:
                raise ValueError("task_id, step_id, and session_id are required")
            try:
                bars = int(args.get("bars", 4))
                candidates = int(args.get("candidates", 1))
            except (TypeError, ValueError):
                raise ValueError("bars and candidates must be integers") from None
            if not 1 <= bars <= 24 or not 1 <= candidates <= 4:
                raise ValueError("bars must be 1..24 and candidates must be 1..4")
            result = self.client.post(
                "/api/audiogen/render-song",
                {
                    "emotion": str(args.get("emotion", "")).strip()[:64],
                    "bars": bars,
                    "k": candidates,
                },
            )
            if result.get("changed") is True or result.get("receipt"):
                raise RuntimeError("KENN returned a Live mutation from an offline AudioGen queue call")
            job = result.get("job") if isinstance(result.get("job"), dict) else None
            if job is None:
                return {**result, "assistant_task": {"ok": False, "errors": ["AudioGen did not return a job identity."]}}
            evidence = self._audiogen_job_evidence(job)
            binding = self.coordinator.record_evidence(
                task_id=task_id,
                step_id=step_id,
                evidence=evidence,
                context=self._assistant_context(session_id),
            )
            return {**result, "job_evidence": evidence, "assistant_task": binding}
        if name == "refresh_assistant_audiogen_job":
            task_id = str(args.get("task_id", "")).strip()[:128]
            step_id = str(args.get("step_id", "")).strip()[:64]
            session_id = str(args.get("session_id", "")).strip()[:128]
            job_id = str(args.get("job_id", "")).strip()[:128]
            if not task_id or not step_id or not session_id or not job_id:
                raise ValueError("task_id, step_id, session_id, and job_id are required")
            result = self.client.get("/api/audiogen/job", {"id": job_id})
            job = result.get("job") if isinstance(result.get("job"), dict) else None
            if job is None:
                return {**result, "assistant_task": {"ok": False, "errors": ["AudioGen job was not found."]}}
            evidence = self._audiogen_job_evidence(job)
            context = self._assistant_context(session_id, audiogen_job_id=job_id)
            if evidence["status"] == "failed":
                binding = self.coordinator.record_failure(
                    task_id=task_id, step_id=step_id, evidence=evidence, context=context,
                )
            else:
                binding = self.coordinator.record_evidence(
                    task_id=task_id, step_id=step_id, evidence=evidence, context=context,
                )
            return {**result, "job_evidence": evidence, "assistant_task": binding}
        if name in {"bind_assistant_automix_job", "refresh_assistant_automix_job"}:
            task_id = str(args.get("task_id", "")).strip()[:128]
            step_id = str(args.get("step_id", "")).strip()[:64]
            session_id = str(args.get("session_id", "")).strip()[:128]
            job_id = str(args.get("job_id", "")).strip()[:128]
            if not task_id or not step_id or not session_id or not job_id:
                raise ValueError("task_id, step_id, session_id, and job_id are required")
            result = self.client.get("/api/automix-status", {"id": job_id})
            evidence = self._automix_job_evidence(result, requested_job_id=job_id)
            if evidence["status"] == "unavailable":
                return {
                    **result,
                    "job_evidence": evidence,
                    "assistant_task": {
                        "ok": False,
                        "errors": [evidence.get("error") or "AutoMix job status was not available."],
                    },
                }
            context = self._assistant_context(session_id, automix_job_id=job_id)
            if evidence["status"] == "failed":
                binding = self.coordinator.record_failure(
                    task_id=task_id, step_id=step_id, evidence=evidence, context=context,
                )
            else:
                binding = self.coordinator.record_evidence(
                    task_id=task_id, step_id=step_id, evidence=evidence, context=context,
                )
            return {**result, "job_evidence": evidence, "assistant_task": binding}
        if name == "generate_audiogen_audio_candidate":
            prompt = str(args.get("prompt", "")).strip()[:512]
            if not prompt:
                raise ValueError("prompt is required")
            result = self.client.post(
                "/api/audiogen/generate",
                {
                    "prompt": prompt,
                    "emotion": str(args.get("emotion", ""))[:64],
                    "bars": args.get("bars", 8),
                },
            )
            if result.get("changed") is True or result.get("receipt"):
                raise RuntimeError("KENN returned a Live mutation from an offline AudioGen candidate call")
            src = str(result.get("src", "")).strip()
            listen_url = ""
            if src.startswith("/"):
                listen_url = str(getattr(self.client, "base_url", "")).rstrip("/") + src
            elif src.startswith("http://") or src.startswith("https://"):
                listen_url = src
            return {
                "schema": "kenn.audiogen_audio_candidate.v1",
                "ok": bool(result.get("ok")),
                "emotion": result.get("emotion", ""),
                "bars": result.get("bars", ""),
                "audio_url": listen_url,
                "artifact": result.get("artifact"),
                "portfolio_title": result.get("portfolio_title", ""),
                "audition": {
                    "status": "ready" if listen_url else "unavailable",
                    "audio_url": listen_url,
                    "transport": "local_http",
                    "live_mutation": False,
                },
                "limitations": [] if listen_url else ["AudioGen did not return a listenable local WAV URL."],
                "error": result.get("error", ""),
            }
        if name == "compare_audiogen_audio_candidates":
            source_a = str(args.get("source_a", "")).strip()[:512]
            source_b = str(args.get("source_b", "")).strip()[:512]
            if not source_a or not source_b:
                raise ValueError("source_a and source_b are required")
            result = self.client.post(
                "/api/audiogen/audio-compare",
                {"source_a": source_a, "source_b": source_b},
            )
            if result.get("changed") is True or result.get("receipt"):
                raise RuntimeError("KENN returned a Live mutation from an offline audio comparison call")
            return result
        if name == "create_midi_clip_from_artifact":
            job_id = str(args.get("job_id", "")).strip()[:128]
            session_id = str(args.get("session_id", "")).strip()[:128]
            if not job_id or not session_id:
                raise ValueError("job_id and session_id are required")
            response = self.client.get("/api/audiogen/job", {"id": job_id})
            job = response.get("job") if isinstance(response, dict) else None
            if not isinstance(job, dict):
                return {"ok": False, "error": "AudioGen job was not available.", "job_id": job_id}
            safe_job = safe_audio_job(job)
            if str(safe_job.get("status", "")).lower() not in {"completed", "success", "complete"}:
                return {"ok": False, "error": "AudioGen job is not complete; no Live proposal was created.", "job_id": job_id, "status": safe_job.get("status", "unknown")}
            artifact = safe_job.get("artifact") if isinstance(safe_job.get("artifact"), dict) else None
            imported = midi_import_payload(artifact)
            if not imported.get("ok"):
                return {
                    "ok": False,
                    "error": "AudioGen MIDI artifact is not import-ready; no Live proposal was created.",
                    "job_id": job_id,
                    "artifact": artifact,
                    "validation": imported.get("validation"),
                    "limitations": imported.get("errors", []),
                }
            payload = {
                "session_id": session_id,
                "track_index": args.get("track_index"),
                "track_name": str(args.get("track_name", ""))[:256],
                "clip_slot_index": args.get("clip_slot_index"),
                "length": imported["length"],
                "notes": imported["notes"],
                "source_artifact_sha256": imported["source_artifact_sha256"],
                "source_artifact_id": imported.get("artifact_id", ""),
                "source_context": imported.get("generation_context"),
            }
            result = self.client.post("/api/ableton/midi-clip/proposal", payload)
            if result.get("receipt") or result.get("changed") is True:
                raise RuntimeError("KENN returned a mutation from an artifact proposal-only MCP call")
            return {
                **result,
                "source": {
                    "job_id": job_id,
                    "artifact_id": imported.get("artifact_id", ""),
                    "sha256": imported.get("source_artifact_sha256", ""),
                },
            }
        if name == "generate_audiogen_midi_revision_proposal":
            session_id = str(args.get("session_id", "")).strip()[:128]
            feedback_id = str(args.get("feedback_id", "")).strip()[:128]
            if not session_id or not feedback_id:
                raise ValueError("session_id and feedback_id are required")
            self._assistant_binding_ids(args)
            try:
                seed = int(args["seed"])
            except (KeyError, TypeError, ValueError):
                raise ValueError("seed must be an integer for a revision candidate") from None
            feedback_result = self.client.get(
                "/api/ableton/audition-feedback",
                {"session_id": session_id, "limit": 100},
            )
            items = feedback_result.get("feedback", []) if isinstance(feedback_result, dict) else []
            feedback = next(
                (
                    item for item in items
                    if isinstance(item, dict) and str(item.get("feedback_id", "")) == feedback_id
                ),
                None,
            )
            if feedback is None:
                raise ValueError("feedback_id was not found in the requested session")
            brief = build_audition_revision_brief(feedback, comparison=args.get("comparison"))
            target = brief["target"]
            payload = {
                "session_id": session_id,
                "track_index": target["track_index"],
                "track_name": target["track_name"],
                "clip_slot_index": target["clip_slot_index"],
                "emotion": str(args.get("emotion", "joy"))[:64],
                "bars": args.get("bars", 4),
                "seed": str(seed),
                "revision_brief": brief,
            }
            result = self.client.post("/api/audiogen/midi-proposal", payload)
            if result.get("receipt") or result.get("changed") is True:
                raise RuntimeError("KENN returned a mutation from a revision proposal-only MCP call")
            result = {**result, "revision_brief": brief}
            binding = self._bind_assistant_proposal(args=args, result=result, session_id=session_id)
            if binding is not None:
                result = {**result, "assistant_task": binding}
            return result
        if name == "generate_audiogen_midi_proposal":
            session_id = str(args.get("session_id", "")).strip()[:128]
            track_name = str(args.get("track_name", "")).strip()[:256]
            if not session_id or not track_name:
                raise ValueError("session_id and track_name are required")
            payload = {
                "session_id": session_id,
                "track_index": args.get("track_index"),
                "track_name": track_name,
                "clip_slot_index": args.get("clip_slot_index"),
                "emotion": str(args.get("emotion", "joy"))[:64],
                "bars": args.get("bars", 4),
                "seed": str(args.get("seed", ""))[:128],
            }
            result = self.client.post("/api/audiogen/midi-proposal", payload)
            if result.get("receipt") or result.get("changed") is True:
                raise RuntimeError("KENN returned a mutation from an AudioGen proposal-only MCP call")
            return result
        if name == "mix_review_recommendations":
            review_id = str(args.get("review_id", "")).strip()[:128]
            if not review_id:
                raise ValueError("review_id is required")
            result = self.client.get("/api/mix-review-status", {"id": review_id})
            review = result.get("review") if isinstance(result, dict) else None
            if not isinstance(review, dict):
                return {
                    "ok": False,
                    "review_id": review_id,
                    "recommendations": [],
                    "error": "Mix Review did not return a review record.",
                    "limitations": ["No measured review evidence was available; no Live target may be inferred."],
                }
            from kenn.project_analysis import (
                prioritize_recommendations,
                recommendations_from_mix_review,
                summarize_recommendations,
            )

            genre = str(args.get("genre", "")).strip() or None
            plugin_session_id = str(args.get("plugin_session_id", "")).strip()[:128]
            realtime_context = None
            realtime_error = ""
            realtime_recommendations: list[Any] = []
            if plugin_session_id:
                try:
                    plugin_result = self.client.get(
                        "/api/plugin-live-review", {"session_id": plugin_session_id}
                    )
                except KennTransportError as exc:
                    plugin_result = None
                    realtime_error = f"Realtime plug-in review was unavailable: {exc}"
                if isinstance(plugin_result, dict) and plugin_result.get("ok") is True:
                    candidate_context = plugin_result.get("live_context")
                    if isinstance(candidate_context, dict):
                        realtime_context = candidate_context
                        realtime_recommendations = _realtime_mix_recommendations(candidate_context)
                    else:
                        realtime_error = "No validated realtime plug-in bus context was available for this session."
                elif not realtime_error:
                    realtime_error = "No fresh realtime plug-in review was available for this session."
            recommendation_inputs = recommendations_from_mix_review(review)
            recommendation_inputs.extend(realtime_recommendations)
            ranked = prioritize_recommendations(recommendation_inputs, genre=genre)
            from kenn.core.mixdown_coach import build_mixdown_coach
            mixdown_coach = build_mixdown_coach(review)
            realtime_mix_comparison = None
            if plugin_session_id and isinstance(realtime_context, dict):
                realtime_mix_comparison = build_realtime_mix_comparison(
                    review,
                    realtime_context,
                    review_id=review_id,
                    plugin_session_id=plugin_session_id,
                )
            recommendations = [item.payload() for item in ranked]
            for item in recommendations:
                if item.get("category") == "realtime_mix":
                    item.update({
                        "source_review_id": None,
                        "source_scope": "plugin_bus_realtime",
                        "plugin_session_id": plugin_session_id,
                        "live_target_inference_allowed": False,
                        "live_handoff": "Treat this as a bus-level listening check; KENN will not infer a responsible Live track/device or apply automatic master EQ.",
                    })
                else:
                    item.update({
                        "source_review_id": review_id,
                        "source_scope": "uploaded_or_rendered_audio",
                        "live_target_inference_allowed": False,
                        "live_handoff": "Supply an exact Live track/device/parameter separately; create a normal confirmation-only proposal and verify it by ear.",
                    })
            response = {
                "ok": True,
                "schema": "kenn.mix_review_recommendations.v1",
                "review_id": review_id,
                "status": review.get("status", result.get("status", "unknown")),
                "recommendations": recommendations,
                "summary": summarize_recommendations(ranked),
                "mixdown_coach": mixdown_coach,
                "realtime_mix_comparison": realtime_mix_comparison,
                "limitations": [
                    "Findings describe the uploaded/rendered audio review, not the current Live session.",
                    "The review does not identify a responsible Live track or device; KENN will not infer one.",
                    "Recommendations are advisory until an exact Live target, parameter, and user-confirmed proposal exist.",
                ],
            }
            if plugin_session_id:
                response["realtime_plugin_review"] = realtime_context
                response["realtime_recommendation_available"] = bool(realtime_recommendations)
                response["limitations"].append(
                    "Realtime plug-in evidence is a validated bus observation; it does not identify a Live track/device or authorize a mutation."
                )
                if realtime_error:
                    response["limitations"].append(realtime_error)
            return response
        if name == "launch_clip_proposal":
            session_id = str(args.get("session_id", "")).strip()[:128]
            if not session_id:
                raise ValueError("session_id is required")
            payload = {
                "session_id": session_id,
                "track_index": args.get("track_index"),
                "clip_slot_index": args.get("clip_slot_index"),
                "stop": bool(args.get("stop", False)),
            }
            return self.client.post("/api/ableton/command", {
                "session_id": session_id,
                "command": f"propose clip launch track {payload['track_index']} slot {payload['clip_slot_index']}",
                "proposal_action": "launch_clip",
                "payload": payload,
            })
        if name == "launch_scene_proposal":
            session_id = str(args.get("session_id", "")).strip()[:128]
            if not session_id:
                raise ValueError("session_id is required")
            payload = {
                "session_id": session_id,
                "scene_name": str(args.get("scene_name", "")),
            }
            return self.client.post("/api/ableton/command", {
                "session_id": session_id,
                "command": f"propose create scene {payload['scene_name']}",
                "proposal_action": "create_scene",
                "payload": payload,
            })
        if name == "clip_warp_pitch_proposal":
            session_id = str(args.get("session_id", "")).strip()[:128]
            if not session_id:
                raise ValueError("session_id is required")
            payload = {
                "session_id": session_id,
                "track_index": args.get("track_index"),
                "clip_slot_index": args.get("clip_slot_index"),
                "warp_mode": args.get("warp_mode"),
                "pitch_coarse": args.get("pitch_coarse"),
            }
            return self.client.post("/api/ableton/command", {
                "session_id": session_id,
                "command": f"propose clip warp pitch track {payload['track_index']} slot {payload['clip_slot_index']}",
                "proposal_action": "set_clip_warp_pitch",
                "payload": payload,
            })
        if name == "duplicate_loop_proposal":
            session_id = str(args.get("session_id", "")).strip()[:128]
            if not session_id:
                raise ValueError("session_id is required")
            payload = {
                "session_id": session_id,
                "track_index": args.get("track_index"),
                "clip_slot_index": args.get("clip_slot_index"),
            }
            return self.client.post("/api/ableton/command", {
                "session_id": session_id,
                "command": f"propose duplicate loop track {payload['track_index']} slot {payload['clip_slot_index']}",
                "proposal_action": "duplicate_loop",
                "payload": payload,
            })
        if name == "create_midi_clip_proposal":
            session_id = str(args.get("session_id", "")).strip()[:128]
            if not session_id:
                raise ValueError("session_id is required")
            payload = {
                "session_id": session_id,
                "track_index": args.get("track_index"),
                "track_name": str(args.get("track_name", ""))[:256],
                "clip_slot_index": args.get("clip_slot_index"),
                "length": args.get("length"),
                "notes": args.get("notes"),
                "source_artifact_sha256": str(args.get("source_artifact_sha256", ""))[:128],
                "source_artifact_id": str(args.get("source_artifact_id", ""))[:256],
            }
            result = self.client.post("/api/ableton/midi-clip/proposal", payload)
            if result.get("receipt") or result.get("changed") is True:
                raise RuntimeError("KENN returned a mutation from a MIDI proposal-only MCP call")
            return result
        if name == "update_midi_clip_proposal":
            session_id = str(args.get("session_id", "")).strip()[:128]
            if not session_id:
                raise ValueError("session_id is required")
            result = self.client.post("/api/ableton/midi-clip/update-proposal", {
                "session_id": session_id,
                "track_index": args.get("track_index"),
                "track_name": str(args.get("track_name", ""))[:256],
                "clip_slot_index": args.get("clip_slot_index"),
                "notes": args.get("notes"),
            })
            if result.get("receipt") or result.get("changed") is True:
                raise RuntimeError("KENN returned a mutation from a MIDI clip update proposal-only MCP call")
            return result
        if name == "kenn_session_doctor":
            from kenn.core.session_doctor import SessionDoctor
            from kenn.plugin_handoff import live_context_summary
            session_id = str(args.get("session_id", "doctor_session"))
            session_state = self.client.get("/api/ableton/osc/session", {"detail": "understanding"})
            telemetry = live_context_summary(session_id)
            report = SessionDoctor.audit(session_state if isinstance(session_state, dict) else {}, meters=telemetry)
            remediated = None
            if args.get("auto_remediate") and report.remediation_batch:
                remediated = self.client.post("/api/kenn/autonomous-execute-batch", {
                    "session_id": str(args.get("session_id", "doctor_session")),
                    "batch": report.remediation_batch,
                })
            return {
                "ok": True,
                "track_count": report.track_count,
                "issues_found": report.issues_found,
                "summary": report.summary,
                "issues": [
                    {
                        "code": i.code,
                        "severity": i.severity,
                        "track_index": i.track_index,
                        "track_name": i.track_name,
                        "description": i.description,
                        "suggested_action": i.suggested_action,
                        "proposed_value": i.proposed_value,
                    }
                    for i in report.issues
                ],
                "remediation_batch": report.remediation_batch,
                "remediation_execution": remediated,
            }
        if name == "kenn_generate_midi_pattern":
            from kenn.core.generative_midi import generate_chord_progression, generate_euclidean_rhythm, generate_drum_pattern
            ptype = str(args.get("pattern_type", "chords")).lower()
            if ptype == "chords":
                notes = generate_chord_progression(
                    root=str(args.get("root", "C")),
                    scale_name=str(args.get("scale", "minor")),
                    progression=str(args.get("progression", "pop_i_v_vi_iv")),
                )
            elif ptype == "euclidean":
                notes = generate_euclidean_rhythm(
                    hits=int(args.get("hits", 5)),
                    steps=int(args.get("steps", 8)),
                    pitch=int(args.get("pitch", 36)),
                )
            elif ptype == "drums":
                notes = generate_drum_pattern(
                    genre=str(args.get("genre", "trap")),
                    bars=int(args.get("bars", 2)),
                )
            else:
                raise ValueError(f"Unknown pattern_type: {ptype}")
            return {"ok": True, "pattern_type": ptype, "note_count": len(notes), "notes": notes}
        if name == "kenn_search_knowledge":
            from kenn.core.chat_retrieval import search, load_chunks, load_terms
            query = str(args.get("query", ""))
            limit = int(args.get("limit", 3))
            chunks = load_chunks()
            terms = load_terms()
            raw_results = search(query, chunks, terms, limit=limit)
            return {
                "ok": True,
                "query": query,
                "results": [
                    {
                        "score": round(score, 2),
                        "source": r.get("source"),
                        "title": r.get("title"),
                        "kind": r.get("kind"),
                        "text_snippet": (r.get("text") or "")[:300],
                    }
                    for score, r in raw_results
                ],
            }
        if name == "kenn_context":
            session_id = str(args.get("session_id", "")).strip()[:128]
            # Context is an explicit intelligence read, not a liveness probe:
            # request the richer, still read-only snapshot so tempo, meter,
            # key/scale, mixer observations, routing, sends, clip inventory,
            # and selected-object state are available to the LLM.  The fast
            # control/proposal path continues to use topology-only reads.
            snapshot = self.client.get("/api/ableton/osc/session", {"detail": "understanding"})
            plugin_session_id = str(args.get("plugin_session_id", "")).strip()[:128]
            plugin_frames: list[dict[str, Any]] = []
            if plugin_session_id:
                plugin_result = self.client.get(
                    "/api/plugin-live-review", {"session_id": plugin_session_id}
                )
                plugin_context = plugin_result.get("live_context") if isinstance(plugin_result, dict) else None
                if isinstance(plugin_result, dict) and plugin_result.get("ok") is True and isinstance(plugin_context, dict):
                    plugin_frames.append(plugin_context)
            include_device_matrix = args.get("include_device_matrix", True)
            include_device_parameters = args.get("include_device_parameters", False)
            if not isinstance(include_device_matrix, bool) or not isinstance(include_device_parameters, bool):
                raise ValueError("include_device_matrix and include_device_parameters must be boolean")
            device_matrix = None
            if include_device_matrix:
                device_matrix = self.client.get(
                    "/api/ableton/device-matrix",
                    {"parameters": "1" if include_device_parameters else "0"},
                )
            audiogen_jobs: list[dict[str, Any]] = []
            try:
                audiogen_status = self.client.get("/api/audiogen/status")
                queue = audiogen_status.get("render_queue") if isinstance(audiogen_status, dict) else {}
                if isinstance(queue, dict):
                    for group in ("running", "queued", "recent"):
                        items = queue.get(group) if isinstance(queue.get(group), list) else []
                        audiogen_jobs.extend(item for item in items if isinstance(item, dict))
            except KennTransportError:
                # Context is still useful when an optional creative service is
                # unavailable; the limitation is made explicit below.
                audiogen_status = None
            audiogen_job_id = str(args.get("audiogen_job_id", "")).strip()[:128]
            if audiogen_job_id:
                exact_job_result = self.client.get("/api/audiogen/job", {"id": audiogen_job_id})
                exact_job = exact_job_result.get("job") if isinstance(exact_job_result, dict) else None
                if isinstance(exact_job, dict):
                    exact_identity = str(exact_job.get("job_id") or exact_job.get("id") or "")
                    existing_identities = {
                        str(item.get("job_id") or item.get("id") or "")
                        for item in audiogen_jobs
                    }
                    if exact_identity not in existing_identities:
                        audiogen_jobs.append(exact_job)

            mix_reviews: list[dict[str, Any]] = []
            mix_review_id = str(args.get("mix_review_id", "")).strip()[:128]
            if mix_review_id:
                mix_result = self.client.get("/api/mix-review-status", {"id": mix_review_id})
                if isinstance(mix_result, dict):
                    review = mix_result.get("review")
                    mix_reviews.append(review if isinstance(review, dict) else mix_result)

            automix_receipts: list[dict[str, Any]] = []
            automix_job_id = str(args.get("automix_job_id", "")).strip()[:128]
            if automix_job_id:
                automix_result = self.client.get("/api/automix-status", {"id": automix_job_id})
                if isinstance(automix_result, dict):
                    automix_receipt = self._automix_job_evidence(
                        automix_result, requested_job_id=automix_job_id,
                    )
                    if automix_receipt.get("status") != "unavailable":
                        automix_receipts.append(automix_receipt)

            feedback_items: list[dict[str, Any]] = []
            if session_id:
                try:
                    feedback_result = self.client.get(
                        "/api/ableton/audition-feedback",
                        {"session_id": session_id, "limit": 16},
                    )
                    if isinstance(feedback_result, dict):
                        items = feedback_result.get("feedback")
                        if isinstance(items, list):
                            feedback_items = [item for item in items if isinstance(item, dict)]
                except KennTransportError:
                    feedback_result = None

            profile_memory = self.profile_store.context_memory(session_id) if session_id else {
                "producer_preferences": [], "episodic_outcomes": [],
            }

            context = build_session_context(
                snapshot=snapshot,
                session_id=session_id,
                plugin_frames=plugin_frames,
                mix_review_receipts=mix_reviews,
                audiogen_jobs=audiogen_jobs,
                automix_receipts=automix_receipts,
                audition_feedback=feedback_items,
                device_matrix=device_matrix,
                audiogen_available=isinstance(audiogen_status, dict) and audiogen_status.get("ok") is True,
                producer_preferences=profile_memory["producer_preferences"],
                episodic_outcomes=profile_memory["episodic_outcomes"],
            )
            if mix_review_id and plugin_session_id and mix_reviews and plugin_frames:
                # Keep the comparison in the canonical context as a typed
                # measurement. This lets planners and later intelligence
                # layers consume the same scope-aware evidence without
                # re-querying either source or reconstructing it from prose.
                realtime_mix_comparison = build_realtime_mix_comparison(
                    mix_reviews[0],
                    plugin_frames[0],
                    review_id=mix_review_id,
                    plugin_session_id=plugin_session_id,
                )
                context["realtime_mix_comparison"] = realtime_mix_comparison
                context["measurements"].append({
                    "kind": "realtime_mix_comparison",
                    **realtime_mix_comparison,
                })
                context["sources"].append({
                    "kind": "realtime_mix_comparison",
                    "status": "observed" if realtime_mix_comparison.get("comparison_available") else "unavailable",
                    "observed_at": time.time(),
                    "schema": realtime_mix_comparison.get("schema", ""),
                })
            if plugin_frames:
                context["limitations"].append(
                    "Realtime plug-in evidence is a validated bus observation; it does not identify a Live track or device and does not authorize a mutation."
                )
            elif plugin_session_id:
                context["limitations"].append(
                    "No fresh realtime plug-in review was available for the supplied plugin_session_id."
                )
            else:
                context["limitations"].append(
                    "No realtime plug-in session was supplied; this context does not invent meter data."
                )
            if not audiogen_jobs and not isinstance(audiogen_status, dict):
                context["limitations"].append("AudioGen status was unavailable for this context read.")
            if session_id and feedback_result is None:
                context["limitations"].append("Audition feedback was unavailable for this context read.")
            if not mix_review_id:
                context["limitations"].append("No Mix Review id was supplied; uploaded review receipts were not queried.")
            if not automix_job_id:
                context["limitations"].append("No AutoMix job id was supplied; offline render receipts were not queried.")
            refresh_session_context_fingerprint(context)
            return context
        if name == "kenn_context_delta":
            session_id = str(args.get("session_id", "")).strip()[:128]
            if not session_id:
                raise ValueError("session_id is required")
            context_args = {
                key: args[key]
                for key in (
                    "session_id", "plugin_session_id", "mix_review_id", "automix_job_id", "audiogen_job_id",
                    "include_device_matrix", "include_device_parameters",
                )
                if key in args
            }
            context = self._dispatch("kenn_context", context_args)
            model = self._world_models.get(session_id)
            if model is None:
                if len(self._world_models) >= self._max_world_models:
                    self._world_models.pop(next(iter(self._world_models)))
                model = SessionWorldModel(session_id=session_id)
                self._world_models[session_id] = model
            observed = model.observe_context(context)
            return {
                "schema": "kenn.session_world_delta.v1",
                "session_id": session_id,
                "delta": observed["delta"],
                "snapshot_fingerprint": context.get("snapshot_fingerprint", ""),
                "read_only": True,
                "advisory_only": True,
                "live_mutation_authorized": False,
            }
        if name == "producer_profile":
            session_id = str(args.get("session_id", "")).strip()[:128]
            return {
                "ok": True,
                "schema": "kenn.producer_profile.v1",
                "session_id": session_id,
                "scope": "session_scoped",
                "memory": self.profile_store.context_memory(session_id),
                "advisory_only": True,
                "live_mutation_authorized": False,
            }
        if name == "record_producer_preference":
            return self.profile_store.record_preference(
                session_id=str(args.get("session_id", "")),
                key=str(args.get("key", "")),
                value=str(args.get("value", "")),
                source_turn_id=str(args.get("source_turn_id", "")),
                user_statement=str(args.get("user_statement", "")),
            )
        if name == "forget_producer_preference":
            return {
                "ok": self.profile_store.forget_preference(
                    session_id=str(args.get("session_id", "")), key=str(args.get("key", "")),
                ),
                "schema": "kenn.producer_profile.v1",
                "advisory_only": True,
                "live_mutation_authorized": False,
            }
        if name == "clear_producer_profile":
            return {
                "ok": True,
                "schema": "kenn.producer_profile.v1",
                "cleared": self.profile_store.clear_profile(str(args.get("session_id", ""))),
                "advisory_only": True,
                "live_mutation_authorized": False,
            }
        if name == "record_supervised_session_outcome":
            outcome = args.get("outcome")
            if not isinstance(outcome, dict):
                raise ValueError("outcome must be a privacy-safe session outcome object")
            result = self.session_outcome_store.record(outcome)
            result.setdefault("schema", SESSION_OUTCOME_SCHEMA)
            result["advisory_only"] = True
            result["live_mutation_authorized"] = False
            return result
        if name == "supervised_session_outcome_summary":
            try:
                limit = int(args.get("limit", 100))
            except (TypeError, ValueError):
                raise ValueError("limit must be an integer")
            if not 1 <= limit <= 100:
                raise ValueError("limit must be between 1 and 100")
            return self.session_outcome_store.summary(limit)
        if name == "kenn_session_intelligence":
            # Reuse the established one-owner context read. The resulting
            # intelligence brief is advisory and cannot be sent to any Live
            # action endpoint.
            context_args = {
                key: args[key]
                for key in (
                    "session_id", "plugin_session_id", "mix_review_id", "automix_job_id", "audiogen_job_id",
                    "include_device_matrix", "include_device_parameters",
                )
                if key in args
            }
            context = self._dispatch("kenn_context", context_args)
            # Retrieval provenance must come from KENN's own cache, never an
            # MCP caller. The cache is scoped by session id and this helper
            # emits source identifiers/classes only, not chunks or queries.
            retrieval_sources = []
            session_id = str(args.get("session_id", "")).strip()[:128]
            if session_id:
                try:
                    from kenn.core.session_memory import load_session
                    retrieval_sources = retrieval_sources_from_cache(
                        load_session(session_id=session_id).get("last_retrieved_results")
                    )
                except Exception:
                    # Optional previous-turn provenance cannot make the fresh
                    # Live briefing unsafe or unavailable.
                    retrieval_sources = []
            brief = build_session_intelligence(
                context,
                project_intent={
                    "genre": args.get("genre", ""),
                    "goal": args.get("goal", ""),
                    "references": args.get("references", []),
                },
                retrieval_sources=retrieval_sources,
            )
            brief["explanation_sections"] = explanation_sections(brief)
            return brief
        if name == "start_production_diagnosis":
            goal = str(args.get("goal", "")).strip()[:1_024]
            session_id = str(args.get("session_id", "")).strip()[:128]
            if not goal or not session_id:
                raise ValueError("goal and session_id are required")
            context = self._dispatch(
                "kenn_context",
                {
                    "session_id": session_id,
                    "include_device_matrix": True,
                    "include_device_parameters": False,
                },
            )
            started = start_diagnostic_loop(goal=goal, context=context)
            if not started.get("ok"):
                return started
            persisted = self.diagnostic_store.start(started["loop"])
            if not persisted.get("ok"):
                return {**persisted, "execution_authorized": False}
            planned = next_diagnostic_plan(started["loop"], context)
            if not planned.get("ok"):
                return planned
            return {
                "ok": True,
                "schema": "kenn.production_diagnosis.v1",
                "loop": started["loop"],
                "next_plan": planned["plan"],
                "execution_authorized": False,
            }
        if name == "record_diagnostic_test_result":
            supplied_loop = args.get("loop")
            result = args.get("result")
            if supplied_loop is not None and not isinstance(supplied_loop, dict):
                raise ValueError("loop must be an object when supplied")
            if not isinstance(result, dict):
                raise ValueError("result must be an object")
            loop_id = str(args.get("loop_id") or (supplied_loop or {}).get("loop_id") or "").strip()[:128]
            if not loop_id:
                raise ValueError("loop_id or a loop containing loop_id is required")
            loop = self.diagnostic_store.load(loop_id)
            if loop is None:
                return {
                    "ok": False,
                    "errors": ["Diagnostic loop was not found in KENN's authoritative ledger."],
                    "execution_authorized": False,
                }
            if supplied_loop is not None and supplied_loop != loop:
                return {
                    "ok": False,
                    "status": "diagnostic_state_mismatch",
                    "errors": ["Caller-supplied diagnostic state differs from KENN's authoritative loop."],
                    "loop": loop,
                    "execution_authorized": False,
                }
            if result.get("source") != "user_observation":
                return {
                    "ok": False,
                    "errors": ["MCP diagnostic continuation accepts only an explicit user_observation; measurements and receipts must be resolved by KENN."],
                    "execution_authorized": False,
                }
            session_id = str(loop.get("session_id", "")).strip()[:128]
            if not session_id:
                return {"ok": False, "errors": ["Diagnostic loop requires a session_id."]}
            context = self._dispatch(
                "kenn_context",
                {
                    "session_id": session_id,
                    "include_device_matrix": True,
                    "include_device_parameters": False,
                },
            )
            freshness = next_diagnostic_plan(loop, context)
            if not freshness.get("ok"):
                return {
                    "ok": False,
                    "schema": "kenn.production_diagnosis.v1",
                    "loop": loop,
                    "continuation_ready": False,
                    "requires_restart": True,
                    "errors": freshness.get("errors", []),
                    "execution_authorized": False,
                }
            recorded = record_diagnostic_result(loop, result)
            if not recorded.get("ok"):
                return recorded
            updated_loop = recorded["loop"]
            stored = self.diagnostic_store.update(expected=loop, updated=updated_loop)
            if not stored.get("ok"):
                return {**stored, "execution_authorized": False}
            planned = next_diagnostic_plan(updated_loop, context)
            if not planned.get("ok"):
                return {
                    "ok": True,
                    "schema": "kenn.production_diagnosis.v1",
                    "loop": updated_loop,
                    "continuation_ready": False,
                    "requires_restart": True,
                    "errors": planned.get("errors", []),
                    "execution_authorized": False,
                }
            return {
                "ok": True,
                "schema": "kenn.production_diagnosis.v1",
                "loop": updated_loop,
                "continuation_ready": True,
                "requires_restart": False,
                "next_plan": planned["plan"],
                "execution_authorized": False,
            }
        if name == "plan_assistant_goal":
            goal = str(args.get("goal", "")).strip()[:1_024]
            session_id = str(args.get("session_id", "")).strip()[:128]
            if not goal or not session_id:
                raise ValueError("goal and session_id are required")
            if diagnostic_plan_for(goal) is not None:
                result = self._dispatch(
                    "start_production_diagnosis",
                    {"goal": goal, "session_id": session_id},
                )
                return {
                    **result,
                    "schema": "kenn.planned_assistant_goal.v1",
                    "workflow": "diagnostic",
                    "execution_authorized": False,
                }
            result = self._dispatch(
                "plan_assistant_task",
                {"goal": goal, "session_id": session_id},
            )
            return {
                **result,
                "schema": "kenn.planned_assistant_goal.v1",
                "workflow": "deliberative_task",
                "execution_authorized": False,
            }
        if name == "plan_assistant_task":
            goal = str(args.get("goal", "")).strip()[:1_024]
            session_id = str(args.get("session_id", "")).strip()[:128]
            if not goal or not session_id:
                raise ValueError("goal and session_id are required")
            context = self._assistant_context(session_id)
            planning_started = time.perf_counter()
            if self.planner is None:
                preflight = deliberative_preflight_plan(goal, context)
                if preflight is None:
                    return {
                        "ok": False,
                        "status": "planner_unavailable",
                        "errors": ["No local deliberative planner is configured for this MCP process."],
                        "planning_latency_ms": round((time.perf_counter() - planning_started) * 1_000, 3),
                        "execution_authorized": False,
                    }
                shadow = {
                    "accepted": True,
                    "planner_source": "deterministic_preflight",
                    "plan": preflight,
                }
            else:
                shadow = run_shadow_sketch(
                    goal=goal,
                    context=context,
                    generator=self.planner,
                    model_provider=self.planner_provider,
                    model_id=self.planner_id,
                )
            if not shadow.get("accepted") or not isinstance(shadow.get("plan"), dict):
                return {
                    "ok": False,
                    "status": "planning_rejected",
                    "errors": shadow.get("errors", ["The deliberative plan was rejected."]),
                    "planning_latency_ms": round((time.perf_counter() - planning_started) * 1_000, 3),
                    "execution_authorized": False,
                }
            started = self.coordinator.start(plan=shadow["plan"], context=context)
            return {
                **started,
                "schema": "kenn.planned_assistant_task.v1",
                "planner_source": shadow.get("planner_source", "unknown"),
                "planning_latency_ms": round((time.perf_counter() - planning_started) * 1_000, 3),
                "execution_authorized": False,
            }
        if name == "start_assistant_task":
            plan = args.get("plan")
            session_id = str(args.get("session_id", "")).strip()[:128]
            if not isinstance(plan, dict) or not session_id:
                raise ValueError("plan and session_id are required")
            return self.coordinator.start(plan=plan, context=self._assistant_context(session_id))
        if name == "resume_assistant_task":
            task_id = str(args.get("task_id", "")).strip()[:128]
            session_id = str(args.get("session_id", "")).strip()[:128]
            if not task_id or not session_id:
                raise ValueError("task_id and session_id are required")
            return self.coordinator.resume(task_id=task_id, context=self._assistant_context(session_id))
        if name == "replan_assistant_task":
            task_id = str(args.get("task_id", "")).strip()[:128]
            session_id = str(args.get("session_id", "")).strip()[:128]
            follow_up = str(args.get("follow_up", "")).strip()[:1_000]
            if not task_id or not session_id:
                raise ValueError("task_id and session_id are required")
            source = self.coordinator.store.load(task_id)
            if source is None:
                return {"ok": False, "errors": ["Assistant task was not found."], "execution_authorized": False}
            if str(source.get("session_id") or "") != session_id:
                return {"ok": False, "errors": ["Assistant task belongs to another session."], "execution_authorized": False}
            if source.get("status") in {"waiting_for_job", "waiting_for_confirmation"}:
                return {
                    "ok": False,
                    "errors": ["A task waiting for an identity-bound job or confirmation must be resolved before replanning."],
                    "execution_authorized": False,
                }
            ended_with_clarification = bool(
                source.get("status") == "completed"
                and source.get("plan", {}).get("steps")
                and source["plan"]["steps"][-1].get("kind") == "clarification"
            )
            if (source.get("status") == "waiting_for_user" or ended_with_clarification) and not follow_up:
                return {
                    "ok": False,
                    "errors": ["The producer's follow-up is required to continue a clarification task."],
                    "execution_authorized": False,
                }
            original_goal = str(source.get("goal") or source.get("plan", {}).get("goal") or "").strip()[:1_024]
            planning_goal = original_goal
            if follow_up:
                planning_goal = (original_goal + "\nProducer follow-up: " + follow_up)[:1_024]
            context = self._assistant_context(session_id)
            planning_started = time.perf_counter()
            if self.planner is None:
                preflight = deliberative_preflight_plan(planning_goal, context)
                if preflight is None:
                    return {
                        "ok": False,
                        "status": "planner_unavailable",
                        "errors": ["No local deliberative planner is configured for this MCP process."],
                        "planning_latency_ms": round((time.perf_counter() - planning_started) * 1_000, 3),
                        "execution_authorized": False,
                    }
                shadow = {"accepted": True, "planner_source": "deterministic_preflight", "plan": preflight}
            else:
                shadow = run_shadow_sketch(
                    goal=planning_goal,
                    context=context,
                    generator=self.planner,
                    model_provider=self.planner_provider,
                    model_id=self.planner_id,
                )
            if not shadow.get("accepted") or not isinstance(shadow.get("plan"), dict):
                return {
                    "ok": False,
                    "status": "planning_rejected",
                    "errors": shadow.get("errors", ["The replacement plan was rejected."]),
                    "planning_latency_ms": round((time.perf_counter() - planning_started) * 1_000, 3),
                    "execution_authorized": False,
                }
            replaced = self.coordinator.store.replace_for_replan(
                source_task_id=task_id,
                plan=shadow["plan"],
                context=context,
                reason=("Producer clarification supplied." if follow_up else "Fresh session context required replanning."),
            )
            if not replaced.get("ok"):
                return {**replaced, "execution_authorized": False}
            replacement = replaced["task"]
            return {
                "ok": True,
                "schema": "kenn.replanned_assistant_task.v1",
                "planner_source": shadow.get("planner_source", "unknown"),
                "planning_latency_ms": round((time.perf_counter() - planning_started) * 1_000, 3),
                "source_task_id": task_id,
                "task": replacement,
                "next_step": self.coordinator.next_step(task=replacement, context=context),
                "execution_authorized": False,
            }
        if name == "record_assistant_observation":
            task_id = str(args.get("task_id", "")).strip()[:128]
            step_id = str(args.get("step_id", "")).strip()[:64]
            session_id = str(args.get("session_id", "")).strip()[:128]
            if not task_id or not step_id or not session_id:
                raise ValueError("task_id, step_id, and session_id are required")
            context = self._assistant_context(session_id)
            return self.coordinator.record_evidence(
                task_id=task_id, step_id=step_id, evidence=context, context=context,
            )
        if name == "record_assistant_user_response":
            task_id = str(args.get("task_id", "")).strip()[:128]
            step_id = str(args.get("step_id", "")).strip()[:64]
            session_id = str(args.get("session_id", "")).strip()[:128]
            response = str(args.get("response", "")).strip()[:1_000]
            if not task_id or not step_id or not session_id or not response:
                raise ValueError("task_id, step_id, session_id, and response are required")
            return self.coordinator.record_evidence(
                task_id=task_id,
                step_id=step_id,
                evidence={"schema": "kenn.user_response.v1", "response": response},
                context=self._assistant_context(session_id),
            )
        if name == "record_assistant_live_receipt":
            task_id = str(args.get("task_id", "")).strip()[:128]
            step_id = str(args.get("step_id", "")).strip()[:64]
            session_id = str(args.get("session_id", "")).strip()[:128]
            receipt_id = str(args.get("receipt_id", "")).strip()[:128]
            if not task_id or not step_id or not session_id or not receipt_id:
                raise ValueError("task_id, step_id, session_id, and receipt_id are required")
            journal = self.client.get(
                "/api/ableton/receipts", {"session_id": session_id, "limit": 200},
            )
            rows = journal.get("receipts") if isinstance(journal.get("receipts"), list) else []
            row = next((
                item for item in rows
                if isinstance(item, dict)
                and item.get("session_id") == session_id
                and isinstance(item.get("receipt"), dict)
                and item["receipt"].get("receipt_id") == receipt_id
            ), None)
            if row is None:
                return {"ok": False, "errors": ["Receipt was not found in this session's KENN journal."]}
            return self.coordinator.record_evidence(
                task_id=task_id,
                step_id=step_id,
                evidence=row["receipt"],
                context=self._assistant_context(session_id),
            )
        raise ValueError(f"Unknown KENN MCP tool: {name}")

    def _assistant_context(
        self, session_id: str, *, audiogen_job_id: str = "", automix_job_id: str = "",
    ) -> dict[str, Any]:
        return self._dispatch(
            "kenn_context",
            {
                "session_id": str(session_id)[:128],
                "audiogen_job_id": str(audiogen_job_id)[:128],
                "automix_job_id": str(automix_job_id)[:128],
                "include_device_matrix": True,
                "include_device_parameters": False,
            },
        )

    @staticmethod
    def _assistant_binding_ids(args: dict[str, Any]) -> tuple[str, str]:
        task_id = str(args.get("assistant_task_id", "")).strip()[:128]
        step_id = str(args.get("assistant_step_id", "")).strip()[:64]
        if bool(task_id) != bool(step_id):
            raise ValueError("assistant_task_id and assistant_step_id must be supplied together")
        return task_id, step_id

    def _bind_assistant_proposal(
        self, *, args: dict[str, Any], result: dict[str, Any], session_id: str,
    ) -> dict[str, Any] | None:
        task_id, step_id = self._assistant_binding_ids(args)
        if not task_id:
            return None
        proposal = result.get("proposal") if isinstance(result.get("proposal"), dict) else None
        if proposal is None:
            return {"ok": False, "errors": ["Proposal response did not include a typed proposal."]}
        evidence = {
            **proposal,
            "status": "confirmation_required",
            "requires_confirmation": True,
        }
        try:
            return self.coordinator.record_evidence(
                task_id=task_id,
                step_id=step_id,
                evidence=evidence,
                context=self._assistant_context(session_id),
            )
        except Exception as exc:
            # Proposal creation is non-mutating and remains useful even if the
            # optional task ledger cannot be updated in this call.
            return {
                "ok": False,
                "error_kind": "assistant_sync_failed",
                "errors": [f"{type(exc).__name__}: {exc}"],
                "retry_allowed": True,
            }

    @staticmethod
    def _audiogen_job_evidence(job: dict[str, Any]) -> dict[str, Any]:
        safe = safe_audio_job(job)
        job_id = str(safe.get("job_id") or safe.get("id") or "").strip()[:128]
        raw_status = str(safe.get("status") or "").strip().lower()
        status = {
            "complete": "completed",
            "completed": "completed",
            "success": "completed",
            "succeeded": "completed",
            "pending": "pending",
            "queued": "queued",
            "running": "running",
            "failed": "failed",
            "error": "failed",
        }.get(raw_status, "unknown")
        return {
            **safe,
            "schema": "kenn.audiogen_render_job.v1",
            "job_id": job_id,
            "status": status,
        }

    @staticmethod
    def _automix_job_evidence(
        result: dict[str, Any], *, requested_job_id: str,
    ) -> dict[str, Any]:
        """Normalize the public AutoMix status response into task evidence.

        The status endpoint is deliberately read-only and omits filesystem
        paths and style blobs.  Requiring its returned identity to match the
        requested id prevents a stale or mismatched response from being
        attached to an assistant task.
        """
        if not isinstance(result, dict) or result.get("ok") is not True:
            return {
                "schema": "kenn.automix.local_receipt.v1",
                "status": "unavailable",
                "job_id": str(requested_job_id)[:128],
                "error": str((result or {}).get("error") or "AutoMix status was unavailable.")[:512]
                if isinstance(result, dict) else "AutoMix status was unavailable.",
            }
        returned_id = str(result.get("id") or result.get("job_id") or "").strip()[:128]
        if not returned_id or returned_id != str(requested_job_id)[:128]:
            return {
                "schema": "kenn.automix.local_receipt.v1",
                "status": "unavailable",
                "job_id": str(requested_job_id)[:128],
                "error": "AutoMix status did not return the requested job identity.",
            }
        raw_status = str(result.get("status") or "").strip().lower()
        status = {
            "complete": "completed",
            "completed": "completed",
            "success": "completed",
            "succeeded": "completed",
            "pending": "pending",
            "queued": "queued",
            "running": "running",
            "failed": "failed",
            "error": "failed",
        }.get(raw_status, "unknown")
        evidence: dict[str, Any] = {
            "schema": "kenn.automix.local_receipt.v1",
            "job_id": returned_id,
            "project_id": str(result.get("project_id") or "")[:128],
            "engine": "automix",
            "status": status,
        }
        if isinstance(result.get("progress"), (int, float)) and not isinstance(result.get("progress"), bool):
            progress = float(result["progress"])
            if math.isfinite(progress):
                evidence["progress"] = max(0.0, min(100.0, progress))
        genre = str(result.get("genre") or "").strip()[:96]
        if genre:
            evidence["source"] = {"genre": genre}
        if status == "failed":
            evidence["error"] = str(result.get("error") or "AutoMix reported a failed job.")[:512]
        elif status == "unknown":
            evidence["status"] = "unavailable"
            evidence["error"] = "AutoMix returned an unsupported job status."
        return evidence

    @staticmethod
    def _index(args: dict[str, Any], name: str) -> int:
        try:
            value = int(args[name])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"{name} must be a non-negative integer") from None
        if value < 0:
            raise ValueError(f"{name} must be a non-negative integer")
        return value

    @staticmethod
    def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


__all__ = ["KennHTTPClient", "KennMCPFacade", "KennTransportError", "MCP_PROTOCOL_VERSION", "TOOLS", "open_loopback_companion", "validate_companion_base_url"]
