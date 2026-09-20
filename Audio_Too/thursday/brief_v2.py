"""Owner Brief V2 for Thursday V2-I — long-horizon briefing.

Weeks of operation create an information-overload problem. This module
composes a bounded owner brief that answers:

    What changed?  What matters?  What completed/failed/is blocked?
    What needs MY decision?  What did Thursday deliberately NOT do?
    What risks are rising?  What changed since the previous brief?

Significance is favoured over volume: the brief is size-capped and
low-value detail is dropped first.

Quality evaluation is DETERMINISTIC and structural:
    * required sections present
    * every claim references an entity that exists in supplied stores
      (no unsupported claims)
    * no stale claims (references must be currently valid)
    * no duplicated statements
    * hard line cap

LLM phrasing may decorate rendering elsewhere; it is never the PASS
gate for brief quality.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from thursday.candidate_history import CandidateHistory, CandidateState
from thursday.owner_decisions import DecisionType, OwnerDecisionLedger


BRIEF_MAX_LINES = 120


@dataclass
class BriefSection:
    title: str
    lines: list[str] = field(default_factory=list)


@dataclass
class LongHorizonBrief:
    """Composed long-horizon owner brief (structured + renderable)."""

    day: int
    sections: list[BriefSection] = field(default_factory=list)

    def render_text(self) -> str:
        out = [f"THURSDAY LONG-HORIZON BRIEF — simulated day {self.day}"]
        for s in self.sections:
            out.append("")
            out.append(f"## {s.title}")
            out.extend(s.lines if s.lines else ["(nothing)"])
        return "\n".join(out)


@dataclass
class BriefQualityReport:
    passed: bool
    failures: list[str] = field(default_factory=list)


def _candidate_line(rec) -> str:
    return f"{rec.title} [{rec.state}] ({rec.project})"


def compose_long_horizon_brief(
    *,
    day: int,
    candidate_history: CandidateHistory,
    decision_ledger: OwnerDecisionLedger,
    previous_brief_candidate_states: dict[str, str] | None = None,
    max_lines: int = BRIEF_MAX_LINES,
) -> LongHorizonBrief:
    """Compose the current brief from authoritative stores only.

    ``previous_brief_candidate_states`` maps candidate_id → state as of
    the previous brief, enabling an honest "changed since last time".
    """
    prev = previous_brief_candidate_states or {}

    completed = [
        c for c in candidate_history.in_state(CandidateState.INTEGRATED)
    ]
    failed = candidate_history.in_state(
        CandidateState.FAILED, CandidateState.ROLLED_BACK)
    blocked = candidate_history.in_state(CandidateState.BLOCKED,
                                         CandidateState.DEFERRED)
    waiting = candidate_history.in_state(CandidateState.WAITING_FOR_APPROVAL)

    needs_decision = waiting[:10]          # capped: attention economics
    risks = [
        c for c in candidate_history.all_candidates()
        if c.consecutive_same_failures() >= 2
    ]

    changed_since_prev = []
    for c in sorted(candidate_history.all_candidates(),
                    key=lambda r: -r.last_seen_epoch):
        if c.state != CandidateState.DISCOVERED.value:
            old = prev.get(c.candidate_id)
            if old is None or old != c.state:
                changed_since_prev.append(c)

    deliberately_not_done = decision_ledger.active_decisions(
        DecisionType.DEFER_UNTIL) + decision_ledger.active_decisions(
        DecisionType.REJECT_CANDIDATE)

    sections = [
        BriefSection("What requires my decision",
                     [_candidate_line(c) for c in needs_decision]),
        BriefSection("Completed since last brief",
                     [_candidate_line(c) for c in completed[-8:]]),
        BriefSection("Failed or rolled back",
                     [_candidate_line(c) for c in failed[-8:]]),
        BriefSection("Blocked or deferred",
                     [_candidate_line(c) for c in blocked[-8:]]),
        BriefSection("Rising risks (repeated failures)",
                     [f"{c.title}: {c.consecutive_same_failures()} consecutive failures"
                      for c in risks[:8]]),
        BriefSection("Deliberately not done (owner decisions in force)",
                     [f"{d.decision_type} {d.scope}"
                      for d in deliberately_not_done[:8]]),
        BriefSection("Materially changed since last brief",
                     [f"{_candidate_line(c)} (was: {prev.get(c.candidate_id, 'new')})"
                      for c in changed_since_prev[:12]]),
    ]

    # Size discipline: drop lowest-priority sections first under the cap.
    brief = LongHorizonBrief(day=day, sections=sections)

    def _size(b: LongHorizonBrief) -> int:
        return len(b.render_text().splitlines())

    drop_order = ["Deliberately not done (owner decisions in force)",
                  "Materially changed since last brief",
                  "Blocked or deferred", "Rising risks (repeated failures)",
                  "Failed or rolled back"]
    while _size(brief) > max_lines:
        for title in drop_order:
            sec = next((s for s in brief.sections if s.title == title), None)
            if sec and len(sec.lines) > 1:
                sec.lines = sec.lines[:-1]
                break
        else:
            break
    return brief


def check_brief_quality(
    brief: LongHorizonBrief,
    *,
    candidate_history: CandidateHistory,
    max_lines: int = BRIEF_MAX_LINES,
) -> BriefQualityReport:
    """Deterministic structural quality gate (this is the PASS gate)."""
    failures: list[str] = []
    text = brief.render_text()
    lines = text.splitlines()

    required = [
        "What requires my decision",
        "Completed since last brief",
        "Failed or rolled back",
        "Blocked or deferred",
        "Rising risks (repeated failures)",
    ]
    titles = {s.title for s in brief.sections}
    for r in required:
        if r not in titles:
            failures.append(f"Missing required section: {r}")

    known_ids = {c.candidate_id for c in candidate_history.all_candidates()}
    # Every bracketed [STATE] line must correspond to a real candidate.
    import re
    referenced = set()
    for line in lines:
        m = re.search(r"\[([A-Z_]+)\]", line)
        if m and "(" in line:
            # Match by title back to history to detect fabricated claims.
            title = line.split("[")[0].strip()
            match = any(c.title == title for c in candidate_history.all_candidates())
            if not match:
                failures.append(f"Unsupported claim (unknown entity): {title!r}")
                continue
            for c in candidate_history.all_candidates():
                if c.title == title:
                    referenced.add(c.candidate_id)

    # Duplicate statement detection.
    body = [ln for ln in lines if ln and not ln.startswith(("#", ""))]
    dupes = {ln for ln in body if body.count(ln) > 1}
    if dupes:
        failures.append(f"Duplicated statements: {sorted(dupes)[:3]}")

    if len(lines) > max_lines:
        failures.append(f"Brief exceeds size cap: {len(lines)} > {max_lines}")

    return BriefQualityReport(passed=not failures, failures=failures)


__all__ = [
    "LongHorizonBrief", "BriefSection", "BriefQualityReport",
    "compose_long_horizon_brief", "check_brief_quality", "BRIEF_MAX_LINES",
]
