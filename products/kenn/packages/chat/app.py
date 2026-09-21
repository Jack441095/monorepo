"""Scoped, retrieval-only HTTP surface for KENN mix advice.

This module deliberately imports KENN's real chat core instead of copying it.
By default the engine is this repository's own ``source/`` tree (no external
dependency); this wrapper owns the public boundary, request controls, and
response minimisation.

Importing successfully does not mean the engine can answer questions: the
knowledge index is generated in wrapper-owned runtime storage and must be
built from the approved repository notes before grounded answers are
available. See docs/KENN_BETA_GAP_MATRIX.md.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Literal


from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field


from index_runtime import configure_index_dir


SERVICE_ROOT = Path(__file__).resolve().parent
# SERVICE_ROOT is <product>/packages/chat.
REPO_ROOT = SERVICE_ROOT.parents[1]
# ENGINE_ROOT's default is this repo's own source/ tree (the local
# structural equivalent of the old Audio_Too/studio/kenn outer directory --
# apps/backend/src/kenn/ is the inner "kenn" package, same as .../kenn/kenn/ was).
# This removes the previous hard dependency on an external Audio_Too
# checkout, but importing the engine successfully is not the same as it
# being able to answer questions -- see the module docstring and
# docs/KENN_BETA_GAP_MATRIX.md for the remaining blockers (several
# still-external sibling-module imports reachable only from
# specialist code paths this wrapper seals off).
ENGINE_ROOT = Path(
    os.environ.get(
        "KENN_ENGINE_ROOT",
        str(REPO_ROOT / "apps" / "backend" / "src"),
    )
).expanduser().resolve()
ENGINE_REPO_ROOT = REPO_ROOT

if not ENGINE_ROOT.is_dir():
    raise RuntimeError(f"KENN engine checkout not found at {ENGINE_ROOT}")
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))
if str(ENGINE_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_REPO_ROOT))

# The public service is permanently retrieval-only. Set this before importing
# any KENN module because session_memory and the LLM config read environment
# variables at import or first use.
os.environ["AUDIO_TOO_LLM_ENABLED"] = "0"

runtime_dir = Path(
    os.environ.get("KENN_CHAT_RUNTIME_DIR", str(SERVICE_ROOT / ".runtime"))
).expanduser()
runtime_dir.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("KENN_CHATS_DIR", str(runtime_dir / "chats"))
os.environ.setdefault("KENN_DB_PATH", str(runtime_dir / "kenn.db"))
os.environ.setdefault("KENN_SESSION_FILE", str(runtime_dir / "session.json"))

from kenn.core.chat import (  # noqa: E402
    answer_payload,
    classify_answer_mode,
    query_is_out_of_scope,
    route_query,
)
from kenn.core.chat_routing import business_pricing_query  # noqa: E402
from kenn.core.chat_retrieval import normalized_terms  # noqa: E402

INDEX_DIR_OVERRIDE = os.environ.get("KENN_CHAT_INDEX_DIR")
if INDEX_DIR_OVERRIDE:
    configure_index_dir(Path(INDEX_DIR_OVERRIDE))


MIX_ADVICE_TERMS = {
    "acoustic",
    "arrangement",
    "bass",
    "background noise",
    "buffer",
    "buzz",
    "cardioid",
    "chatter",
    "clip",
    "clipping",
    "compression",
    "compressor",
    "converter",
    "crest factor",
    "cutoff",
    "dynamic eq",
    "dither",
    "distorted",
    "drums",
    "dynamics",
    "eq",
    "effects chain",
    "envelope",
    "expander",
    "expansion",
    "export",
    "fader",
    "filter",
    "freeze",
    "flatten",
    "frequency",
    "frequency-dependent",
    "gain staging",
    "gate",
    "gating",
    "harsh",
    "headroom",
    "harmonics",
    "high-pass",
    "integrated",
    "lufs",
    "meter",
    "measurement",
    "kick",
    "overload",
    "groove",
    "kHz",
    "k-weighting",
    "latency",
    "limiter",
    "listening position",
    "loudness",
    "low end",
    "low mids",
    "master",
    "mastering",
    "masking",
    "microphone",
    "mix",
    "mixing",
    "multiband",
    "mono",
    "mp3",
    "muddy",
    "nearfield",
    "offline",
    "off axis",
    "overhead",
    "phase",
    "pitch",
    "podcast",
    "polarity",
    "printing",
    "recording",
    "reamping",
    "reconstruction",
    "reference",
    "reverb",
    "release",
    "resonance",
    "return",
    "rms",
    "room",
    "sample",
    "sample rate",
    "saturation",
    "sibilance",
    "slope",
    "sine oscillator",
    "singer",
    "snare",
    "streaming",
    "stereo",
    "timing",
    "sub",
    "sustained",
    "tail",
    "threshold",
    "translation",
    "transient",
    "true peak",
    "video",
    "vocal",
    "vocals",
    "width",
    "warp",
    "quantize",
    "dialogue",
    "noise",
    "spectral",
    "clipper",
    "tension",
    "drop",
    "build",
    "808",
    "speaker",
    "phone",
    "marker",
    "pad",
    "fade",
    "repitch",
    "artifact",
}

DISALLOWED_MARKERS = (
    "ableton session",
    "automate my",
    "automate the",
    "autonomous",
    "control my daw",
    "control my session",
    "control the daw",
    "control ableton",
    "create a mix",
    "create music",
    "create a song",
    "create audio",
    "dialogue anchor",
    "generate a mix",
    "generate music",
    "generate audio",
    "launch a clip",
    "launch clip",
    "mix review upload",
    "render my mix",
    "render the mix",
    "run a command",
    "session control",
    "long-form ott",
    "ott loudness",
    "upload",
    "wav file",
    "wwise",
    "unreal engine",
    "unity",
)

DISALLOWED_WORDS = {
    "agent",
    "execute",
    "game",
    "osc",
    "script",
}

RANKING_MARKERS = (
    "which is better",
    "what is best",
    "best plugin",
    "recommend a plugin",
    "favourite",
    "favorite",
)

RANKING_PRODUCT_TERMS = (
    "compressor",
    "daw",
    "eq",
    "limiter",
    "mic",
    "microphone",
    "plugin",
    "plugins",
    "software",
)

RANKING_CUES = (
    "best",
    "better",
    "choose",
    "pick",
    "prefer",
    "recommend",
    "should i use",
    "which of these",
    "would you use",
)

NON_ADVICE_MARKERS = (
    "history of mixing",
    "mix engineer charge",
    "mix engineer salary",
    "mixing engineer charge",
    "mixing engineer salary",
    "recommend a studio",
    "studio recommendation",
    "who invented mixing",
    "write lyrics",
)

DIRECT_ACTION_MARKERS = (
    "apply these mix changes",
    "change my mix",
    "edit my mix",
    "fix my mix",
    "improve my mix",
    "make my mix",
    "mix this for me",
    "mix my song",
    "mix my track",
    "play my mix",
    "process my mix",
    "review my mix",
    "review this mix",
    "run my mix",
    "tell me if it is good",
    "tell me if it's good",
    "work on my mix",
)

ADVICE_INTRO_MARKERS = (
    "advice",
    "explain",
    "how can i",
    "how do i",
    "how should i",
    "show me how",
    "tell me how",
    "tips",
    "what should i",
    "why does",
    "why is",
)

QUERY_EXPANSIONS = (
    (
        ("harsh", "limiting", "mastering"),
        "limiter clipper saturation pre-master mastered print",
    ),
    (
        ("bass", "harmonics", "wide"),
        "low end sub bass stereo width mono compatibility phase",
    ),
    (
        ("frequency-dependent", "nasal"),
        "dynamic eq resonance bell frequency selective vocal",
    ),
    (
        ("reconstructed", "samples"),
        "true peak inter-sample reconstruction PCM meter",
    ),
    (
        ("integrated", "RMS", "LUFS"),
        "integrated loudness K-weighting gating channel measurement",
    ),
    (
        ("AES", "streaming", "recommendation"),
        "streaming loudness platform context specification target limiting",
    ),
)


class HistoryTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1200)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=1200)
    history: list[HistoryTurn] = Field(default_factory=list, max_length=4)


class FixedWindowLimiter:
    """Small single-process limiter suitable for the local service.

    Railway deployment must keep this service single-process or replace this
    with a shared limiter before scaling horizontally.
    """

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._windows: dict[str, list[float]] = {}

    def __call__(self, request: Request) -> None:
        client = request.client.host if request.client else "unknown"
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            timestamps = [stamp for stamp in self._windows.get(client, []) if stamp >= cutoff]
            if len(timestamps) >= self.max_requests:
                raise HTTPException(status_code=429, detail="Too many requests; try again shortly")
            timestamps.append(now)
            self._windows[client] = timestamps

    def reset(self) -> None:
        with self._lock:
            self._windows.clear()


def _positive_int(name: str, default: int, maximum: int) -> int:
    try:
        return max(1, min(maximum, int(os.environ.get(name, str(default)))))
    except ValueError:
        return default


def _positive_float(name: str, default: float, maximum: float) -> float:
    try:
        return max(0.1, min(maximum, float(os.environ.get(name, str(default)))))
    except ValueError:
        return default


def allowed_origins() -> list[str]:
    raw = os.environ.get(
        "KENN_CHAT_ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    )
    origins = [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]
    if not origins or "*" in origins:
        raise RuntimeError("KENN_CHAT_ALLOWED_ORIGINS must be a non-empty explicit list")
    return origins


RATE_LIMITER = FixedWindowLimiter(
    _positive_int("KENN_CHAT_RATE_LIMIT_REQUESTS", 30, 10_000),
    _positive_float("KENN_CHAT_RATE_LIMIT_WINDOW_SECONDS", 60.0, 86_400.0),
)
ENGINE_TIMEOUT_SECONDS = _positive_float("KENN_CHAT_ENGINE_TIMEOUT_SECONDS", 30.0, 120.0)


class _RetrievalOnlyOrchestrator:
    """Null specialist dispatcher for the public text-only boundary."""

    def dispatch(self, *args: Any, **kwargs: Any) -> None:
        return None


_RETRIEVAL_ONLY_ORCHESTRATOR = _RetrievalOnlyOrchestrator()
_ENGINE_CALL_LOCK = threading.Lock()

app = FastAPI(title="KENN Mix Advice", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def _normalised_question(question: str) -> str:
    return " ".join(question.split()).strip()


def _contains_mix_advice_term(question: str) -> bool:
    lowered = question.lower()
    if any(term in lowered for term in MIX_ADVICE_TERMS):
        return True
    # Reuse KENN's conservative vocabulary aliases for short, common audio
    # typos (for example ``sidechane bas to kik``). This only widens the
    # public gate when the corrected token is already an approved mix term.
    terms = normalized_terms(question)
    return any(term in terms for term in MIX_ADVICE_TERMS if " " not in term)


def _is_direct_action_request(question: str) -> bool:
    lowered = question.casefold()
    if any(marker in lowered for marker in ADVICE_INTRO_MARKERS):
        return False
    return any(marker in lowered for marker in DIRECT_ACTION_MARKERS)


def _is_ranking_request(question: str) -> bool:
    lowered = question.casefold()
    if any(marker in lowered for marker in RANKING_MARKERS):
        return True
    if "best practice" in lowered or "best way" in lowered:
        return False
    return any(term in lowered for term in RANKING_PRODUCT_TERMS) and any(
        cue in lowered for cue in RANKING_CUES
    )


def _scope_reason(question: str, history: list[dict[str, str]]) -> tuple[bool, str, str]:
    """Return (allowed, route, reason) using KENN routing as the authority."""
    lowered = question.lower()
    history_text = " ".join(str(turn.get("content") or "").lower() for turn in history)
    if any(marker in history_text for marker in ("mix review lab context", "uploaded-track analysis", "kenn_evidence_packet_v1:")):
        return False, "out_of_scope", "This public chat does not accept uploaded-track or live-session evidence."
    if any(marker in lowered for marker in DISALLOWED_MARKERS):
        return False, "out_of_scope", "The public KENN surface does not accept control, upload, or generation requests."
    if any(marker in lowered for marker in NON_ADVICE_MARKERS):
        return False, "out_of_scope", "KENN answers mix-engineering advice, not general or non-technical mix topics."
    if business_pricing_query(question):
        return False, "out_of_scope", "KENN does not provide client pricing or quote policy on the public advice surface."
    if _is_direct_action_request(question):
        return False, "out_of_scope", "The public KENN surface gives mix advice but does not alter or analyse audio."
    if any(word in set(lowered.replace("/", " ").split()) for word in DISALLOWED_WORDS):
        return False, "out_of_scope", "The public KENN surface is limited to text-based mix advice."
    if _is_ranking_request(question):
        return False, "out_of_scope", "KENN does not rank plugins or make taste-based choices."
    if query_is_out_of_scope(question):
        return False, "out_of_scope", "The question is outside KENN's mix-advice scope."

    route = route_query(question, history)
    if route in {"conversation", "clarify", "game_audio", "out_of_scope"}:
        return False, route, "KENN needs a specific, source-backed mix-engineering question."
    if not _contains_mix_advice_term(question) and not _contains_mix_advice_term(history_text):
        return False, route, "KENN answers mix-engineering questions, not general-purpose questions."
    return True, route, ""


def _abstention_payload(question: str, reason: str, route: str = "out_of_scope") -> dict[str, Any]:
    # Keep the public wording narrower than KENN's full local weak-match helper:
    # it must not advertise disallowed Ableton control, uploads, or business
    # workflows from the larger private assistant.
    return {
        "question": question,
        "answer": (
            "I can help with source-backed mix-engineering questions within KENN's approved knowledge. "
            "I can't help with that request here. No audio is uploaded or analysed by this chat."
        ),
        "sources": [],
        "found": False,
        "confidence": "low",
        "source_quality": "low",
        "topics": [],
        "intent": "out_of_scope",
        "route": "out_of_scope",
        "answer_mode": "quick_fix",
        "intent_guard": "not_needed",
        "weak_match": True,
        "diagnostic_reason": reason,
        "llm_enhanced": False,
        "llm_available": False,
        "audio_uploaded": False,
        "scope": "mix_advice_only",
        "routed_from": route,
    }


def _public_sources(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Expose provenance without returning approved-note document contents."""
    public: list[dict[str, Any]] = []
    for source in payload.get("sources") or []:
        if not isinstance(source, dict):
            continue
        public.append(
            {
                key: source[key]
                for key in ("source", "page", "kind", "title", "score", "trust_score", "label")
                if key in source
            }
        )
    return public


def _public_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Reduce the engine result to the website contract and privacy boundary."""
    return {
        "question": payload.get("question", ""),
        "answer": payload.get("answer", ""),
        "sources": _public_sources(payload),
        "found": bool(payload.get("found")),
        "confidence": payload.get("confidence", "low"),
        "source_quality": payload.get("source_quality", "low"),
        "topics": payload.get("topics") or [],
        "intent": payload.get("intent", ""),
        "route": payload.get("route", ""),
        "answer_mode": payload.get("answer_mode", ""),
        "weak_match": bool(payload.get("weak_match")),
        "diagnostic_reason": payload.get("diagnostic_reason", ""),
        "llm_enhanced": False,
        "llm_available": False,
        "audio_uploaded": False,
        "scope": "mix_advice_only",
    }


def _expanded_retrieval_query(question: str) -> str:
    lowered = question.casefold()
    for required_terms, expansion in QUERY_EXPANSIONS:
        if all(term in lowered for term in required_terms):
            return f"{question} {expansion}"
    return ""


def _scoped_answer_payload(
    question: str,
    history: list[dict[str, str]],
    answer_mode: str,
) -> dict[str, Any]:
    """Call KENN's answer entry point with specialist paths sealed off.

    The preserved engine's answer function also serves Ableton control,
    Mix Review, AudioGen, and specialist-agent requests. The wrapper has
    already rejected explicit requests for those capabilities, but the
    engine's broad keyword router can still classify an ordinary text question
    as a specialist request. Temporarily sealing those imported dispatch hooks
    keeps this product boundary retrieval-only without modifying Audio_Too.
    Calls are serialised because the engine exposes module-level references.
    """
    import kenn.core.chat_answer as chat_answer_module

    def _retrieval_only_route(query: str, route_history: list[dict[str, str]] | None = None) -> str:
        # Preserve the answer-shape distinction between Ableton workflow
        # guidance and general production advice. The public boundary has
        # already rejected control, upload, and generation requests above;
        # retaining the safe ``ableton`` label here cannot execute anything,
        # but prevents an Ableton question from being rendered as a generic
        # mix-diagnosis answer.
        detected = route_query(query, route_history)
        # ``query_topics`` intentionally uses broad aliases, and words such
        # as "dynamics" can contain an Ableton-related token as a substring.
        # Preserve the Ableton answer shape only when the user explicitly
        # names Live/Ableton or a concrete Live concept; otherwise keep the
        # public response in the production-advice shape.
        explicit_live = bool(re.search(
            r"\b(?:ableton|live|midi|clip|scene|warp|automation|arrangement|osc)\b",
            query.casefold(),
        ))
        if detected == "ableton" and explicit_live:
            return "ableton"
        return "production"

    replacements: dict[str, Any] = {
        "get_orchestrator": lambda: _RETRIEVAL_ONLY_ORCHESTRATOR,
        "audio_generation_payload": lambda *args, **kwargs: None,
        "mix_review_timeline_lookup": lambda *args, **kwargs: None,
        "latest_track_memory_lookup": lambda *args, **kwargs: None,
        "mix_review_followup_payload": lambda *args, **kwargs: None,
        "route_query": _retrieval_only_route,
    }
    with _ENGINE_CALL_LOCK:
        originals = {name: getattr(chat_answer_module, name) for name in replacements}
        try:
            for name, replacement in replacements.items():
                setattr(chat_answer_module, name, replacement)
            return answer_payload(
                question,
                limit=4,
                history=history,
                allow_llm=False,
                session_id="",
                answer_mode=answer_mode,
            )
        except SystemExit as exc:
            # chat_retrieval.py raises SystemExit("Index not found...") when
            # no knowledge index is built (this repository currently ships
            # no knowledge content -- see docs/KENN_BETA_GAP_MATRIX.md
            # GAP-03/GAP-11). Never let that reach a request thread as an
            # unhandled process-exit signal; fail into the same honest
            # abstention contract as any other unanswerable question.
            return {
                "question": question,
                "answer": "",
                "sources": [],
                "found": False,
                "weak_match": True,
                "confidence": "low",
                "source_quality": "low",
                "topics": [],
                "intent": "engine_unavailable",
                "route": "out_of_scope",
                "answer_mode": answer_mode,
                "diagnostic_reason": f"KENN's knowledge engine is unavailable in this build: {exc}",
            }
        finally:
            for name, original in originals.items():
                setattr(chat_answer_module, name, original)


def answer_mix_question(question: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    question = _normalised_question(question)
    history = history or []
    allowed, route, reason = _scope_reason(question, history)
    if not allowed:
        return _abstention_payload(question, reason, route)

    mode = classify_answer_mode(question, route, history=history)
    payload = _scoped_answer_payload(question, history, mode)
    expanded_query = _expanded_retrieval_query(question)
    if expanded_query:
        expanded_payload = _scoped_answer_payload(expanded_query, history, mode)
        if (
            expanded_payload.get("found")
            and not expanded_payload.get("weak_match")
            and expanded_payload.get("sources")
        ):
            # Prefer the explicitly expanded intent when one is defined. This
            # prevents a broad specialist note from winning over a more
            # specific approved source. Keep the visitor-facing question
            # original while retaining grounded answer provenance.
            expanded_payload["question"] = question
            payload = expanded_payload
    # KENN's own weak-match gate is authoritative: never turn an ungrounded
    # answer into a public answer merely because the route looked plausible.
    if not payload.get("found") or payload.get("weak_match") or not payload.get("sources"):
        return _abstention_payload(
            question,
            "KENN found no sufficiently strong approved source match, so it abstained.",
            route,
        )
    return _public_payload(payload)


# Ensure mix-review local_engine is in sys.path
MIX_REVIEW_DIR = REPO_ROOT / "packages" / "mix-review" / "core"
if MIX_REVIEW_DIR.is_dir() and str(MIX_REVIEW_DIR) not in sys.path:
    sys.path.insert(0, str(MIX_REVIEW_DIR))

try:
    from local_engine import analyze_wav, UnsupportedAudioError, MAX_UPLOAD_BYTES as LOCAL_ENGINE_MAX_BYTES
except ImportError:
    analyze_wav = None  # Fallback if not importable directly


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(..., min_length=1, max_length=100)
    rating: int = Field(..., ge=1, le=5)
    comments: str = Field(default="", max_length=2000)
    context_type: Literal["chat", "mix_review"] = "chat"


class MixReviewJsonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(default="uploaded.wav", max_length=255)
    audio_base64: str = Field(..., min_length=1)
    mix_goal: str = Field(default="general", max_length=50)


MAX_PUBLIC_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB public limit


@app.middleware("http")
async def add_request_id_middleware(request: Request, call_next: Any) -> Any:
    req_id = request.headers.get("X-Request-ID") or f"req-{uuid.uuid4().hex[:12]}"
    request.state.request_id = req_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = req_id
    return response


@app.get("/health")
def health(request: Request) -> dict[str, Any]:
    from kenn.retrieval.retrieval import retrieval_status

    req_id = getattr(request.state, "request_id", "unknown")
    return {
        "ok": True,
        "status": "ok",
        "service": "kenn-public-api",
        "version": "1.0.0-beta",
        "schema_version": "kenn.public_api.v1",
        "request_id": req_id,
        "scope": "public_beta",
        "retrieval": retrieval_status(),
        "features": {
            "chat": True,
            "mix_review": True,
            "feedback": True,
            "automix": False,
            "stem_separation": False,
            "audio_generation": False,
            "voice_control": False,
            "live_daw_mutation": False,
        },
        "privacy": (
            "Uploaded audio files are analyzed on the server for mix review diagnostics "
            "and are not retained for model training."
        ),
    }


@app.post("/chat")
async def public_chat(request_body: ChatRequest, request: Request, _: None = Depends(RATE_LIMITER)) -> dict[str, Any]:
    req_id = getattr(request.state, "request_id", f"req-{uuid.uuid4().hex[:12]}")
    history = [turn.model_dump() for turn in request_body.history]
    try:
        data = await asyncio.wait_for(
            asyncio.to_thread(answer_mix_question, request_body.question, history),
            timeout=ENGINE_TIMEOUT_SECONDS,
        )
        return {
            "ok": True,
            "request_id": req_id,
            "schema_version": "kenn.public_api.v1",
            "analysis_version": "1.0.0-beta",
            "data": data,
        }
    except TimeoutError:
        raise HTTPException(status_code=504, detail="KENN took too long to answer; please try again") from None


@app.post("/kenn/chat")
async def chat(request_body: ChatRequest, _: None = Depends(RATE_LIMITER)) -> dict[str, Any]:
    history = [turn.model_dump() for turn in request_body.history]
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(answer_mix_question, request_body.question, history),
            timeout=ENGINE_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        raise HTTPException(status_code=504, detail="KENN took too long to answer; please try again") from None



@app.post("/mix-review")
async def mix_review(
    request: Request,
    file: UploadFile = File(None),
    json_body: Optional[MixReviewJsonRequest] = None,
    _: None = Depends(RATE_LIMITER),
) -> dict[str, Any]:
    req_id = getattr(request.state, "request_id", f"req-{uuid.uuid4().hex[:12]}")

    if analyze_wav is None:
        raise HTTPException(status_code=503, detail="Mix Review analysis engine unavailable.")

    file_bytes: bytes = b""
    filename: str = "uploaded.wav"
    mix_goal: str = "general"

    # Handle multipart file upload or JSON payload
    if file is not None and file.filename:
        filename = Path(file.filename.replace("\\", "/")).name
        file_bytes = await file.read()
    elif json_body is not None:
        filename = Path(json_body.filename.replace("\\", "/")).name

        mix_goal = json_body.mix_goal
        try:
            import base64
            file_bytes = base64.b64decode(json_body.audio_base64)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid base64 audio data.")
    else:
        # Try reading raw body if content-type is audio/wav
        body_bytes = await request.body()
        if body_bytes:
            file_bytes = body_bytes
        else:
            raise HTTPException(
                status_code=400,
                detail="Missing WAV audio file. Upload a .wav file via multipart form or base64 JSON payload.",
            )

    if not filename.lower().endswith(".wav"):
        raise HTTPException(
            status_code=400,
            detail="Unsupported file format. Only 16-bit or 24-bit PCM .wav files are supported in the public beta.",
        )

    if len(file_bytes) > MAX_PUBLIC_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Uploaded file exceeds maximum limit of 50 MB ({len(file_bytes)} bytes uploaded).",
        )

    if len(file_bytes) < 44:
        raise HTTPException(status_code=400, detail="File too small to be a valid WAV file.")

    try:
        receipt = await asyncio.wait_for(
            asyncio.to_thread(analyze_wav, file_bytes, filename=filename, mix_goal=mix_goal),
            timeout=60.0,
        )
        if not receipt.get("ok"):
            raise HTTPException(status_code=400, detail=receipt.get("error", "Corrupt or unreadable WAV audio file."))

        receipt["request_id"] = req_id
        return {
            "ok": True,
            "request_id": req_id,
            "schema_version": "kenn.public_api.v1",
            "analysis_version": receipt.get("analysis_version", "kenn.mix_review.local_engine.v1"),
            "receipt": receipt,
        }
    except UnsupportedAudioError as err:
        raise HTTPException(status_code=400, detail=f"Unsupported audio format: {err}")
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Mix Review analysis timed out; please try a shorter audio clip.")
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Mix Review engine failed: {err}")



@app.post("/feedback")
async def feedback(body: FeedbackRequest, request: Request, _: None = Depends(RATE_LIMITER)) -> dict[str, Any]:
    req_id = getattr(request.state, "request_id", f"req-{uuid.uuid4().hex[:12]}")
    feedback_id = f"fb-{uuid.uuid4().hex[:12]}"

    fb_entry = {
        "feedback_id": feedback_id,
        "target_request_id": body.request_id,
        "rating": body.rating,
        "comments": body.comments,
        "context_type": body.context_type,
        "timestamp": time.time(),
    }

    # Store feedback entry
    fb_file = runtime_dir / "feedback.jsonl"
    try:
        import json
        with open(fb_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(fb_entry) + "\n")
    except Exception:
        pass

    return {
        "ok": True,
        "request_id": req_id,
        "feedback_id": feedback_id,
        "status": "received",
    }


@app.get("/eval")
async def eval_receipt(_: None = Depends(RATE_LIMITER)) -> dict[str, Any]:
    """Run the local held-out suites and return only the machine receipt."""
    from eval_runner import run_evaluation

    try:
        return await asyncio.wait_for(asyncio.to_thread(run_evaluation), timeout=120.0)
    except TimeoutError:
        raise HTTPException(status_code=504, detail="KENN evaluation timed out") from None


def reset_rate_limit_for_tests() -> None:
    RATE_LIMITER.reset()
