"""Small typed envelopes around KENN specialist-agent dispatch.

They intentionally describe routing and execution state, not a fabricated
confidence score or an agent's prose as evidence. Existing specialist payloads
remain backward compatible while callers gain a stable traceable boundary.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _text(value: object, *, limit: int = 2_048) -> str:
    return str(value or "").strip()[:limit]


@dataclass(frozen=True)
class AgentRequest:
    request_id: str
    trace_id: str
    capability: str
    objective: str
    project_id: str = ""
    autonomy_level: str = "suggest"
    created_at: str = field(default_factory=_now)
    schema: str = "kenn.agent-request.v1"

    @classmethod
    def create(cls, *, capability: str, objective: str, project_id: str = "", trace_id: str = "", autonomy_level: str = "suggest") -> "AgentRequest":
        request_id = str(uuid4())
        return cls(
            request_id=request_id,
            trace_id=_text(trace_id, limit=128) or request_id,
            capability=_text(capability, limit=128),
            objective=_text(objective),
            project_id=_text(project_id, limit=128),
            autonomy_level=_text(autonomy_level, limit=32) or "suggest",
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AgentResult:
    request_id: str
    trace_id: str
    agent: str
    status: str
    output_kind: str
    warnings: tuple[str, ...] = ()
    completed_at: str = field(default_factory=_now)
    schema: str = "kenn.agent-result.v1"

    @classmethod
    def from_dispatch(cls, request: AgentRequest, *, agent: str, payload: object) -> "AgentResult":
        result = payload if isinstance(payload, dict) else {}
        status = _text(result.get("status"), limit=64) or "unknown"
        if status in {"failed", "error"}:
            output_kind = "failure"
        elif status in {"awaiting_upload", "needs_input"}:
            output_kind = "input_required"
        elif status:
            output_kind = "agent_response"
        else:
            output_kind = "unknown"
        warnings: list[str] = []
        if status in {"failed", "error"}:
            warnings.append("Specialist dispatch reported a failure; do not treat its message as verified engineering evidence.")
        if result.get("result") is None and output_kind == "agent_response":
            warnings.append("No structured specialist result was returned; this response is guidance or an action prompt.")
        return cls(
            request_id=request.request_id,
            trace_id=request.trace_id,
            agent=_text(agent, limit=128),
            status=status,
            output_kind=output_kind,
            warnings=tuple(warnings),
        )

    def to_dict(self) -> dict:
        return {**asdict(self), "warnings": list(self.warnings)}
