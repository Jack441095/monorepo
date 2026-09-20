"""Typed task DAG for dependency-aware multi-agent execution.

Scoped deliberately narrow: this powers `SubagentRuntime.dispatch_graph`
(multi-agent swarm chains), not the brain-plan executor in
`orchestrator.py`, which stays linear and untouched — that path is
entangled with live confirmation pause/resume and is exercised on every
conversational turn, so it's out of scope here (see the orchestration
upgrade plan). A flat ordered chain — what `dispatch_swarm` has always
taken — is just a graph where each node depends on the one before it;
`TaskGraph.from_linear_chain` builds exactly that.

No execution logic lives here on purpose: `SubagentResult`/`SwarmResult`
live in `thursday.subagent_runtime`, and this module must not import it
(that module imports this one), so `TaskGraph` only knows about structure
— which nodes exist and how they depend on each other — not how a node
actually runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# Mirrors orchestrator._MAX_PLAN_STEPS — a hard cap on graph size, not a
# tunable. Every new loop construct in this system gets one; see the
# "endless autonomous loop" anti-pattern this guards against.
MAX_GRAPH_NODES = 8


class TaskNodeStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass
class TaskNode:
    """One unit of work in a task graph: an agent dispatch plus its
    dependency edges. `result` is populated by the executor after the node
    runs (a `SubagentResult`, left untyped here to avoid the import cycle
    described in the module docstring)."""

    id: str
    agent: str
    params: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    status: TaskNodeStatus = TaskNodeStatus.PENDING
    result: Any = None


class TaskGraphError(ValueError):
    """Malformed graph: duplicate id, unknown dependency, cycle, or over the
    node cap."""


class TaskGraph:
    """A directed acyclic graph of `TaskNode`s, executed batch-by-batch —
    each batch is a set of nodes whose dependencies are all already
    satisfied, so nodes within a batch can run in parallel."""

    def __init__(self) -> None:
        self._nodes: dict[str, TaskNode] = {}

    def add_node(self, node: TaskNode) -> None:
        if node.id in self._nodes:
            raise TaskGraphError(f"duplicate task id: {node.id!r}")
        if len(self._nodes) + 1 > MAX_GRAPH_NODES:
            raise TaskGraphError(f"task graph exceeds the {MAX_GRAPH_NODES}-node cap")
        self._nodes[node.id] = node

    @property
    def nodes(self) -> dict[str, TaskNode]:
        return dict(self._nodes)

    def topological_batches(self) -> list[list[str]]:
        """Return node ids grouped into dependency-ordered batches.

        Each batch's node ids are sorted for deterministic ordering. Raises
        `TaskGraphError` if any node depends on an id that isn't in the
        graph, or if the dependency edges form a cycle.
        """
        for node in self._nodes.values():
            for dep in node.depends_on:
                if dep not in self._nodes:
                    raise TaskGraphError(
                        f"node {node.id!r} depends on unknown node {dep!r}"
                    )

        remaining = dict(self._nodes)
        done: set[str] = set()
        batches: list[list[str]] = []
        while remaining:
            ready = [
                node_id
                for node_id, node in remaining.items()
                if all(dep in done for dep in node.depends_on)
            ]
            if not ready:
                raise TaskGraphError(
                    f"cycle detected among nodes: {sorted(remaining)}"
                )
            ready.sort()
            batches.append(ready)
            for node_id in ready:
                done.add(node_id)
                del remaining[node_id]
        return batches

    @classmethod
    def from_linear_chain(cls, agent_chain: list[dict[str, Any]]) -> "TaskGraph":
        """Build the trivial single-parent-chain graph `dispatch_swarm` has
        always executed: each step depends on the previous one, in order.
        Steps with no agent name are skipped, exactly as the original
        `dispatch_swarm` loop's `if not agent_name: continue` did."""
        graph = cls()
        prev_id: str | None = None
        for i, step in enumerate(agent_chain):
            agent_name = str(step.get("agent") or step.get("name") or "")
            if not agent_name:
                continue
            node_id = f"step_{i}"
            graph.add_node(
                TaskNode(
                    id=node_id,
                    agent=agent_name,
                    params=list(step.get("params") or []),
                    depends_on=[prev_id] if prev_id else [],
                )
            )
            prev_id = node_id
        return graph
