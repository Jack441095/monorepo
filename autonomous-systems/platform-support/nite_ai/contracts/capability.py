"""Capability contracts.

A CapabilityDefinition describes *what* can be done (stable dotted ID like
``audio.mix.analyze``), not who does it or how it is presented. Providers are
referenced by ID only — inversion of control keeps the platform free of
product imports.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from nite_ai._serialization import dataclass_to_dict, json_schema_for
from nite_ai.contracts.agent import validate_capability_id
from nite_ai.contracts.tool import LatencyClass
from nite_ai.errors import ValidationError
from nite_ai.permissions import ActionRisk, Permission, PrivacyClass, validate_risk

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?$")


def validate_semver(version: str) -> None:
    if not _SEMVER_RE.match(version):
        raise ValidationError(f"version must be semver (e.g. '1.0.0'), got {version!r}")


@dataclass(frozen=True)
class CapabilityDefinition:
    """Typed description of a product-provided capability."""

    capability_id: str                      # stable dotted machine id, e.g. audio.mix.analyze
    version: str                            # semver of this capability contract/impl
    description: str                        # for developers/logs — never a UI string id
    input_schema: dict = field(default_factory=dict)
    output_schema: dict = field(default_factory=dict)
    permissions: tuple[Permission, ...] = ()
    risk: ActionRisk = ActionRisk.LOW
    latency_class: LatencyClass = LatencyClass.INTERACTIVE
    max_privacy_class: PrivacyClass = PrivacyClass.USER_TEXT
    provider_id: str | None = None          # e.g. "kenn.mix_analyzer" — reference only
    available: bool = True
    handler: Callable | None = None         # optional in-process IoC hook; never serialized

    def __post_init__(self) -> None:
        validate_capability_id(self.capability_id)
        validate_semver(self.version)
        if not self.description:
            raise ValidationError("CapabilityDefinition.description must not be empty")
        if self.risk.requires_elevated_permissions and not self.permissions:
            raise ValidationError("elevated-risk capabilities must declare permissions")
        try:
            validate_risk(self.risk, self.permissions)
        except ValidationError as exc:
            raise ValidationError(f"capability {self.capability_id}: {exc}") from None

    def to_dict(self) -> dict:
        data = dataclass_to_dict(self)
        data.pop("handler", None)  # callables are never serializable
        return data


def capability_definition_json_schema() -> dict:
    return json_schema_for(CapabilityDefinition)


__all__ = ["ActionRisk", "CapabilityDefinition", "capability_definition_json_schema"]
