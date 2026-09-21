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

from kenn.routes.chat_routes import handle_ask, handle_suggest, handle_feedback, handle_session_clear
from kenn.routes.daw_routes import handle_live_command, handle_session_card, handle_osc_undo
from kenn.routes.mix_review_routes import (
    handle_mix_review_status,
    handle_mix_review_report_json,
    handle_mix_review_reference_json,
    handle_reference_preset_download,
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


class ReferenceMatchRequest(BaseModel):
    mix_name: Optional[str] = "mix.wav"
    ref_name: Optional[str] = "reference.wav"
    mix_wav_base64: str = Field(..., description="Base64 encoded mix WAV")
    ref_wav_base64: str = Field(..., description="Base64 encoded commercial reference WAV")


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


# --- Ableton Live 12 DAW Endpoints -------------------------------------------

@app.post("/api/ableton/command")
async def ableton_command_endpoint(req: CommandRequest):
    status, result = handle_live_command(
        req.model_dump(),
        pending_proposals=_PENDING_PROPOSALS,
    )
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
