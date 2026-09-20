"""Tests for evaluation and telemetry contracts plus JSON Schema exposure."""

import json

import pytest

from nite_ai.contracts.agent import agent_request_json_schema, agent_result_json_schema
from nite_ai.evaluation import (
    EvaluationCase,
    EvaluationKind,
    EvaluationSuite,
    ExpectedOutcome,
    Metric,
    ObservedOutcome,
    MetricDirection,
)
from nite_ai.errors import ValidationError
from nite_ai.telemetry import TaskEvent, TaskEventKind, TraceContext, new_trace_id


def test_evaluation_case_pass_and_fail() -> None:
    case = EvaluationCase(
        case_id="route.mix.1",
        kind=EvaluationKind.ROUTING,
        expected=ExpectedOutcome(status="success", capability_id="audio.mix.analyze"),
    )
    good = case.evaluate(ObservedOutcome(status="success", capability_id="audio.mix.analyze"))
    bad = case.evaluate(ObservedOutcome(status="success", capability_id="audio.stems.split"))
    assert good.passed
    assert not bad.passed and "capability" in bad.failure_reason


def test_failed_result_needs_reason() -> None:
    from nite_ai.evaluation import EvaluationResult

    with pytest.raises(ValidationError):
        EvaluationResult(case_id="c", passed=False)


def test_suite_rejects_duplicate_case_ids() -> None:
    case = EvaluationCase(case_id="same", kind=EvaluationKind.GOLDEN)
    with pytest.raises(ValidationError):
        EvaluationSuite(suite_id="s", cases=(case, case))


def test_metric_direction_recorded() -> None:
    assert Metric("routing_accuracy", 0.93).direction.value == "higher_is_better"
    assert (
        Metric("latency_ms", 120.0, direction=MetricDirection.LOWER_IS_BETTER).direction
        is MetricDirection.LOWER_IS_BETTER
    )


def test_trace_context_and_child() -> None:
    root = TraceContext(trace_id=new_trace_id(), span_id="abcdef0123456789")
    child = root.child(task_id="t-1")
    assert child.trace_id == root.trace_id
    assert child.parent_span_id == root.span_id
    with pytest.raises(ValidationError):
        TraceContext(trace_id="NOT-HEX", span_id="abcdef")


def test_task_event_metadata_only_serialization() -> None:
    ev = TaskEvent(
        event=TaskEventKind.TOOL_CALLED,
        trace_id=new_trace_id(),
        timestamp_epoch=1724300000.0,
        tool_id="util.library.search",
        duration_ms=12.5,
        retry_count=0,
        cache_hit=False,
    )
    d = ev.to_dict()
    text = json.dumps(d, sort_keys=True)
    assert json.loads(text)["event"] == "tool_called"
    # no content-bearing fields exist on the contract at all
    assert not any(k in {"payload", "content", "text"} for k in d)


def test_json_schema_generation() -> dict:
    schema = agent_request_json_schema()
    assert schema["type"] == "object"
    for key in ("request_id", "trace_id", "capability_id"):
        assert key in schema["required"]
    result_schema = agent_result_json_schema()
    assert set(result_schema["properties"]) >= {
        "status",
        "result",
        "evidence",
        "artifacts",
        "warnings",
        "error",
    }
    # schemas must themselves be valid JSON documents
    json.dumps(schema)
    json.dumps(result_schema)
