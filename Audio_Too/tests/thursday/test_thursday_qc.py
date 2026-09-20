"""Tests for thursday.qc (structural validation) and
SubagentRuntime.dispatch_graph(..., qc=True) (validate + bounded repair)."""

from __future__ import annotations

from thursday.qc import QCReport, validate_chain_result
from thursday.subagent_runtime import (
    SubagentResult,
    SubagentRuntime,
    SubagentStatus,
    register_agent,
)
from thursday.taskgraph import TaskGraph, TaskNode


def _ok(agent: str, output: str, metadata: dict | None = None) -> SubagentResult:
    return SubagentResult(agent=agent, command="run", output=output, status=SubagentStatus.SUCCESS, metadata=metadata or {})


def _err(agent: str, error: str) -> SubagentResult:
    return SubagentResult(agent=agent, command="run", output="", status=SubagentStatus.ERROR, error=error)


# ── validate_chain_result: pure structural checks ───────────────────────


def test_all_pass_produces_a_passing_report():
    report = validate_chain_result([_ok("A", "did the thing"), _ok("B", "did another thing")])
    assert isinstance(report, QCReport)
    assert report.passed is True
    assert report.findings == []


def test_empty_artifact_on_success_is_flagged():
    report = validate_chain_result([_ok("A", "fine"), _ok("B", "   ")])
    assert report.passed is False
    assert len(report.findings) == 1
    assert report.findings[0].category == "empty_artifact"
    assert report.findings[0].index == 1


def test_already_failed_nodes_are_not_flagged_by_qc():
    # A hard failure is already reflected in the chain's overall status --
    # QC only inspects nodes that claimed success.
    report = validate_chain_result([_err("A", "boom")])
    assert report.passed is True
    assert report.findings == []


def test_schema_mismatch_missing_keys_is_flagged():
    result = _ok("A", '{"title": "x"}', metadata={"expected_schema": ["title", "summary"]})
    report = validate_chain_result([result])
    assert report.passed is False
    assert report.findings[0].category == "schema_mismatch"
    assert "summary" in report.findings[0].detail


def test_schema_declared_but_output_not_json_is_flagged():
    result = _ok("A", "not json at all", metadata={"expected_schema": ["title"]})
    report = validate_chain_result([result])
    assert report.passed is False
    assert report.findings[0].category == "schema_mismatch"


def test_schema_satisfied_passes():
    result = _ok("A", '{"title": "x", "summary": "y"}', metadata={"expected_schema": ["title", "summary"]})
    report = validate_chain_result([result])
    assert report.passed is True


def test_repairable_indices_matches_finding_positions():
    report = validate_chain_result([_ok("A", "fine"), _ok("B", ""), _ok("C", "fine")])
    assert report.repairable_indices == [1]


# ── dispatch_graph(qc=True): validate + bounded repair integration ─────


def test_dispatch_graph_qc_repairs_an_empty_output_on_retry():
    calls = {"n": 0}

    def flaky_empty_entry(ctx, params):
        calls["n"] += 1
        # First call "succeeds" but with nothing to show for it; second call
        # (the QC repair dispatch) returns real content.
        output = "" if calls["n"] == 1 else "real output now"
        return SubagentResult(agent="QC_Flaky", command="run", output=output, status=SubagentStatus.SUCCESS)

    register_agent("QC_Flaky", flaky_empty_entry)

    graph = TaskGraph()
    graph.add_node(TaskNode(id="a", agent="QC_Flaky"))

    runtime = SubagentRuntime(max_workers=2)
    result = runtime.dispatch_graph(graph, qc=True)

    assert calls["n"] == 2
    assert result.qc_report is not None
    assert result.qc_report.passed is True
    assert result.agent_results[0].output == "real output now"
    assert result.produced_artifacts[0].content == "real output now"


def test_dispatch_graph_qc_leaves_unrepairable_finding_as_a_surfaced_caveat():
    def always_empty_entry(ctx, params):
        return SubagentResult(agent="QC_AlwaysEmpty", command="run", output="", status=SubagentStatus.SUCCESS)

    register_agent("QC_AlwaysEmpty", always_empty_entry)

    graph = TaskGraph()
    graph.add_node(TaskNode(id="a", agent="QC_AlwaysEmpty"))

    runtime = SubagentRuntime(max_workers=2)
    result = runtime.dispatch_graph(graph, qc=True)

    assert result.qc_report is not None
    assert result.qc_report.passed is False
    assert result.qc_report.findings[0].category == "empty_artifact"
    # The node still reports SUCCESS overall (a bad-but-present output isn't
    # a hard chain failure) -- the caveat lives in qc_report, not the status.
    assert result.status == SubagentStatus.SUCCESS


def test_dispatch_graph_without_qc_flag_has_no_qc_report():
    def ok_entry(ctx, params):
        return SubagentResult(agent="QC_Off", command="run", output="fine", status=SubagentStatus.SUCCESS)

    register_agent("QC_Off", ok_entry)

    graph = TaskGraph()
    graph.add_node(TaskNode(id="a", agent="QC_Off"))

    runtime = SubagentRuntime(max_workers=2)
    result = runtime.dispatch_graph(graph)

    assert result.qc_report is None
