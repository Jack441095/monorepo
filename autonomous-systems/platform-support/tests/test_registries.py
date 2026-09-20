"""Tests for tool contracts and both registries."""

import pytest

from nite_ai.capabilities import CapabilityRegistry, ToolRegistry
from nite_ai.contracts import (
    CapabilityDefinition,
    LatencyClass,
    ResultStatus,
    ToolDefinition,
    ToolRequest,
    ToolResult,
)
from nite_ai.errors import AgentError, DuplicateRegistrationError, ErrorCategory, ValidationError
from nite_ai.permissions import ActionRisk, Permission


def test_tool_register_lookup(tool_registry: ToolRegistry, search_tool: ToolDefinition) -> None:
    tool_registry.register(search_tool)
    assert tool_registry.lookup("util.library.search") is search_tool
    assert len(tool_registry) == 1
    assert tool_registry.lookup("util.library.search", version="0.1.0") is search_tool


def test_tool_duplicate_rejected(tool_registry: ToolRegistry, search_tool: ToolDefinition) -> None:
    tool_registry.register(search_tool)
    with pytest.raises(DuplicateRegistrationError):
        tool_registry.register(search_tool)


def test_unknown_tool_rejected(tool_registry: ToolRegistry) -> None:
    with pytest.raises(ValidationError):
        tool_registry.lookup("nope.nada")


def test_capability_register_and_versions(
    capability_registry: CapabilityRegistry, mix_capability: CapabilityDefinition
) -> None:
    capability_registry.register(mix_capability)
    v2 = CapabilityDefinition(
        capability_id="audio.mix.analyze",
        version="1.1.0",
        description="Newer analysis",
    )
    capability_registry.register(v2)
    assert capability_registry.versions("audio.mix.analyze") == ("1.0.0", "1.1.0")
    assert capability_registry.lookup("audio.mix.analyze").version == "1.1.0"
    assert capability_registry.lookup("audio.mix.analyze", "1.0.0") is mix_capability


def test_capability_duplicate_version_rejected(
    capability_registry: CapabilityRegistry, mix_capability: CapabilityDefinition
) -> None:
    capability_registry.register(mix_capability)
    with pytest.raises(DuplicateRegistrationError):
        capability_registry.register(
            CapabilityDefinition(
                capability_id="audio.mix.analyze",
                version="1.0.0",
                description="dup",
            )
        )


def test_capability_risk_requires_permissions() -> None:
    with pytest.raises(ValidationError):
        CapabilityDefinition(
            capability_id="system.file.delete",
            version="1.0.0",
            description="delete files",
            risk=ActionRisk.CRITICAL,
        )


def test_bad_semver_rejected(capability_registry: CapabilityRegistry) -> None:
    with pytest.raises(ValidationError):
        capability_registry.register(
            CapabilityDefinition(
                capability_id="a.b", version="latest", description="bad version"
            )
        )


def test_platform_does_not_import_providers(capability_registry: CapabilityRegistry) -> None:
    """IoC check: provider ids are strings; nothing imports product packages."""
    import sys

    cap = CapabilityDefinition(
        capability_id="workflow.email.draft",
        version="0.1.0",
        description="Thursday-owned example registered via adapter",
        provider_id="thursday.email_service",
    )
    capability_registry.register(cap)
    assert capability_registry.lookup("workflow.email.draft").provider_id == "thursday.email_service"
    imported = {m.split(".")[0] for m in sys.modules}
    assert not (imported & {"thursday", "kenn", "audio_too"})


def test_tool_result_contract(tool_registry: ToolRegistry, search_tool: ToolDefinition) -> None:
    req = ToolRequest(tool_id=search_tool.tool_id, request_id="tr-1")
    ok = ToolResult(request_id="tr-1", status=ResultStatus.SUCCESS, payload={"hits": 3})
    assert ok.ok
    bad = ToolResult(
        request_id="tr-1",
        status=ResultStatus.TIMEOUT,
        error=AgentError(ErrorCategory.TIMEOUT, "exceeded 5s"),
    )
    assert not bad.ok
    with pytest.raises(ValidationError):
        ToolResult(request_id="tr-1", status=ResultStatus.FAILED)


def test_elevated_risk_tool_must_declare_permissions() -> None:
    with pytest.raises(ValidationError):
        ToolDefinition(
            tool_id="sys.exec.command",
            version="1.0.0",
            description="run a command",
            risk=ActionRisk.HIGH,
            permissions=(),
            latency_class=LatencyClass.BACKGROUND,
        )


def test_permissions_queryable_from_registry(
    capability_registry: CapabilityRegistry, mix_capability: CapabilityDefinition
) -> None:
    capability_registry.register(mix_capability)
    found = capability_registry.lookup("audio.mix.analyze")
    assert Permission.PRIVATE_AUDIO in found.permissions
    assert found.risk is ActionRisk.LOW
