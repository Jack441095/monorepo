"""Marketing planning (Thursday Ops upgrade, phase 2).

Thursday has no working LLM path that can originate real content (the
LLM brain that IS reachable, thursday.brain, runs chat_only and is
structurally forbidden from doing anything but talk or abstain -- see
thursday/orchestrator.py's "LLM Brain Gating" comment -- and even a
non-chat_only brain call would be fabricating marketing claims from
nothing, which the whole reorg has held itself to never doing). So this
module does NOT try to generate a marketing plan's content. It structures
and persists what the founder actually supplies, renders it in the spec's
MARKETING PLAN format, and is honest -- "Not specified" -- about anything
left blank rather than inventing a core message, an audience, or proof
points that were never given.

Every plan is approval-gated before anything public happens with it: the
founder-facing task_ledger entry created alongside it is
approval_required=True. That flag is a planning marker only, not a
substitute for thursday's real confirmation-token system (see
task_ledger.py's own module docstring for why).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime

from thursday.atomic_io import atomic_write
from thursday.ops.ops_intake import parse_structured_command
from thursday.runtime_paths import DATA_DIR

MARKETING_PLANS_FILE = DATA_DIR / "marketing_plans.json"

_NOT_SPECIFIED = "Not specified — founder to provide."

FIELD_ALIASES = {
    "audience": "audience",
    "core message": "core_message",
    "message": "core_message",
    "proof": "proof_evidence",
    "evidence": "proof_evidence",
    "proof/evidence": "proof_evidence",
    "channels": "channels",
    "content ideas": "content_ideas",
    "assets": "assets_needed",
    "assets needed": "assets_needed",
    "risks": "risks",
}

_LIST_FIELDS = {"channels", "content_ideas", "assets_needed", "risks"}

_COMMAND_PREFIXES = [
    "create marketing plan:", "new marketing plan:", "add marketing plan:",
]


@dataclass
class MarketingPlan:
    plan_id: str
    created_at: str
    objective: str
    audience: str = ""
    core_message: str = ""
    proof_evidence: str = ""
    channels: list[str] = field(default_factory=list)
    content_ideas: list[str] = field(default_factory=list)
    assets_needed: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    task_id: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _load() -> dict:
    if MARKETING_PLANS_FILE.exists():
        try:
            data = json.loads(MARKETING_PLANS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "plans" in data:
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {"next_id": 1, "plans": {}}


def _save(data: dict) -> None:
    MARKETING_PLANS_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        atomic_write(MARKETING_PLANS_FILE, json.dumps(data, indent=2))
    except OSError:
        pass


def parse_create_marketing_plan_command(text: str):
    """Returns (objective, fields_dict) or None if not this command.
    Raises ValueError if the shape matches but the objective is empty.
    """
    return parse_structured_command(text, _COMMAND_PREFIXES, FIELD_ALIASES, _LIST_FIELDS)


def create_marketing_plan(
    objective: str,
    *,
    audience: str = "",
    core_message: str = "",
    proof_evidence: str = "",
    channels: list[str] | None = None,
    content_ideas: list[str] | None = None,
    assets_needed: list[str] | None = None,
    risks: list[str] | None = None,
) -> MarketingPlan:
    from thursday.ops import task_ledger

    data = _load()
    plan_id = f"mkt-{data['next_id']}"
    data["next_id"] += 1

    task = task_ledger.create_task(
        "marketing",
        objective,
        approval_required=True,
        next_action="Review the marketing plan and approve before anything goes public.",
    )

    plan = MarketingPlan(
        plan_id=plan_id,
        created_at=datetime.now().isoformat(),
        objective=objective,
        audience=audience,
        core_message=core_message,
        proof_evidence=proof_evidence,
        channels=list(channels or []),
        content_ideas=list(content_ideas or []),
        assets_needed=list(assets_needed or []),
        risks=list(risks or []),
        task_id=task.task_id,
    )
    data["plans"][plan_id] = plan.to_dict()
    _save(data)
    return plan


def get_marketing_plan(plan_id: str) -> MarketingPlan | None:
    data = _load()
    raw = data["plans"].get(plan_id)
    return MarketingPlan(**raw) if raw else None


def list_marketing_plans() -> list[MarketingPlan]:
    data = _load()
    plans = [MarketingPlan(**raw) for raw in data["plans"].values()]
    plans.sort(key=lambda p: p.created_at)
    return plans


def render_marketing_plan(plan: MarketingPlan) -> str:
    def _line(items: list[str]) -> str:
        return ", ".join(items) if items else _NOT_SPECIFIED

    lines = [
        "MARKETING PLAN",
        "",
        f"OBJECTIVE: {plan.objective}",
        f"AUDIENCE: {plan.audience or _NOT_SPECIFIED}",
        f"CORE MESSAGE: {plan.core_message or _NOT_SPECIFIED}",
        f"PROOF/EVIDENCE: {plan.proof_evidence or _NOT_SPECIFIED}",
        f"CHANNELS: {_line(plan.channels)}",
        f"CONTENT IDEAS: {_line(plan.content_ideas)}",
        f"ASSETS NEEDED: {_line(plan.assets_needed)}",
        "APPROVAL REQUIRED BEFORE: publishing anything from this plan publicly "
        "(website, social, email, or any external channel).",
        f"RISKS: {_line(plan.risks)}",
        f"NEXT ACTION: Review and approve ({plan.task_id}), or refine with "
        "another \"create marketing plan:\" command.",
    ]
    return "\n".join(lines)


def audit_marketing_readiness() -> str:
    """Deterministic checklist over what Thursday can actually observe:
    task_ledger's marketing-workstream tasks. No website-copy, brand-tone,
    or content-quality data source is wired up -- says so plainly rather
    than guessing at readiness it has no evidence for.
    """
    from thursday.ops import task_ledger

    marketing_tasks = task_ledger.tasks_by_workstream("marketing")
    plans = list_marketing_plans()

    lines = ["MARKETING READINESS AUDIT", ""]
    lines.append(f"Marketing plans on file: {len(plans)}")
    lines.append(f"Marketing tasks in the ledger: {len(marketing_tasks)}")
    open_tasks = [t for t in marketing_tasks if t.status not in ("done", "cancelled")]
    lines.append(f"Open marketing tasks: {len(open_tasks)}")
    pending_approval = [t for t in marketing_tasks if t.approval_required and t.status not in ("done", "cancelled")]
    lines.append(f"Plans awaiting approval: {len(pending_approval)}")
    lines.append("")
    lines.append(
        "Website copy quality, brand tone consistency, and channel "
        "performance have no connected data source -- Evidence missing, "
        "not assessed here."
    )
    return "\n".join(lines)
