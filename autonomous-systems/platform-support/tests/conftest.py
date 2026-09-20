"""Shared test fixtures — synthetic data only, no real user content."""

import pytest

from nite_ai.capabilities import CapabilityRegistry, ToolRegistry
from nite_ai.contracts import CapabilityDefinition, LatencyClass, ToolDefinition
from nite_ai.errors import RetryPolicy
from nite_ai.permissions import ActionRisk, Permission


@pytest.fixture
def capability_registry() -> CapabilityRegistry:
    return CapabilityRegistry()


@pytest.fixture
def mix_capability() -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_id="audio.mix.analyze",
        version="1.0.0",
        description="Analyse a mix and return structured issues",
        permissions=(Permission.READ, Permission.PRIVATE_AUDIO),
        risk=ActionRisk.LOW,
        latency_class=LatencyClass.FAST_ANALYSIS,
        provider_id="kenn.mix_analyzer",
    )


@pytest.fixture
def tool_registry() -> ToolRegistry:
    return ToolRegistry()


@pytest.fixture
def search_tool() -> ToolDefinition:
    return ToolDefinition(
        tool_id="util.library.search",
        version="0.1.0",
        description="Search a local library index",
        timeout_seconds=5.0,
        retry_policy=RetryPolicy(max_attempts=2),
    )
