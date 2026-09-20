"""Phase 3-4A tests: adapter layer (IoC, permissions, evidence transport) and context budgeting."""

import sys

import pytest

from nite_ai.adapters import ProductAdapter
from nite_ai.capabilities import CapabilityRegistry
from nite_ai.contracts import (
    AgentRequest,
    AgentResult,
    CapabilityDefinition,
    ConfidenceKind,
    EvidenceItem,
    EvidencePacket,
    ResultStatus,
)
from nite_ai.context import (
    ContextBudget,
    ContextLayer,
    ContextRef,
    build_envelope,
    select_context,
)
from nite_ai.errors import ErrorCategory, ValidationError
from nite_ai.permissions import Permission, PrivacyClass


def thursday_like_capability():
    return CapabilityDefinition(
        capability_id="workflow.status.summary",
        version="0.1.0",
        description="Read-only company status summary (Thursday-owned)",
        permissions=(Permission.READ,),
    )


def kenn_like_capability():
    return CapabilityDefinition(
        capability_id="audio.mix.analyze",
        version="1.0.0",
        description="Mix analysis returning structured evidence (KENN-owned)",
        permissions=(Permission.READ, Permission.PRIVATE_AUDIO),
    )


def make_agent_request(capability_id, granted):
    return AgentRequest(
        request_id=f"req-{capability_id}",
        trace_id="trace-adapter",
        capability_id=capability_id,
        payload={},
        granted_permissions=granted,
    )


def test_adapter_dispatches_and_preserves_ids():
    registry = CapabilityRegistry()
    adapter = ProductAdapter("thursday")
    seen = {}

    def handler(req: AgentRequest) -> AgentResult:
        seen["trace"] = req.trace_id
        return AgentResult(
            request_id=req.request_id, status=ResultStatus.SUCCESS, result={"summary": "ok"}
        )

    adapter.register(registry, thursday_like_capability(), handler)
    result = adapter.dispatch(
        make_agent_request("workflow.status.summary", granted=(Permission.READ,))
    )
    assert result.ok and result.request_id == "req-workflow.status.summary"
    assert seen["trace"] == "trace-adapter"
    # capability is also discoverable via the shared registry
    assert registry.lookup("workflow.status.summary").provider_id is None


def test_adapter_enforces_permissions_and_evidence_survives():
    registry = CapabilityRegistry()
    adapter = ProductAdapter("kenn")

    def mix_handler(req):
        packet = EvidencePacket(
            packet_id="evidence.test.1",
            source="test.mix_review",
            facts=(
                EvidenceItem(
                    name="low_mid_db", value=3.2, unit="dB",
                    confidence_kind=ConfidenceKind.MEASURED, confidence=0.95,
                ),
            ),
        )
        return AgentResult(
            request_id=req.request_id,
            status=ResultStatus.SUCCESS,
            result={"issues": ["LOW_MID_BUILDUP"]},
            evidence=packet,
        )

    adapter.register(registry, kenn_like_capability(), mix_handler)

    denied = adapter.dispatch(make_agent_request("audio.mix.analyze", granted=()))
    assert not denied.ok
    assert denied.error.category is ErrorCategory.PERMISSION_DENIED

    allowed = adapter.dispatch(
        make_agent_request(
            "audio.mix.analyze", granted=(Permission.READ, Permission.PRIVATE_AUDIO)
        )
    )
    # Structured evidence survives transport intact — never collapsed into prose.
    assert allowed.evidence.facts[0].name == "low_mid_db"
    assert allowed.evidence.facts[0].confidence_kind is ConfidenceKind.MEASURED
    assert allowed.result["issues"] == ["LOW_MID_BUILDUP"]


def test_adapter_unknown_capability_structured_failure():
    adapter = ProductAdapter("thursday")
    result = adapter.dispatch(make_agent_request("no.such.cap", granted=()))
    assert result.error.category is ErrorCategory.NOT_SUPPORTED


def test_platform_never_imports_product_modules():
    forbidden = {m for m in sys.modules if m.split(".")[0] in {"thursday", "kenn", "audio_too"}}
    assert not forbidden


def test_context_budget_selection_priority():
    refs = (
        ContextRef(ContextLayer.REQUEST, "req-1", estimated_tokens=100),
        ContextRef(ContextLayer.HISTORY_SUMMARY, "hist-1", estimated_tokens=500),
        ContextRef(ContextLayer.EVIDENCE, "ev-1", estimated_tokens=200),
        ContextRef(ContextLayer.TASK_STATE, "task-1", estimated_tokens=150),
        ContextRef(ContextLayer.RETRIEVED_MEMORY, "mem-1", estimated_tokens=300),
    )
    selected = select_context(refs, ContextBudget(max_total_tokens=460))
    assert [r.ref_id for r in selected] == ["req-1", "task-1", "ev-1"]


def test_context_inline_only_for_request_layer():
    with pytest.raises(ValidationError):
        ContextRef(ContextLayer.EVIDENCE, "e1", payload={"x": 1})


def test_context_secret_payload_rejected():
    with pytest.raises(ValidationError):
        ContextRef(
            ContextLayer.REQUEST, "r1", privacy_class=PrivacyClass.SECRET, payload={"k": "v"}
        )


def test_build_envelope_requires_request_layer():
    with pytest.raises(ValidationError):
        build_envelope((ContextRef(ContextLayer.EVIDENCE, "e1"),), ContextBudget(100))
