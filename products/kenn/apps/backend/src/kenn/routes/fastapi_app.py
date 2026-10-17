"""Modern FastAPI Application for KENN.

Provides type-safe, OpenAPI-documented ASGI entry points for KENN's core services:
- Chat & Grounded Knowledge Retrieval
- Ableton Live 12 Control & Session State
- Mix Review & Reference Matching Engine
- Static Frontend SPA Delivery

Launch with:
    uvicorn kenn.routes.fastapi_app:app --host 127.0.0.1 --port 8090
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, Field

from kenn.routes.chat_routes import (
    handle_ask,
    handle_suggest,
    handle_feedback,
    handle_session_clear,
    handle_get_memory,
    handle_record_preference,
    handle_delete_preference,
    handle_preference_history,
    handle_restore_preference,
    handle_delete_episode,
    handle_clear_memory,
    handle_record_correction,
    handle_get_corrections,
    handle_record_followed_advice,
    handle_get_followed_advice,
    handle_export_session_data,
    handle_reset_session_data,
)
from kenn.routes.daw_routes import handle_confirmation_revoke, handle_live_command, handle_parameter_inspection, handle_parameter_proposal, handle_session_card, handle_osc_undo, handle_offline_scan_proposal, handle_offline_scan_start, handle_offline_scan_status, handle_offline_scan_cancel
from kenn.routes.mix_review_routes import (
    handle_mix_review_status,
    handle_mix_review_report_json,
    handle_mix_review_reference_json,
    handle_reference_preset_download,
)
from kenn.routes.mix_archive_routes import (
    handle_list_mixes,
    handle_get_mix,
    handle_add_mix,
    handle_update_notes,
    handle_add_revision,
    handle_delete_mix,
    handle_export_archive,
    handle_import_archive,
    handle_grade_against_reference,
)
from kenn.core.local_mix_review_service import local_mix_review

app = FastAPI(
    title="KENN Audio Engineering Companion",
    description="Interactive AI Producer & Mixing Engineer Companion for Ableton Live 12",
    version="1.0.0",
)

# CORS
_DEFAULT_ALLOWED_ORIGINS = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:8090",
    "http://localhost:8090",
)
_allowed_origins = tuple(
    origin.strip().rstrip("/")
    for origin in os.environ.get("KENN_ALLOWED_ORIGINS", ",".join(_DEFAULT_ALLOWED_ORIGINS)).split(",")
    if origin.strip() and origin.strip() != "*"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(_allowed_origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

_PENDING_PROPOSALS: dict[str, Any] = {}


# --- Request/Response Models -------------------------------------------------

class AskRequest(BaseModel):
    question: str
    session_id: Optional[str] = ""
    plugin_session_id: Optional[str] = ""
    limit: Optional[int] = 5
    history: Optional[list[dict[str, Any]]] = None
    session_context: Optional[dict[str, Any]] = None


class CommandRequest(BaseModel):
    command: Optional[str] = ""
    session_id: Optional[str] = ""
    confirm_token: Optional[str] = None
    confirmation_token: Optional[str] = None
    proposal: Optional[dict[str, Any]] = None
    idempotency_key: Optional[str] = ""


class UndoRequest(BaseModel):
    session_id: str
    receipt: dict[str, Any]
    proposal: Optional[dict[str, Any]] = None
    confirm_token: Optional[str] = ""
    idempotency_key: Optional[str] = ""


class ConfirmationRevokeRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128, strict=True)
    confirm_token: str = Field(min_length=1, max_length=512, strict=True)


class ReferenceMatchRequest(BaseModel):
    mix_name: Optional[str] = "mix.wav"
    ref_name: Optional[str] = "reference.wav"
    mix_wav_base64: str = Field(..., description="Base64 encoded mix WAV")
    ref_wav_base64: str = Field(..., description="Base64 encoded commercial reference WAV")


class PreferenceRecordRequest(BaseModel):
    session_id: str
    key: str
    value: str
    source_turn_id: Optional[str] = "turn-ui"
    user_statement: Optional[str] = ""


class PreferenceRestoreRequest(BaseModel):
    session_id: str
    preference_id: str


class PreferenceDeleteRequest(BaseModel):
    session_id: str
    key: str


class EpisodeDeleteRequest(BaseModel):
    session_id: str
    episode_id: str


class MemoryClearRequest(BaseModel):
    session_id: str


class CorrectionRecordRequest(BaseModel):
    session_id: str
    user_statement: Optional[str] = ""
    topic: Optional[str] = "general"
    correction_text: str
    source_turn_id: Optional[str] = "turn-ui"


class FollowedAdviceRecordRequest(BaseModel):
    session_id: str
    user_statement: Optional[str] = ""
    action: str
    grade_before: Optional[float] = None
    grade_after: Optional[float] = None
    source_turn_id: Optional[str] = "turn-ui"


class SessionResetRequest(BaseModel):
    session_id: str



# --- Core Endpoints ----------------------------------------------------------

@app.get("/api/health")
async def health():
    from kenn.retrieval.retrieval import retrieval_status

    return {
        "status": "ok",
        "service": "kenn",
        "version": "1.0.0",
        "daw": "Ableton Live 12",
        "subsystems": {"retrieval": retrieval_status()},
    }


@app.post("/api/ask")
async def ask_endpoint(req: AskRequest, request: Request):
    status, result = handle_ask(
        req.model_dump(),
        request_id=f"req-{os.urandom(6).hex()}",
    )
    return JSONResponse(status_code=status, content=result)


@app.get("/api/suggest")
async def suggest_endpoint(q: Optional[str] = ""):
    status, result = handle_suggest(q or "")
    return JSONResponse(status_code=status, content=result)


@app.post("/api/feedback")
async def feedback_endpoint(req: dict[str, Any]):
    status, result = handle_feedback(req)
    return JSONResponse(status_code=status, content=result)


@app.post("/api/session/clear")
async def session_clear_endpoint(req: dict[str, Any]):
    status, result = handle_session_clear(req.get("id") or req.get("session_id") or "")
    return JSONResponse(status_code=status, content=result)


# --- Stage 4 Project Memory & Personalisation Endpoints ---------------------

@app.get("/api/memory")
async def get_memory_endpoint(session_id: str):
    status, result = handle_get_memory(session_id)
    return JSONResponse(status_code=status, content=result)


@app.post("/api/memory/preference")
async def record_preference_endpoint(req: PreferenceRecordRequest):
    status, result = handle_record_preference(req.model_dump())
    return JSONResponse(status_code=status, content=result)


@app.get("/api/memory/preference/history")
async def preference_history_endpoint(session_id: str, key: str | None = None):
    status, result = handle_preference_history(session_id, key)
    return JSONResponse(status_code=status, content=result)


@app.post("/api/memory/preference/restore")
async def restore_preference_endpoint(req: PreferenceRestoreRequest):
    status, result = handle_restore_preference(req.model_dump())
    return JSONResponse(status_code=status, content=result)


@app.delete("/api/memory/preference")
async def delete_preference_endpoint(session_id: str, key: str):
    status, result = handle_delete_preference(session_id, key)
    return JSONResponse(status_code=status, content=result)


@app.delete("/api/memory/episode")
async def delete_episode_endpoint(session_id: str, episode_id: str):
    status, result = handle_delete_episode(session_id, episode_id)
    return JSONResponse(status_code=status, content=result)


@app.post("/api/memory/clear")
async def clear_memory_endpoint(req: MemoryClearRequest):
    status, result = handle_clear_memory(req.session_id)
    return JSONResponse(status_code=status, content=result)


# --- Milestone E7: Remembering the Session Endpoints -------------------------

@app.post("/api/session/correction")
async def record_correction_endpoint(req: CorrectionRecordRequest):
    status, result = handle_record_correction(req.model_dump())
    return JSONResponse(status_code=status, content=result)


@app.get("/api/session/corrections")
async def get_corrections_endpoint(session_id: str, limit: Optional[int] = 32):
    status, result = handle_get_corrections(session_id, limit=limit or 32)
    return JSONResponse(status_code=status, content=result)


@app.post("/api/session/followed-advice")
async def record_followed_advice_endpoint(req: FollowedAdviceRecordRequest):
    status, result = handle_record_followed_advice(req.model_dump())
    return JSONResponse(status_code=status, content=result)


@app.get("/api/session/followed-advice")
async def get_followed_advice_endpoint(session_id: str, limit: Optional[int] = 32):
    status, result = handle_get_followed_advice(session_id, limit=limit or 32)
    return JSONResponse(status_code=status, content=result)


@app.get("/api/session/export")
async def export_session_endpoint(session_id: str):
    status, result = handle_export_session_data(session_id)
    return JSONResponse(status_code=status, content=result)


@app.post("/api/session/reset")
async def reset_session_endpoint(req: SessionResetRequest):
    status, result = handle_reset_session_data(req.session_id)
    return JSONResponse(status_code=status, content=result)



# --- Ableton Live 12 DAW Endpoints -------------------------------------------

@app.post("/api/ableton/command")
async def ableton_command_endpoint(req: CommandRequest):
    status, result = handle_live_command(
        req.model_dump(),
        pending_proposals=_PENDING_PROPOSALS,
    )
    return JSONResponse(status_code=status, content=result)


@app.post("/api/ableton/confirmation/revoke")
async def confirmation_revoke_endpoint(req: ConfirmationRevokeRequest):
    status, result = handle_confirmation_revoke(req.model_dump())
    return JSONResponse(status_code=status, content=result)


@app.post("/api/ableton/parameter/inspect")
def parameter_inspection(payload: dict):
    status, result = handle_parameter_inspection(payload)
    return JSONResponse(status_code=status, content=result)


@app.post("/api/ableton/parameter/proposal")
async def parameter_proposal_endpoint(payload: dict[str, Any]):
    status, result = handle_parameter_proposal(payload)
    return JSONResponse(status_code=status, content=result)


@app.post("/api/ableton/offline-scan/proposal")
async def offline_scan_proposal_endpoint(payload: dict[str, Any]):
    status, result = handle_offline_scan_proposal(payload)
    return JSONResponse(status_code=status, content=result)


@app.post("/api/ableton/offline-scan/start")
async def offline_scan_start_endpoint(payload: dict[str, Any]):
    status, result = handle_offline_scan_start(payload)
    return JSONResponse(status_code=status, content=result)


@app.post("/api/ableton/offline-scan/status")
async def offline_scan_status_endpoint(payload: dict[str, Any]):
    status, result = handle_offline_scan_status(payload)
    return JSONResponse(status_code=status, content=result)


@app.post("/api/ableton/offline-scan/cancel")
async def offline_scan_cancel_endpoint(payload: dict[str, Any]):
    status, result = handle_offline_scan_cancel(payload)
    return JSONResponse(status_code=status, content=result)


@app.get("/api/ableton/session-card")
async def session_card_endpoint():
    status, result = handle_session_card()
    return JSONResponse(status_code=status, content=result)


@app.post("/api/ableton/osc/undo")
async def osc_undo_endpoint(req: UndoRequest):
    status, result = handle_osc_undo(req.model_dump())
    return JSONResponse(status_code=status, content=result)


# --- Mix Review & Reference Matching Endpoints -------------------------------

@app.get("/api/mix-review-status")
async def mix_review_status_endpoint(id: str):
    status, result = handle_mix_review_status(id, local_mix_review)
    return JSONResponse(status_code=status, content=result)


@app.get("/api/mix-review-report/{review_id}.json")
async def mix_review_report_endpoint(review_id: str):
    status, body = handle_mix_review_report_json(review_id, local_mix_review)
    if body is None:
        raise HTTPException(status_code=status, detail="Report not found")
    return Response(content=body, media_type="application/json")


@app.post("/api/mix-review/reference-match")
async def reference_match_endpoint(req: ReferenceMatchRequest):
    status, result = handle_mix_review_reference_json(req.model_dump(), local_mix_review)
    return JSONResponse(status_code=status, content=result)


@app.get("/api/mix-review/reference-preset/{review_id}.adv")
async def reference_preset_endpoint(review_id: str):
    status, adv_bytes, filename = handle_reference_preset_download(review_id, local_mix_review)
    if adv_bytes is None:
        raise HTTPException(status_code=status, detail="EQ preset not found")
    return Response(
        content=adv_bytes,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --- Mix Archive & Reference Library Endpoints (Milestone E6) ----------------

class MixAddRequest(BaseModel):
    producer_id: str
    name: str
    audio_ref: str
    tempo: Optional[float] = 120.0
    genre: Optional[str] = "electronic"
    target_loudness: Optional[float] = -14.0
    session_notes: Optional[str] = ""
    reference_track_ref: Optional[str] = None
    session_id: Optional[str] = None
    initial_grade: Optional[dict[str, Any]] = None
    initial_snapshot: Optional[dict[str, Any]] = None


class MixNotesRequest(BaseModel):
    mix_id: str
    producer_id: str
    session_notes: str


class MixRevisionRequest(BaseModel):
    mix_id: str
    producer_id: str
    what_changed: str
    suggestion_applied: Optional[dict[str, Any]] = None
    analysis_snapshot: Optional[dict[str, Any]] = None
    measured_grade: Optional[dict[str, Any]] = None


class MixGradeReferenceRequest(BaseModel):
    reference_mix_id: str
    producer_id: str
    current_meters: dict[str, Any]
    technical_report: Optional[dict[str, Any]] = None
    request_text: Optional[str] = ""


@app.get("/api/mix-archive/list")
async def mix_archive_list_endpoint(producer_id: str, session_id: Optional[str] = None):
    status, result = handle_list_mixes(producer_id, session_id=session_id)
    return JSONResponse(status_code=status, content=result)


@app.get("/api/mix-archive/mix/{mix_id}")
async def mix_archive_get_endpoint(mix_id: str, producer_id: str):
    status, result = handle_get_mix(mix_id, producer_id)
    return JSONResponse(status_code=status, content=result)


@app.post("/api/mix-archive/add")
async def mix_archive_add_endpoint(req: MixAddRequest):
    status, result = handle_add_mix(req.model_dump())
    return JSONResponse(status_code=status, content=result)


@app.post("/api/mix-archive/notes")
async def mix_archive_notes_endpoint(req: MixNotesRequest):
    status, result = handle_update_notes(req.model_dump())
    return JSONResponse(status_code=status, content=result)


@app.post("/api/mix-archive/revision")
async def mix_archive_revision_endpoint(req: MixRevisionRequest):
    status, result = handle_add_revision(req.model_dump())
    return JSONResponse(status_code=status, content=result)


@app.delete("/api/mix-archive/mix/{mix_id}")
async def mix_archive_delete_endpoint(mix_id: str, producer_id: str):
    status, result = handle_delete_mix(mix_id, producer_id)
    return JSONResponse(status_code=status, content=result)


@app.get("/api/mix-archive/export")
async def mix_archive_export_endpoint(producer_id: str):
    status, result = handle_export_archive(producer_id)
    return JSONResponse(status_code=status, content=result)


@app.post("/api/mix-archive/import")
async def mix_archive_import_endpoint(producer_id: str, payload: dict[str, Any]):
    status, result = handle_import_archive(producer_id, payload)
    return JSONResponse(status_code=status, content=result)


@app.post("/api/mix-archive/grade-reference")
async def mix_archive_grade_reference_endpoint(req: MixGradeReferenceRequest):
    status, result = handle_grade_against_reference(req.model_dump())
    return JSONResponse(status_code=status, content=result)


# --- Milestone E10: Before/After Comparison Endpoints -------------------------

class BeforeAfterCompareRequest(BaseModel):
    before_snapshot: dict[str, Any]
    after_snapshot: dict[str, Any]
    before_grade: Optional[dict[str, Any]] = None
    after_grade: Optional[dict[str, Any]] = None
    lever: Optional[dict[str, Any]] = None
    receipt_id: Optional[str] = None
    session_id: Optional[str] = "default-session"


class BeforeAfterRegradeRequest(BaseModel):
    current_meters: dict[str, Any]
    original_meters: dict[str, Any]
    original_grade: Optional[dict[str, Any]] = None
    technical_report: Optional[dict[str, Any]] = None
    request_text: Optional[str] = ""
    applied_lever: Optional[dict[str, Any]] = None


@app.get("/api/mix/before-after/{receipt_id}")
async def get_before_after_endpoint(receipt_id: str):
    from kenn.core.session_memory import get_before_after_comparison
    comparison = get_before_after_comparison(receipt_id)
    if comparison is None:
        raise HTTPException(status_code=404, detail=f"No comparison found for receipt '{receipt_id}'")
    return JSONResponse(status_code=200, content={"ok": True, "receipt_id": receipt_id, "comparison": comparison})


@app.post("/api/mix/before-after/compare")
async def compare_before_after_endpoint(req: BeforeAfterCompareRequest):
    from kenn.core.suggestion_levers import build_before_after_comparison
    from kenn.core.session_memory import save_before_after_comparison

    comparison = build_before_after_comparison(
        before_snapshot=req.before_snapshot,
        after_snapshot=req.after_snapshot,
        before_grade=req.before_grade,
        after_grade=req.after_grade,
        lever=req.lever,
    )
    if req.receipt_id:
        save_before_after_comparison(
            receipt_id=req.receipt_id,
            session_id=req.session_id or "default-session",
            before_snapshot=req.before_snapshot,
            after_snapshot=req.after_snapshot,
            comparison=comparison,
        )
    return JSONResponse(status_code=200, content={"ok": True, "comparison": comparison})


@app.post("/api/mix/before-after/regrade")
async def regrade_against_original_endpoint(req: BeforeAfterRegradeRequest):
    from kenn.core.suggestion_levers import regrade_against_original

    result = regrade_against_original(
        current_meters=req.current_meters,
        original_meters=req.original_meters,
        original_grade=req.original_grade,
        technical_report=req.technical_report,
        request_text=req.request_text or "",
        applied_lever=req.applied_lever,
    )
    return JSONResponse(status_code=200, content={"ok": True, "result": result})


# --- Curriculum Endpoints (Milestone E8) -------------------------------------


class CurriculumStartRequest(BaseModel):
    session_id: str
    topic_id: str
    current_meters: dict[str, Any]
    current_grade: Optional[dict[str, Any]] = None


class CurriculumEvaluateRequest(BaseModel):
    session_id: str
    current_meters: dict[str, Any]
    current_grade: Optional[dict[str, Any]] = None
    last_applied_lever: Optional[dict[str, Any]] = None


class CurriculumActionRequest(BaseModel):
    session_id: str


@app.get("/api/curriculum/catalog")
async def get_curriculum_catalog_endpoint():
    """Return authored curriculum catalog with verifiable objectives and cited standards."""
    from kenn.core.mix_curriculum import MixCurriculumManager

    manager = MixCurriculumManager()
    catalog = manager.list_catalog()
    return JSONResponse(status_code=200, content={"ok": True, "catalog": catalog})


@app.post("/api/curriculum/start")
async def start_curriculum_lesson_endpoint(req: CurriculumStartRequest):
    """Start a structured mixing curriculum session with objective and starting grade."""
    from kenn.core.mix_curriculum import MixCurriculumManager

    manager = MixCurriculumManager()
    try:
        session = manager.start_lesson(
            session_id=req.session_id,
            topic_id=req.topic_id,
            current_meters=req.current_meters,
            current_grade=req.current_grade,
        )
        return JSONResponse(status_code=200, content={"ok": True, "session": session})
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/curriculum/status")
async def get_curriculum_status_endpoint(session_id: str):
    """Retrieve active curriculum session state, objective, and failed suggestions log."""
    from kenn.core.mix_curriculum import MixCurriculumManager

    manager = MixCurriculumManager()
    session = manager.get_session_status(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"No active curriculum session found for session '{session_id}'",
        )
    return JSONResponse(status_code=200, content={"ok": True, "session": session})


@app.post("/api/curriculum/evaluate")
async def evaluate_curriculum_progress_endpoint(req: CurriculumEvaluateRequest):
    """Evaluate telemetry against active curriculum objective and log failed suggestion gaps."""
    from kenn.core.mix_curriculum import MixCurriculumManager

    manager = MixCurriculumManager()
    result = manager.evaluate_progress(
        session_id=req.session_id,
        current_meters=req.current_meters,
        current_grade=req.current_grade,
        last_applied_lever=req.last_applied_lever,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error", "Evaluation failed"))
    return JSONResponse(status_code=200, content=result)


@app.post("/api/curriculum/pause")
async def pause_curriculum_lesson_endpoint(req: CurriculumActionRequest):
    """Pause an in-progress curriculum lesson without discarding telemetry."""
    from kenn.core.mix_curriculum import MixCurriculumManager

    manager = MixCurriculumManager()
    success = manager.pause_lesson(req.session_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Could not pause: session '{req.session_id}' not found",
        )
    return JSONResponse(status_code=200, content={"ok": True, "status": "paused"})


@app.post("/api/curriculum/resume")
async def resume_curriculum_lesson_endpoint(req: CurriculumActionRequest):
    """Resume a paused curriculum lesson."""
    from kenn.core.mix_curriculum import MixCurriculumManager

    manager = MixCurriculumManager()
    success = manager.resume_lesson(req.session_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Could not resume: session '{req.session_id}' not found",
        )
    return JSONResponse(status_code=200, content={"ok": True, "status": "in_progress"})


@app.post("/api/curriculum/abandon")
async def abandon_curriculum_lesson_endpoint(req: CurriculumActionRequest):
    """Mark curriculum lesson as abandoned while preserving log history."""
    from kenn.core.mix_curriculum import MixCurriculumManager

    manager = MixCurriculumManager()
    success = manager.abandon_lesson(req.session_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Could not abandon: session '{req.session_id}' not found",
        )
    return JSONResponse(status_code=200, content={"ok": True, "status": "abandoned"})


# --- Expert Network Endpoints (Milestone E11) ---------------------------------


class ExpertContributionSubmitRequest(BaseModel):
    contributor_name: str
    credentials: str
    content_type: str
    topic: str
    title: str
    content_markdown: str
    target_standards: Optional[list[str]] = None


class ExpertContributionReviewRequest(BaseModel):
    contribution_id: str
    decision: str
    reviewer_name: str
    feedback: Optional[str] = ""


@app.get("/api/expert-network/contributions")
async def get_expert_contributions_endpoint(
    topic: Optional[str] = None,
    content_type: Optional[str] = None,
):
    """Return vetted, peer-approved expert engineering contributions."""
    from kenn.core.expert_network import ExpertNetworkStore

    store = ExpertNetworkStore()
    contributions = store.list_surfaced_expert_content(
        topic=topic,
        content_type=content_type,
    )
    return JSONResponse(status_code=200, content={"ok": True, "contributions": contributions})


@app.post("/api/expert-network/submit")
async def submit_expert_contribution_endpoint(req: ExpertContributionSubmitRequest):
    """Submit a new expert engineering contribution for peer review."""
    from kenn.core.expert_network import ExpertNetworkStore

    store = ExpertNetworkStore()
    try:
        contrib = store.submit_contribution(
            contributor_name=req.contributor_name,
            credentials=req.credentials,
            content_type=req.content_type,
            topic=req.topic,
            title=req.title,
            content_markdown=req.content_markdown,
            target_standards=req.target_standards,
        )
        return JSONResponse(status_code=201, content={"ok": True, "contribution": contrib})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/expert-network/review")
async def review_expert_contribution_endpoint(req: ExpertContributionReviewRequest):
    """Adjudicate an expert submission. Only approved contributions pass the vetting gate."""
    from kenn.core.expert_network import ExpertNetworkStore

    store = ExpertNetworkStore()
    try:
        contrib = store.review_contribution(
            contribution_id=req.contribution_id,
            decision=req.decision,
            reviewer_name=req.reviewer_name,
            feedback=req.feedback or "",
        )
        return JSONResponse(status_code=200, content={"ok": True, "contribution": contrib})
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/expert-network/history/{contribution_id}")
async def get_expert_history_endpoint(contribution_id: str):
    """Retrieve full version history and cryptographic hashes for an expert contribution."""
    from kenn.core.expert_network import ExpertNetworkStore

    store = ExpertNetworkStore()
    history = store.get_contribution_history(contribution_id)
    if not history:
        raise HTTPException(
            status_code=404,
            detail=f"No revision history found for contribution '{contribution_id}'",
        )
    return JSONResponse(
        status_code=200,
        content={"ok": True, "contribution_id": contribution_id, "history": history},
    )




