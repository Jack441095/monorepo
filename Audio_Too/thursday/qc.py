"""Lightweight, non-LLM-by-default QC pass for multi-agent swarm/graph chains.

Invoked only after a `dispatch_graph`/`dispatch_swarm` chain completes (via
`dispatch_graph(..., qc=True)`) — never on single-turn service calls, so
trivial conversational turns don't pay for an extra validation pass. Checks
are cheap and structural: did every node that claimed success actually
produce output, and if a node declared a JSON schema (via
`SubagentResult.metadata["expected_schema"]`, a list of required top-level
keys), does its output actually parse and match it.

A hard failure (agent error, timeout, unregistered agent) is not this
module's job to fix — that's already reflected in the chain's overall
status. This only flags nodes that *claimed* success but produced something
suspect, so the caller can attempt one bounded repair re-dispatch.

No execution logic lives here on purpose — see `thursday/taskgraph.py` for
why (avoids an import cycle with `thursday.subagent_runtime`, which imports
this module).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from thursday.subagent_runtime import SubagentResult


@dataclass(frozen=True)
class QCFinding:
    """One flagged node from a completed chain."""

    index: int
    agent: str
    category: str  # "empty_artifact" | "schema_mismatch"
    detail: str


@dataclass(frozen=True)
class QCReport:
    passed: bool
    findings: list[QCFinding] = field(default_factory=list)

    @property
    def repairable_indices(self) -> list[int]:
        """Positions in `SwarmResult.agent_results` worth a repair attempt."""
        return [f.index for f in self.findings]


def validate_chain_result(agent_results: list["SubagentResult"]) -> QCReport:
    """Structurally validate a completed swarm/graph chain's per-node results.

    Only inspects nodes that reported success (`result.ok`) — a node that
    already failed is reflected in the chain's overall status and isn't
    this module's concern.
    """
    findings: list[QCFinding] = []
    for i, result in enumerate(agent_results):
        if not result.ok:
            continue

        if not result.output or not result.output.strip():
            findings.append(QCFinding(
                index=i, agent=result.agent, category="empty_artifact",
                detail=f"{result.agent} reported success but produced no output",
            ))
            continue

        expected_schema = result.metadata.get("expected_schema")
        if not expected_schema:
            continue

        try:
            parsed = json.loads(result.output)
        except (json.JSONDecodeError, TypeError):
            findings.append(QCFinding(
                index=i, agent=result.agent, category="schema_mismatch",
                detail=f"{result.agent}'s output is not valid JSON",
            ))
            continue

        if not isinstance(parsed, dict):
            findings.append(QCFinding(
                index=i, agent=result.agent, category="schema_mismatch",
                detail=f"{result.agent}'s output is not a JSON object",
            ))
            continue

        missing = [key for key in expected_schema if key not in parsed]
        if missing:
            findings.append(QCFinding(
                index=i, agent=result.agent, category="schema_mismatch",
                detail=f"{result.agent}'s output is missing keys: {missing}",
            ))

    return QCReport(passed=not findings, findings=findings)
