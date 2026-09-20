"""Shared evaluation contracts.

Schemas only — no framework, no runner, no mandatory LLM-judge dependency.
Designed to cover unit, golden, routing, tool-selection, agent-completion,
audio-analysis, and human-review evaluation styles via `EvaluationKind`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from nite_ai._serialization import dataclass_to_dict
from nite_ai.contracts.agent import ResultStatus
from nite_ai.errors import ValidationError
from nite_ai.versioning import CONTRACT_SCHEMA_VERSION


class EvaluationKind(str, Enum):
    UNIT = "unit"
    GOLDEN = "golden"
    ROUTING = "routing"
    TOOL_SELECTION = "tool_selection"
    AGENT_COMPLETION = "agent_completion"
    AUDIO_ANALYSIS = "audio_analysis"
    HUMAN_REVIEW = "human_review"


class MetricDirection(str, Enum):
    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"


@dataclass(frozen=True)
class Metric:
    name: str
    value: float
    direction: MetricDirection = MetricDirection.HIGHER_IS_BETTER
    unit: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValidationError("Metric.name must not be empty")


@dataclass(frozen=True)
class ExpectedOutcome:
    """What a case expects. All fields optional; absent fields are unchecked."""

    status: ResultStatus | None = None
    capability_id: str | None = None      # for routing/tool-selection cases
    tool_id: str | None = None
    result_keys: tuple[str, ...] = ()     # required keys in the structured result
    max_warnings: int | None = None

    def matches(self, observed: "ObservedOutcome") -> tuple[bool, str]:
        if self.status is not None and observed.status is not self.status:
            return False, f"status {observed.status} != expected {self.status}"
        if self.capability_id and observed.capability_id != self.capability_id:
            return False, f"capability {observed.capability_id!r} != expected {self.capability_id!r}"
        if self.tool_id and observed.tool_id != self.tool_id:
            return False, f"tool {observed.tool_id!r} != expected {self.tool_id!r}"
        if self.result_keys:
            keys = set((observed.result or {}).keys())
            missing = [k for k in self.result_keys if k not in keys]
            if missing:
                return False, f"result missing keys: {missing}"
        if self.max_warnings is not None and len(observed.warnings) > self.max_warnings:
            return False, f"too many warnings: {len(observed.warnings)} > {self.max_warnings}"
        return True, ""


@dataclass(frozen=True)
class ObservedOutcome:
    status: ResultStatus
    capability_id: str = ""
    tool_id: str = ""
    result: dict[str, Any] | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    kind: EvaluationKind
    input_payload: dict[str, Any] = field(default_factory=dict)
    expected: ExpectedOutcome = ExpectedOutcome()
    tags: tuple[str, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        if not self.case_id:
            raise ValidationError("EvaluationCase.case_id must not be empty")

    def evaluate(self, observed: ObservedOutcome) -> "EvaluationResult":
        passed, reason = self.expected.matches(observed)
        return EvaluationResult(
            case_id=self.case_id,
            passed=passed,
            failure_reason=reason,
            observed=observed,
        )


@dataclass(frozen=True)
class EvaluationResult:
    case_id: str
    passed: bool
    failure_reason: str = ""
    observed: ObservedOutcome | None = None
    metrics: tuple[Metric, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.passed and not self.failure_reason:
            raise ValidationError("failed EvaluationResult must include a failure_reason")

    def to_dict(self) -> dict:
        return dataclass_to_dict(self)


@dataclass(frozen=True)
class EvaluationSuite:
    suite_id: str
    cases: tuple[EvaluationCase, ...] = ()
    schema_version: str = CONTRACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.suite_id:
            raise ValidationError("EvaluationSuite.suite_id must not be empty")
        ids = [c.case_id for c in self.cases]
        if len(ids) != len(set(ids)):
            raise ValidationError("EvaluationSuite contains duplicate case_ids")


__all__ = [
    "EvaluationCase",
    "EvaluationKind",
    "EvaluationResult",
    "EvaluationSuite",
    "ExpectedOutcome",
    "Metric",
    "MetricDirection",
    "ObservedOutcome",
]
