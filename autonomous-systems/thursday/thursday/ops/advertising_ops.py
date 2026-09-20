"""Advertising planning (Thursday Ops upgrade, phase 2).

Same non-fabrication stance as thursday.ops.marketing_ops: Thursday cannot
originate ad copy, target audiences, or budget recommendations from
nothing without either a working LLM (not reliably available -- see
thursday/orchestrator.py's chat_only brain gate) or real market data it
doesn't have. This module structures and persists what the founder
supplies and is honest about what's unverified.

The one deterministic thing Thursday genuinely can check without
fabricating anything: whether NITE DSP's own systems record readiness
signals for running ads at all (any marketing plans on file, any
advertising-workstream tasks already tracked). It cannot check landing
page / checkout / analytics readiness -- no data source for those exists
-- so ad_readiness_check() says "Evidence missing" for those rather than
guessing, and NEVER returns a decision more permissive than
"prepare only" on the strength of missing data.

**Hard safety rule, not just a plan field**: nothing in this module spends
money or launches a live ad. create_campaign_plan() only ever produces a
plan and a task_ledger entry requiring approval -- there is no
"launch_campaign" function here, deliberately.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime

from thursday.atomic_io import atomic_write
from thursday.ops.ops_intake import parse_structured_command
from thursday.runtime_paths import DATA_DIR

CAMPAIGN_PLANS_FILE = DATA_DIR / "ad_campaign_plans.json"

_NOT_SPECIFIED = "Not specified — founder to provide."
_EVIDENCE_MISSING = "Evidence missing — no data source connected yet."

FIELD_ALIASES = {
    "platform": "platform",
    "audience": "audience",
    "budget": "budget_scenarios",
    "budget scenarios": "budget_scenarios",
    "messaging": "messaging_angle",
    "messaging angle": "messaging_angle",
    "angle": "messaging_angle",
    "ad copy": "ad_copy_variants",
    "copy": "ad_copy_variants",
    "creative": "creative_brief",
    "creative brief": "creative_brief",
    "landing page": "landing_page_requirements",
    "tracking": "tracking_requirements",
    "risks": "risks",
}

_LIST_FIELDS = {"budget_scenarios", "ad_copy_variants", "risks"}

_COMMAND_PREFIXES = [
    "create campaign plan:", "new campaign plan:", "create ad campaign plan:",
]


@dataclass
class AdCampaignPlan:
    plan_id: str
    created_at: str
    product: str
    platform: str = ""
    audience: str = ""
    budget_scenarios: list[str] = field(default_factory=list)
    messaging_angle: str = ""
    ad_copy_variants: list[str] = field(default_factory=list)
    creative_brief: str = ""
    landing_page_requirements: str = ""
    tracking_requirements: str = ""
    risks: list[str] = field(default_factory=list)
    task_id: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _load() -> dict:
    if CAMPAIGN_PLANS_FILE.exists():
        try:
            data = json.loads(CAMPAIGN_PLANS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "plans" in data:
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {"next_id": 1, "plans": {}}


def _save(data: dict) -> None:
    CAMPAIGN_PLANS_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        atomic_write(CAMPAIGN_PLANS_FILE, json.dumps(data, indent=2))
    except OSError:
        pass


def parse_create_campaign_plan_command(text: str):
    return parse_structured_command(text, _COMMAND_PREFIXES, FIELD_ALIASES, _LIST_FIELDS)


def create_campaign_plan(
    product: str,
    *,
    platform: str = "",
    audience: str = "",
    budget_scenarios: list[str] | None = None,
    messaging_angle: str = "",
    ad_copy_variants: list[str] | None = None,
    creative_brief: str = "",
    landing_page_requirements: str = "",
    tracking_requirements: str = "",
    risks: list[str] | None = None,
) -> AdCampaignPlan:
    from thursday.ops import task_ledger

    data = _load()
    plan_id = f"ad-{data['next_id']}"
    data["next_id"] += 1

    task = task_ledger.create_task(
        "advertising",
        f"Ad campaign plan: {product}",
        approval_required=True,
        risk_level="medium",
        next_action="Review the campaign plan and approve before any spend or launch.",
    )

    plan = AdCampaignPlan(
        plan_id=plan_id,
        created_at=datetime.now().isoformat(),
        product=product,
        platform=platform,
        audience=audience,
        budget_scenarios=list(budget_scenarios or []),
        messaging_angle=messaging_angle,
        ad_copy_variants=list(ad_copy_variants or []),
        creative_brief=creative_brief,
        landing_page_requirements=landing_page_requirements,
        tracking_requirements=tracking_requirements,
        risks=list(risks or []),
        task_id=task.task_id,
    )
    data["plans"][plan_id] = plan.to_dict()
    _save(data)
    return plan


def get_campaign_plan(plan_id: str) -> AdCampaignPlan | None:
    data = _load()
    raw = data["plans"].get(plan_id)
    return AdCampaignPlan(**raw) if raw else None


def list_campaign_plans() -> list[AdCampaignPlan]:
    data = _load()
    plans = [AdCampaignPlan(**raw) for raw in data["plans"].values()]
    plans.sort(key=lambda p: p.created_at)
    return plans


def render_campaign_plan(plan: AdCampaignPlan) -> str:
    def _line(items: list[str]) -> str:
        return ", ".join(items) if items else _NOT_SPECIFIED

    lines = [
        "AD CAMPAIGN PLAN",
        "",
        f"PRODUCT: {plan.product}",
        f"PLATFORM: {plan.platform or _NOT_SPECIFIED}",
        f"AUDIENCE: {plan.audience or _NOT_SPECIFIED}",
        f"BUDGET SCENARIOS: {_line(plan.budget_scenarios)}",
        f"MESSAGING ANGLE: {plan.messaging_angle or _NOT_SPECIFIED}",
        f"AD COPY VARIANTS: {_line(plan.ad_copy_variants)}",
        f"CREATIVE BRIEF: {plan.creative_brief or _NOT_SPECIFIED}",
        f"LANDING PAGE REQUIREMENTS: {plan.landing_page_requirements or _NOT_SPECIFIED}",
        f"TRACKING REQUIREMENTS: {plan.tracking_requirements or _NOT_SPECIFIED}",
        f"RISKS: {_line(plan.risks)}",
        "APPROVAL REQUIRED: before any spend or launch, on any platform, "
        "at any budget.",
        f"NEXT ACTION: Review and approve ({plan.task_id}), or refine with "
        "another \"create campaign plan:\" command.",
    ]
    return "\n".join(lines)


def ad_readiness_check() -> str:
    """The AD READINESS CHECK template. Only two lines here are things
    Thursday can actually verify (plans/tasks on file); everything else
    has no connected data source and says so -- and the overall Decision
    line never claims more than "Not ready" / "Prepare only" when
    anything critical reads Evidence missing, regardless of how the
    prepared items look.
    """
    from thursday.ops import task_ledger

    plans = list_campaign_plans()
    ad_tasks = task_ledger.tasks_by_workstream("advertising")
    approved_something = any(
        t.status == "done" and t.approval_required for t in ad_tasks
    )

    lines = [
        "AD READINESS CHECK",
        "",
        f"Product ready? {_EVIDENCE_MISSING}",
        f"Landing page ready? {_EVIDENCE_MISSING}",
        f"Checkout ready? {_EVIDENCE_MISSING}",
        f"Download delivery ready? {_EVIDENCE_MISSING}",
        f"Support page ready? {_EVIDENCE_MISSING}",
        f"Refund policy ready? {_EVIDENCE_MISSING}",
        f"Analytics ready? {_EVIDENCE_MISSING}",
        f"Conversion event ready? {_EVIDENCE_MISSING}",
        f"Budget approved? {'Yes (task approved) ' if approved_something else 'No'} — "
        f"{len(ad_tasks)} advertising task(s) in the ledger.",
        f"Audience defined? {'Yes, in at least one plan on file.' if any(p.audience for p in plans) else 'No plan on file defines one yet.'}",
        f"Creative assets ready? {_EVIDENCE_MISSING}",
        f"Legal/privacy copy ready? {_EVIDENCE_MISSING}",
        f"Founder approval received? {'At least one approved ad task exists.' if approved_something else 'No.'}",
        "",
        "Decision:",
        "- Prepare only" if plans or ad_tasks else "- Not ready",
        "",
        "(Most items above have no connected data source yet and read "
        "\"Evidence missing\" rather than a guessed status -- the decision "
        "line will never exceed \"Prepare only\" until those are wired up "
        "and confirmed ready.)",
    ]
    return "\n".join(lines)
