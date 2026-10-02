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

``_dispatch`` only routes. The tool bodies live in ``kenn.core.mcp``, one module
per verb family, behind the ``HANDLERS`` table there.
"""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

from kenn.core.assistant_coordinator import AssistantCoordinator
from kenn.core.assistant_profile_memory import AssistantProfileStore, PREFERENCE_KEYS
from kenn.core.assistant_task_memory import AssistantTaskStore
from kenn.core.diagnostic_loop_store import DiagnosticLoopStore
from kenn.core.mcp import HANDLERS
from kenn.core.mcp.errors import KennTransportError
from kenn.core.session_context import safe_audio_job
from kenn.core.session_outcome_store import SessionOutcomeStore
from kenn.core.session_world_model import SessionWorldModel

# Re-exported unchanged: server.py and orchestrator.py have imported these
# realtime helpers from here since before the dispatch table existed, and
# test_mcp_facade.py imports _realtime_mix_recommendation directly.
from kenn.core.mcp.realtime import (
    _realtime_context_is_current,
    _realtime_mix_recommendation,
    _realtime_mix_recommendations,
)


MCP_PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "kenn-live"
SERVER_VERSION = "0.1.0"


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
        "description": "Ask KENN to create a confirmation-only Live proposal, including bounded track and return-track creation, track controls, audio/MIDI-track creation, device work, qualified Dry/Wet setup, clip/scene actions, and evidence-backed parameter changes. It never applies the proposal.",
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
        """Route one MCP intent to its handler.

        The table used to be a 1900-line if/elif chain here.  Every condition in
        it was an exact name equality, so no two intents could match at once and
        a dict lookup is the same routing -- including the refusal for a name the
        companion never advertised.
        """
        handler = HANDLERS.get(name)
        if handler is None:
            raise ValueError(f"Unknown KENN MCP tool: {name}")
        return handler(self, args)

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
