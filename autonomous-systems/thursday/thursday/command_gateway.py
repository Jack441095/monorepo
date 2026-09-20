"""Command/result envelope gateway for Thursday.

Wraps Thursday execution in the versioned ``CommandEnvelope`` → ``ResultEnvelope``
contract (``audio_too.contracts``), propagating the ``correlation_id`` so an entire
workflow can be traced by a single id. This is the typed, machine-facing entry
point; ``orchestrator.handle()`` remains the natural-language one.

Boundary note: this stays inside the Thursday domain — it must not emit business
domain events (that would cross the enforced package boundary). The returned
``ResultEnvelope`` is the typed, correlated output.
"""

from __future__ import annotations

from typing import Callable

# PublicError is vendored locally (see thursday/_compat.py); everything else
# here (CommandEnvelope, ContractError, ResultEnvelope, ResultStatus,
# AssistantResponse) is audio_too's real, versioned command/result contract
# -- a genuine cross-repo integration point, not something safe to fork a
# local copy of. Deferred to a lazy, typed-error import so this module still
# imports cleanly standalone; every function that needs the real contract
# types calls _contracts() first. See docs/EXTRACTION_COUPLING.md.
from thursday._compat import PublicError
from thursday.redaction import get_logger as _get_redacting_logger

DEFAULT_CAPABILITY = "thursday.ask"
logger = _get_redacting_logger(__name__)


class CommandGatewayUnavailable(RuntimeError):
    """Raised when audio_too's command/result contract types aren't installed."""


def _contracts():
    try:
        from audio_too import (
            AssistantResponse,
            CommandEnvelope,
            ContractError,
            ResultEnvelope,
            ResultStatus,
        )
    except ImportError as exc:
        raise CommandGatewayUnavailable(
            "command_gateway requires the audio_too package's contract "
            f"types (not installed): {exc}"
        ) from exc
    return AssistantResponse, CommandEnvelope, ContractError, ResultEnvelope, ResultStatus


class AssistantResultText(str):
    """String-compatible answer carrying optional structured contract fields."""

    assistant_payload: dict

    def __new__(cls, answer: str, payload: dict | None = None):
        instance = super().__new__(cls, answer)
        instance.assistant_payload = dict(payload or {})
        return instance


def command_for_text(
    text: str,
    *,
    capability: str = DEFAULT_CAPABILITY,
    actor_id: str = "dashboard",
    correlation_id: str = "",
    project_id: str = "",
    idempotency_key: str = "",
) -> CommandEnvelope:
    """Build a CommandEnvelope for a natural-language Thursday request."""
    _, CommandEnvelope, _, _, _ = _contracts()
    return CommandEnvelope.new(
        capability=capability,
        actor_id=actor_id,
        payload={"text": str(text or "")},
        correlation_id=correlation_id,
        project_id=project_id,
        idempotency_key=idempotency_key,
    )


def _failed(
    envelope: CommandEnvelope, code: str, message: str, *, retryable: bool = False
) -> ResultEnvelope:
    _, _, ContractError, ResultEnvelope, ResultStatus = _contracts()
    return ResultEnvelope(
        command_id=envelope.command_id,
        status=ResultStatus.FAILED,
        result={},
        correlation_id=envelope.correlation_id,
        error=ContractError(code=code, message=message, retryable=retryable),
    )


def assistant_response_for(
    value: object,
    *,
    session: dict | None = None,
) -> AssistantResponse:
    """Normalize legacy string/dict outputs into the shared assistant contract."""
    AssistantResponse, _, _, _, _ = _contracts()
    if isinstance(value, AssistantResponse):
        return value

    if isinstance(value, dict):
        payload = value
    elif isinstance(value, AssistantResultText):
        payload = {**value.assistant_payload, "answer": str(value)}
    else:
        payload = {"answer": str(value)}
    answer = str(payload.get("answer") or "").strip()
    if not answer:
        answer = "Thursday completed the request but returned no answer."

    session = session or {}
    last_user_turn = next(
        (turn for turn in reversed(session.get("turns", [])) if turn.get("role") == "user"),
        {},
    )
    intent = str(payload.get("intent") or last_user_turn.get("intent") or "")
    service = str(payload.get("service") or last_user_turn.get("service_used") or "")
    metadata = dict(payload.get("metadata") or {})
    for key in ("navigate_url", "navigate_label", "greeting", "turn_id"):
        if payload.get(key) not in (None, ""):
            metadata[key] = payload[key]

    pending_confirmation = session.get("context", {}).get("pending_confirmation")
    if not isinstance(pending_confirmation, dict):
        pending_confirmation = {}
    requires_confirmation = bool(
        payload.get("requires_confirmation", bool(pending_confirmation))
    )
    confirmation_token = str(
        payload.get("confirmation_token") or pending_confirmation.get("token") or ""
    )
    if pending_confirmation:
        metadata.setdefault("confirmation_risk", pending_confirmation.get("risk", ""))
        metadata.setdefault("confirmation_service", pending_confirmation.get("service_id", ""))

    return AssistantResponse(
        answer=answer,
        session_id=str(payload.get("session_id") or session.get("session_id") or ""),
        intent=intent,
        route=str(payload.get("route") or ""),
        service=service,
        confidence=str(payload.get("confidence") or "unknown"),
        grounding=dict(payload.get("grounding") or {}),
        sources=tuple(payload.get("sources") or ()),
        requires_confirmation=requires_confirmation,
        confirmation_token=confirmation_token,
        suggestions=tuple(payload.get("suggestions") or ()),
        metadata=metadata,
    )


def result_for_response(
    envelope: CommandEnvelope,
    response: AssistantResponse,
) -> ResultEnvelope:
    """Wrap a validated assistant response in the platform result envelope."""
    _, _, _, ResultEnvelope, ResultStatus = _contracts()
    return ResultEnvelope(
        command_id=envelope.command_id,
        status=ResultStatus.SUCCEEDED,
        result={"capability": envelope.capability, **response.to_dict()},
        correlation_id=envelope.correlation_id,
    )


def execute_command(
    envelope: CommandEnvelope,
    *,
    session: dict | None = None,
    handle_fn: Callable[..., object] | None = None,
) -> ResultEnvelope:
    """Execute a Thursday command and return a ResultEnvelope (never raises).

    The command's ``correlation_id`` is carried into the result so an entire
    workflow shares one trace id. ``handle_fn`` is injectable for tests; it
    defaults to the orchestrator's natural-language ``handle()``.
    """
    if handle_fn is None:
        from thursday.orchestrator import handle as handle_fn

    text = str(envelope.payload.get("text", "")).strip()
    if not text:
        return _failed(envelope, "invalid_command", "payload.text is required")

    try:
        raw_response = handle_fn(text, session, correlation_id=envelope.correlation_id)
    except PublicError as exc:
        logger.warning(
            "Thursday command rejected correlation_id=%s capability=%s code=%s",
            envelope.correlation_id,
            envelope.capability,
            exc.details.code.value,
        )
        return _failed(
            envelope,
            exc.details.code.value,
            exc.details.message,
            retryable=exc.details.retryable,
        )
    except Exception:  # a command must always resolve to a ResultEnvelope
        logger.exception(
            "Thursday command failed correlation_id=%s capability=%s",
            envelope.correlation_id,
            envelope.capability,
        )
        return _failed(
            envelope,
            "execution_error",
            "Thursday could not complete the request.",
            retryable=True,
        )

    response = assistant_response_for(raw_response, session=session)

    return result_for_response(envelope, response)
