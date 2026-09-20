"""Typed specialist-agent dispatch envelope tests."""

from __future__ import annotations

from kenn.core.agent_contracts import AgentRequest, AgentResult


def test_agent_request_carries_objective_and_trace() -> None:
    request = AgentRequest.create(
        capability="kenn.agent.mix_reviewer", objective="Review this mix", project_id="project-1", trace_id="trace-1",
    )
    payload = request.to_dict()
    assert payload["schema"] == "kenn.agent-request.v1"
    assert payload["trace_id"] == "trace-1"
    assert payload["project_id"] == "project-1"


def test_agent_result_labels_input_requirement_and_non_evidence_guidance() -> None:
    request = AgentRequest.create(capability="kenn.agent.mix_reviewer", objective="Review")
    result = AgentResult.from_dispatch(request, agent="mix_reviewer", payload={"status": "awaiting_upload"})
    assert result.output_kind == "input_required"
    assert result.warnings == ()

    guidance = AgentResult.from_dispatch(request, agent="mix_reviewer", payload={"status": "completed"})
    assert guidance.output_kind == "agent_response"
    assert "No structured specialist result" in guidance.warnings[0]
