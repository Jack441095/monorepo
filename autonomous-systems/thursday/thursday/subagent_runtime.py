"""Subagent runtime — first-class in-process agent dispatch.

Replaces the legacy subprocess-based `run_agent()` from the agent launcher
with a thread-pool-based in-process dispatch that returns structured results.

Key features:
- **SubagentResult**: typed result object (output, status, timing, agent metadata)
- **dispatch()**: run any registered agent in a managed thread with timeout
- **bounded concurrency**: thread-pool caps parallel agent tasks
- **context isolation**: each dispatch gets a shallow-copy context
- **graceful failure**: timeouts and exceptions return error results, never crash
"""

from __future__ import annotations

import copy
import logging
import time
import traceback
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FuturesTimeout
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from thursday.retry import DEFAULT_RETRY_POLICY, RetryPolicy
from thursday.taskgraph import TaskGraph, TaskGraphError

logger = logging.getLogger(__name__)


# ── Result type ─────────────────────────────────────────────────────────


class SubagentStatus(Enum):
    """Terminal status for a subagent dispatch."""

    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class SubagentResult:
    """Structured result returned by every agent dispatch.

    Attributes:
        agent:      Agent name (e.g. ``"Admin"``, ``"Marketing"``).
        command:    The command that was dispatched.
        output:     The primary text output from the agent.
        status:     Terminal status of the dispatch.
        exit_code:  Numeric exit code (0 = success).
        elapsed_ms: Wall-clock milliseconds for the dispatch.
        error:      Error message if status != SUCCESS.
        metadata:   Arbitrary additional data returned by the agent.
    """

    agent: str
    command: str
    output: str
    status: SubagentStatus
    exit_code: int = 0
    elapsed_ms: float = 0.0
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == SubagentStatus.SUCCESS


def _is_retryable_subagent_result(result: SubagentResult) -> bool:
    """Classify whether a failed dispatch is worth retrying.

    Timeouts are transient by nature. Errors are retried unless they're a
    permanent condition (e.g. the agent was never registered) that a retry
    cannot fix.
    """
    if result.status == SubagentStatus.TIMEOUT:
        return True
    if result.status == SubagentStatus.ERROR:
        return "is not registered" not in result.error
    return False


import uuid


@dataclass(frozen=True)
class AgentArtifact:
    """Data payload artifact passed between subagents in a swarm task chain."""

    source_agent: str
    content: str
    artifact_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    target_agent: str | None = None
    artifact_type: str = "text"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentHandoff:
    """Handoff instruction detailing task and upstream artifacts for the next agent."""

    from_agent: str
    to_agent: str
    task_instruction: str
    artifacts: list[AgentArtifact] = field(default_factory=list)


@dataclass(frozen=True)
class SwarmResult:
    """Aggregated result returned by a multi-agent swarm execution."""

    swarm_id: str
    status: SubagentStatus
    agent_results: list[SubagentResult]
    produced_artifacts: list[AgentArtifact]
    final_summary: str
    elapsed_ms: float = 0.0
    qc_report: Any = None  # thursday.qc.QCReport | None; set only when dispatch_graph(qc=True)

    @property
    def ok(self) -> bool:
        return self.status == SubagentStatus.SUCCESS


# ── Capability declarations ─────────────────────────────────────────────


class DataScope(Enum):
    """What data stores the agent can access."""

    READ_ONLY = "read_only"
    LOCAL_MUTATION = "local_mutation"
    FULL = "full"


@dataclass(frozen=True)
class AgentCapability:
    """Declares what a single agent is allowed to do.

    Attributes:
        writes:         Whether the agent can create/update records.
        external_send:  Whether the agent can send emails or external messages.
        data_scope:     What data stores the agent can access.
        description:    Human-readable description of the agent's role.
    """

    writes: bool = False
    external_send: bool = False
    data_scope: DataScope = DataScope.READ_ONLY
    description: str = ""


# Capability map for all known agents.
AGENT_CAPABILITIES: dict[str, AgentCapability] = {
    "Admin": AgentCapability(
        writes=True,
        external_send=True,
        data_scope=DataScope.FULL,
        description="Handles invoices, projects, clients, emails, drafts, and data exports.",
    ),
    "Marketing": AgentCapability(
        writes=True,
        external_send=True,
        data_scope=DataScope.FULL,
        description="Generates outreach, social posts, campaigns, and manages leads.",
    ),
    "Research": AgentCapability(
        writes=False,
        external_send=False,
        data_scope=DataScope.READ_ONLY,
        description="Suggests PDFs, web sources, and research plans. Read-only.",
    ),
}


# ── Agent entry-point protocol ──────────────────────────────────────────

# Each agent must expose:
#   execute(context: dict, params: list[str]) -> SubagentResult
#
# ``context`` contains:
#   - "agent":     Agent name
#   - "repo_root": Path to the repo root
#   - "cwd":       Working directory
#   - "env":       Shallow copy of os.environ
#
# ``params`` is the CLI arg list that would have been passed to main.py.

# Registry of in-process entry points (agent_name -> execute callable).
_AGENT_ENTRY_POINTS: dict[str, Callable[[dict, list[str]], SubagentResult]] = {}


def register_agent(name: str, entry_point: Callable[[dict, list[str]], SubagentResult]) -> None:
    """Register an in-process agent entry point."""
    _AGENT_ENTRY_POINTS[name] = entry_point


def get_registered_agents() -> dict[str, Callable[[dict, list[str]], SubagentResult]]:
    """Return a snapshot of registered entry points."""
    return dict(_AGENT_ENTRY_POINTS)


def register_default_agents(api: Any) -> None:
    """Register Admin/Marketing/Research as SubagentRuntime entry points.

    Wraps the exact same handler functions the `admin_agent`/`marketing_agent`/
    `research_agent` services already call (`registry/handlers.py`) — this
    does not change what those handlers do or add a second code path for
    them, it only makes them reachable via `SubagentRuntime.dispatch` for
    genuinely parallel multi-agent execution (see orchestrator.py's
    "parallel_swarm" brain-decision branch). Idempotent: safe to call before
    every dispatch, registration is just a dict assignment.
    """
    from thursday.registry.handlers import (
        _handle_admin_agent, _handle_marketing_agent, _handle_research_agent,
    )

    def _wrap(
        agent_name: str, handler: Callable[[Any, str], str],
    ) -> Callable[[dict, list[str]], SubagentResult]:
        def entry(ctx: dict, params: list[str]) -> SubagentResult:
            text = params[0] if params else ""
            output = handler(api, text)
            return SubagentResult(
                agent=agent_name, command=text, output=output or "",
                status=SubagentStatus.SUCCESS,
            )
        return entry

    register_agent("Admin", _wrap("Admin", _handle_admin_agent))
    register_agent("Marketing", _wrap("Marketing", _handle_marketing_agent))
    register_agent("Research", _wrap("Research", _handle_research_agent))


# ── Runtime ─────────────────────────────────────────────────────────────


class SubagentRuntime:
    """In-process agent dispatcher with bounded concurrency and timeouts.

    Usage::

        runtime = SubagentRuntime(max_workers=4, default_timeout=120)
        result = runtime.dispatch("Admin", ["email", "Follow up with Jordan"])
        print(result.output)
    """

    def __init__(
        self,
        max_workers: int = 4,
        default_timeout: float = 120.0,
        repo_root: Path | None = None,
    ):
        self._max_workers = max_workers
        self._default_timeout = default_timeout
        self._repo_root = repo_root or Path(__file__).resolve().parents[1]
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="subagent",
        )
        self._active_futures: dict[str, Future[SubagentResult]] = {}

    # ── Context builder ─────────────────────────────────────────────

    def _build_context(self, agent_name: str) -> dict[str, Any]:
        """Build an isolated context dict for a dispatch."""
        import os

        return {
            "agent": agent_name,
            "repo_root": self._repo_root,
            "cwd": self._repo_root / "business" / "agents",
            "env": dict(os.environ),
        }

    # ── Core dispatch ───────────────────────────────────────────────

    def dispatch(
        self,
        agent_name: str,
        params: list[str],
        *,
        timeout: float | None = None,
        context_overrides: dict[str, Any] | None = None,
        retry_policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    ) -> SubagentResult:
        """Dispatch an agent task, retrying transient failures.

        Args:
            agent_name:        Registered agent name (e.g. ``"Admin"``).
            params:            CLI arguments for the agent.
            timeout:           Per-dispatch timeout in seconds (None → default).
            context_overrides: Extra context keys merged into the agent context.
            retry_policy:      Bounded retry schedule for transient failures
                                (timeouts, non-permanent errors). See
                                `thursday.retry`.

        Returns:
            SubagentResult with the agent's output and metadata.
        """
        result = self._dispatch_once(
            agent_name, params, timeout=timeout, context_overrides=context_overrides,
        )
        attempt = 0
        while (
            not result.ok
            and _is_retryable_subagent_result(result)
            and attempt < retry_policy.max_attempts - 1
        ):
            delay_index = min(attempt, len(retry_policy.backoff_seconds) - 1)
            time.sleep(retry_policy.backoff_seconds[delay_index])
            attempt += 1
            result = self._dispatch_once(
                agent_name, params, timeout=timeout, context_overrides=context_overrides,
            )
        return result

    def _dispatch_once(
        self,
        agent_name: str,
        params: list[str],
        *,
        timeout: float | None = None,
        context_overrides: dict[str, Any] | None = None,
    ) -> SubagentResult:
        """Single dispatch attempt — see `dispatch()` for the retrying wrapper."""
        effective_timeout = timeout if timeout is not None else self._default_timeout
        command = params[0] if params else "unknown"

        # Validate agent is registered
        entry_point = _AGENT_ENTRY_POINTS.get(agent_name)
        if entry_point is None:
            return SubagentResult(
                agent=agent_name,
                command=command,
                output="",
                status=SubagentStatus.ERROR,
                exit_code=1,
                error=f"Agent '{agent_name}' is not registered. "
                f"Available: {sorted(_AGENT_ENTRY_POINTS.keys())}",
            )

        # Check capability
        cap = AGENT_CAPABILITIES.get(agent_name)
        if cap is None:
            logger.warning("No capability declaration for agent '%s'", agent_name)

        # Build isolated context
        ctx = self._build_context(agent_name)
        if context_overrides:
            ctx.update(context_overrides)

        # Shallow-copy for isolation
        ctx = copy.copy(ctx)

        import datetime
        start_time_iso = datetime.datetime.now().isoformat()

        start = time.monotonic()
        future: Future[SubagentResult] = self._pool.submit(
            self._run_agent, entry_point, agent_name, command, ctx, params,
        )
        task_id = f"{agent_name}:{command}:{id(future)}"
        self._active_futures[task_id] = future

        try:
            result = future.result(timeout=effective_timeout)
            elapsed = (time.monotonic() - start) * 1000
            # Enrich with timing
            res = SubagentResult(
                agent=result.agent,
                command=result.command,
                output=result.output,
                status=result.status,
                exit_code=result.exit_code,
                elapsed_ms=elapsed,
                error=result.error,
                metadata=result.metadata,
            )
            self._log_execution_trace(res, start_time_iso)
            return res
        except FuturesTimeout:
            elapsed = (time.monotonic() - start) * 1000
            future.cancel()
            logger.warning("Agent '%s' timed out after %.0fms", agent_name, elapsed)
            res = SubagentResult(
                agent=agent_name,
                command=command,
                output="",
                status=SubagentStatus.TIMEOUT,
                exit_code=124,
                elapsed_ms=elapsed,
                error=f"Agent '{agent_name}' timed out after {effective_timeout:.0f}s",
            )
            self._log_execution_trace(res, start_time_iso)
            return res
        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            tb = traceback.format_exc()
            logger.error("Agent '%s' dispatch failed: %s\n%s", agent_name, exc, tb)
            res = SubagentResult(
                agent=agent_name,
                command=command,
                output="",
                status=SubagentStatus.ERROR,
                exit_code=1,
                elapsed_ms=elapsed,
                error=str(exc),
            )
            self._log_execution_trace(res, start_time_iso)
            return res
        finally:
            self._active_futures.pop(task_id, None)

    def _log_execution_trace(self, result: SubagentResult, start_time_iso: str) -> None:
        """Log subagent execution details to execution_traces.jsonl."""
        import json
        from thursday.runtime_paths import runtime_dir

        try:
            analytics_dir = runtime_dir("analytics", "THURSDAY_ANALYTICS_DIR")
            analytics_dir.mkdir(parents=True, exist_ok=True)
            trace_file = analytics_dir / "execution_traces.jsonl"

            trace_data = {
                "timestamp": start_time_iso,
                "agent": result.agent,
                "command": result.command,
                "status": result.status.value,
                "elapsed_ms": result.elapsed_ms,
                "error": result.error,
                "output_summary": result.output[:200] if result.output else ""
            }

            with open(trace_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(trace_data) + "\n")
        except Exception as exc:
            logger.warning("Failed to write subagent execution trace: %s", exc)

    @staticmethod
    def _run_agent(
        entry_point: Callable[[dict, list[str]], SubagentResult],
        agent_name: str,
        command: str,
        ctx: dict,
        params: list[str],
    ) -> SubagentResult:
        """Execute the agent entry point in a worker thread."""
        try:
            return entry_point(ctx, params)
        except Exception as exc:
            tb = traceback.format_exc()
            logger.error("Agent '%s' raised: %s\n%s", agent_name, exc, tb)
            return SubagentResult(
                agent=agent_name,
                command=command,
                output="",
                status=SubagentStatus.ERROR,
                exit_code=1,
                error=f"{type(exc).__name__}: {exc}",
            )

    # ── Concurrent dispatch ─────────────────────────────────────────

    def dispatch_many(
        self,
        tasks: list[tuple[str, list[str]]],
        *,
        timeout: float | None = None,
    ) -> list[SubagentResult]:
        """Dispatch multiple agent tasks concurrently and collect results.

        Args:
            tasks:   List of ``(agent_name, params)`` tuples.
            timeout: Per-task timeout.

        Returns:
            List of SubagentResult in the same order as *tasks*.
        """
        futures: list[Future[SubagentResult]] = []
        for agent_name, params in tasks:
            effective_timeout = timeout if timeout is not None else self._default_timeout
            entry_point = _AGENT_ENTRY_POINTS.get(agent_name)
            if entry_point is None:
                # Immediate error result
                command = params[0] if params else "unknown"
                futures.append(self._pool.submit(
                    lambda a=agent_name, c=command: SubagentResult(
                        agent=a, command=c, output="",
                        status=SubagentStatus.ERROR, exit_code=1,
                        error=f"Agent '{a}' is not registered.",
                    )
                ))
            else:
                ctx = self._build_context(agent_name)
                command = params[0] if params else "unknown"
                futures.append(self._pool.submit(
                    self._run_agent, entry_point, agent_name, command, ctx, params,
                ))

        effective_timeout = timeout if timeout is not None else self._default_timeout
        results: list[SubagentResult] = []
        for future in futures:
            try:
                results.append(future.result(timeout=effective_timeout))
            except FuturesTimeout:
                future.cancel()
                results.append(SubagentResult(
                    agent="unknown", command="unknown", output="",
                    status=SubagentStatus.TIMEOUT, exit_code=124,
                    error=f"Timed out after {effective_timeout:.0f}s",
                ))
            except Exception as exc:
                results.append(SubagentResult(
                    agent="unknown", command="unknown", output="",
                    status=SubagentStatus.ERROR, exit_code=1,
                    error=str(exc),
                ))
        return results

    # ── Graph Dispatch ──────────────────────────────────────────────

    def dispatch_graph(
        self,
        graph: TaskGraph,
        *,
        timeout: float | None = None,
        context_overrides: dict[str, Any] | None = None,
        retry_policy: RetryPolicy = DEFAULT_RETRY_POLICY,
        qc: bool = False,
    ) -> SwarmResult:
        """Execute a dependency-aware task graph.

        Nodes within a topological batch (no dependency on each other) run
        in parallel; batches run in dependency order. Execution stops at the
        first batch containing a failure — the same stop-on-first-failure
        semantics `dispatch_swarm`'s linear chain has always had. Each
        completed node's output becomes an upstream artifact available to
        every later node, exactly as `dispatch_swarm` accumulated artifacts
        across its chain.

        Args:
            graph:         The `TaskGraph` to execute.
            timeout:       Per-node timeout.
            context_overrides: Base context overrides merged into every node.
            retry_policy:  Bounded retry schedule applied per failed node.
            qc:            When true, validate results that claimed success
                            (`thursday.qc.validate_chain_result`) and attempt
                            one bounded repair re-dispatch per flagged node.
                            Off by default — this is extra work only
                            multi-agent chains should pay for, never a
                            single-turn service call.

        Returns:
            SwarmResult detailing overall status, individual node results,
            and intermediate artifacts produced.
        """
        import time as time_module
        import uuid
        from dataclasses import asdict

        swarm_id = str(uuid.uuid4())[:12]
        start = time_module.time()
        effective_timeout = timeout if timeout is not None else self._default_timeout
        base_ctx_overrides = dict(context_overrides or {})

        nodes = graph.nodes
        batches = graph.topological_batches()

        agent_results: list[SubagentResult] = []
        executed_node_ids: list[str] = []
        produced_artifacts: list[AgentArtifact] = []
        overall_ok = True

        for batch in batches:
            if not overall_ok:
                break

            upstream_dicts = [asdict(art) for art in produced_artifacts]
            context_str = (
                "\n".join(
                    f"[{art.source_agent} Output]: {art.content}"
                    for art in produced_artifacts[-3:]
                )
                if produced_artifacts
                else ""
            )

            futures: dict[str, Future[SubagentResult]] = {}
            for node_id in batch:
                node = nodes[node_id]
                entry_point = _AGENT_ENTRY_POINTS.get(node.agent)
                params = list(node.params)
                if context_str:
                    params.append(f"--context={context_str}")
                command = params[0] if params else "unknown"

                if entry_point is None:
                    agent_results.append(SubagentResult(
                        agent=node.agent, command=command, output="",
                        status=SubagentStatus.ERROR, exit_code=1,
                        error=f"Agent '{node.agent}' is not registered.",
                    ))
                    executed_node_ids.append(node_id)
                    overall_ok = False
                    continue

                ctx = self._build_context(node.agent)
                ctx.update(base_ctx_overrides)
                ctx["_upstream_artifacts"] = upstream_dicts
                ctx = copy.copy(ctx)

                futures[node_id] = self._pool.submit(
                    self._run_agent, entry_point, node.agent, command, ctx, params,
                )

            for node_id, future in futures.items():
                node = nodes[node_id]
                node_params = list(node.params)
                if context_str:
                    node_params.append(f"--context={context_str}")
                try:
                    result = future.result(timeout=effective_timeout)
                except FuturesTimeout:
                    future.cancel()
                    result = SubagentResult(
                        agent=node.agent,
                        command=node_params[0] if node_params else "unknown",
                        output="", status=SubagentStatus.TIMEOUT, exit_code=124,
                        error=f"Agent '{node.agent}' timed out after {effective_timeout:.0f}s",
                    )
                except Exception as exc:
                    result = SubagentResult(
                        agent=node.agent, command="unknown", output="",
                        status=SubagentStatus.ERROR, exit_code=1, error=str(exc),
                    )

                attempt = 0
                while (
                    not result.ok
                    and _is_retryable_subagent_result(result)
                    and attempt < retry_policy.max_attempts - 1
                ):
                    delay_index = min(attempt, len(retry_policy.backoff_seconds) - 1)
                    time_module.sleep(retry_policy.backoff_seconds[delay_index])
                    attempt += 1
                    result = self._dispatch_once(
                        node.agent, node_params, timeout=timeout,
                        context_overrides={
                            **base_ctx_overrides,
                            "_upstream_artifacts": upstream_dicts,
                        },
                    )

                agent_results.append(result)
                executed_node_ids.append(node_id)
                if result.ok:
                    produced_artifacts.append(AgentArtifact(
                        source_agent=node.agent,
                        content=result.output,
                        metadata=result.metadata,
                    ))
                else:
                    overall_ok = False
                    logger.warning(
                        "Graph '%s' node '%s' (%s) failed: %s",
                        swarm_id, node_id, node.agent, result.error,
                    )

        qc_report = None
        if qc:
            qc_report = self._run_qc_and_repair(
                swarm_id=swarm_id,
                agent_results=agent_results,
                executed_node_ids=executed_node_ids,
                produced_artifacts=produced_artifacts,
                nodes=nodes,
                base_ctx_overrides=base_ctx_overrides,
                timeout=timeout,
            )

        elapsed = round((time_module.time() - start) * 1000, 1)
        final_summary = "\n\n".join(
            f"[{r.agent}]: {r.output if r.ok else 'Failed: ' + r.error}" for r in agent_results
        )

        return SwarmResult(
            swarm_id=swarm_id,
            status=SubagentStatus.SUCCESS if overall_ok else SubagentStatus.ERROR,
            agent_results=agent_results,
            produced_artifacts=produced_artifacts,
            qc_report=qc_report,
            final_summary=final_summary,
            elapsed_ms=elapsed,
        )

    def _run_qc_and_repair(
        self,
        *,
        swarm_id: str,
        agent_results: list[SubagentResult],
        executed_node_ids: list[str],
        produced_artifacts: list[AgentArtifact],
        nodes: dict[str, Any],
        base_ctx_overrides: dict[str, Any],
        timeout: float | None,
    ):
        """Validate nodes that claimed success and attempt one bounded
        repair re-dispatch per flagged node. Mutates `agent_results` and
        `produced_artifacts` in place for any node that repairs cleanly;
        a node that fails to repair is left as-is (its original findings
        stay in the returned report as a surfaced caveat, not a blocker).

        This budget is separate from `dispatch_graph`'s transient-failure
        retries: it exists for nodes that already succeeded but produced a
        suspect output (empty, or not matching a declared schema), not for
        timeouts/connection errors — repairing a bad output isn't the same
        problem as retrying a flaky call.
        """
        from thursday.qc import validate_chain_result

        report = validate_chain_result(agent_results)
        if report.passed:
            return report

        for finding in report.findings:
            idx = finding.index
            node_id = executed_node_ids[idx]
            node = nodes[node_id]

            repaired = self._dispatch_once(
                node.agent, list(node.params), timeout=timeout,
                context_overrides=dict(base_ctx_overrides),
            )
            if not (repaired.ok and repaired.output and repaired.output.strip()):
                continue

            artifact_index = sum(1 for r in agent_results[:idx] if r.ok)
            agent_results[idx] = repaired
            produced_artifacts[artifact_index] = AgentArtifact(
                source_agent=repaired.agent,
                content=repaired.output,
                metadata=repaired.metadata,
            )

        # Re-validate so the returned report reflects post-repair reality.
        return validate_chain_result(agent_results)

    def dispatch_swarm(
        self,
        agent_chain: list[dict[str, Any]],
        *,
        timeout: float | None = None,
        context_overrides: dict[str, Any] | None = None,
    ) -> SwarmResult:
        """Execute a coordinated multi-agent swarm pipeline.

        Thin compatibility wrapper: builds the trivial single-parent-chain
        `TaskGraph` this method has always executed (each step depends on
        the one before it) and runs it via `dispatch_graph`. Signature and
        `SwarmResult` shape are unchanged from before `dispatch_graph`
        existed — every existing caller keeps working as-is. For real
        dependency graphs with parallel branches, call `dispatch_graph`
        directly with a hand-built `TaskGraph` instead.

        Args:
            agent_chain: List of step dicts:
                [
                    {"agent": "Research", "params": ["task_1"]},
                    {"agent": "Admin", "params": ["task_2"]},
                    ...
                ]
            timeout: Per-step timeout.
            context_overrides: Base context overrides.

        Returns:
            SwarmResult detailing overall status, individual agent step results,
            and intermediate artifacts produced.
        """
        import uuid

        try:
            graph = TaskGraph.from_linear_chain(agent_chain)
        except TaskGraphError as exc:
            return SwarmResult(
                swarm_id=str(uuid.uuid4())[:12],
                status=SubagentStatus.ERROR,
                agent_results=[],
                produced_artifacts=[],
                final_summary=f"Swarm chain rejected: {exc}",
                elapsed_ms=0.0,
            )

        return self.dispatch_graph(graph, timeout=timeout, context_overrides=context_overrides)

    # ── Info ────────────────────────────────────────────────────────

    @property
    def active_count(self) -> int:
        """Number of currently executing agent tasks."""
        return len(self._active_futures)

    @property
    def max_workers(self) -> int:
        return self._max_workers

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the thread pool."""
        self._pool.shutdown(wait=wait)
