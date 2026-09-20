"""Tests for thursday.taskgraph (structure) and SubagentRuntime.dispatch_graph
(dependency-aware, parallel-batch execution)."""

from __future__ import annotations

import time

from thursday.retry import RetryPolicy
from thursday.subagent_runtime import (
    SubagentResult,
    SubagentRuntime,
    SubagentStatus,
    SwarmResult,
    register_agent,
)
from thursday.taskgraph import MAX_GRAPH_NODES, TaskGraph, TaskGraphError, TaskNode


# ── TaskGraph structure ─────────────────────────────────────────────────


def test_topological_batches_linear_chain_is_one_node_per_batch():
    graph = TaskGraph()
    graph.add_node(TaskNode(id="a", agent="A"))
    graph.add_node(TaskNode(id="b", agent="B", depends_on=["a"]))
    graph.add_node(TaskNode(id="c", agent="C", depends_on=["b"]))

    assert graph.topological_batches() == [["a"], ["b"], ["c"]]


def test_topological_batches_diamond_dependency():
    #     a
    #    / \
    #   b   c
    #    \ /
    #     d
    graph = TaskGraph()
    graph.add_node(TaskNode(id="a", agent="A"))
    graph.add_node(TaskNode(id="b", agent="B", depends_on=["a"]))
    graph.add_node(TaskNode(id="c", agent="C", depends_on=["a"]))
    graph.add_node(TaskNode(id="d", agent="D", depends_on=["b", "c"]))

    assert graph.topological_batches() == [["a"], ["b", "c"], ["d"]]


def test_topological_batches_independent_nodes_share_one_batch():
    graph = TaskGraph()
    graph.add_node(TaskNode(id="a", agent="A"))
    graph.add_node(TaskNode(id="b", agent="B"))

    assert graph.topological_batches() == [["a", "b"]]


def test_unknown_dependency_raises():
    graph = TaskGraph()
    graph.add_node(TaskNode(id="a", agent="A", depends_on=["ghost"]))
    try:
        graph.topological_batches()
        assert False, "expected TaskGraphError"
    except TaskGraphError as exc:
        assert "ghost" in str(exc)


def test_cycle_raises():
    graph = TaskGraph()
    graph.add_node(TaskNode(id="a", agent="A", depends_on=["b"]))
    graph.add_node(TaskNode(id="b", agent="B", depends_on=["a"]))
    try:
        graph.topological_batches()
        assert False, "expected TaskGraphError"
    except TaskGraphError as exc:
        assert "cycle" in str(exc).lower()


def test_duplicate_node_id_raises():
    graph = TaskGraph()
    graph.add_node(TaskNode(id="a", agent="A"))
    try:
        graph.add_node(TaskNode(id="a", agent="B"))
        assert False, "expected TaskGraphError"
    except TaskGraphError:
        pass


def test_node_cap_enforced():
    graph = TaskGraph()
    for i in range(MAX_GRAPH_NODES):
        graph.add_node(TaskNode(id=f"n{i}", agent="A"))
    try:
        graph.add_node(TaskNode(id="one_too_many", agent="A"))
        assert False, "expected TaskGraphError"
    except TaskGraphError as exc:
        assert "cap" in str(exc).lower()


def test_from_linear_chain_skips_steps_without_an_agent_name():
    graph = TaskGraph.from_linear_chain([
        {"agent": "A", "params": ["x"]},
        {"params": ["skipped, no agent"]},
        {"agent": "B", "params": ["y"]},
    ])
    batches = graph.topological_batches()
    assert batches == [["step_0"], ["step_2"]]
    assert graph.nodes["step_2"].depends_on == ["step_0"]


def test_from_linear_chain_over_cap_raises():
    chain = [{"agent": f"A{i}"} for i in range(MAX_GRAPH_NODES + 1)]
    try:
        TaskGraph.from_linear_chain(chain)
        assert False, "expected TaskGraphError"
    except TaskGraphError:
        pass


# ── SubagentRuntime.dispatch_graph: real parallel execution ────────────


def test_dispatch_graph_runs_independent_nodes_in_parallel():
    def slow_entry(ctx, params):
        time.sleep(0.4)
        return SubagentResult(agent=ctx["agent"], command="run", output="done", status=SubagentStatus.SUCCESS)

    register_agent("TG_Slow1", slow_entry)
    register_agent("TG_Slow2", slow_entry)

    graph = TaskGraph()
    graph.add_node(TaskNode(id="a", agent="TG_Slow1"))
    graph.add_node(TaskNode(id="b", agent="TG_Slow2"))

    runtime = SubagentRuntime(max_workers=4)
    start = time.monotonic()
    result = runtime.dispatch_graph(graph)
    elapsed = time.monotonic() - start

    assert isinstance(result, SwarmResult)
    assert result.ok is True
    assert len(result.agent_results) == 2
    # Two independent 0.4s nodes should finish in ~0.4s, not ~0.8s, if truly parallel.
    assert elapsed < 0.7, f"expected parallel execution, took {elapsed:.2f}s"


def test_dispatch_graph_diamond_threads_artifacts_from_both_parents():
    def research_entry(ctx, params):
        return SubagentResult(agent="TG_Research", command="r", output="fact A", status=SubagentStatus.SUCCESS)

    def review_entry(ctx, params):
        return SubagentResult(agent="TG_Review", command="r", output="fact B", status=SubagentStatus.SUCCESS)

    def synth_entry(ctx, params):
        upstream = ctx.get("_upstream_artifacts", [])
        sources = sorted(a["source_agent"] for a in upstream)
        return SubagentResult(
            agent="TG_Synth", command="synth",
            output=f"synthesized from {sources}", status=SubagentStatus.SUCCESS,
        )

    register_agent("TG_Research", research_entry)
    register_agent("TG_Review", review_entry)
    register_agent("TG_Synth", synth_entry)

    graph = TaskGraph()
    graph.add_node(TaskNode(id="root", agent="TG_Research"))
    graph.add_node(TaskNode(id="review", agent="TG_Review"))
    graph.add_node(TaskNode(id="synth", agent="TG_Synth", depends_on=["root", "review"]))

    runtime = SubagentRuntime(max_workers=4)
    result = runtime.dispatch_graph(graph)

    assert result.ok is True
    assert len(result.agent_results) == 3
    synth_result = [r for r in result.agent_results if r.agent == "TG_Synth"][0]
    assert "TG_Research" in synth_result.output
    assert "TG_Review" in synth_result.output


def test_dispatch_graph_stops_remaining_batches_after_a_failure():
    ran = []

    def ok_entry(ctx, params):
        ran.append(ctx["agent"])
        return SubagentResult(agent=ctx["agent"], command="r", output="ok", status=SubagentStatus.SUCCESS)

    def fail_entry(ctx, params):
        ran.append(ctx["agent"])
        return SubagentResult(agent=ctx["agent"], command="r", output="", status=SubagentStatus.ERROR, error="boom")

    register_agent("TG_First", ok_entry)
    register_agent("TG_Fails", fail_entry)
    register_agent("TG_Never", ok_entry)

    graph = TaskGraph()
    graph.add_node(TaskNode(id="first", agent="TG_First"))
    graph.add_node(TaskNode(id="fails", agent="TG_Fails", depends_on=["first"]))
    graph.add_node(TaskNode(id="never", agent="TG_Never", depends_on=["fails"]))

    runtime = SubagentRuntime(max_workers=4)
    result = runtime.dispatch_graph(graph, retry_policy=RetryPolicy(max_attempts=1))

    assert result.ok is False
    assert "TG_Never" not in ran
    assert ran == ["TG_First", "TG_Fails"]
