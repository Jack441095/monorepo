"""Agent briefing (Thursday Ops upgrade — "Can you brief Codex/Gemini/
another agent on this?").

Adds no new content-generation of its own -- like weekly_report.py, this
composes what already-real, already-tested modules produce
(task_ledger, qa_ops's live-parsed beta checklist, funding_ops's
live-queried traction) into one document shaped for handing to a
*different* AI agent to continue work from, rather than for the founder
to read directly. The two audiences want different things: the founder
wants a quick status; another agent picking up work needs explicit
source citations and an explicit instruction not to treat any of this as
license to fabricate beyond what's here -- so this format carries that
instruction as a first-class section, not just an implicit convention.

An optional ``topic`` narrows which real sections get included (e.g.
"beta" pulls in qa_ops, "funding" pulls in funding_ops) -- see
_TOPIC_SECTIONS. No topic means include everything.
"""

from __future__ import annotations

from datetime import datetime

_TOPIC_SECTIONS = {
    "beta": {"tasks", "beta"},
    "submit": {"tasks", "beta"},
    "funding": {"tasks", "funding"},
    "investment": {"tasks", "funding"},
    "marketing": {"tasks", "marketing"},
    "advertising": {"tasks", "marketing"},
    "tasks": {"tasks"},
}
_ALL_SECTIONS = {"tasks", "beta", "funding", "marketing"}

_EVIDENCE_DISCIPLINE = (
    "EVIDENCE DISCIPLINE FOR WHOEVER PICKS THIS UP:\n"
    "  Every figure below was read live from a real source (the task "
    "ledger, the actual beta checklist file, or a live database query) "
    "at the timestamp above -- none of it is estimated or remembered. "
    "Do not extend, round up, or fill gaps in this briefing with "
    "plausible-sounding numbers or claims. Where something below says "
    "\"not tracked\" or \"unavailable,\" that is the honest current state, "
    "not a placeholder to fabricate a fix for -- verify from the real "
    "source cited before adding anything new here."
)


def _sections_for(topic: str) -> set[str]:
    topic_lower = topic.strip().lower()
    for key, sections in _TOPIC_SECTIONS.items():
        if key in topic_lower:
            return sections
    return set(_ALL_SECTIONS)


def compose_agent_briefing(topic: str = "") -> dict:
    from thursday.ops import task_ledger

    sections = _sections_for(topic)
    data: dict = {
        "generated_at": datetime.now().isoformat(),
        "topic": topic or "(general — no topic given)",
        "sections_included": sorted(sections),
    }

    if "tasks" in sections:
        data["tasks"] = {
            "active": [t.to_dict() for t in task_ledger.active_tasks()],
            "blocked": [t.to_dict() for t in task_ledger.blocked_tasks()],
            "needs_approval": [t.to_dict() for t in task_ledger.tasks_requiring_approval()],
        }

    if "beta" in sections:
        from thursday.ops import qa_ops
        data["beta_readiness_report"] = qa_ops.beta_readiness_check()

    if "funding" in sections:
        from thursday.ops import funding_ops
        data["funding_readiness_report"] = funding_ops.funding_readiness_report()

    if "marketing" in sections:
        from thursday.ops import marketing_ops, advertising_ops
        data["marketing_readiness_report"] = marketing_ops.audit_marketing_readiness()
        data["ad_readiness_report"] = advertising_ops.ad_readiness_check()

    return data


def render_agent_briefing(data: dict) -> str:
    lines = [
        "AGENT BRIEFING",
        f"Generated: {data['generated_at']}",
        f"Topic: {data['topic']}",
        f"Sections included: {', '.join(data['sections_included'])}",
        "",
        _EVIDENCE_DISCIPLINE,
        "",
    ]

    if "tasks" in data:
        t = data["tasks"]
        lines.append("TASK LEDGER STATE:")
        if t["active"]:
            lines.append(f"  Active ({len(t['active'])}):")
            for raw in t["active"]:
                lines.append(f"    - [{raw['workstream']}] {raw['objective']} ({raw['task_id']}) — {raw['status']}")
        else:
            lines.append("  Active: none.")
        if t["blocked"]:
            lines.append(f"  Blocked ({len(t['blocked'])}):")
            for raw in t["blocked"]:
                reason = raw["blockers"][-1] if raw["blockers"] else "no reason recorded"
                lines.append(f"    - [{raw['workstream']}] {raw['objective']} ({raw['task_id']}): {reason}")
        else:
            lines.append("  Blocked: none.")
        if t["needs_approval"]:
            lines.append(f"  Awaiting approval ({len(t['needs_approval'])}):")
            for raw in t["needs_approval"]:
                lines.append(f"    - [{raw['workstream']}] {raw['objective']} ({raw['task_id']})")
        else:
            lines.append("  Awaiting approval: none.")
        lines.append("")

    if "beta_readiness_report" in data:
        lines.append("--- BETA READINESS (live-parsed, see report for source path) ---")
        lines.append(data["beta_readiness_report"])
        lines.append("")

    if "funding_readiness_report" in data:
        lines.append("--- FUNDING READINESS (live-queried) ---")
        lines.append(data["funding_readiness_report"])
        lines.append("")

    if "marketing_readiness_report" in data:
        lines.append("--- MARKETING READINESS ---")
        lines.append(data["marketing_readiness_report"])
        lines.append("")

    if "ad_readiness_report" in data:
        lines.append("--- AD READINESS ---")
        lines.append(data["ad_readiness_report"])
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def brief_agent(topic: str = "") -> str:
    return render_agent_briefing(compose_agent_briefing(topic))


# ── Command parsing ───────────────────────────────────────────────────────

_COMMAND_PREFIXES = [
    "brief another agent on", "brief another agent",
    "brief an agent on", "brief an agent",
    "brief codex on", "brief codex",
    "brief gemini on", "brief gemini",
]


def parse_brief_agent_command(text: str) -> str | None:
    """Returns the topic string (possibly empty) if ``text`` is a brief-
    agent command, else None. Unlike task_ledger/ops_intake's parsers,
    this never raises -- there's no invalid form of "brief agent" the way
    an empty task objective is invalid; a bare "brief another agent" with
    no topic is a legitimate request for a general briefing.
    """
    stripped = text.strip()
    lower = stripped.lower()
    # Longest-prefix-first so "brief another agent on X" doesn't get cut
    # short by the topic-less "brief another agent" entry matching first.
    for prefix in sorted(_COMMAND_PREFIXES, key=len, reverse=True):
        if lower.startswith(prefix.lower()):
            topic = stripped[len(prefix):].strip()
            if topic.lower().startswith("on "):
                topic = topic[3:].strip()
            return topic
    return None
