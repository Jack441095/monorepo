"""Minimal in-process capability/tool registry.

Inversion of control: products register their own implementations; the shared
platform never imports Thursday, KENN, or SLO source. No database, no network,
no discovery — just validated registration and lookup.
"""

from __future__ import annotations

from nite_ai.contracts.capability import CapabilityDefinition, validate_semver
from nite_ai.contracts.tool import ToolDefinition
from nite_ai.errors import DuplicateRegistrationError, ValidationError


class CapabilityRegistry:
    """In-process registry keyed by stable capability id, version-aware."""

    def __init__(self) -> None:
        self._by_id: dict[str, dict[str, CapabilityDefinition]] = {}
        self._order: list[CapabilityDefinition] = []

    def register(self, definition: CapabilityDefinition) -> None:
        versions = self._by_id.setdefault(definition.capability_id, {})
        if definition.version in versions:
            raise DuplicateRegistrationError(
                f"{definition.capability_id}@{definition.version}", kind="capability"
            )
        versions[definition.version] = definition
        self._order.append(definition)

    def lookup(self, capability_id: str, version: str | None = None) -> CapabilityDefinition:
        versions = self._by_id.get(capability_id)
        if not versions:
            raise ValidationError(f"unknown capability: {capability_id}")
        if version is None:
            return max(versions.values(), key=lambda d: _semver_key(d.version))
        if version not in versions:
            raise ValidationError(f"unknown capability version: {capability_id}@{version}")
        return versions[version]

    def versions(self, capability_id: str) -> tuple[str, ...]:
        return tuple(sorted(self._by_id.get(capability_id, {}), key=_semver_key))

    def enumerate(self) -> tuple[CapabilityDefinition, ...]:  # noqa: A003
        return tuple(self._order)

    def available(self) -> tuple[CapabilityDefinition, ...]:
        return tuple(d for d in self._order if d.available)

    def __len__(self) -> int:
        return len(self._order)


class ToolRegistry:
    """In-process registry for ToolDefinitions (single latest version per id)."""

    def __init__(self) -> None:
        self._tools: dict[str, dict[str, ToolDefinition]] = {}

    def register(self, tool: ToolDefinition) -> None:
        versions = self._tools.setdefault(tool.tool_id, {})
        if tool.version in versions:
            raise DuplicateRegistrationError(f"{tool.tool_id}@{tool.version}", kind="tool")
        versions[tool.version] = tool

    def lookup(self, tool_id: str, version: str | None = None) -> ToolDefinition:
        versions = self._tools.get(tool_id)
        if not versions:
            raise ValidationError(f"unknown tool: {tool_id}")
        if version is None:
            return max(versions.values(), key=lambda t: _semver_key(t.version))
        if version not in versions:
            raise ValidationError(f"unknown tool version: {tool_id}@{version}")
        return versions[version]

    def enumerate(self) -> tuple[ToolDefinition, ...]:  # noqa: A003
        return tuple(
            max(v.values(), key=lambda t: _semver_key(t.version)) for v in self._tools.values()
        )

    def __len__(self) -> int:
        return len(self._tools)


def _semver_key(version: str) -> tuple[int, int, int, str]:
    core, *rest = version.split("-", 1)
    major, minor, patch = (int(p) for p in core.split("."))
    # release > pre-release for equal x.y.z
    suffix = "" if not rest else rest[0]
    return (major, minor, patch, "!" if not suffix else suffix)
