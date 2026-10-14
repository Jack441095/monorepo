#!/usr/bin/env python3
"""Local web chat server for KENN."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import secrets
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
# This file is launched directly from kenn/, while its modules are imported
# through the ``kenn`` package. Add the package parent before those imports.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from kenn.paths import FRONTEND_ROOT, LEGACY_WEB_ROOT, PRODUCT_ROOT, RUNTIME_ROOT, TOOLING_ROOT

# Compatibility name retained for modules that receive ``repo_root``. It now
# means the stable product workspace root, not an inferred package parent.
REPO_ROOT = PRODUCT_ROOT

# Load .env from the product root so action-policy flags are available
# regardless of how the server is launched.
_env_file = REPO_ROOT / ".env"
if _env_file.is_file():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#"):
            continue
        _key, _, _val = _line.partition("=")
        if _key and _ and _key not in os.environ:
            os.environ[_key.strip()] = _val.strip()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(TOOLING_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(TOOLING_ROOT / "scripts"))

from kenn.core.chat import answer_payload, answer_payload_stream, warm_index
from kenn.core.session_memory import list_db_sessions, load_session, session_info as kenn_session_info, clear_session, get_cross_session_trends, save_mix_version, list_mix_versions, save_session_feedback, save_audition_feedback, list_audition_feedback, remember_automix_project, get_remembered_automix_project, get_pending_automix_jobs, clear_pending_automix_job
from kenn.core.suggestions import catalog_payload, typeahead
from kenn.core.lm_identity import APP_NAME
from kenn.core.response_contract import augment_payload
from kenn.plugin_handoff import (
    get_plugin_parameters,
    ingest_live_context,
    ingest_live_context_batch,
    live_context_summary,
    live_review_summary,
    plugin_insert_sources,
    queue_owned_plugin_parameters,
    pop_pending_parameter_updates,
    set_plugin_parameter,
    set_plugin_parameters,
)
from kenn.core.evidence import (
    from_ableton_session,
    from_mix_review_context,
    from_realtime_mix_comparison,
    from_plugin_context,
    from_stem_masking_context,
    from_audio_classification_context,
    history_turn as evidence_history_turn,
)
from kenn.core.endpoint_policy import endpoint_policy
from kenn.core.live_action_service import LiveActionService
from kenn.core.live_command import handle_command
from kenn.core.request_classifier import classify_non_request, non_request_reply
from kenn.core.live_session_questions import answer_live_session_question
from kenn.core.live_receipt_journal import list_receipts, record_receipt
from kenn.core.audiogen_artifacts import safe_artifact_metadata
from kenn.core.audiogen_midi import artifact_from_event_payload
from kenn.core.audiogen_context import build_live_generation_context
from kenn.core.midi_clip_service import (
    CREATE_PROPOSAL_SCHEMA,
    MidiClipActionService,
    REMOVE_PROPOSAL_SCHEMA,
    RECEIPT_SCHEMA as MIDI_CLIP_RECEIPT_SCHEMA,
    UPDATE_PROPOSAL_SCHEMA,
)
from kenn.core.clip_duplication_service import (
    ClipDuplicationActionService,
    PROPOSAL_SCHEMA as CLIP_DUPLICATION_PROPOSAL_SCHEMA,
    RECEIPT_SCHEMA as CLIP_DUPLICATION_RECEIPT_SCHEMA,
    UNDO_PROPOSAL_SCHEMA as CLIP_DUPLICATION_UNDO_PROPOSAL_SCHEMA,
)
from kenn.core.clip_rename_service import (
    ClipRenameActionService,
    PROPOSAL_SCHEMA as CLIP_RENAME_PROPOSAL_SCHEMA,
    RECEIPT_SCHEMA as CLIP_RENAME_RECEIPT_SCHEMA,
    UNDO_PROPOSAL_SCHEMA as CLIP_RENAME_UNDO_PROPOSAL_SCHEMA,
)
from kenn.core.clip_audition_service import (
    ClipAuditionActionService,
    PROPOSAL_SCHEMA as CLIP_AUDITION_PROPOSAL_SCHEMA,
    RECEIPT_SCHEMA as CLIP_AUDITION_RECEIPT_SCHEMA,
    clip_fingerprint,
)
from kenn.core.sample_import_service import (
    IMPORT_PROPOSAL_SCHEMA as SAMPLE_IMPORT_PROPOSAL_SCHEMA,
    RECEIPT_SCHEMA as SAMPLE_IMPORT_RECEIPT_SCHEMA,
    REMOVE_PROPOSAL_SCHEMA as SAMPLE_IMPORT_REMOVE_PROPOSAL_SCHEMA,
    SampleImportService,
)
from kenn.core.audition_feedback import build_audition_feedback
from kenn.core.audition_revision import validate_revision_brief
from kenn.core import timing_stats
from kenn.core.support_diagnostics import build_support_diagnostics, save_support_diagnostics
from kenn.core.companion_instance import CompanionAlreadyRunning, CompanionInstanceLock

try:
    # KENN's local bridge is the production integration point. Keep the
    # historical agents import as a compatibility fallback for older repo
    # layouts, but do not let its absence make the status endpoint claim that
    # Ableton support is unavailable when the live command gateway is healthy.
    from kenn.ableton_osc_bridge import AbletonOSCClient
except ImportError:
    try:
        from agents.MixReview.ableton_live_api import AbletonOSCClient
    except ImportError:
        AbletonOSCClient = None

WEBSITE_ROOT = PRODUCT_ROOT / "packages" / "website"
ANALYSIS_TOOL_ROOT = PRODUCT_ROOT / "packages" / "audio-analysis"
_built_frontend = FRONTEND_ROOT / "dist"
STATIC_ROOT = Path(os.environ.get(
    "KENN_STATIC_ROOT",
    str(_built_frontend if _built_frontend.exists() else LEGACY_WEB_ROOT),
)).expanduser().resolve()
PORTFOLIO_AUDIO_ROOT = RUNTIME_ROOT / "portfolio" / "audio"
PORTFOLIO_AUDIO_ROOTS: list[Path] = [PORTFOLIO_AUDIO_ROOT]
HOST = os.getenv("KENN_HOST", "127.0.0.1").strip() or "127.0.0.1"
PORT = int(os.getenv("KENN_PORT", "8090"))
# Imperative-word routing lives in kenn.core.live_imperative so server.py stays
# a thin dispatcher; the names below are compat aliases for callers that
# reached into server (see tests/test_safety_typos.py).
from kenn.core.live_imperative import (
    COMMON_SHORT_WORDS as _COMMON_SHORT_WORDS,
    LIVE_IMPERATIVE_RE as _LIVE_IMPERATIVE_RE,
    LIVE_IMPERATIVE_VERBS as _LIVE_IMPERATIVE_VERBS,
    is_live_imperative as _is_live_imperative,
)


# Turn and confirmation state lives in kenn.core.live_turn so server.py stays
# a thin dispatcher; the names below are compat aliases for callers that
# reached into server (see tests/test_confirmation_cancellation_routes.py,
# tests/test_server_smoke.py).
from kenn.core.live_turn import (
    SAYS_YES as _SAYS_YES,
    continues_live_turn as _continues_live_turn,
    proposal_waiting as _proposal_waiting,
)


def _fetch_return_tracks():
    from kenn.ableton_osc_bridge import live_client

    return live_client.get_return_tracks()


def _chat_wants_live(question: str) -> bool:
    """The rule parser, on the last cached look at the set, reads a Live change in a chat message."""
    from kenn.core.chat_live_router import wants_live_change
    from kenn.core.return_tracks_cache import attach_return_tracks
    from kenn.mixing_doctor import get_latest_session_state

    from kenn.core.chat_live_router import needs_return_tracks

    snapshot = get_latest_session_state()
    if isinstance(snapshot, dict) and needs_return_tracks(question, snapshot):
        # The cached snapshot never lists returns, and a message about one (a send, or its level) needs them. Kept for
        # a few seconds: this runs for every chat message. The global stays
        # here (not in the helper) so tests can still seed/clear it via
        # monkeypatch on server._RETURNS_CACHE.
        global _RETURNS_CACHE
        snapshot, _RETURNS_CACHE = attach_return_tracks(
            snapshot, _RETURNS_CACHE, now=time.monotonic(), fetch=_fetch_return_tracks
        )
    return wants_live_change(question, snapshot)


_RETURNS_CACHE: tuple[float, list] | None = None


# Health reporting lives in kenn.core.live_health so server.py stays a thin
# dispatcher; the name below is a compat alias for the /api/health handler.
from kenn.core.live_health import cached_ableton_health as _cached_ableton_health


_PENDING_PROPOSALS: dict[str, dict] = {}


def _live_session_track_evidence(question: str, session_id: str) -> list[dict] | None:
    """Real, bounded track/device evidence for one question, if the question
    names an instrument role and a live Ableton snapshot is available.

    Returns ``None`` (never an empty-but-attempted list) whenever nothing
    can be honestly claimed: no session_id, no Live connection, or the
    question doesn't name exactly one role. This never fabricates audio
    characteristics -- only the real track name/index/device list already
    visible in a fresh snapshot.
    """
    if not session_id:
        return None
    try:
        from kenn.ableton_osc_bridge import live_client
        from kenn.mixing_doctor import get_latest_session_state
        from kenn.core.track_classifier import find_tracks_by_question_role

        state = live_client.query_session_state()
        state = get_latest_session_state()
        if not state or not isinstance(state, dict):
            from kenn.ableton_osc_bridge import live_client
        state = None
        try:
            state = live_client.query_session_state()
        except Exception:
            pass
        if not isinstance(state, dict) or state.get("status") in {"offline", "dispatched"}:
            cached = get_latest_session_state()
            if isinstance(cached, dict) and cached.get("status") == "connected":
                state = cached
    except Exception:
        return None
    if not isinstance(state, dict) or state.get("status") != "connected":
        return None
    tracks = [t for t in (state.get("tracks") or []) if isinstance(t, dict)]
    matches = find_tracks_by_question_role(question, tracks)
    return matches or None


def grounded_knowledge_answer(
    question: str,
    session_id: str = "",
    plugin_session_id: str = "",
    mix_review_id: str = "",
    *,
    correlation_id: str = "",
) -> dict:
    """Answer one audio-engineering question with retrieval only: no LLM,
    no Ableton/Mix Review/AudioGen specialist dispatch, no Live mutation.
    Used by the read-only MCP tool and can be reused anywhere else that
    needs a bounded, abstention-safe knowledge answer.

    When ``session_id`` is supplied and the question names one instrument
    role (e.g. "why is my vocal getting masked"), a real, bounded track/
    device evidence section is appended -- ties the answer to what's
    actually in the live session instead of only general knowledge. When
    ``plugin_session_id`` is supplied, the latest already-captured,
    read-only plug-in bus evidence is added as a typed context turn so the
    answer can explain measured peak/spectral observations. When
    ``mix_review_id`` is supplied, the bounded stored Mix Review metrics are
    added in the same typed form; when both ids are present, a scope-labelled
    realtime-versus-uploaded comparison is returned too. These are purely
    additive: missing or unmatched identifiers provide no extra evidence.
    The named project's preferences can inform the answer, but the request
    cannot record a chat turn or change another request's routing policy.
    """
    import kenn.core.chat_answer as chat_answer_module

    plugin_evidence = None
    mix_review_evidence = None
    mix_review_record = None
    plugin_context = None
    realtime_mix_comparison = None
    history: list[dict] = []
    if plugin_session_id:
        plugin_context = live_context_summary(plugin_session_id)
        plugin_packet = from_plugin_context(plugin_context)
        if plugin_packet:
            history.append(evidence_history_turn(plugin_packet))
            # Keep the same typed projection available to callers;
            # they should not have to scrape measurements from prose.
            # The packet contains bounded features only, never audio.
            plugin_evidence = plugin_packet.payload()
    if mix_review_id and mix_review and hasattr(mix_review, "mix_review_status"):
        try:
            review_result = mix_review.mix_review_status(mix_review_id)
            candidate = review_result.get("review") if isinstance(review_result, dict) else None
            if isinstance(candidate, dict):
                mix_review_record = candidate
                # Convert the local registry record to the existing typed
                # upload-evidence envelope. Only measured numeric fields
                # and bounded reference deltas are allowed into history.
                mix_handoff = {
                    "schema": "kenn_mix_review_handoff.v1",
                    "metrics": candidate.get("metrics", {}),
                    "reference_comparison": candidate.get("reference_comparison"),
                }
                mix_packet = from_mix_review_context(mix_handoff)
                if mix_packet:
                    history.append(evidence_history_turn(mix_packet))
                    mix_review_evidence = {
                        **mix_packet.payload(),
                        "review_id": mix_review_id,
                        "status": candidate.get("status", review_result.get("status", "unknown")),
                    }
        except Exception:
            # An optional review record must not make a general
            # knowledge answer unavailable. The caller simply receives
            # no review evidence and can retry through the specialist
            # Mix Review path if needed.
            mix_review_record = None
    if mix_review_record is not None and isinstance(plugin_context, dict):
        from kenn.core.realtime_mix_comparison import build_realtime_mix_comparison

        realtime_mix_comparison = build_realtime_mix_comparison(
            mix_review_record,
            plugin_context,
            review_id=mix_review_id,
            plugin_session_id=plugin_session_id,
        )
        comparison_packet = from_realtime_mix_comparison(realtime_mix_comparison)
        if comparison_packet:
            history.append(evidence_history_turn(comparison_packet))
    payload = chat_answer_module.answer_payload(
        question, limit=4, history=history, session_id=session_id,
        plugin_session_id=plugin_session_id, correlation_id=correlation_id,
        retrieval_only=True,
    )

    evidence = _live_session_track_evidence(question, session_id)
    if evidence:
        lines = "\n".join(
            f"- Track {item['track_index']} \"{item['track_name']}\" ({item['display_name']}): "
            + (", ".join(item["devices"]) if item["devices"] else "no devices")
            for item in evidence
        )
        payload["answer"] = (
            f"{payload.get('answer', '')}\n\n"
            f"Live session evidence (observed just now, not inferred):\n{lines}"
        )
        payload["session_evidence"] = evidence
    if plugin_evidence is not None:
        payload["plugin_evidence"] = plugin_evidence
    if mix_review_record is not None:
        payload["mix_review_evidence"] = mix_review_evidence
        if isinstance(plugin_context, dict):
            from kenn.core.realtime_mix_comparison import build_realtime_mix_comparison

            realtime_mix_comparison = build_realtime_mix_comparison(
                mix_review_record,
                plugin_context,
                review_id=mix_review_id,
                plugin_session_id=plugin_session_id,
            )
    if realtime_mix_comparison is not None:
        payload["realtime_mix_comparison"] = realtime_mix_comparison
    return payload


# HTTP plumbing lives in kenn.core.server_http_helpers so server.py and the
# route modules share one copy; the name below is a compat alias for callers
# that reached into server (see routes/audio_handler.py).
from kenn.core.server_http_helpers import multipart_files as _multipart_files

from kenn.server_rate_limit import (
    client_key,
    rate_allowed,
)
from kenn.server_payloads import (
    safe_error_payload,
    mix_review_context_turn,
    session_context_turn,
    public_audiogen_result,
    public_audiogen_job,
    public_audiogen_status,
    public_audiogen_history,
)

if str(ANALYSIS_TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_TOOL_ROOT))
if str(WEBSITE_ROOT) not in sys.path:
    sys.path.insert(0, str(WEBSITE_ROOT))
# automix_jobs.py does `from app.api_schemas import ...`, which needs the
# PARENT of business/app/ on sys.path (so `app` resolves as a package) --
# WEBSITE_ROOT above only adds business/app/ itself, one level too deep.
# Without this, automix_public/automix_jobs silently fail to import (caught
# by the bare `except ImportError` below) and AutoMix returns 503 on every
# upload when KENN is launched standalone. Found live in a real browser
# 2026-08-05 -- see docs/KENN_HUB_UNIFICATION_PLAN_2026-08-05.md.
if str(WEBSITE_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(WEBSITE_ROOT.parent))

try:
    import demo_feedback
except ImportError:  # pragma: no cover - standalone fallback for unusual copies
    demo_feedback = None

from kenn.core import request_validation
from kenn.core.action_policy import action_allowed, action_denied_message

try:
    from audio_analysis.mix_review import mix_review
except ImportError:  # pragma: no cover - standalone fallback for unusual copies
    try:
        from kenn.core.local_mix_review_service import local_mix_review as mix_review
    except Exception:  # pragma: no cover - preserve a clean unavailable state
        mix_review = None

def _load_optional_audiogen_bridge():
    """Load the adjacent AudioGen bridge only when its root is configured.

    KENN remains portable and starts without AudioGen.  A local installation
    can opt in with ``KENN_AUDIOGEN_ROOT`` pointing at the Audio_Too root; the
    three import roots below match that repository's app and studio layout.
    No producer path is returned by public KENN payloads.
    """
    configured_root = str(os.getenv("KENN_AUDIOGEN_ROOT", "")).strip()
    if configured_root:
        root = Path(configured_root).expanduser()
        for candidate in (root, root / "business" / "app", root / "studio" / "audiogen"):
            if candidate.exists() and str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
    try:
        import importlib
        return importlib.import_module("audiogen_bridge")
    except Exception:  # pragma: no cover - optional subsystem/dependencies
        return None


audiogen_bridge = _load_optional_audiogen_bridge()
if audiogen_bridge is not None:
    # AudioGen is an optional adjacent repository.  Its public portfolio URL
    # is intentionally the same local `/portfolio/audio/<name>` namespace,
    # but its files live outside KENN's repo root.  Keep the URL opaque while
    # allowing the local companion to serve only the bridge's configured
    # portfolio directory.
    configured_audio_root = getattr(audiogen_bridge, "PORTFOLIO_AUDIO", None)
    if configured_audio_root:
        configured_audio_root = Path(configured_audio_root).expanduser().resolve()
        if configured_audio_root not in PORTFOLIO_AUDIO_ROOTS:
            PORTFOLIO_AUDIO_ROOTS.append(configured_audio_root)

try:
    import automix_public
    import automix_jobs
except ImportError:  # pragma: no cover - optional subsystem
    automix_public = None
    automix_jobs = None

try:
    import song_projects
except ImportError:  # pragma: no cover - optional subsystem
    song_projects = None


# Song-lifecycle resolution lives in kenn.core.song_lifecycle so server.py and
# the route modules share one copy; aliases kept for routes/audio_handler.py
# and routes/upload_handler.py, which reached into server.
from kenn.core.song_lifecycle import (
    read_match_evidence as _read_match_evidence,
    resolve_session_project,
)


# See kenn.core.server_http_helpers for why the prefix is stripped once here.
from kenn.core.server_http_helpers import strip_kenn_prefix as _strip_kenn_prefix


from kenn.core.chat_context import (
    plugin_live_context_turn as _plugin_live_context_turn,
    stem_masking_context_turn as _stem_masking_context_turn,
    attach_stem_masking_evidence as _attach_stem_masking_evidence,
    audio_classification_context_turn as _audio_classification_context_turn,
    attach_audio_classification_evidence as _attach_audio_classification_evidence,
    stored_mix_review_evidence as _stored_mix_review_evidence,
    attach_explicit_audio_evidence as _attach_explicit_audio_evidence,
    ableton_session_context_turn as _ableton_session_context_turn,
    attach_your_set,
)


# Tool-answer wording lives in kenn.core.server_http_helpers so the trigger and
# the attachment handler stay identical; alias kept for routes/upload_handler.py.
from kenn.core.server_http_helpers import build_tool_answer as _build_tool_answer


try:
    import stem_separation_bridge
except ImportError:  # pragma: no cover - optional subsystem (needs the isolated Demucs venv)
    stem_separation_bridge = None

try:
    from kenn.core.tool_registry_defaults import register_defaults as _register_tool_defaults
    _register_tool_defaults()
except ImportError:  # pragma: no cover - optional subsystem
    pass

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        status = str(args[1]) if len(args) > 1 and str(args[1]).isdigit() else ""
        self.structured_log("http_request", status=status)

    def request_id(self) -> str:
        request_id = getattr(self, "_request_id", "")
        if not request_id:
            request_id = secrets.token_hex(6)
            self._request_id = request_id
        return request_id

    def structured_log(self, event: str, **fields: object) -> None:
        record = {
            "timestamp": int(time.time()),
            "event": event,
            "request_id": self.request_id(),
            "method": getattr(self, "command", ""),
            "path": urlparse(getattr(self, "path", "")).path,
            "client": getattr(self, "client_address", ("unknown", 0))[0],
            **fields,
        }
        print(json.dumps(record, ensure_ascii=True), file=sys.stderr, flush=True)

    def allowed_cors_origin(self) -> str:
        origin = self.headers.get("Origin", "").rstrip("/")
        configured = os.getenv("KENN_ALLOWED_ORIGINS", "")
        allowed = {
            "http://127.0.0.1:8080",
            "http://localhost:8080",
            "http://127.0.0.1:8090",
            "http://localhost:8090",
        }
        allowed.update(item.strip().rstrip("/") for item in configured.split(",") if item.strip())
        return origin if origin in allowed else ""

    def send_cors_headers(self) -> None:
        origin = self.allowed_cors_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-CSRF-Token, Authorization")
            self.send_header("Access-Control-Allow-Credentials", "true")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; object-src 'none'; base-uri 'self'; "
            "frame-ancestors 'self' http://127.0.0.1:8080 http://localhost:8080; "
            "script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; media-src 'self' blob:",
        )
        super().end_headers()

    def send_json(self, status: int, payload: dict) -> None:
        started = getattr(self, "_ask_started", None)
        if started is not None:
            self._ask_started = None  # keep-alive reuses this handler for the next request
            try:
                from kenn.core import route_log

                route_log.record(str(payload.get("route") or payload.get("answer_mode") or f"status_{status}"),
                                 (time.perf_counter() - started) * 1000, brain=bool(payload.get("llm_enhanced")),
                                 proposal=bool(payload.get("proposal")))
            except Exception:
                pass  # timing is diagnostic; it must never cost the reply
            turn = getattr(self, "_ask_turn", None)
            self._ask_turn = None
            if turn and status == 200:
                # What the tester typed when KENN had to ask (kept on this Mac; see core/asked_log.py).
                try:
                    from kenn.core import asked_log

                    asked_log.record(turn[0], turn[1], {"status": asked_log.reply_status(payload),
                                                        "answer": payload.get("answer")})
                except Exception:
                    pass
        error_id = self.request_id()
        if status >= 500:
            # The reply stays generic; the local log keeps what went wrong, or a 500 can't be traced afterwards.
            self.structured_log("server_error", status=status, error=str(payload.get("error") or "")[:500])
        payload = safe_error_payload(status, payload, error_id)
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_cors_headers()
        self.end_headers()
        self._write_body(body)

    def _write_body(self, body: bytes, *, flush: bool = False) -> bool:
        """Write a response body without turning a client disconnect into a server error."""
        try:
            self.wfile.write(body)
            if flush:
                self.wfile.flush()
            return True
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            self.close_connection = True
            return False

    def handle_safe_live_action(self, action: str, payload: dict) -> None:
        """Handle the only supported HTTP Live mutation path."""
        from kenn.routes.daw_command_handler import handle_safe_live_action
        handle_safe_live_action(self, action, payload)

    def handle_live_command(self, payload: dict) -> None:
        """Plan or execute a user-facing, LLM-compatible Live command."""
        from kenn.routes.daw_command_handler import handle_live_command
        handle_live_command(self, mix_review, _PENDING_PROPOSALS, payload)

    def _maybe_handle_live_inspection(self, question: str, session_id: str) -> dict | None:
        """Answer narrow, read-only Live inventory questions through the
        snapshot-bound command gateway.

        Generic KENN chat remains retrieval-first.  Inventory questions are
        different: a knowledge note cannot truthfully answer what is on the
        user's current track.  Only phrases that clearly ask for tracks or
        devices are routed here, and the command gateway can only inspect or
        clarify on this path; it cannot create or execute a mutation.
        """
        from kenn.core.chat_live_router import asks_how_to

        if asks_how_to(question):
            return None  # "can I fit my samples to the track's tempo?" wants the notes, not "the tempo is 120 BPM"
        session_result = answer_live_session_question(question, session_id=session_id)
        if session_result is not None:
            structured_intent = session_result.get("intent")
            if isinstance(structured_intent, dict):
                session_result["live_intent"] = structured_intent
                session_result["intent"] = str(structured_intent.get("action") or "inspect")
            session_result.update({
                "route": "ableton_live_inspection",
                "found": session_result.get("status") == "inspected",
                "answer_mode": "live_inspection",
                "sources": [],
            })
            return session_result

        lower = str(question or "").strip().lower()
        inspection_cue = (
            "track" in lower
            and any(word in lower for word in ("device", "what is on", "what's on", "whats on"))
        ) or any(cue in lower for cue in ("list my tracks", "what tracks", "show my tracks", "show the tracks"))
        # "What devices are on the Drum Bus?" never says "track", and went to the manual's Drum Buss note on
        # 26 Sept 2026. Without "track" it could also be advice ("which plugins are good for vocals?"), so Live
        # only answers when it found the track the question names.
        device_cue = bool(re.search(r"\b(?:what|which|list|show)\b.*\b(?:devices|plugins?|plug-ins?|processors)\b", lower))
        if not inspection_cue and not device_cue:
            return None
        result = handle_command(question, session_id=session_id)
        action = (result.get("intent") or {}).get("action")
        if not inspection_cue and result.get("status") != "inspected":
            return None
        if action not in {"inspect_tracks", "inspect_devices"} and result.get("status") not in {"offline"}:
            return None
        structured_intent = result.get("intent")
        if isinstance(structured_intent, dict):
            result["live_intent"] = structured_intent
            result["intent"] = str(structured_intent.get("action") or "inspect")
        result.update({
            "route": "ableton_live_inspection",
            "found": result.get("status") == "inspected",
            "answer_mode": "live_inspection",
            "sources": [],
        })
        return result

    def _maybe_handle_midi_generation(self, question: str, session_id: str) -> dict | None:
        """Turn "write a 4-bar chord progression in D minor" into a confirmable MIDI clip."""
        from kenn.core.live_action_service import LiveActionService
        from kenn.core.midi_generation_chat import generation_kind, propose_generated_clip

        if generation_kind(question) is None:
            return None
        if not session_id:
            # Unnamed callers used to share the owner "chat" and could dismiss or apply each other's clips.
            return {
                "ok": False, "status": "invalid", "answer": "A KENN session ID is required to prepare a clip.",
                "proposal": None, "confirmation_token": "", "requires_confirmation": False,
                "route": "ableton_controller", "answer_mode": "live_command", "found": True, "sources": [],
            }
        result = propose_generated_clip(question, session_id=session_id, service=LiveActionService())
        if result is None:
            return None
        proposal = result.get("proposal") if isinstance(result.get("proposal"), dict) else None
        token = str((proposal or {}).get("confirmation_token") or "")
        return {
            "ok": True,
            **result,
            "proposal": proposal,
            "confirmation_token": token,
            "requires_confirmation": proposal is not None,
            "route": "ableton_controller",
            "answer_mode": "live_command",
            "found": True,
            "sources": [],
        }

    def _maybe_handle_live_command_from_chat(self, question: str, session_id: str) -> dict | None:
        """Give imperative Live requests the command gateway's exact answer.

        Only a proposal, a refusal, or an undo outcome is taken over; any other
        gateway result falls through so ordinary production questions keep
        reaching the knowledge chat.
        """
        if _SAYS_YES.match(question) and _proposal_waiting(session_id):
            # "yes" / "apply it" after a proposal got "I need more direction": KENN changes Live only from the card.
            return {"ok": True, "answer": "Press Apply on the card to make that change. KENN only changes Live from the "
                                          "card, so nothing has changed yet.",
                    "status": "confirmation_pending", "route": "ableton_controller", "answer_mode": "live_command",
                    "found": True, "confidence": "high", "source_quality": "high", "sources": []}
        imperative = _is_live_imperative(question)
        continuing = _continues_live_turn(question, session_id)
        parsed_live = _chat_wants_live(question)
        if not (imperative or continuing or parsed_live):
            return None
        result = handle_command(question, session_id=session_id)
        intents = [result.get(key) for key in ("intent", "live_intent") if isinstance(result.get(key), dict)]
        proposal = result.get("proposal") if isinstance(result.get("proposal"), dict) else None
        token = str((proposal or {}).get("confirmation_token") or result.get("confirmation_token") or "").strip()
        is_proposal = result.get("status") == "confirmation_required" and proposal is not None and bool(token)
        is_refusal = result.get("status") == "refused"
        is_undo = any(intent.get("action") == "undo" for intent in intents)
        # When the message is about Live (mid-change, or the parser read a Live change in it), KENN's own question is
        # the answer ("that would take the vocal above 0 dB", "'Synth' is already centred"); a notes page isn't.
        from kenn.core.chat_live_router import LIVE_WITHOUT_ACTION

        is_live_question = ((continuing or parsed_live) and result.get("status") == "clarification_required"
                            and any(intent.get("action") not in {None, "", "action"}
                                    or set(intent.get("missing_fields") or []) & LIVE_WITHOUT_ACTION for intent in intents))
        if not (is_proposal or is_refusal or is_undo or is_live_question):
            return None
        if is_proposal:
            _PENDING_PROPOSALS[token] = proposal
        return {
            "ok": True,
            "answer": result.get("answer") or "",
            "requires_confirmation": is_proposal,
            "confirmation_token": token if is_proposal else "",
            "proposal": proposal if is_proposal else None,
            "status": result.get("status"),
            "route": "ableton_controller",
            "orchestration": {"agent": "ableton_controller", "result": result},
            "answer_mode": "live_command",
            "undo_of_receipt_id": str(result.get("undo_of_receipt_id") or ""),
            "found": True,
            "confidence": "high",
            "source_quality": "high",
            "sources": [],
        }

    def send_bytes(self, status: int, body: bytes, content_type: str, *, filename: str = "") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_cors_headers()
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self._write_body(body)

    def enforce_rate_limit(self, scope: str) -> bool:
        allowed, retry_after = rate_allowed(client_key(self), scope)
        if allowed:
            return True
        payload = {
            "error": "Too many requests. Please wait before trying again.",
            "retry_after_seconds": retry_after,
        }
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(429)
        self.send_header("Content-Type", "application/json")
        # Content-Length is essential: without it, HTTP/1.1 keep-alive clients
        # cannot determine the response boundary on 429 and reset the socket.
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Retry-After", str(retry_after))
        self.send_cors_headers()
        self.end_headers()
        self._write_body(body, flush=True)
        return False

    def do_OPTIONS(self) -> None:
        if self.headers.get("Origin") and not self.allowed_cors_origin():
            self.send_json(403, {"error": "Cross-origin request rejected."})
            return
        self.send_response(204)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        parsed = _strip_kenn_prefix(urlparse(self.path))
        if self.headers.get("Origin") and not self.allowed_cors_origin():
            self.send_json(403, {"error": "Cross-origin request rejected."})
            return
        if endpoint_policy("kenn", "GET", parsed.path).mutates:
            if not self.enforce_rate_limit("mutation"):
                return
        if parsed.path == "/api/health":
            # Deterministic subsystem rollup (2026-09-07 beta-sprint P0
            # reliability fix): additive only -- the base ok/app/specialty
            # contract is unchanged.  Ableton health uses the background
            # auditor's cache rather than a synchronous OSC probe, so this
            # endpoint remains fast while Live is offline or an OSC exchange
            # is already in progress.
            subsystems: dict[str, Any] = {"abletonosc": _cached_ableton_health()}
            try:
                from kenn.retrieval.retrieval import retrieval_status

                subsystems["knowledge_index"] = retrieval_status()
            except Exception as exc:
                subsystems["knowledge_index"] = {"available": False, "error": str(exc)}
            try:
                from kenn.llm.llm_rewrite import answering_model

                subsystems["answer_model"] = answering_model()
            except Exception as exc:
                subsystems["answer_model"] = {"available": False, "error": str(exc)}
            try:
                from kenn.core.live_action_service import runtime_state_counts
                from kenn.core.live_control_planner import pending_proposal_count

                runtime_state = runtime_state_counts()
                runtime_state["pending_proposals"] += pending_proposal_count()
                if mix_review and hasattr(mix_review, "runtime_state_counts"):
                    runtime_state.update(mix_review.runtime_state_counts())
                subsystems["runtime_state"] = runtime_state
            except Exception:
                # Health must stay available even if optional state diagnostics fail.
                subsystems["runtime_state"] = {"available": False}
            self.send_json(200, {"ok": True, "app": APP_NAME, "specialty": "Ableton Live", "subsystems": subsystems})
        if parsed.path == "/api/audio/telemetry":
            from kenn.audio_telemetry import get_telemetry_manager
            latest = get_telemetry_manager().get_latest()
            anomalies = get_telemetry_manager().diagnose_anomalies(latest) if latest else []
            self.send_json(200, {
                "ok": True,
                "telemetry": latest.to_dict() if latest else None,
                "anomalies": anomalies,
            })
            return
        if parsed.path == "/api/mix/plan":
            query = parse_qs(parsed.query).get("query", ["Optimize mix"])[0]
            from kenn.agent.mix_planner import get_mix_planner
            plan = get_mix_planner().create_plan(query)
            self.send_json(200, {
                "ok": True,
                "plan": plan.to_dict(),
            })
            return
        if parsed.path == "/api/guardian/status":
            from kenn.core.ambient_guardian import get_ambient_guardian
            guardian = get_ambient_guardian()
            try:
                from kenn.mixing_doctor import get_latest_session_state
                state = get_latest_session_state()
                if isinstance(state, dict) and state.get("tracks"):
                    guardian.evaluate_session(state)
            except Exception:
                pass
            self.send_json(200, {"ok": True, "guardian": guardian.get_status()})
            return
        if parsed.path in {"/api/genre_curves", "/kenn/api/genre_curves"}:
            from kenn.routes.session_intelligence_handler import handle_get_genre_curves
            handle_get_genre_curves(self)
            return
        if parsed.path in {"/api/racks", "/kenn/api/racks"}:
            from kenn.routes.racks_handler import handle_get_racks
            handle_get_racks(self)
            return
        if parsed.path in {"/api/session/world_model", "/kenn/api/session/world_model"}:
            from kenn.routes.session_intelligence_handler import handle_get_world_model
            handle_get_world_model(self)
            return
        if parsed.path in {"/api/session/doctor/audit", "/kenn/api/session/doctor/audit"}:
            from kenn.routes.doctor_handler import handle_get_doctor_audit
            handle_get_doctor_audit(self)
            return
        if parsed.path in {"/api/slo/classifications", "/kenn/api/slo/classifications"}:
            from kenn.core.slo_classification_adapter import (
                SloClassificationUnavailable,
                list_classifications,
            )

            query = parse_qs(parsed.query)
            try:
                limit = int(query.get("limit", ["100"])[0])
            except (TypeError, ValueError):
                self.send_json(400, {"schema": "kenn.slo-classifications/v1", "status": "error", "error": "limit must be an integer."})
                return
            review_value = query.get("needs_review", [""])[0].strip().lower()
            needs_review = None if not review_value else review_value in {"1", "true", "yes"}
            try:
                payload = list_classifications(
                    query=query.get("q", [""])[0].strip(),
                    category=query.get("category", [""])[0].strip(),
                    needs_review=needs_review,
                    limit=limit,
                )
                self.send_json(200, payload)
            except (SloClassificationUnavailable, ValueError) as exc:
                self.send_json(503, {"schema": "kenn.slo-classifications/v1", "status": "unavailable", "items": [], "error": str(exc)})
            return
        if parsed.path.startswith("/api/slo/classifications/"):
            from kenn.core.slo_classification_adapter import (
                SloClassificationUnavailable,
                get_classification,
            )

            sample_id = parsed.path.rsplit("/", 1)[-1]
            try:
                payload = get_classification(sample_id)
                if payload is None:
                    self.send_json(404, {"schema": "kenn.slo-classifications/v1", "status": "error", "error": "Classification not found."})
                else:
                    self.send_json(200, payload)
            except SloClassificationUnavailable as exc:
                self.send_json(503, {"schema": "kenn.slo-classifications/v1", "status": "unavailable", "error": str(exc)})
            return
        if parsed.path in {"/api/mix-doctor/scorecard", "/kenn/api/mix-doctor/scorecard"}:
            from kenn.core.mix_doctor import get_mix_doctor
            report = get_mix_doctor().get_latest_report()
            if report is None:
                from kenn.mixing_doctor import get_latest_session_state
                from kenn.audio_telemetry import get_telemetry_manager
                snap = get_latest_session_state()
                meters = get_telemetry_manager().get_latest()
                m_dict = meters.to_dict() if meters else None
                report = get_mix_doctor().audit_session(snap, meters=m_dict)
            from kenn.audio_telemetry import get_telemetry_manager
            from kenn.core.grade import grade_session
            latest_meters = get_telemetry_manager().get_latest()
            scorecard = report.to_dict()
            scorecard["grade"] = grade_session(scorecard, latest_meters.to_dict() if latest_meters else None)
            self.send_json(200, {"ok": True, "scorecard": scorecard})
            return
        if parsed.path == "/api/guardian/events":
            from kenn.core.ambient_guardian import get_ambient_guardian
            guardian = get_ambient_guardian()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache, no-transform")
            self.send_header("X-Accel-Buffering", "no")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                # Send initial snapshot event
                initial_status = guardian.get_status()
                self._write_body(
                    f"event: status\ndata: {json.dumps(initial_status)}\n\n".encode("utf-8"),
                    flush=True,
                )
            except Exception:
                return
            return
        if parsed.path == "/api/session-outcomes/summary":
            query = parse_qs(parsed.query)
            try:
                limit = int(query.get("limit", ["100"])[0])
            except (TypeError, ValueError):
                self.send_json(400, {"ok": False, "error": "limit must be an integer."})
                return
            if not 1 <= limit <= 100:
                self.send_json(400, {"ok": False, "error": "limit must be between 1 and 100."})
                return
            try:
                from kenn.core.session_outcome_store import SessionOutcomeStore

                self.send_json(200, SessionOutcomeStore().summary(limit))
            except Exception as exc:
                self.send_json(503, {
                    "ok": False,
                    "error": str(exc),
                    "schema": "kenn.session_outcome_summary.v1",
                    "advisory_only": True,
                    "live_mutation_authorized": False,
                })
            return
        if parsed.path == "/api/plugin/inserts":
            query = parse_qs(parsed.query)
            result = plugin_insert_sources(str(query.get("conversation_id", [""])[0]),
                                           str(query.get("plugin_session_id", [""])[0]))
            self.send_json(200 if result.get("ok") else 400, result)
            return
        if parsed.path == "/api/plugin-live-review":
            query = parse_qs(parsed.query)
            session_id = str(query.get("session_id", [""])[0]).strip()
            if not session_id:
                self.send_json(400, {"ok": False, "error": "Missing session_id query param."})
                return
            result = live_review_summary(session_id)
            self.send_json(200 if result.get("ok") else 404, result)
            return
        if parsed.path == "/api/plugin/parameters":
            query = parse_qs(parsed.query)
            session_id = str(query.get("session_id", [""])[0]).strip()
            pop_pending = str(query.get("pop_pending", ["0"])[0]).strip().lower() in ("1", "true", "yes")
            if pop_pending:
                result = pop_pending_parameter_updates(session_id)
            else:
                result = get_plugin_parameters(session_id)
            self.send_json(200 if result.get("ok") else 400, result)
            return
        if parsed.path == "/api/realtime-mix-recommendations":
            query = parse_qs(parsed.query)
            session_id = str(query.get("session_id", [""])[0]).strip()[:128]
            if not session_id:
                self.send_json(400, {"ok": False, "error": "Missing session_id query param."})
                return
            result = live_review_summary(session_id)
            context = result.get("live_context") if isinstance(result, dict) else None
            from kenn.core.mcp_facade import _realtime_context_is_current, _realtime_mix_recommendations

            recommendations = (
                _realtime_mix_recommendations(context)
                if isinstance(context, dict)
                else []
            )
            limitations = [
                "Realtime findings are validated plug-in bus observations, not track-level diagnoses.",
                "No responsible Live track/device is inferred and no automatic master EQ or other mutation is authorized.",
            ]
            if isinstance(context, dict) and not _realtime_context_is_current(context):
                limitations.append("The retained plug-in context is stale_or_unknown for current diagnosis; recommendations are withheld.")
            if result.get("ok") is not True:
                self.send_json(404, {
                    "ok": False,
                    "schema": "kenn.realtime_mix_recommendations.v1",
                    "session_id": session_id,
                    "recommendations": [],
                    "recommendations_available": False,
                    "advisory_only": True,
                    "capture_requested": False,
                    "error": result.get("error") or "No validated realtime plug-in review was available.",
                    "limitations": limitations,
                })
                return
            self.send_json(200, {
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
            })
            return
        if parsed.path == "/api/realtime-session-review":
            query = parse_qs(parsed.query)
            plugin_session_id = str(query.get("plugin_session_id", [""])[0]).strip()[:128]
            focus = str(query.get("focus", [""])[0]).strip()[:512]
            try:
                from kenn.core.realtime_session_review import build_realtime_session_review, realtime_knowledge_guidance
                from kenn.mixing_doctor import get_latest_session_state, get_mixing_alerts

                plugin_review = None
                plugin_recommendations = []
                if plugin_session_id:
                    plugin_review = live_review_summary(plugin_session_id)
                    plugin_context = plugin_review.get("live_context") if isinstance(plugin_review, dict) else None
                    if isinstance(plugin_context, dict):
                        from kenn.core.mcp_facade import _realtime_mix_recommendations
                        plugin_recommendations = [
                            item.payload() for item in _realtime_mix_recommendations(plugin_context)
                        ]
                result = build_realtime_session_review(
                    get_latest_session_state(),
                    mixing_alerts=get_mixing_alerts(),
                    plugin_review=plugin_review,
                    plugin_recommendations=plugin_recommendations,
                )
                if result.get("ok"):
                    result["knowledge_guidance"] = realtime_knowledge_guidance(focus, result) if focus else []
                self.send_json(200 if result.get("ok") else 503, result)
            except Exception as exc:
                self.send_json(503, {
                    "ok": False,
                    "schema": "kenn.realtime_session_review.v1",
                    "status": "unavailable",
                    "error": str(exc),
                    "advisory_only": True,
                    "capture_requested": False,
                    "mutation_authorized": False,
                })
            return
        if parsed.path == "/api/realtime-mix-comparison":
            query = parse_qs(parsed.query)
            review_id = str(query.get("review_id", [""])[0]).strip()[:128]
            plugin_session_id = str(query.get("session_id", [""])[0]).strip()[:128]
            if not review_id or not plugin_session_id:
                self.send_json(400, {"ok": False, "error": "review_id and session_id query params are required."})
                return
            if not mix_review:
                self.send_json(503, {"ok": False, "error": "Mix Review Lab is unavailable."})
                return
            review_result = mix_review.mix_review_status(review_id)
            review = review_result.get("review") if isinstance(review_result, dict) else None
            live_result = live_review_summary(plugin_session_id)
            live_context = live_result.get("live_context") if isinstance(live_result, dict) else None
            from kenn.core.realtime_mix_comparison import build_realtime_mix_comparison

            comparison = build_realtime_mix_comparison(
                review,
                live_context,
                review_id=review_id,
                plugin_session_id=plugin_session_id,
            )
            if not isinstance(review, dict):
                comparison.update({"ok": False, "error": review_result.get("error", "Mix Review was not found.")})
            elif not isinstance(live_context, dict):
                comparison.update({"ok": False, "error": live_result.get("error", "No realtime plug-in context was available.")})
            self.send_json(200 if comparison.get("ok") else 404, comparison)
            return
        if parsed.path == "/api/support/diagnostics":
            cached_snapshot = None
            try:
                from kenn.mixing_doctor import get_latest_session_state
                cached_snapshot = get_latest_session_state()
            except Exception:
                pass
            self.send_json(
                200,
                build_support_diagnostics(
                    live_snapshot=cached_snapshot,
                    repo_root=REPO_ROOT,
                ),
            )
            return
        if parsed.path == "/api/admin/reload-index":
            try:
                from kenn.retrieval.retrieval import unload_embedding_index
                from kenn.core.chat_retrieval import load_chunks, load_terms, warm_index
                unload_embedding_index()
                load_chunks.cache_clear()
                load_terms.cache_clear()
                try:
                    from kenn.core.knowledge_graph import reset_graph_cache
                    reset_graph_cache()
                except Exception:
                    pass
                try:
                    from kenn.core.feedback_signals import reset_cache as reset_feedback_cache
                    reset_feedback_cache()
                except Exception:
                    pass
                warm_index()
                self.send_json(200, {"ok": True, "message": "Index hot-reloaded successfully."})
            except Exception as e:
                self.send_json(500, {"ok": False, "error": str(e)})
            return
        if parsed.path == "/api/sessions":
            self.send_json(200, {"sessions": list_db_sessions(limit=20)})
            return
        if parsed.path == "/api/mixing-doctor/alerts":
            try:
                from kenn.mixing_doctor import get_mixing_alerts
                self.send_json(200, {"ok": True, "alerts": get_mixing_alerts()})
            except Exception as e:
                self.send_json(500, {"ok": False, "error": str(e)})
            return
        if parsed.path == "/api/ableton/session-card":
            # D1.6 (docs/KENN_FUTURE_PLAN.md Phase 1): the live session
            # visualizer card reads from Mixing Doctor's own 2s poll cache
            # rather than round-tripping to Ableton on every render frame
            # (D6.3's architecture decision) -- this never touches OSC
            # itself, it's just exposing what the auditor loop already has.
            try:
                from kenn.mixing_doctor import get_latest_session_state
                self.send_json(200, {"ok": True, "session": get_latest_session_state()})
            except Exception as e:
                self.send_json(500, {"ok": False, "error": str(e)})
            return
        if parsed.path in {"/api/realtime/status", "/kenn/api/realtime/status"}:
            from kenn.mixing_doctor import is_realtime_enabled
            self.send_json(200, {"ok": True, "enabled": is_realtime_enabled()})
            return
        if parsed.path in {"/api/ableton/project-audio", "/kenn/api/ableton/project-audio"}:
            from kenn.core.ableton_project_detector import detect_active_ableton_project, find_project_bounces
            proj = detect_active_ableton_project()
            if not proj:
                self.send_json(200, {"ok": False, "error": "No active Ableton Live project detected.", "bounces": []})
                return
            bounces = find_project_bounces(proj["project_dir"]) if proj.get("project_dir") else []
            self.send_json(200, {
                "ok": True,
                "project_name": proj["project_name"],
                "project_dir": proj["project_dir"],
                "als_path": proj["als_path"],
                "bounces": bounces,
            })
            return
        if parsed.path in {"/api/ableton/session-tracks", "/kenn/api/ableton/session-tracks"}:
            from kenn.routes.daw_routes import handle_session_tracks
            code, payload = handle_session_tracks()
            self.send_json(code, payload)
            return
        if parsed.path in {"/api/ableton/project-audio/poll", "/kenn/api/ableton/project-audio/poll"}:
            from kenn.routes.daw_routes import handle_project_audio_poll
            since_raw = parse_qs(parsed.query).get("since", ["0"])[0].strip()
            code, payload = handle_project_audio_poll(since_raw)
            self.send_json(code, payload)
            return
        if parsed.path in {"/api/ableton/project-audio/file", "/kenn/api/ableton/project-audio/file"}:
            from kenn.routes.daw_routes import handle_project_audio_file
            file_path = parse_qs(parsed.query).get("path", [""])[0].strip()
            code, data, mime = handle_project_audio_file(file_path)
            if code == 200:
                self.send_bytes(code, data, mime)
            else:
                self.send_json(code, data)
            return
        if parsed.path == "/api/project-manager/report":
            from kenn.routes.doctor_handler import handle_project_manager_report
            code, payload = handle_project_manager_report()
            self.send_json(code, payload)
            return
        if parsed.path == "/api/project-health/report":
            from kenn.routes.doctor_handler import handle_project_health_report
            code, payload = handle_project_health_report()
            self.send_json(code, payload)
            return
        if parsed.path == "/api/kenn/automix/pending-completions":
            # D2.3 (docs/KENN_FUTURE_PLAN.md Phase 2), "still open" half:
            # a revision job queued via _handle_mix_revision returns
            # immediately with "this runs in the background" and nothing
            # ever told the chat when it actually finished. This is a
            # one-shot check per job -- a completed/failed job is cleared
            # from the pending list the moment it's returned here, so the
            # frontend never surfaces the same completion twice.
            if not automix_jobs:
                self.send_json(503, {"ok": False, "error": "AutoMix is unavailable."})
                return
            try:
                query = parse_qs(parsed.query)
                session_id = query.get("session_id", [""])[0].strip()
                pending_ids = get_pending_automix_jobs(session_id)
                completions = []
                for job_id in pending_ids:
                    job = automix_jobs.get_job_status(job_id)
                    if not job or job.get("status") not in {"complete", "failed"}:
                        continue
                    clear_pending_automix_job(session_id, job_id)
                    entry = {
                        "job_id": job_id,
                        "project_id": job.get("project_id", ""),
                        "status": job.get("status", ""),
                        "error": job.get("error_message", "") if job.get("status") == "failed" else "",
                    }
                    if job.get("status") == "complete":
                        entry["match_evidence"] = _read_match_evidence(job.get("project_id", ""))
                    completions.append(entry)
                self.send_json(200, {"ok": True, "completions": completions})
            except Exception as e:
                self.send_json(500, {"ok": False, "error": str(e)})
            return
        if parsed.path == "/api/orchestrator/agents":
            try:
                from kenn.orchestrator import get_orchestrator
                self.send_json(200, {"ok": True, "agents": get_orchestrator().list_agents()})
            except Exception as e:
                self.send_json(500, {"ok": False, "error": str(e)})
            return
        if parsed.path == "/api/ableton/status":
            if AbletonOSCClient is not None:
                try:
                    from kenn.ableton_osc_bridge import live_client

                    probe = live_client.probe_connection()
                    live_status = str(probe.get("status") or "offline")
                    self.send_json(200, {
                        "ok": True,
                        "status": live_status,
                        "connected": live_status == "connected",
                        "host": live_client.host,
                        "port": live_client.send_port,
                    })
                except Exception as exc:
                    # The companion is available even when Live is not; keep
                    # that distinction visible to the UI instead of turning
                    # a disconnected DAW into a server error.
                    self.send_json(200, {
                        "ok": True,
                        "status": "offline",
                        "connected": False,
                        "error": str(exc),
                    })
            else:
                self.send_json(500, {"ok": False, "status": "error", "error": "Ableton client not available"})
            return
        if parsed.path == "/api/auth/session":
            self.send_json(200, {
                "ok": True,
                "authenticated": True,
                "csrf_token": "kenn-csrf-session",
                "user": "Jack",
            })
            return
        if parsed.path in {
            "/api/ableton/ping",
            "/api/ableton/watchdog",
            "/api/ableton/capabilities",
            "/api/ableton/device-matrix",
        }:
            from kenn.routes.ableton_routes import (
                handle_ableton_ping,
                handle_ableton_watchdog,
                handle_ableton_capabilities,
                handle_ableton_device_matrix,
            )
            client = None
            if AbletonOSCClient is not None:
                try:
                    from kenn.ableton_osc_bridge import live_client
                    client = live_client
                except Exception:
                    client = None
            if parsed.path == "/api/ableton/ping":
                code, payload = handle_ableton_ping(client)
            elif parsed.path == "/api/ableton/watchdog":
                code, payload = handle_ableton_watchdog(client)
            elif parsed.path == "/api/ableton/capabilities":
                code, payload = handle_ableton_capabilities(client)
            else:
                query = parse_qs(parsed.query)
                without_params = str(query.get("parameters", ["1"])[0]).strip().lower() in {"0", "false", "no"}
                code, payload = handle_ableton_device_matrix(client, without_parameters=without_params)
            self.send_json(code, payload)
            return
        if parsed.path in {"/api/ableton/world-model", "/kenn/api/ableton/world-model"}:
            try:
                from kenn.ableton_osc_bridge import live_client
                from kenn.core.live_world_state import world_state
                refresh = str(parse_qs(parsed.query).get("refresh", [""])[0]).lower() in {"1", "true", "yes"}
                model = world_state.current(live_client, force=refresh)
                self.send_json(200 if model.get("status") == "connected" else 503, model)
            except Exception as exc:
                self.send_json(503, {"status": "error", "error": str(exc)})
            return
        if parsed.path == "/guide":
            from kenn.core.tester_guide import guide_html

            self.send_bytes(200, guide_html().encode("utf-8"), "text/html; charset=utf-8")
            return
        if parsed.path == "/setup":
            # First-run page for the packaged app (kenn/core/live_setup.py does the work).
            self.send_bytes(200, (Path(__file__).with_name("setup_page.html")).read_bytes(), "text/html; charset=utf-8")
            return
        if parsed.path in {"/api/support/asked-log", "/kenn/api/support/asked-log"}:
            # A count for the support page's checkbox; the entries themselves only leave inside a diagnostics file.
            from kenn.core import asked_log

            self.send_json(200, {"ok": True, "count": len(asked_log.entries())})
            return
        if parsed.path in {"/api/setup/status", "/kenn/api/setup/status"}:
            from kenn.ableton_osc_bridge import live_client
            from kenn.core.live_setup import setup_status

            self.send_json(200, setup_status(live_client))
            return
        if parsed.path in {"/api/ableton/remote-script", "/kenn/api/ableton/remote-script"}:
            try:
                from kenn.ableton_osc_bridge import live_client
                version = live_client.get_remote_script_version()
                # 200 either way: a 5xx body is sanitised, hiding the "deploy it" reason.
                self.send_json(200, version)
            except Exception as exc:
                self.send_json(503, {"success": False, "error": str(exc)})
            return
        if parsed.path == "/api/ableton/osc/session":
            from kenn.routes.ableton_routes import handle_osc_session
            client = None
            if AbletonOSCClient is not None:
                try:
                    from kenn.ableton_osc_bridge import live_client
                    client = live_client
                except Exception:
                    client = None
            detail = str(parse_qs(parsed.query).get("detail", [""])[0])
            code, payload = handle_osc_session(client, detail=detail)
            self.send_json(code, payload)
            return
        if parsed.path == "/api/ableton/osc/song-time":
            from kenn.routes.ableton_routes import handle_osc_song_time
            client = None
            if AbletonOSCClient is not None:
                try:
                    from kenn.ableton_osc_bridge import live_client
                    client = live_client
                except Exception:
                    client = None
            code, payload = handle_osc_song_time(client)
            self.send_json(code, payload)
            return
        if parsed.path == "/api/ableton/osc/locators":
            from kenn.routes.ableton_routes import handle_osc_locators
            client = None
            if AbletonOSCClient is not None:
                try:
                    from kenn.ableton_osc_bridge import live_client
                    client = live_client
                except Exception:
                    client = None
            code, payload = handle_osc_locators(client)
            self.send_json(code, payload)
            return
        if parsed.path == "/api/ableton/arrangement-analysis":
            from kenn.routes.ableton_routes import handle_arrangement_analysis
            client = None
            if AbletonOSCClient is not None:
                try:
                    from kenn.ableton_osc_bridge import live_client
                    client = live_client
                except Exception:
                    client = None
            session_id = str(parse_qs(parsed.query).get("session_id", [""])[0])
            code, payload = handle_arrangement_analysis(client, session_id=session_id)
            self.send_json(code, payload)
            return
        if parsed.path == "/api/ableton/osc/return-tracks":
            from kenn.routes.ableton_routes import handle_osc_return_tracks
            client = None
            if AbletonOSCClient is not None:
                try:
                    from kenn.ableton_osc_bridge import live_client
                    client = live_client
                except Exception:
                    client = None
            code, payload = handle_osc_return_tracks(client)
            self.send_json(code, payload)
            return
        if parsed.path == "/api/ableton/osc/midi-clip":
            from kenn.routes.ableton_routes import handle_osc_midi_clip
            client = None
            if AbletonOSCClient is not None:
                try:
                    from kenn.ableton_osc_bridge import live_client
                    client = live_client
                except Exception:
                    client = None
            query = parse_qs(parsed.query)
            t_idx = str(query.get("track_index", [""])[0])
            c_idx = str(query.get("clip_slot_index", [""])[0])
            code, payload = handle_osc_midi_clip(client, t_idx, c_idx)
            self.send_json(code, payload)
            return
        if parsed.path == "/api/ableton/osc/clip-slot":
            from kenn.routes.ableton_routes import handle_osc_clip_slot
            client = None
            if AbletonOSCClient is not None:
                try:
                    from kenn.ableton_osc_bridge import live_client
                    client = live_client
                except Exception:
                    client = None
            query = parse_qs(parsed.query)
            t_idx = str(query.get("track_index", [""])[0])
            c_idx = str(query.get("clip_slot_index", [""])[0])
            code, payload = handle_osc_clip_slot(client, t_idx, c_idx)
            self.send_json(code, payload)
            return
        if parsed.path == "/api/ableton/osc/device-parameters":
            from kenn.routes.ableton_routes import handle_osc_device_parameters
            client = None
            if AbletonOSCClient is not None:
                try:
                    from kenn.ableton_osc_bridge import live_client
                    client = live_client
                except Exception:
                    client = None
            query = parse_qs(parsed.query)
            t_idx = str(query.get("track_index", [""])[0])
            d_idx = str(query.get("device_index", [""])[0])
            code, payload = handle_osc_device_parameters(client, t_idx, d_idx)
            self.send_json(code, payload)
            return
        if parsed.path == "/api/ableton/osc/device-parameter-value-string":
            from kenn.routes.ableton_routes import handle_osc_device_parameter_value_string
            client = None
            if AbletonOSCClient is not None:
                try:
                    from kenn.ableton_osc_bridge import live_client
                    client = live_client
                except Exception:
                    client = None
            query = parse_qs(parsed.query)
            t_idx = str(query.get("track_index", [""])[0])
            d_idx = str(query.get("device_index", [""])[0])
            p_idx = str(query.get("parameter_index", [""])[0])
            code, payload = handle_osc_device_parameter_value_string(client, t_idx, d_idx, p_idx)
            self.send_json(code, payload)
            return
        if parsed.path in {"/kenn/api/ask/upgrade", "/api/ask/upgrade"}:
            from kenn.core import answer_upgrades

            query = parse_qs(parsed.query)
            self.send_json(200, answer_upgrades.get(
                str(query.get("id", [""])[0]), session_id=str(query.get("session_id", [""])[0]),
            ))
            return
        if parsed.path == "/api/ableton/receipts":
            query = parse_qs(parsed.query)
            session_id = str(query.get("session_id", [""])[0]).strip()
            try:
                limit = int(query.get("limit", ["50"])[0])
            except (TypeError, ValueError):
                self.send_json(400, {"ok": False, "error": "limit must be an integer."})
                return
            self.send_json(200, {
                "ok": True,
                "schema": "kenn.ableton_receipt_journal.v1",
                "receipts": list_receipts(session_id=session_id, limit=limit),
            })
            return
        if parsed.path == "/api/ableton/audition-feedback":
            query = parse_qs(parsed.query)
            session_id = str(query.get("session_id", [""])[0]).strip()
            try:
                limit = int(query.get("limit", ["20"])[0])
            except (TypeError, ValueError):
                self.send_json(400, {"ok": False, "error": "limit must be an integer."})
                return
            self.send_json(200, {
                "ok": True,
                "schema": "kenn.audition_feedback.v1",
                "feedback": list_audition_feedback(session_id=session_id, limit=limit),
                "advisory_only": True,
            })
            return
        if parsed.path == "/api/mix-versions":
            query = parse_qs(parsed.query)
            session_id = str(query.get("session_id", [""])[0]).strip()
            if session_id:
                versions = list_mix_versions(session_id)
                self.send_json(200, {"ok": True, "versions": versions})
            else:
                self.send_json(400, {"ok": False, "error": "Missing session_id query param"})
            return
        if parsed.path == "/api/session-trends":
            self.send_json(200, get_cross_session_trends())
            return
        if parsed.path == "/api/session":
            query = parse_qs(parsed.query)
            session_id = str(query.get("id", [""])[0]).strip()
            if session_id:
                state = load_session(session_id=session_id)
                self.send_json(200, kenn_session_info(state=state, session_id=session_id))
            else:
                self.send_json(400, {"error": "Missing session id."})
            return
        if parsed.path == "/api/audiogen/status":
            if not self.enforce_rate_limit("audiogen_status"):
                return
            self.handle_audiogen_status()
            return
        if parsed.path == "/api/audiogen/job":
            if not self.enforce_rate_limit("audiogen_status"):
                return
            self.handle_audiogen_job(parsed)
            return
        if parsed.path == "/api/audiogen/history":
            if not self.enforce_rate_limit("audiogen_status"):
                return
            self.handle_audiogen_history(parsed)
            return
        if parsed.path == "/api/audiogen/audio-compare":
            self.send_json(405, {"ok": False, "error": "Use POST to compare two local AudioGen WAV candidates."})
            return
        if parsed.path == "/api/catalog":
            self.send_json(200, catalog_payload(limit=2))
            return
        if parsed.path == "/api/mix-review-status":
            if not self.enforce_rate_limit("mix_review_status"):
                return
            if not mix_review:
                self.send_json(503, {"error": "Mix Review Lab is unavailable."})
                return
            try:
                query = parse_qs(parsed.query)
                review_id = query.get("id", [""])[0]
                result = mix_review.mix_review_status(review_id)
                review = result.get("review") if isinstance(result.get("review"), dict) else None
                if review is not None:
                    from kenn.project_analysis import recommendations_from_mix_review

                    # Preserve the raw review as the source of truth while
                    # exposing the same action schema as live-project tools.
                    result["recommendations"] = [
                        item.payload() for item in recommendations_from_mix_review(review)
                    ]
                    from kenn.core.advice_next_step import with_mix_review_next_step

                    result["review"] = with_mix_review_next_step(review)
                self.send_json(200, result)
            except Exception as exc:
                self.send_json(500, {"error": f"Failed to get mix review status: {exc}"})
            return
        if parsed.path == "/api/automix-status":
            if not self.enforce_rate_limit("automix_status"):
                return
            if not automix_jobs:
                self.send_json(503, {"error": "AutoMix is unavailable."})
                return
            query = parse_qs(parsed.query)
            job_id = query.get("id", [""])[0].strip()
            if not job_id:
                self.send_json(400, {"error": "Missing job id."})
                return
            job = automix_jobs.get_job_status(job_id)
            if not job:
                self.send_json(404, {"error": "Job not found."})
                return
            # Same public-safe allowlist as business/app's
            # /api/public/automix-start/status -- never leak result_path
            # or the raw style_prefs blob to the browser.
            self.send_json(200, {
                "ok": True,
                "id": job.get("id", ""),
                "project_id": job.get("project_id", ""),
                "status": job.get("status", ""),
                "progress": job.get("progress", 0),
                "genre": job.get("genre", ""),
                "error": job.get("error_message", "") if job.get("status") == "failed" else "",
            })
            return
        if parsed.path == "/api/automix-download":
            if not self.enforce_rate_limit("automix_status"):
                return
            if not automix_public:
                self.send_json(503, {"error": "AutoMix is unavailable."})
                return
            query = parse_qs(parsed.query)
            job_id = query.get("id", [""])[0].strip()
            kind = query.get("kind", ["wav"])[0].strip().lower()
            if not job_id:
                self.send_json(400, {"error": "Missing job id."})
                return
            if kind == "zip":
                zip_path = automix_public.delivery_zip_path(job_id)
                if not zip_path:
                    self.send_json(404, {"error": "Delivery not ready or job not found."})
                    return
                self.send_bytes(200, zip_path.read_bytes(), "application/zip", filename=f"automix-{job_id}.zip")
                return
            wav = automix_public.delivery_wav_bytes(job_id)
            if not wav:
                self.send_json(404, {"error": "Mixdown not ready or job not found."})
                return
            wav_bytes, filename = wav
            self.send_bytes(200, wav_bytes, "audio/wav", filename=filename)
            return
        if parsed.path in {"/api/session/demo-audio", "/kenn/api/session/demo-audio"}:
            demo_wav_path = Path(__file__).resolve().parents[4] / ".runtime" / "investor-demo-audio" / "KENN_Demo_Mix_Analysis.wav"
            if not demo_wav_path.exists():
                demo_wav_path = Path(__file__).resolve().parents[3] / "KENN Demo Audio" / "01_Kick.wav"
            if demo_wav_path.exists():
                self.send_bytes(200, demo_wav_path.read_bytes(), "audio/wav", filename="KENN_Demo_Mix_Analysis.wav")
            else:
                self.send_json(404, {"error": "Demo audio file not found."})
            return
        if parsed.path == "/api/stem-separate-status":
            if not self.enforce_rate_limit("stem_separate_status"):
                return
            if not stem_separation_bridge:
                self.send_json(503, {"error": "Stem separation is unavailable."})
                return
            query = parse_qs(parsed.query)
            job_id = query.get("id", [""])[0].strip()
            if not job_id:
                self.send_json(400, {"error": "Missing job id."})
                return
            job = stem_separation_bridge.job_status(job_id)
            if not job:
                self.send_json(404, {"error": "Job not found."})
                return
            stems_ready = sorted((job.get("result") or {}).get("stems") or {})
            self.send_json(200, {
                "ok": True,
                "id": job.get("id", ""),
                "status": job.get("status", ""),
                "progress": job.get("progress", 0),
                "message": job.get("message", ""),
                "error": job.get("error", ""),
                "stems_ready": stems_ready,
            })
            return
        if parsed.path == "/api/stem-separate-download":
            if not self.enforce_rate_limit("stem_separate_status"):
                return
            if not stem_separation_bridge:
                self.send_json(503, {"error": "Stem separation is unavailable."})
                return
            query = parse_qs(parsed.query)
            job_id = query.get("id", [""])[0].strip()
            stem = query.get("stem", ["all"])[0].strip().lower()
            if not job_id:
                self.send_json(400, {"error": "Missing job id."})
                return
            if stem == "all":
                zip_path = stem_separation_bridge.job_zip_path(job_id)
                if not zip_path:
                    self.send_json(404, {"error": "Stems not ready or job not found."})
                    return
                self.send_bytes(200, zip_path.read_bytes(), "application/zip", filename=f"stems-{job_id}.zip")
                return
            if stem not in stem_separation_bridge.STEM_NAMES:
                self.send_json(400, {"error": f"Unknown stem {stem!r}."})
                return
            stem_path = stem_separation_bridge.job_stem_path(job_id, stem)
            if not stem_path:
                self.send_json(404, {"error": "Stem not ready or job not found."})
                return
            self.send_bytes(200, stem_path.read_bytes(), "audio/wav", filename=f"{stem}-{job_id}.wav")
            return
        if parsed.path.startswith("/api/mix-review-report/"):
            if not self.enforce_rate_limit("report"):
                return
            if not mix_review:
                self.send_json(503, {"error": "Mix Review Lab is unavailable."})
                return
            try:
                report_ref = parsed.path.rsplit("/", 1)[-1]
                review_id = report_ref.rsplit(".", 1)[0]
                if report_ref.endswith(".json"):
                    body = mix_review.report_json_bytes(review_id)
                    if body is None:
                        self.send_json(404, {"error": "Mix review report not found."})
                        return
                    self.send_bytes(200, body, "application/json", filename=f"mix-review-{review_id}.json")
                    return
                if report_ref.endswith(".html"):
                    html_body = mix_review.report_html(review_id)
                    if html_body is None:
                        self.send_json(404, {"error": "Mix review report not found."})
                        return
                    self.send_bytes(200, html_body.encode("utf-8"), "text/html; charset=utf-8")
                    return
            except Exception as exc:
                self.send_json(500, {"error": f"Failed to load report: {exc}"})
            return
        if parsed.path.startswith("/api/mix-review/reference-preset/"):
            if not mix_review:
                self.send_json(503, {"error": "Mix Review Lab is unavailable."})
                return
            try:
                report_ref = parsed.path.rsplit("/", 1)[-1]
                review_id = report_ref.replace(".adv", "").strip()
                res = mix_review.mix_review_status(review_id)
                review = res.get("review") or {}
                adv_b64 = (review.get("reference_comparison") or {}).get("eq8_preset_adv_base64")
                if not adv_b64:
                    self.send_json(404, {"error": "No EQ Eight preset found for this reference review."})
                    return
                adv_bytes = base64.b64decode(adv_b64)
                self.send_bytes(200, adv_bytes, "application/octet-stream", filename=f"Reference_Match_{review_id}.adv")
            except Exception as exc:
                self.send_json(500, {"error": f"Failed to export EQ preset: {exc}"})
            return
        if parsed.path.startswith("/portfolio/audio/"):
            self.serve_portfolio_audio(parsed.path)
            return
        if parsed.path == "/api/suggest":
            if not self.enforce_rate_limit("suggest"):
                return
            query = parse_qs(parsed.query).get("q", [""])[0]
            try:
                limit = int(parse_qs(parsed.query).get("limit", ["8"])[0])
            except ValueError:
                limit = 8
            self.send_json(200, {"ok": True, "query": query, "suggestions": typeahead(query, limit=limit)})
            return
        if parsed.path == "/api/knowledge-graph":
            source = parse_qs(parsed.query).get("source", [""])[0]
            if not source:
                self.send_json(400, {"ok": False, "error": "Missing source query param."})
                return
            try:
                from kenn.core.knowledge_graph import related_sources
                from kenn.core.chat_retrieval import load_chunks
                chunks = load_chunks()
                related = related_sources(source, chunks, limit=5)
                self.send_json(200, {"ok": True, "source": source, "related": related})
            except Exception as e:
                self.send_json(500, {"ok": False, "error": str(e)})
            return
        self.serve_static(parsed.path)

    def do_POST(self) -> None:
        parsed = _strip_kenn_prefix(urlparse(self.path))
        if self.headers.get("Origin") and not self.allowed_cors_origin():
            self.send_json(403, {"error": "Cross-origin request rejected."})
            return
        if parsed.path == "/api/mix-review":
            if not self.enforce_rate_limit("mix_review"):
                return
            self.handle_mix_review()
            return
        if parsed.path == "/api/audio-analysis":
            if not self.enforce_rate_limit("mix_review"):
                return
            reference = parse_qs(parsed.query).get("reference", [""])[0].strip().lower()
            if reference not in {"", "pink_noise", "pink-noise", "pink"}:
                self.send_json(400, {"ok": False, "error": "Unsupported analysis reference; use reference=pink_noise."})
                return
            self.handle_audio_analysis(include_pink_noise_reference=bool(reference))
            return
        if parsed.path == "/api/auth/login":
            self.send_json(200, {
                "ok": True,
                "authenticated": True,
                "csrf_token": "kenn-csrf-session",
                "user": "Jack",
            })
            return
        if parsed.path == "/api/audio/telemetry":
            # Same 1 MB ceiling as the other JSON routes; these two used to read whatever length was claimed.
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = -1
            if length < 0 or length > 1024 * 1024:
                self.send_json(413, {"error": "Request body exceeds 1 MB limit."})
                return
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                data = json.loads(raw.decode("utf-8"))
            except Exception:
                data = {}
            from kenn.audio_telemetry import get_telemetry_manager
            frame = get_telemetry_manager().ingest(data)
            anomalies = get_telemetry_manager().diagnose_anomalies(frame)
            self.send_json(200, {
                "ok": True,
                "telemetry": frame.to_dict(),
                "anomalies": anomalies,
            })
            return
        if parsed.path == "/api/mix/plan":
            # Same ceiling as /api/audio/telemetry above.
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = -1
            if length < 0 or length > 1024 * 1024:
                self.send_json(413, {"error": "Request body exceeds 1 MB limit."})
                return
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                data = json.loads(raw.decode("utf-8"))
            except Exception:
                data = {}
            query = data.get("query", "Optimize mix and master")
            from kenn.agent.mix_planner import get_mix_planner
            plan = get_mix_planner().create_plan(query)
            self.send_json(200, {
                "ok": True,
                "plan": plan.to_dict(),
            })
            return
        if parsed.path == "/api/audio-analysis/compare":
            if not self.enforce_rate_limit("mix_review"):
                return
            self.handle_audio_analysis_compare()
            return
        if parsed.path == "/api/mix-review/masking":
            if not self.enforce_rate_limit("mix_review"):
                return
            self.handle_mix_review_masking()
            return
        if parsed.path in {"/api/mix-review/reference", "/api/mix-review/reference-match"}:
            if not self.enforce_rate_limit("mix_review"):
                return
            content_type = self.headers.get("Content-Type", "")
            if "multipart/form-data" in content_type:
                self.handle_mix_reference()
            else:
                self.handle_mix_reference_json()
            return
        if parsed.path in {"/api/track-diagnostic/scan", "/kenn/api/track-diagnostic/scan"}:
            if not self.enforce_rate_limit("mix_review"):
                return
            from kenn.routes.audio_handler import handle_track_diagnostic_scan
            handle_track_diagnostic_scan(self)
            return
        if parsed.path in {"/api/track-diagnostic/apply", "/kenn/api/track-diagnostic/apply"}:
            from kenn.routes.audio_handler import handle_track_diagnostic_apply
            handle_track_diagnostic_apply(self)
            return
        if parsed.path == "/api/automix-upload":
            if not self.enforce_rate_limit("automix_upload"):
                return
            self.handle_automix_upload()
            return
        if parsed.path == "/api/stem-separate-upload":
            if not self.enforce_rate_limit("stem_separate_upload"):
                return
            self.handle_stem_separate_upload()
            return
        if parsed.path == "/api/ask-attachment":
            if not self.enforce_rate_limit("ask"):
                return
            self.handle_ask_attachment()
            return
        if parsed.path not in {
            "/api/setup/install-remote-script",
            "/kenn/api/setup/install-remote-script",
            "/api/support/diagnostics/save",
            "/kenn/api/support/diagnostics/save",
            "/api/support/asked-log/clear",
            "/kenn/api/support/asked-log/clear",
            "/api/ask", "/api/feedback", "/api/session/feedback", "/api/mix-review-step",
            "/api/audiogen/generate", "/api/audiogen/render-song",
            "/api/session/clear", "/api/ableton/apply-repair", "/api/mix-version/save",
            "/api/audio-dev", "/api/ableton/osc/volume", "/api/ableton/osc/pan", "/api/speak",
            "/api/audio-analysis",
            "/api/audio-analysis/compare",
            # Added 2026-08-06 alongside mute/solo/arm/transport/clip/scene
            # control -- found via the packaging boot test (D0.2) that this
            # allowlist 404s any POST path not explicitly listed here,
            # before the route handlers below ever run. The chat-driven
            # verification of these features never caught this because
            # chat calls live_client directly in-process, never through
            # these dedicated HTTP routes -- a real gap between "verified
            # live via chat" and "reachable via direct HTTP POST."
            "/api/ableton/osc/mute", "/api/ableton/osc/solo", "/api/ableton/osc/arm",
            "/api/ableton/osc/transport/play", "/api/ableton/osc/transport/stop",
            "/api/ableton/osc/tempo", "/api/ableton/osc/clip/launch",
            "/api/ableton/osc/scene/launch", "/api/ableton/osc/undo",
            "/api/ableton/command",
            "/api/ableton/parameter/inspect",
            "/api/ableton/parameter/proposal",
            "/api/ableton/confirmation/revoke",
            "/api/ableton/midi-clip/proposal",
            "/api/ableton/midi-clip/update-proposal",
            "/api/ableton/clip-duplication/proposal",
            "/api/ableton/clip-rename/proposal",
            "/api/ableton/sample-import/proposal",
            "/api/ableton/clip-audition/proposal",
            "/api/ableton/audition-feedback",
            "/api/audiogen/midi-proposal",
            "/api/audiogen/audio-compare",
            "/api/plugin-handoff",
            "/api/plugin-handoff-batch",
            "/api/plugin/parameters",
            "/api/knowledge/ask",
            "/api/ableton/audition_delta",
            "/api/rack/build",
            "/kenn/api/rack/build",
            "/api/racks/synthesize",
            "/kenn/api/racks/synthesize",
            "/api/midi/detect_scale",
            "/kenn/api/midi/detect_scale",
            "/api/midi/groove",
            "/kenn/api/midi/groove",
            "/api/midi/bassline",
            "/kenn/api/midi/bassline",
            "/api/session/doctor/audit",
            "/kenn/api/session/doctor/audit",
            "/api/session/doctor/remediate",
            "/kenn/api/session/doctor/remediate",
            "/api/mix-doctor/audit",
            "/kenn/api/mix-doctor/audit",
            "/api/unmasking/analyze",
            "/kenn/api/unmasking/analyze",
            "/api/unmasking/carve",
            "/kenn/api/unmasking/carve",
            "/api/voice/intent",
            "/kenn/api/voice/intent",
            "/api/mastering/profile",
            "/kenn/api/mastering/profile",
            "/api/mastering/apply",
            "/kenn/api/mastering/apply",
            "/api/reference/analyze",
            "/kenn/api/reference/analyze",
            "/api/reference/match-curve",
            "/kenn/api/reference/match-curve",
            "/api/gain-staging/audit",
            "/kenn/api/gain-staging/audit",
            "/api/gain-staging/trim",
            "/kenn/api/gain-staging/trim",
            "/api/arrangement/analyze",
            "/kenn/api/arrangement/analyze",
            "/api/arrangement/remediate",
            "/kenn/api/arrangement/remediate",
            "/api/midi/generate/counterpoint",
            "/kenn/api/midi/generate/counterpoint",
            "/api/midi/generate/bassline",
            "/kenn/api/midi/generate/bassline",
            "/api/vocal/audit",
            "/kenn/api/vocal/audit",
            "/api/vocal/de-resonate",
            "/kenn/api/vocal/de-resonate",
            "/api/stems/export-plan",
            "/kenn/api/stems/export-plan",
            "/api/stems/certificate",
            "/kenn/api/stems/certificate",
            "/api/realtime/toggle",
            "/kenn/api/realtime/toggle",
        }:
            self.send_json(404, {"error": "Not found"})
            return
        if endpoint_policy("kenn", "POST", parsed.path).mutates:
            # Batched DSP evidence only updates the feature cache. Its own
            # bounded budget cannot spend or raise the Live-control budget.
            scope = "plugin_handoff_batch" if parsed.path == "/api/plugin-handoff-batch" else "mutation"
            if not self.enforce_rate_limit(scope):
                return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > 1024 * 1024:
                self.send_json(413, {"error": "Request body exceeds 1 MB limit."})
                return
            payload = request_validation.validate_json_payload(
                json.loads(self.rfile.read(length).decode("utf-8"))
            )
        except (json.JSONDecodeError, ValueError):
            self.send_json(400, {"error": "Invalid JSON."})
            return
        if parsed.path in {"/api/support/diagnostics/save", "/kenn/api/support/diagnostics/save"}:
            # Writes one redacted file into KENN's own data folder, for the tester to attach to a report.
            if payload.get("confirm") is not True:
                self.send_json(400, {"ok": False, "error": "Saving diagnostics needs an explicit confirm."})
                return
            cached_snapshot = None
            try:
                from kenn.mixing_doctor import get_latest_session_state
                cached_snapshot = get_latest_session_state()
            except Exception:
                pass
            directory = Path(os.environ.get("KENN_DIAGNOSTICS_DIR") or (REPO_ROOT / ".runtime" / "diagnostics")).expanduser()
            try:
                saved = save_support_diagnostics(
                    build_support_diagnostics(live_snapshot=cached_snapshot, repo_root=REPO_ROOT,
                                              include_asked_log=payload.get("include_asked_log") is True), directory)
            except OSError as exc:
                self.send_json(500, {"ok": False, "error": f"KENN could not write the diagnostics file ({exc.strerror})."})
                return
            self.send_json(200, {"ok": True, "path": str(saved), "filename": saved.name})
            return
        if parsed.path in {"/api/support/asked-log/clear", "/kenn/api/support/asked-log/clear"}:
            if payload.get("confirm") is not True:
                self.send_json(400, {"ok": False, "error": "Clearing needs an explicit confirm."})
                return
            from kenn.core import asked_log

            self.send_json(200, {"ok": True, "cleared": asked_log.clear()})
            return
        if parsed.path in {"/api/setup/install-remote-script", "/kenn/api/setup/install-remote-script"}:
            # Writes into the user's Ableton User Library: only on an explicit confirm from the setup page.
            if payload.get("confirm") is not True:
                self.send_json(400, {"ok": False, "error": "Installing AbletonOSC needs an explicit confirm."})
                return
            from kenn.core.live_setup import install_remote_script

            result = install_remote_script()
            self.send_json(200 if result.get("ok") else 500, result)
            return
        if parsed.path in {"/api/realtime/toggle", "/kenn/api/realtime/toggle"}:
            from kenn.mixing_doctor import set_realtime_enabled, is_realtime_enabled
            req_val = payload.get("enabled")
            new_val = bool(req_val) if req_val is not None else not is_realtime_enabled()
            set_realtime_enabled(new_val)
            self.send_json(200, {"ok": True, "enabled": new_val})
            return
        if parsed.path in {"/api/ableton/audition_delta", "/kenn/api/ableton/audition_delta"}:
            from kenn.routes.session_intelligence_handler import handle_post_audition_delta
            handle_post_audition_delta(self, payload)
            return
        if parsed.path in {"/api/rack/build", "/kenn/api/rack/build"}:
            from kenn.routes.racks_handler import handle_post_rack_build
            handle_post_rack_build(self, payload)
            return
        if parsed.path in {"/api/racks/synthesize", "/kenn/api/racks/synthesize"}:
            from kenn.routes.racks_handler import handle_post_racks_synthesize
            handle_post_racks_synthesize(self, payload)
            return
        if parsed.path in {"/api/session/doctor/audit", "/kenn/api/session/doctor/audit"}:
            from kenn.routes.doctor_handler import handle_post_doctor_audit
            handle_post_doctor_audit(self, payload)
            return
        if parsed.path in {"/api/session/doctor/remediate", "/kenn/api/session/doctor/remediate"}:
            from kenn.routes.doctor_handler import handle_post_doctor_remediate
            handle_post_doctor_remediate(self, payload)
            return
        if parsed.path == "/api/audio-dev":
            query = str(payload.get("query", ""))
            code_context = payload.get("code_context")
            language = str(payload.get("language", "cpp"))
            from kenn.audio_dev_agent import ask_audio_dev_agent
            result = ask_audio_dev_agent(query, code_context=code_context, language=language)
            self.send_json(200, result)
            return
        if parsed.path == "/api/knowledge/ask":
            question = str(payload.get("question") or "").strip()
            if not question:
                self.send_json(400, {"ok": False, "error": "A question is required."})
                return
            session_id = str(payload.get("session_id") or "").strip()[:128]
            plugin_session_id = str(payload.get("plugin_session_id") or "").strip()[:128]
            mix_review_id = str(payload.get("mix_review_id") or "").strip()[:128]
            result = grounded_knowledge_answer(
                question,
                session_id=session_id,
                plugin_session_id=plugin_session_id,
                mix_review_id=mix_review_id,
                correlation_id=self.request_id(),
            )
            self.send_json(200, {"ok": True, **result})
            return
        if parsed.path == "/api/plugin-handoff-batch":
            result = ingest_live_context_batch(payload)
            self.send_json(200 if "frames" in result else 400, result)
            return
        if parsed.path == "/api/plugin-handoff":
            # Local plug-ins submit an opt-in bus snapshot, never DAW control
            # data or audio.  AutoMix stays unavailable until the user supplies
            # a stem set through the normal upload workflow.
            result = ingest_live_context(payload, session_id=str(payload.get("session_id", "")))
            self.send_json(200 if result.get("ok") else 400, result)
            return
        if parsed.path in {"/api/mix-doctor/audit", "/kenn/api/mix-doctor/audit"}:
            from kenn.core.mix_doctor import get_mix_doctor
            from kenn.audio_telemetry import get_telemetry_manager
            session_snapshot = payload.get("session_snapshot")
            if not session_snapshot:
                from kenn.mixing_doctor import get_latest_session_state
                session_snapshot = get_latest_session_state()
            meters = payload.get("meters")
            if not meters:
                latest_m = get_telemetry_manager().get_latest()
                if latest_m:
                    meters = latest_m.to_dict()
            report = get_mix_doctor().audit_session(session_snapshot, meters=meters)
            self.send_json(200, {"ok": True, "report": report.to_dict()})
            return
        if parsed.path in {"/api/unmasking/analyze", "/kenn/api/unmasking/analyze"}:
            from kenn.core.stem_unmasking import get_stem_unmasking_engine
            tracks = payload.get("tracks", [])
            meters = payload.get("meters")
            engine = get_stem_unmasking_engine()
            collisions = engine.detect_collisions(tracks, meters=meters)
            dag = engine.synthesize_unmasking_dag(collisions)
            self.send_json(200, {
                "ok": True,
                "collision_count": len(collisions),
                "collisions": [c.to_dict() for c in collisions],
                "unmasking_dag": dag,
            })
            return
        if parsed.path in {"/api/unmasking/carve", "/kenn/api/unmasking/carve"}:
            from kenn.core.stem_unmasking import get_stem_unmasking_engine
            engine = get_stem_unmasking_engine()
            tracks = payload.get("tracks", [])
            collisions = engine.detect_collisions(tracks)
            dag = engine.synthesize_unmasking_dag(collisions)
            self.send_json(200, {"ok": True, "carving_dag": dag})
            return
        if parsed.path in {"/api/voice/intent", "/kenn/api/voice/intent"}:
            from kenn.speech.voice_copilot import get_voice_copilot
            spoken_text = str(payload.get("spoken_text", payload.get("text", ""))).strip()
            intent = get_voice_copilot().classify_intent(spoken_text)
            self.send_json(200, {"ok": True, "intent": intent.to_dict()})
            return
        if parsed.path in {"/api/mastering/profile", "/kenn/api/mastering/profile"}:
            from kenn.core.mastering_engine import get_mastering_engine
            engine = get_mastering_engine()
            profile_name = str(payload.get("profile", payload.get("profile_name", "SPOTIFY_STREAMING"))).strip()
            profiles = engine.get_supported_profiles()
            if profile_name.upper() in profiles:
                p = profiles[profile_name.upper()]
                self.send_json(200, {"ok": True, "profile": p.to_dict()})
            else:
                self.send_json(400, {"ok": False, "error": f"Unknown profile: {profile_name}. Available: {list(profiles.keys())}"})
            return
        if parsed.path in {"/api/mastering/apply", "/kenn/api/mastering/apply"}:
            from kenn.core.mastering_engine import get_mastering_engine
            engine = get_mastering_engine()
            profile_name = str(payload.get("profile", payload.get("profile_name", "SPOTIFY_STREAMING"))).strip()
            snapshot = payload.get("session_snapshot")
            meters = payload.get("meters", payload.get("current_metrics"))
            report = engine.synthesize_mastering_dag(profile_name=profile_name, session_snapshot=snapshot, meters=meters)
            self.send_json(200, {"ok": True, "mastering_report": report.to_dict(), "mastering_dag": report.mastering_dag})
            return
        if parsed.path in {"/api/reference/analyze", "/kenn/api/reference/analyze"}:
            from kenn.core.reference_matcher import get_reference_matcher
            matcher = get_reference_matcher()
            ref_name = str(payload.get("reference_name", "Commercial Reference")).strip()
            session_spec = payload.get("session_spectrum", [])
            ref_spec = payload.get("reference_spectrum", [])
            report = matcher.compute_spectral_delta(session_spec, ref_spec, reference_name=ref_name)
            response = {"ok": report.available, "analysis": report.to_dict()}
            if not report.available:
                response["error"] = report.diagnostic_reason
            self.send_json(200 if report.available else 400, response)
            return
        if parsed.path in {"/api/reference/match-curve", "/kenn/api/reference/match-curve"}:
            from kenn.core.reference_matcher import get_reference_matcher
            matcher = get_reference_matcher()
            ref_name = str(payload.get("reference_name", "Commercial Reference")).strip()
            session_spec = payload.get("session_spectrum", [])
            ref_spec = payload.get("reference_spectrum", [])
            report = matcher.compute_spectral_delta(session_spec, ref_spec, reference_name=ref_name)
            response = {
                "ok": report.available,
                "available": report.available,
                "eq_recipe": report.eq_recipe,
                "delta_curve": report.delta_curve,
                "rms_spectral_delta_db": report.rms_spectral_delta_db,
            }
            if not report.available:
                response["error"] = report.diagnostic_reason
            self.send_json(200 if report.available else 400, response)
            return
        if parsed.path in {"/api/gain-staging/audit", "/kenn/api/gain-staging/audit"}:
            from kenn.core.auto_gain_stager import get_auto_gain_stager
            stager = get_auto_gain_stager()
            tracks = payload.get("tracks", [])
            meters = payload.get("meters")
            audit = stager.audit_gain_staging(tracks, meters=meters)
            self.send_json(200, {"ok": True, "audit": audit.to_dict()})
            return
        if parsed.path in {"/api/gain-staging/trim", "/kenn/api/gain-staging/trim"}:
            from kenn.core.auto_gain_stager import get_auto_gain_stager
            stager = get_auto_gain_stager()
            tracks = payload.get("tracks", [])
            meters = payload.get("meters")
            audit = stager.audit_gain_staging(tracks, meters=meters)
            self.send_json(200, {
                "ok": True,
                "trim_plan": audit.remediation_batch,
                "tracks_overloaded": audit.tracks_overloaded,
                "nominal_target_dbfs": audit.nominal_target_dbfs,
            })
            return
        if parsed.path in {"/api/arrangement/analyze", "/kenn/api/arrangement/analyze"}:
            from kenn.core.arrangement_doctor import get_arrangement_doctor
            doc = get_arrangement_doctor()
            tracks = payload.get("tracks", [])
            sections = payload.get("sections")
            total_bars = int(payload.get("total_bars", 64))
            report = doc.analyze_timeline(tracks=tracks, timeline_sections=sections, total_bars=total_bars)
            self.send_json(200, {"ok": True, "arrangement_report": report.to_dict()})
            return
        if parsed.path in {"/api/arrangement/remediate", "/kenn/api/arrangement/remediate"}:
            from kenn.core.arrangement_doctor import get_arrangement_doctor
            doc = get_arrangement_doctor()
            tracks = payload.get("tracks", [])
            sections = payload.get("sections")
            report = doc.analyze_timeline(tracks=tracks, timeline_sections=sections)
            self.send_json(200, {"ok": True, "transition_recipes": report.transition_recipes, "drop_contrast_delta": report.drop_contrast_delta})
            return
        if parsed.path in {"/api/midi/generate/counterpoint", "/kenn/api/midi/generate/counterpoint"}:
            from kenn.core.midi_copilot import get_midi_copilot
            copilot = get_midi_copilot()
            root = str(payload.get("root", "F")).strip()
            scale = str(payload.get("scale", "NATURAL_MINOR")).strip()
            bars = int(payload.get("bars", 4))
            swing = str(payload.get("swing", "STRAIGHT")).strip()
            clip = copilot.generate_counterpoint(root=root, scale=scale, bars=bars, swing=swing)
            self.send_json(200, {"ok": True, "clip": clip.to_dict()})
            return
        if parsed.path in {"/api/midi/generate/bassline", "/kenn/api/midi/generate/bassline"}:
            from kenn.core.midi_copilot import get_midi_copilot
            copilot = get_midi_copilot()
            root = str(payload.get("root", "F")).strip()
            scale = str(payload.get("scale", "NATURAL_MINOR")).strip()
            bars = int(payload.get("bars", 4))
            style = str(payload.get("style", "ROLLING_16TH")).strip()
            swing = str(payload.get("swing", "STRAIGHT")).strip()
            clip = copilot.generate_bassline(root=root, scale=scale, bars=bars, style=style, swing=swing)
            self.send_json(200, {"ok": True, "clip": clip.to_dict()})
            return
        if parsed.path in {"/api/vocal/audit", "/kenn/api/vocal/audit"}:
            from kenn.core.vocal_surgeon import get_vocal_surgeon
            surgeon = get_vocal_surgeon()
            t_name = str(payload.get("track_name", "Lead Vocal")).strip()
            peaks = payload.get("spectral_peaks")
            meters = payload.get("meters")
            report = surgeon.audit_vocal_track(track_name=t_name, spectral_peaks=peaks, meters=meters)
            self.send_json(200, {"ok": True, "vocal_report": report.to_dict()})
            return
        if parsed.path in {"/api/vocal/de-resonate", "/kenn/api/vocal/de-resonate"}:
            from kenn.core.vocal_surgeon import get_vocal_surgeon
            surgeon = get_vocal_surgeon()
            t_name = str(payload.get("track_name", "Lead Vocal")).strip()
            peaks = payload.get("spectral_peaks")
            report = surgeon.audit_vocal_track(track_name=t_name, spectral_peaks=peaks)
            self.send_json(200, {"ok": True, "eq_recipe": report.eq_recipe, "anomalies_detected": report.anomalies_detected})
            return
        if parsed.path in {"/api/stems/export-plan", "/kenn/api/stems/export-plan"}:
            from kenn.core.stem_packager import get_stem_packager
            packager = get_stem_packager()
            tracks = payload.get("tracks", [])
            meta = payload.get("metadata", payload.get("project_metadata"))
            plan = packager.generate_stem_plan(tracks=tracks, project_metadata=meta)
            self.send_json(200, {"ok": True, "stem_plan": plan.to_dict()})
            return
        if parsed.path in {"/api/stems/certificate", "/kenn/api/stems/certificate"}:
            from kenn.core.stem_packager import get_stem_packager
            packager = get_stem_packager()
            tracks = payload.get("tracks", [])
            meta = payload.get("metadata", payload.get("project_metadata"))
            plan = packager.generate_stem_plan(tracks=tracks, project_metadata=meta)
            self.send_json(200, {"ok": True, "certificate": plan.certificate.to_dict()})
            return
        if parsed.path == "/api/plugin/parameters":
            session_id = str(payload.get("session_id", "")).strip()
            if "conversation_id" in payload:
                updates = payload.get("parameters") if "parameters" in payload else {str(payload.get("parameter", "")): payload.get("value")}
                result = queue_owned_plugin_parameters(session_id, str(payload.get("conversation_id") or ""), updates)
            elif "parameters" in payload and isinstance(payload["parameters"], dict):
                result = set_plugin_parameters(session_id, payload["parameters"])
            elif "parameter" in payload:
                result = set_plugin_parameter(session_id, str(payload.get("parameter", "")), payload.get("value"))
            else:
                self.send_json(400, {"ok": False, "error": "Either 'parameter' and 'value' or 'parameters' dict is required."})
                return
            self.send_json(200 if result.get("ok") else 400, result)
            return
        if parsed.path == "/api/ableton/confirmation/revoke":
            from kenn.routes.daw_routes import handle_confirmation_revoke

            status, result = handle_confirmation_revoke(payload)
            self.send_json(status, result)
            return
        if parsed.path == "/api/ableton/command":
            self.handle_live_command(payload)
            return
        if parsed.path == "/api/ableton/parameter/inspect":
            from kenn.routes.daw_routes import handle_parameter_inspection

            status, result = handle_parameter_inspection(payload)
            self.send_json(status, result)
            return

        if parsed.path == "/api/ableton/parameter/proposal":
            from kenn.routes.daw_routes import handle_parameter_proposal

            status, result = handle_parameter_proposal(payload)
            self.send_json(status, result)
            return
        if parsed.path == "/api/ableton/midi-clip/proposal":
            from kenn.routes.daw_routes import handle_midi_clip_proposal
            code, payload = handle_midi_clip_proposal(payload)
            self.send_json(code, payload)
            return
        if parsed.path == "/api/ableton/midi-clip/update-proposal":
            from kenn.routes.daw_routes import handle_midi_clip_update_proposal
            code, payload = handle_midi_clip_update_proposal(payload)
            self.send_json(code, payload)
            return
        if parsed.path == "/api/ableton/clip-duplication/proposal":
            from kenn.routes.daw_routes import handle_clip_duplication_proposal
            code, payload = handle_clip_duplication_proposal(payload)
            self.send_json(code, payload)
            return
        if parsed.path == "/api/ableton/clip-rename/proposal":
            from kenn.routes.daw_routes import handle_clip_rename_proposal
            code, payload = handle_clip_rename_proposal(payload)
            self.send_json(code, payload)
            return
        if parsed.path == "/api/ableton/sample-import/proposal":
            from kenn.routes.daw_routes import handle_sample_import_proposal
            code, payload = handle_sample_import_proposal(payload)
            self.send_json(code, payload)
            return
        if parsed.path == "/api/ableton/clip-audition/proposal":
            from kenn.routes.daw_routes import handle_clip_audition_proposal
            code, payload = handle_clip_audition_proposal(payload)
            self.send_json(code, payload)
            return
        if parsed.path == "/api/ableton/audition-feedback":
            self.handle_audition_feedback(payload)
            return
        if parsed.path == "/api/audiogen/midi-proposal":
            self.handle_audiogen_midi_proposal(payload)
            return
        if parsed.path == "/api/audiogen/audio-compare":
            self.handle_audiogen_audio_compare(payload)
            return
        if parsed.path == "/api/speak":
            # Reuses Thursday's existing Kokoro TTS pipeline directly
            # (thursday/voice_output.py) rather than standing up a second
            # synthesis path -- KENN already has its own assigned voice
            # there (KENN_VOICE = "am_onyx", distinct from Thursday's
            # af_heart), just not wired to this web chat until now. Mirrors
            # business/app/routes/thursday_routes.py's existing
            # /api/thursday/speak handler exactly (same
            # synthesise_isolated() call, same isolated-subprocess safety
            # so a TTS failure can't take the server down).
            text = str(payload.get("text", "")).strip()
            if not text:
                self.send_json(400, {"error": "text is required."})
                return
            try:
                from thursday.voice_output import KENN_VOICE, synthesise_isolated
                wav = synthesise_isolated(text, voice=KENN_VOICE)
            except Exception as exc:
                self.send_json(500, {"error": f"Speech synthesis failed: {exc}"})
                return
            if wav is None:
                self.send_json(503, {"error": "TTS unavailable."})
                return
            self.send_bytes(200, wav, "audio/wav")
            return
        if parsed.path == "/api/ableton/apply-repair":
            self.send_json(410, {"ok": False, "error": "apply-repair is disabled until every repair operation has a typed, reversible proposal."})
            return
        if parsed.path == "/api/ableton/osc/volume":
            self.handle_safe_live_action("set_volume", payload)
            return
        if parsed.path == "/api/ableton/osc/pan":
            self.handle_safe_live_action("set_pan", payload)
            return
        if parsed.path == "/api/ableton/osc/mute":
            self.handle_safe_live_action("set_mute", payload)
            return
        if parsed.path == "/api/ableton/osc/solo":
            self.handle_safe_live_action("set_solo", payload)
            return
        if parsed.path == "/api/ableton/osc/arm":
            self.handle_safe_live_action("set_arm", payload)
            return
        if parsed.path == "/api/ableton/osc/undo":
            from kenn.routes.daw_command_handler import handle_osc_undo
            handle_osc_undo(self, payload)
            return
        if parsed.path == "/api/ableton/osc/transport/play":
            self.handle_safe_live_action("transport_play", payload)
            return
        if parsed.path == "/api/ableton/osc/transport/stop":
            self.handle_safe_live_action("transport_stop", payload)
            return
        if parsed.path == "/api/ableton/osc/tempo":
            self.send_json(410, {"ok": False, "error": "Tempo mutation is disabled until it has a typed, reversible proposal and verified readback."})
            return
        if parsed.path == "/api/ableton/osc/clip/launch":
            self.send_json(410, {"ok": False, "error": "Clip launch is disabled until it has an exact target proposal and verified readback."})
            return
        if parsed.path == "/api/ableton/osc/scene/launch":
            self.send_json(410, {"ok": False, "error": "Scene launch is disabled until it has an exact target proposal and verified readback."})
            return
        if parsed.path == "/api/mix-version/save":
            session_id = str(payload.get("session_id", "")).strip()
            version_label = str(payload.get("version_label", "")).strip()
            metrics = payload.get("metrics", {})
            repair_chain = payload.get("repair_chain", {})
            if session_id and version_label:
                save_mix_version(session_id, version_label, metrics, repair_chain)
                self.send_json(200, {"ok": True, "message": "Mix version saved"})
            else:
                self.send_json(400, {"ok": False, "error": "Missing session_id or version_label"})
            return
        if parsed.path == "/api/feedback":
            if not self.enforce_rate_limit("feedback"):
                return
            self.handle_feedback(payload)
            return
        if parsed.path == "/api/session/feedback":
            if not self.enforce_rate_limit("feedback"):
                return
            self.handle_session_feedback(payload)
            return
        if parsed.path == "/api/session/clear":
            session_id = str(payload.get("id", "")).strip()
            if session_id:
                from kenn.core import answer_upgrades
                from kenn.core.confirmation import revoke_session_confirmations
                from kenn.core.session_context import forget_live_conversation

                answer_upgrades.invalidate(session_id)
                clear_session(session_id)
                revoke_session_confirmations(session_id=session_id)
                forget_live_conversation(session_id)
                self.send_json(200, {"ok": True, "message": f"Session {session_id} cleared."})
            else:
                self.send_json(400, {"error": "Missing session id."})
            return
        if parsed.path == "/api/mix-review-step":
            self.handle_mix_review_step(payload)
            return
        if parsed.path == "/api/audiogen/generate":
            if not self.enforce_rate_limit("audiogen"):
                return
            self.handle_audiogen_generate(payload)
            return
        if parsed.path == "/api/audiogen/render-song":
            if not self.enforce_rate_limit("audiogen"):
                return
            self.handle_audiogen_render_song(payload)
            return
        if parsed.path in {"/api/midi/detect_scale", "/kenn/api/midi/detect_scale"}:
            from kenn.routes.midi_handler import handle_post_midi_detect_scale
            handle_post_midi_detect_scale(self, payload)
            return
        if parsed.path in {"/api/midi/groove", "/kenn/api/midi/groove"}:
            from kenn.routes.midi_handler import handle_post_midi_groove
            handle_post_midi_groove(self, payload)
            return
        if parsed.path in {"/api/midi/bassline", "/kenn/api/midi/bassline"}:
            from kenn.routes.midi_handler import handle_post_midi_bassline
            handle_post_midi_bassline(self, payload)
            return
        question = str(payload.get("question", "")).strip()
        if not question:
            self.send_json(400, {"error": "Question is required."})
            return
        _ask_t0 = time.perf_counter()
        # send_json logs which route answered and how long it took, whichever of the exits below replies.
        self._ask_started = _ask_t0
        self._ask_turn = (str(payload.get("session_id", "")), question)
        if not self.enforce_rate_limit("ask"):
            return
        from kenn.core import answer_upgrades

        session_id = payload.get("session_id")
        session_id = session_id.strip() if isinstance(session_id, str) else ""
        if len(session_id) > 128:
            session_id = ""
        plugin_session_id = payload.get("plugin_session_id")
        plugin_session_id = plugin_session_id.strip() if isinstance(plugin_session_id, str) else ""
        if len(plugin_session_id) > 128:
            plugin_session_id = ""
        payload = {**payload, "session_id": session_id, "plugin_session_id": plugin_session_id}
        upgrade_turn = answer_upgrades.begin_turn(session_id) if session_id else ""

        def send_shortcut_reply(result):
            # Shortcuts bypass the knowledge engine's final turn check; a late proposal must not reach this chat.
            if upgrade_turn and not answer_upgrades.is_current_turn(session_id=session_id, turn_id=upgrade_turn):
                from kenn.core.confirmation import revoke_confirmation

                # The proposal may have issued its token after Cancel revoked the chat's earlier cards.
                # Retire only this discarded card so a newer turn's confirmation stays usable.
                revoke_confirmation(result.get("confirmation_token"), session_id=session_id)
                correlation_id = str(payload.get("correlation_id", "")).strip() or self.request_id()
                result = augment_payload(
                    {
                        "answer": "", "status": "cancelled", "route": "conversation", "sources": [],
                        "requires_confirmation": False, "answer_delivery_discarded": True,
                        "inference_aborted": False, "session_id": session_id,
                        "plugin_session_id": plugin_session_id, "correlation_id": correlation_id,
                    },
                    question=question, session_id=session_id, correlation_id=correlation_id,
                )
            self.send_json(200, result)

        from kenn.core.live_track_analysis import answer_track_analysis, wants_track_analysis
        from kenn.core.live_analysis_binding import wants_insert_binding

        if (wants_track_analysis(question) or wants_insert_binding(question)) and "plugin_handoff" in payload:
            # An explicit native Ask may carry fresh compact features. The
            # handoff validator rejects raw audio and keeps the same owner key.
            handoff = ingest_live_context(payload["plugin_handoff"], session_id=plugin_session_id or session_id)
            if not handoff.get("ok"):
                self.send_json(400, {"error": handoff.get("error", "Invalid plug-in analysis snapshot.")})
                return
        analysis_reply = answer_track_analysis(
            question, session_id=session_id, plugin_session_id=plugin_session_id,
        )
        if analysis_reply is not None:
            token = analysis_reply.get("confirmation_token")
            if token:
                _PENDING_PROPOSALS[token] = analysis_reply["proposal"]
            augmented = augment_payload(
                analysis_reply, question=question, session_id=session_id,
                correlation_id=self.request_id(),
            )
            for key in ("proposal", "confirmation_token", "requires_confirmation"):
                augmented[key] = analysis_reply[key]
            send_shortcut_reply(augmented)
            return
        live_inspection_reply = self._maybe_handle_live_inspection(
            question, str(payload.get("session_id", "")).strip()
        )
        if live_inspection_reply is not None:
            live_inspection_reply = augment_payload(
                live_inspection_reply,
                question=question,
                session_id=str(payload.get("session_id", "")).strip(),
                correlation_id=self.request_id(),
            )
            send_shortcut_reply(live_inspection_reply)
            return
        generation_reply = self._maybe_handle_midi_generation(
            question, str(payload.get("session_id", "")).strip()
        )
        if generation_reply is not None:
            augmented = augment_payload(
                generation_reply,
                question=question,
                session_id=str(payload.get("session_id", "")).strip(),
                correlation_id=self.request_id(),
            )
            for key in ("proposal", "confirmation_token", "requires_confirmation"):
                augmented[key] = generation_reply[key]
            send_shortcut_reply(augmented)
            return
        live_command_reply = self._maybe_handle_live_command_from_chat(
            question, str(payload.get("session_id", "")).strip()
        )
        if live_command_reply is not None:
            augmented = augment_payload(
                live_command_reply,
                question=question,
                session_id=str(payload.get("session_id", "")).strip(),
                correlation_id=self.request_id(),
            )
            for key in ("proposal", "confirmation_token", "requires_confirmation"):
                augmented[key] = live_command_reply[key]
            send_shortcut_reply(augmented)
            return
        non_request_kind = classify_non_request(question)
        if non_request_kind is not None:
            send_shortcut_reply(augment_payload(
                non_request_reply(non_request_kind),
                question=question,
                session_id=str(payload.get("session_id", "")).strip(),
                correlation_id=self.request_id(),
            ))
            return
        checkpoint_reply = None

        def handle_current_checkpoint_reply():
            nonlocal checkpoint_reply
            checkpoint_reply = self._maybe_handle_checkpoint_reply(question, session_id)

        # A late yes/no must not clear or rate the checkpoint created by the next turn.
        if not answer_upgrades.write_if_current(
            handle_current_checkpoint_reply, session_id=session_id, turn_id=upgrade_turn
        ):
            send_shortcut_reply({})
            return
        if checkpoint_reply is not None:
            send_shortcut_reply(checkpoint_reply)
            return
        tool_reply = self._maybe_run_explicit_tool_trigger(
            question, str(payload.get("session_id", "")).strip()
        )
        if tool_reply is not None:
            send_shortcut_reply(tool_reply)
            return
        project_analysis_reply = self._maybe_handle_project_analysis(question)
        if project_analysis_reply is not None:
            send_shortcut_reply(project_analysis_reply)
            return
        revision_reply = self._maybe_handle_mix_revision(
            question,
            str(payload.get("session_id", "")).strip(),
            str(payload.get("project_id", "")).strip(),
        )
        if revision_reply is not None:
            def attach_current_revision_checkpoint():
                nonlocal revision_reply
                revision_reply = self._maybe_attach_checkpoint(revision_reply, session_id)

            answer_upgrades.write_if_current(
                attach_current_revision_checkpoint, session_id=session_id, turn_id=upgrade_turn
            )
            send_shortcut_reply(revision_reply)
            return
        try:
            limit = int(payload.get("limit", 5))
            history = payload.get("history") if isinstance(payload.get("history"), list) else []
            session_turn = session_context_turn(payload.get("session_context"))
            if session_turn:
                history = [*history, session_turn]
            review_turn = mix_review_context_turn(payload.get("mix_review_context"))
            if review_turn:
                history = [*history, review_turn]
            review_evidence = from_mix_review_context(payload.get("mix_review_context"))
            if review_evidence:
                history = [*history, evidence_history_turn(review_evidence)]
            stem_masking_context = payload.get("stem_masking_context")
            stem_masking_turn = _stem_masking_context_turn(stem_masking_context)
            if stem_masking_turn:
                history = [*history, stem_masking_turn]
            audio_classification_context = payload.get("audio_classification_context")
            audio_classification_turn = _audio_classification_context_turn(audio_classification_context)
            if audio_classification_turn:
                history = [*history, audio_classification_turn]
            session_id = payload["session_id"]
            plugin_session_id = payload["plugin_session_id"]
            mix_review_id = str(payload.get("mix_review_id", "")).strip()[:128]
            stored_review, stored_review_packet = _stored_mix_review_evidence(mix_review_id)
            if stored_review_packet is not None:
                history = [*history, evidence_history_turn(stored_review_packet)]
            correlation_id = str(payload.get("correlation_id", "")).strip() or self.request_id()
            plugin_context_id = plugin_session_id or session_id
            plugin_context = live_context_summary(plugin_context_id) if plugin_context_id else None
            plugin_turn = _plugin_live_context_turn(plugin_context_id, plugin_context)
            if plugin_turn:
                history = [*history, plugin_turn]
            if stored_review is not None and stored_review_packet is not None and isinstance(plugin_context, dict) and plugin_session_id:
                from kenn.core.realtime_mix_comparison import build_realtime_mix_comparison

                realtime_mix_comparison = build_realtime_mix_comparison(
                    stored_review,
                    plugin_context,
                    review_id=mix_review_id,
                    plugin_session_id=plugin_session_id,
                )
                comparison_packet = from_realtime_mix_comparison(realtime_mix_comparison)
                if comparison_packet:
                    history.append(evidence_history_turn(comparison_packet))
            ableton_turn = _ableton_session_context_turn(payload.get("include_ableton_context"))
            if ableton_turn:
                history = [*history, ableton_turn]


            if payload.get("stream"):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache, no-transform")
                self.send_header("X-Accel-Buffering", "no")
                self.send_header("Connection", "keep-alive")
                self.end_headers()


                accumulated_answer = ""
                metadata = {}
                for chunk in answer_payload_stream(
                    question, limit=limit, history=history, session_id=session_id,
                    plugin_session_id=plugin_session_id, correlation_id=correlation_id,
                    request_turn_id=upgrade_turn,
                ):
                    if not self._write_body(
                        f"data: {json.dumps(chunk)}\n\n".encode("utf-8"), flush=True
                    ):
                        return
                    if chunk.get("event") == "token":
                        accumulated_answer += chunk.get("token", "")
                    elif chunk.get("event") == "metadata":
                        metadata = chunk.get("data", {})

                if upgrade_turn and not answer_upgrades.is_current_turn(session_id=session_id, turn_id=upgrade_turn) and not metadata.get("answer_delivery_discarded"):
                    metadata = {
                        "answer": "", "status": "cancelled", "route": "conversation", "sources": [],
                        "requires_confirmation": False, "answer_delivery_discarded": True,
                        "inference_aborted": False, "session_id": session_id,
                        "plugin_session_id": plugin_session_id, "correlation_id": correlation_id,
                    }
                metadata = {
                    **metadata,
                    "answer": str(metadata.get("answer") or "") if "answer" in metadata else accumulated_answer,
                }
                def contract_stream_metadata(data):
                    if data["answer"]:
                        result = augment_payload(
                            data,
                            question=question,
                            session_id=session_id,
                            correlation_id=correlation_id,
                            actor_id="kenn.http.stream",
                        )
                    else:
                        from kenn.core.platform_contracts import CommandEnvelope, ResultEnvelope, ResultStatus

                        # Empty completion retracts provisional text. It is a
                        # terminal result, without a required AssistantResponse body.
                        command = CommandEnvelope.new(
                            capability="kenn.ask", actor_id="kenn.http.stream",
                            payload={"question": question}, correlation_id=correlation_id,
                        )
                        envelope = ResultEnvelope(
                            command_id=command.command_id,
                            status=ResultStatus.CANCELLED if data.get("status") == "cancelled" else ResultStatus.SUCCEEDED,
                            result={"capability": command.capability, **data, "session_id": session_id},
                            correlation_id=command.correlation_id,
                        )
                        result = {
                            **data, "schema_version": envelope.schema_version,
                            "request_id": envelope.command_id, "correlation_id": envelope.correlation_id,
                            "status": envelope.status.value, "error_code": "", "envelope": envelope.to_dict(),
                        }
                    result["requires_confirmation"] = bool(data.get("requires_confirmation"))
                    return result

                contracted_metadata = contract_stream_metadata(metadata)

                def attach_current_context():
                    nonlocal contracted_metadata
                    contracted_metadata = _attach_explicit_audio_evidence(
                        contracted_metadata,
                        review_id=mix_review_id,
                        plugin_session_id=plugin_session_id,
                        review=stored_review,
                        mix_evidence=stored_review_packet,
                        plugin_context=plugin_context,
                    )
                    contracted_metadata = _attach_stem_masking_evidence(
                        contracted_metadata, stem_masking_context
                    )
                    contracted_metadata = _attach_audio_classification_evidence(
                        contracted_metadata, audio_classification_context
                    )
                    contracted_metadata = self._maybe_attach_checkpoint(contracted_metadata, session_id)
                    if demo_feedback:
                        demo_feedback.record_question(
                            str(payload.get("session_id", "")),
                            question,
                            contracted_metadata,
                        )
                if not metadata.get("answer_delivery_discarded"):
                    written = answer_upgrades.write_if_current(
                        attach_current_context, session_id=session_id, turn_id=upgrade_turn,
                    )
                    if not written:
                        metadata = {
                            "answer": "", "status": "cancelled", "route": "conversation", "sources": [],
                            "requires_confirmation": False, "answer_delivery_discarded": True,
                            "inference_aborted": False, "session_id": session_id,
                            "plugin_session_id": plugin_session_id, "correlation_id": correlation_id,
                        }
                        contracted_metadata = contract_stream_metadata(metadata)
                if not self._write_body(
                    f"data: {json.dumps({'event': 'metadata', 'data': contracted_metadata})}\n\n".encode("utf-8")
                ):
                    return
                self._write_body(b'data: {"event": "done"}\n\n', flush=True)
                self.close_connection = True
                return
            else:
                _t_context = time.perf_counter() - _ask_t0
                _t_answer = time.perf_counter()
                if answer_upgrades.enabled():
                    # Both answers use the same chat and plug-in context. Only the
                    # foreground answer records the turn in conversation memory.
                    result = answer_payload(
                        question, limit=limit, history=history, session_id=session_id, allow_llm=False,
                        plugin_session_id=plugin_session_id, correlation_id=correlation_id,
                        request_turn_id=upgrade_turn,
                    )
                    if (
                        result.get("llm_available")
                        and not result.get("proposal")
                        and result.get("intent") not in {"clarify", "out_of_scope", "conversation"}
                    ):
                        upgrade_id = answer_upgrades.start(
                            lambda: answer_payload(
                                question, limit=limit, history=history, session_id=session_id,
                                plugin_session_id=plugin_session_id, correlation_id=correlation_id,
                                request_turn_id=upgrade_turn,
                                record_session=False,
                            ),
                            session_id=session_id, turn_id=upgrade_turn,
                        )
                        if upgrade_id:
                            result["answer_upgrade"] = {"id": upgrade_id, "poll_ms": 2000}
                else:
                    result = answer_payload(
                        question, limit=limit, history=history, session_id=session_id,
                        plugin_session_id=plugin_session_id, correlation_id=correlation_id,
                        request_turn_id=upgrade_turn,
                    )
                _answer_ms = (time.perf_counter() - _t_answer) * 1000
                if plugin_turn:
                    result["live_mix_context"] = plugin_context
                if payload.get("ground_in_set") is True:
                    result = attach_your_set(result, question)
                result = _attach_explicit_audio_evidence(
                    result,
                    review_id=mix_review_id,
                    plugin_session_id=plugin_session_id,
                    review=stored_review,
                    mix_evidence=stored_review_packet,
                    plugin_context=plugin_context,
                )
                result = _attach_stem_masking_evidence(result, stem_masking_context)
                result = _attach_audio_classification_evidence(result, audio_classification_context)
                if demo_feedback and not result.get("answer_delivery_discarded"):
                    def record_current_question():
                        result["question_log"] = demo_feedback.record_question(
                            str(payload.get("session_id", "")), question, result,
                        )
                    answer_upgrades.write_if_current(
                        record_current_question, session_id=session_id, turn_id=upgrade_turn,
                    )
                _t_augment = time.perf_counter()
                result = augment_payload(
                    result,
                    question=question,
                    session_id=session_id,
                    correlation_id=correlation_id,
                )
                if not result.get("answer_delivery_discarded"):
                    def attach_current_checkpoint():
                        nonlocal result
                        result = self._maybe_attach_checkpoint(result, session_id)
                    answer_upgrades.write_if_current(
                        attach_current_checkpoint, session_id=session_id, turn_id=upgrade_turn,
                    )
                _augment_ms = (time.perf_counter() - _t_augment) * 1000
                orch_proposal = (
                    result.get("orchestration", {}).get("result", {}).get("proposal")
                    if isinstance(result.get("orchestration"), dict) else None
                )
                if orch_proposal:
                    result["proposal"] = orch_proposal
                    result["confirmation_token"] = orch_proposal.get("confirmation_token", "")
                    result["requires_confirmation"] = True
                _total_ms = (time.perf_counter() - _ask_t0) * 1000
                timing_stats.record("ask", _total_ms)
                _inner = result.get("timings_ms") or {}
                result["timing"] = {
                    "total_ms": round(_total_ms, 1),
                    "context_build_ms": round(_t_context * 1000, 1),
                    "answer_pipeline_ms": round(_answer_ms, 1),
                    "augment_ms": round(_augment_ms, 1),
                    "postprocess_ms": round(_total_ms - _answer_ms, 1),
                    **{k: v for k, v in _inner.items() if isinstance(v, (int, float))},
                }
                _llm_ms = _inner.get("answer_ms", 0)
                _search_ms = _inner.get("search_ms", 0)
                print(
                    f"KENN ask latency: total={_total_ms:.0f}ms"
                    f" ctx={_t_context * 1000:.0f}ms pipeline={_answer_ms:.0f}ms"
                    f" augment={_augment_ms:.0f}ms"
                    f" llm={_llm_ms:.0f}ms search={_search_ms:.0f}ms",
                    file=sys.stderr, flush=True,
                )
                if not answer_upgrades.is_current_turn(session_id=session_id, turn_id=upgrade_turn) and not result.get("answer_delivery_discarded"):
                    result = {
                        "answer": "", "status": "cancelled", "route": "conversation", "sources": [],
                        "requires_confirmation": False, "answer_delivery_discarded": True,
                        "inference_aborted": False, "session_id": session_id,
                        "plugin_session_id": plugin_session_id, "correlation_id": correlation_id,
                    }
                    result = augment_payload(
                        result, question=question, session_id=session_id, correlation_id=correlation_id,
                    )
                self.send_json(200, result)
        except (SystemExit, ValueError) as exc:
            self.send_json(500, {"error": str(exc)})
        except Exception as exc:
            self.send_json(500, {"error": f"Request failed: {exc}"})

    def handle_feedback(self, payload: dict) -> None:
        from kenn.routes.feedback_handler import handle_feedback
        handle_feedback(self, payload)

    def handle_session_feedback(self, payload: dict) -> None:
        from kenn.routes.feedback_handler import handle_session_feedback
        handle_session_feedback(self, payload)

    def handle_audition_feedback(self, payload: dict) -> None:
        from kenn.routes.feedback_handler import handle_audition_feedback
        handle_audition_feedback(self, payload)

    def handle_audiogen_status(self) -> None:
        from kenn.routes.audiogen_handler import handle_audiogen_status
        handle_audiogen_status(self, audiogen_bridge)

    def handle_audiogen_history(self, parsed) -> None:
        from kenn.routes.audiogen_handler import handle_audiogen_history
        handle_audiogen_history(self, audiogen_bridge, parsed)

    def handle_audiogen_job(self, parsed) -> None:
        from kenn.routes.audiogen_handler import handle_audiogen_job
        handle_audiogen_job(self, audiogen_bridge, parsed)

    def handle_audiogen_generate(self, payload: dict) -> None:
        from kenn.routes.audiogen_handler import handle_audiogen_generate
        handle_audiogen_generate(self, audiogen_bridge, payload)

    def handle_audiogen_midi_proposal(self, payload: dict) -> None:
        """Generate symbolic AudioGen events and make a Live proposal.

        AudioGen generation is allowed here, but the Live side remains
        proposal-only.  The generated events are converted into a digest-bound
        artifact and then go through the same exact-target MIDI service as any
        other source.
        """
        from kenn.routes.audiogen_handler import handle_audiogen_midi_proposal
        handle_audiogen_midi_proposal(self, audiogen_bridge, payload)

    @staticmethod
    def _portfolio_audio_bytes(reference: object) -> tuple[bytes, str] | None:
        """Resolve only an opaque local portfolio URL, never an arbitrary path."""
        from kenn.routes.audiogen_handler import _portfolio_audio_bytes
        return _portfolio_audio_bytes(reference)

    def handle_audiogen_audio_compare(self, payload: dict) -> None:
        """Compare two KENN-served AudioGen WAV candidates in memory."""
        from kenn.routes.audiogen_handler import handle_audiogen_audio_compare
        handle_audiogen_audio_compare(self, payload)

    def handle_audiogen_render_song(self, payload: dict) -> None:
        from kenn.routes.audiogen_handler import handle_audiogen_render_song
        handle_audiogen_render_song(self, audiogen_bridge, payload)

    def _maybe_handle_checkpoint_reply(self, question: str, session_id: str) -> dict | None:
        """D2.4 (docs/KENN_FUTURE_PLAN.md Phase 2), incoming half: if the
        previous KENN reply attached a listening checkpoint
        (_maybe_attach_checkpoint below) and this message reads as a
        short yes/no-shaped reply to it, intercept before normal dispatch
        and log accept/reject instead of treating it as a new question.
        The checkpoint is cleared unconditionally here, matched or not --
        it only ever gets one chance to intercept the very next reply, so
        a stale checkpoint can never misinterpret a much later unrelated
        "yes". Checked FIRST, before the mix-revision/tool-trigger checks,
        since "yes"/"no" alone would never match either of those anyway."""
        if not session_id:
            return None
        try:
            from kenn.core.session_memory import clear_pending_checkpoint, get_pending_checkpoint
            checkpoint = get_pending_checkpoint(session_id)
            if not checkpoint:
                return None
            from kenn.core.listening_checkpoint import classify_checkpoint_reply
            verdict = classify_checkpoint_reply(question)
            clear_pending_checkpoint(session_id)
            if verdict not in {"accept", "reject"}:
                return None
            # §13.6.2 ("applied revisions log -- track what KENN applied +
            # whether you kept it"), added 2026-08-08: if this checkpoint
            # was tied to a real project_revision_history row, persist
            # the outcome so it's queryable later, not just a one-off
            # chat reply that vanishes. Best-effort -- a storage failure
            # here must never block the user's yes/no reply itself.
            revision_id = checkpoint.get("revision_history_id")
            if revision_id:
                try:
                    from song_projects import record_revision_outcome
                    record_revision_outcome(revision_id, "kept" if verdict == "accept" else "reverted")
                except Exception:
                    pass
            if verdict == "accept":
                return {
                    "answer": "Great — keeping it. Let me know if you want to change anything else.",
                    "checkpoint_response": "accepted",
                    "found": True,
                    "confidence": "high",
                    "route": "listening_checkpoint",
                }
            return {
                "answer": "Got it — let's try something else. Tell me what direction you'd like instead.",
                "checkpoint_response": "rejected",
                "found": True,
                "confidence": "high",
                "route": "listening_checkpoint",
            }
        except Exception:
            return None

    def _maybe_attach_checkpoint(self, result: dict, session_id: str) -> dict:
        """D2.4, outgoing half: if this response just proposed a concrete,
        inferred change (see listening_checkpoint.detect_concrete_proposal),
        remember it for the next turn and surface it as a distinct
        `listening_checkpoint` field -- deliberately NOT baked into
        `answer` text, since the default chat send streams tokens
        (app.js sends `stream: true`) and the frontend prefers the
        accumulated streamed text over the final metadata event's
        `answer` field, so text appended only to `answer` here would
        never actually render. A separate field survives both the
        streaming and non-streaming paths identically (same pattern as
        `contains_unvalidated_suggestions`)."""
        if not session_id or not isinstance(result, dict):
            return result
        try:
            from kenn.core.listening_checkpoint import detect_concrete_proposal
            description = detect_concrete_proposal(result)
            if description:
                from kenn.core.session_memory import remember_pending_checkpoint
                remember_pending_checkpoint(session_id, description, result.get("revision_history_id"))
                result["listening_checkpoint"] = description
        except Exception:
            pass
        return result

    def _maybe_run_explicit_tool_trigger(self, question: str, session_id: str) -> dict | None:
        """Explicit-only tool routing from chat (Jack's decision, 2026-08-05
        -- docs/KENN_HUB_UNIFICATION_PLAN_2026-08-05.md Phase 3): if the
        message unambiguously asks to run a registered tool AND this
        session already has a resolvable single-file project source, run
        it and return a chat-shaped {answer, ...} reply. Returns None (fall
        through to the normal answer pipeline) only when there's genuinely
        no explicit trigger, or no project at all yet -- never raises,
        never blocks a normal answer.

        Only run_mix_review/run_stem_separation are wired here --
        run_automix needs a resolved STEM SET, not the single-file source
        this resolves; still an open follow-up, see the plan doc.

        Real finding, not assumed (2026-08-05, live-tested against a real
        commercial track): mix_reviews' source WAV is deleted right after
        analysis (see project_source.py's own docstring), so a genuinely
        common sequence -- "review this" then, moments later, "separate
        this into stems" -- has a project_id but no resolvable file.
        Silently falling through used to land on a generic, unrelated
        "upload your file" sub-agent response that doesn't explain why it's
        asking again despite the user just having uploaded something. Now
        answered directly instead."""
        try:
            from kenn.core.tool_trigger import detect_tool_trigger
            tool_name = detect_tool_trigger(question)
            if tool_name not in {"run_mix_review", "run_stem_separation", "run_automix"}:
                return None
            project_id = get_remembered_automix_project(session_id) if session_id else ""
            if not project_id:
                return None
            from kenn.core.tool_registry import invoke_tool

            if tool_name == "run_automix":
                # G3 (docs/KENN_IMPROVEMENT_PLAN.md): unlike
                # run_mix_review/run_stem_separation, run_automix needs a
                # resolved STEM SET, not a single-file source --
                # previously only reachable via a direct file attachment
                # (handle_ask_attachment), never a plain "run automix on
                # this" text trigger, even when a completed separation
                # already exists for this project.
                import stem_separation_bridge
                files = stem_separation_bridge.resolve_stem_files_for_project(project_id)
                if not files:
                    return {
                        "answer": (
                            "I don't have a separated stem set for this project yet. "
                            "Ask me to separate this into stems first, then ask again once that's done."
                        ),
                        "tool_invoked": None,
                    }
                result = invoke_tool(tool_name, session_id=session_id, files=files, project_id=project_id)
                return _build_tool_answer(tool_name, result, "")

            from kenn.core.project_source import resolve_project_source_audio
            source = resolve_project_source_audio(project_id)
            if source is None:
                return {
                    "answer": (
                        "I don't have a file to work with anymore for this project "
                        "(the source audio isn't kept around indefinitely). "
                        "Attach the track directly here, or use the upload panel, and I'll run it."
                    ),
                    "tool_invoked": None,
                }
            file_bytes, filename = source
            extra_kwargs = {}
            if tool_name == "run_stem_separation":
                # D3.3 (docs/KENN_FUTURE_PLAN.md Phase 3): "separate this
                # into stems, then automix it" -- chain straight into a
                # real AutoMix job once separation finishes.
                import stem_separation_bridge
                extra_kwargs["chain_to_automix"] = stem_separation_bridge.requests_automix_chain(question)
            result = invoke_tool(
                tool_name,
                session_id=session_id,
                file_bytes=file_bytes,
                filename=filename,
                project_id=project_id,
                **extra_kwargs,
            )
        except Exception as exc:
            return {"answer": f"Sorry, I couldn't do that: {exc}", "tool_invoked": None}
        return _build_tool_answer(tool_name, result, filename)

    def _maybe_handle_project_analysis(self, question: str) -> dict | None:
        """Route recognised Live-project questions to deterministic analysers.

        This intentionally precedes the general RAG/LLM answer path: the
        model may explain a report later, but cannot invent measurements the
        bridge never supplied.
        """
        try:
            from kenn.mixing_doctor import get_latest_session_state
            from kenn.project_analysis import (
                detect_project_analysis_request,
                format_analysis_answer,
                project_health_report,
                project_manager_report,
                analyze_arrangement,
                creative_suggestions_for_selected_track,
                normalize_session,
            )

            kind = detect_project_analysis_request(question)
            if kind is None:
                return None
            session = get_latest_session_state()
            report = project_manager_report(session) if kind == "project_manager" else project_health_report(session)
            if kind == "arrangement":
                report["recommendations"] = [item.payload() for item in analyze_arrangement(normalize_session(session))]
                report["summary"]["recommendation_count"] = len(report["recommendations"])
            if kind == "creative":
                report["recommendations"] = [
                    item.payload() for item in creative_suggestions_for_selected_track(normalize_session(session))
                ]
                report["summary"]["recommendation_count"] = len(report["recommendations"])
            if kind == "plugin_optimizer":
                report["recommendations"] = [
                    item for item in report["recommendations"] if item["category"] == "plugin_optimisation"
                ]
            return {"answer": format_analysis_answer(kind, report), "project_analysis": report, "route": kind}
        except Exception as exc:
            return {"answer": f"I couldn't analyse the current Ableton project: {exc}", "route": "project_analysis"}

    def _maybe_handle_mix_revision(self, question: str, session_id: str, project_id: str) -> dict | None:
        """Real gap found live 2026-08-06: `is_mix_revision_request()` +
        the actual queue_revision() dispatch (`_handle_mix_revision()` in
        business/app/ableton_bridge.py) were built and tested this same
        session, but only ever reachable via business/app's OWN
        `/api/ableton/ask` route (a separate dashboard chat surface, port
        8080) -- KENN's own `/api/ask` (this file, port 8090, what the
        actual KENN chat UI calls) never checked for a mix-revision
        request at all. Verified live: "make the vocals warmer" through
        this server just returned generic RAG advice about vocal comping,
        no revision job queued. `ableton_bridge.py` already imports
        `kenn.core.*` (no circular import risk the other direction), and
        server.py already imports business/app modules directly
        in-process (automix_jobs, song_projects) the same way. Returns
        None (fall through to the normal answer pipeline) for anything
        that isn't a mix-revision request -- never intercepts a normal
        question.

        Found via a security review 2026-08-08: this dispatch bypassed
        `action_allowed("daw_control")` entirely -- unlike every other
        write-capable action reachable from this same unauthenticated
        `/api/ask` (mute/solo/volume/tempo/macro/scene creation, all
        checked via `_daw_write_denied()` inside their own tool
        functions), a mix-revision request could queue a real AutoMix
        render job for any `project_id` in the request body with zero
        gate at all -- previously this code only ever ran behind
        business/app's session-cookie-protected dashboard route, so it
        never needed its own gate; making it reachable from here removed
        that implicit protection without replacing it. Same class of bug
        as the one fixed 2026-08-06 for the autonomous-agent tool
        functions (see `_daw_write_denied()`'s own docstring)."""
        try:
            from kenn.core.mix_revision_intent import is_mix_revision_request
            if not is_mix_revision_request(question):
                return None
            if not action_allowed("daw_control"):
                return {"answer": action_denied_message("daw_control"), "found": False, "route": "revise_mix"}
            import ableton_bridge
            resolved_project_id = project_id or (resolve_session_project(session_id) if session_id else "")
            return ableton_bridge._handle_mix_revision(
                question, session_id=session_id, project_id=resolved_project_id
            )
        except ImportError:
            return None

    def handle_ask_attachment(self) -> None:
        """POST /api/ask-attachment: a chat message with one or more audio
        files attached directly in the composer, instead of the separate
        upload widget. Jack's decision (2026-08-05): explicit phrase
        required, same rule as text-only chat triggers -- attaching a file
        with no matching instruction gets a clarifying question back, not a
        guess at what to do with it."""
        from kenn.routes.upload_handler import handle_ask_attachment
        handle_ask_attachment(self)

    def handle_mix_review_step(self, payload: dict) -> None:
        from kenn.routes.audio_handler import handle_mix_review_step
        handle_mix_review_step(self, mix_review, payload)

    def handle_audio_analysis(self, *, include_pink_noise_reference: bool = False) -> None:
        """Analyze one uploaded WAV with the KENN-owned analyzer.

        This endpoint is intentionally separate from the legacy Mix Review
        workflow: it returns the versioned spectral evidence contract and
        never writes audio or calls an external analyzer.
        """
        from kenn.routes.audio_handler import handle_audio_analysis
        handle_audio_analysis(self, include_pink_noise_reference=include_pink_noise_reference)

    def handle_audio_analysis_compare(self) -> None:
        """Compare two WAV analyses without retaining either source file."""
        from kenn.routes.audio_handler import handle_audio_analysis_compare
        handle_audio_analysis_compare(self)

    def handle_mix_review_masking(self) -> None:
        """Analyze frequency-band energy competition across 2+ uploaded stems.

        Deliberately separate from ``handle_mix_review``: masking is a
        question about multiple isolated sources competing for the same
        frequency space, which a single finished mixdown cannot answer, so
        this takes several named stem uploads instead of one mixed file.
        """
        from kenn.routes.audio_handler import handle_mix_review_masking
        handle_mix_review_masking(self)

    def handle_mix_review(self) -> None:
        from kenn.routes.audio_handler import handle_mix_review
        handle_mix_review(self, mix_review)

    def handle_automix_upload(self) -> None:
        """Multiple stem files -> a fresh AutoMix project + a real queued
        job, called directly in-process via business/app/automix_public.py
        (same shared-filesystem import pattern already used here for
        mix_review/audiogen_bridge -- no HTTP proxy to :8080). The job row
        lands in the same SQLite DB the standalone AutoMix worker process
        (main.py worker, launched alongside this server by scripts/serve.py)
        already polls, so it gets picked up and rendered the normal way.
        """
        from kenn.routes.upload_handler import handle_automix_upload
        handle_automix_upload(self, automix_public)

    def handle_stem_separate_upload(self) -> None:
        """One mixed track -> a real Demucs stem-separation job, called
        directly in-process via business/app/stem_separation_bridge.py --
        same shared-filesystem import pattern as handle_automix_upload
        above, not the public/token-gated /api/public/stem-separate path
        (that one's for external callers with no dashboard/KENN session)."""
        from kenn.routes.upload_handler import handle_stem_separate_upload
        handle_stem_separate_upload(self, stem_separation_bridge)

    def handle_mix_reference(self) -> None:
        from kenn.routes.audio_handler import handle_mix_reference
        handle_mix_reference(self, mix_review)

    def handle_mix_reference_json(self) -> None:
        from kenn.routes.audio_handler import handle_mix_reference_json
        handle_mix_reference_json(self, mix_review)

    def serve_static(self, path: str) -> None:
        # Any /kenn or /kenn/... prefix is already stripped by do_GET's
        # _strip_kenn_prefix() before path ever reaches here -- this only
        # ever sees bare paths now (e.g. "/", "/app.js", "/styles.css").
        if path == "/":
            path = "/index.html"
        target = (STATIC_ROOT / path.lstrip("/")).resolve()
        if not str(target).startswith(str(STATIC_ROOT.resolve())) or not target.exists():
            spa_target = (STATIC_ROOT / "index.html").resolve()
            if spa_target.exists() and "." not in Path(path).name:
                target = spa_target
            else:
                self.send_response(404)
                self.end_headers()
                self._write_body(b"Not found")
                return
        body = target.read_bytes()
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self._write_body(body)

    def serve_portfolio_audio(self, path: str) -> None:
        filename = Path(path).name
        for root in PORTFOLIO_AUDIO_ROOTS:
            root = root.resolve()
            target = (root / filename).resolve()
            if str(target).startswith(str(root)) and target.exists() and target.suffix.lower() == ".wav":
                self.send_bytes(200, target.read_bytes(), "audio/wav")
                return
        self.send_json(404, {"error": "Audio file not found."})


def ensure_retrieval_index() -> dict[str, Any]:
    """Report the active index and build a notes-only BM25 index when absent."""
    from kenn.retrieval.build_index import NOTES_DIR, build_index
    from kenn.retrieval.index_store import INDEX_DIR, active_version_dir

    active = active_version_dir(INDEX_DIR)
    if active is not None:
        chunks_path = active / "chunks.jsonl"
        try:
            chunk_count = sum(1 for line in chunks_path.open("r", encoding="utf-8") if line.strip())
        except OSError:
            chunk_count = 0
        state = {
            "status": "loaded",
            "version": active.name,
            "chunk_count": chunk_count,
            "embeddings": (active / "embeddings.npy").is_file(),
        }
        print(
            "Retrieval index: "
            f"{state['version']} ({state['chunk_count']} chunks, "
            f"embeddings={'yes' if state['embeddings'] else 'no'})."
        )
        return state

    print("Retrieval index: no active version; building a notes-only BM25 index.")
    previous_skip = os.environ.get("KENN_SKIP_EMBEDDINGS")
    os.environ["KENN_SKIP_EMBEDDINGS"] = "1"
    try:
        chunks = build_index(
            pdf_dir=NOTES_DIR.parent / ".kenn-no-pdf-source",
            notes_dir=NOTES_DIR,
        )
        active = active_version_dir(INDEX_DIR)
        state = {
            "status": "built",
            "version": active.name if active is not None else "unavailable",
            "chunk_count": len(chunks),
            "embeddings": False,
        }
        print(f"Retrieval index: built {state['version']} with {state['chunk_count']} note chunks.")
        return state
    except BaseException as exc:
        # Indexing is an advisory subsystem.  A missing source directory,
        # contradiction gate, or filesystem failure must not prevent chat or
        # Live control from starting in reduced-quality mode.
        state = {
            "status": "degraded",
            "version": "unavailable",
            "chunk_count": 0,
            "embeddings": False,
            "error": str(exc) or type(exc).__name__,
        }
        print(f"WARNING: retrieval index auto-build failed ({state['error']}); continuing without retrieval context.")
        return state
    finally:
        if previous_skip is None:
            os.environ.pop("KENN_SKIP_EMBEDDINGS", None)
        else:
            os.environ["KENN_SKIP_EMBEDDINGS"] = previous_skip


def main() -> int:
    from log_setup import setup_server_logging

    setup_server_logging("kenn", RUNTIME_ROOT / "logs")
    instance_lock = CompanionInstanceLock()
    try:
        lock_metadata = instance_lock.acquire(host=HOST, port=PORT)
    except CompanionAlreadyRunning as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(
        "KENN companion instance lock acquired "
        f"(PID {lock_metadata['pid']}, {instance_lock.path})."
    )
    try:
        if demo_feedback:
            demo_feedback.init_feedback_table()
        if mix_review:
            mix_review.init_reviews_table()
        ensure_retrieval_index()
        warm_index()
        # Clean up old sessions (>7 days) at startup
        try:
            from kenn.core.session_memory import delete_old_sessions
            deleted = delete_old_sessions()
            if deleted:
                print(f"  Cleaned {deleted} expired session(s) from DB.")
        except Exception:
            pass
        try:
            from kenn.mixing_doctor import start_mixing_doctor
            start_mixing_doctor()
        except Exception as exc:
            print(f"WARNING: failed to start mixing doctor: {exc}")
        # Full Zero-Cold-Start System Pre-Warming in background thread
        def _system_zero_cold_start_warmup():
            # 1. Warm CoreML ONNX embedding graph & SQLite DB
            try:
                from kenn.retrieval.retrieval import embed_text
                embed_text("KENN companion zero cold start warmup")
                from kenn.core.session_memory import get_semantic_cache_hit
                get_semantic_cache_hit("status")
            except Exception as e:
                print(f"[!] CoreML warmup notice: {e}")

            # 2. Apple Silicon MLX local inference pre-warming & KV-cache pinning
            try:
                from kenn.llm.llm_rewrite import is_enabled as llm_enabled, mlx_selected
                from kenn.llm.mlx_inference_engine import MLXInferenceEngine
                # Only when MLX will actually answer: pinning a model nobody uses takes memory from Live.
                use_mlx = mlx_selected() and llm_enabled()
                if use_mlx and MLXInferenceEngine.is_available():
                    engine = MLXInferenceEngine.get_instance()
                    engine.prewarm(blocking=True)
            except Exception as exc:
                print(f"[!] MLX pre-warming notice: {exc}")

        threading.Thread(target=_system_zero_cold_start_warmup, daemon=True, name="KENN-ZeroColdStart").start()
        class FastThreadingHTTPServer(ThreadingHTTPServer):
            allow_reuse_address = True

            def server_bind(self):
                super().server_bind()
                try:
                    self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                except (AttributeError, OSError):
                    pass

        server = FastThreadingHTTPServer((HOST, PORT), Handler)
        server.daemon_threads = True
        print(f"{APP_NAME} web chat running at http://{HOST}:{PORT}")
        print("Press Ctrl+C to stop.")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")
        finally:
            server.server_close()
        return 0
    finally:
        instance_lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
