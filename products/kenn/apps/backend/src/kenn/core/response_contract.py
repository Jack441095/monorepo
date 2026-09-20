"""Map KENN domain payloads onto the shared platform response contract."""

from __future__ import annotations

from kenn.core.platform_contracts import (
    AssistantResponse,
    CommandEnvelope,
    ResultEnvelope,
    ResultStatus,
)


def assistant_response_from_payload(payload: dict, *, session_id: str = "") -> AssistantResponse:
    """Build the stable assistant payload while retaining KENN diagnostics as metadata."""
    related = payload.get("related_questions") or []
    suggestions = tuple(
        item if isinstance(item, dict) else {"label": str(item)}
        for item in related
        if item
    )
    metadata = {
        key: payload[key]
        for key in (
            "answer_mode",
            "weak_match",
            "source_quality",
            "diagnostic_reason",
            "turn_id",
            "llm_enhanced",
            "generation_validation",
        )
        if key in payload
    }
    raw_answer = str(payload.get("answer") or "")
    from kenn.core.voice_persona import format_kenn_voice
    formatted_answer = format_kenn_voice(raw_answer, payload)


    return AssistantResponse(
        answer=formatted_answer,
        session_id=session_id,
        intent=str(payload.get("intent") or ""),
        route=str(payload.get("route") or ""),
        service="kenn",
        confidence=str(payload.get("confidence") or "unknown"),
        grounding=dict(payload.get("grounding") or {}),
        sources=tuple(payload.get("sources") or ()),
        suggestions=suggestions,
        metadata=metadata,
    )


def result_envelope_for_payload(
    payload: dict,
    *,
    question: str,
    session_id: str = "",
    correlation_id: str = "",
    actor_id: str = "kenn.http",
) -> ResultEnvelope:
    """Wrap a KENN answer in CommandEnvelope → ResultEnvelope lineage."""
    command = CommandEnvelope.new(
        capability="kenn.ask",
        actor_id=actor_id,
        payload={"question": question},
        correlation_id=correlation_id,
    )
    response = assistant_response_from_payload(payload, session_id=session_id)
    return ResultEnvelope(
        command_id=command.command_id,
        status=ResultStatus.SUCCEEDED,
        result={"capability": command.capability, **response.to_dict()},
        correlation_id=command.correlation_id,
    )


def augment_payload(
    payload: dict,
    *,
    question: str,
    session_id: str = "",
    correlation_id: str = "",
    actor_id: str = "kenn.http",
) -> dict:
    """Return the legacy KENN payload plus its canonical envelope."""
    envelope = result_envelope_for_payload(
        payload,
        question=question,
        session_id=session_id,
        correlation_id=correlation_id,
        actor_id=actor_id,
    )
    return {
        **payload,
        "schema_version": envelope.schema_version,
        "request_id": envelope.command_id,
        "correlation_id": envelope.correlation_id,
        "status": envelope.status.value,
        "error_code": "",
        "requires_confirmation": False,
        "envelope": envelope.to_dict(),
    }
