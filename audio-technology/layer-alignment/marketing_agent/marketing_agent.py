"""Research-only typed marketing planner. It produces plans, never external writes."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import json
from pathlib import Path


class EvidenceKind(str, Enum):
    FACT = "FACT"
    MARKET_OBSERVATION = "MARKET_OBSERVATION"
    INFERENCE = "INFERENCE"
    STRATEGY = "STRATEGY"
    CREATIVE_IDEA = "CREATIVE_IDEA"


@dataclass(frozen=True)
class Insight:
    text: str
    kind: EvidenceKind
    source: str
    confidence: float


@dataclass(frozen=True)
class Audience:
    name: str
    job_to_be_done: str
    evidence: list[Insight] = field(default_factory=list)


@dataclass(frozen=True)
class Experiment:
    name: str
    hypothesis: str
    metric: str
    guardrail: str


@dataclass(frozen=True)
class Campaign:
    name: str
    goal: str
    audience: Audience
    channels: list[str]
    insights: list[Insight]
    experiments: list[Experiment]
    external_writes: list[str] = field(default_factory=list)


def plan_slo_launch() -> Campaign:
    audience = Audience(
        name="Ableton-first sample producers",
        job_to_be_done="Find useful samples quickly without losing trust in tags or musical context",
        evidence=[Insight("Live exposes tag search and sound similarity search as core browser workflows.", EvidenceKind.FACT, "https://www.ableton.com/en/live/", 1.0)],
    )
    insights = [
        Insight("SLO's current benchmark is single-vendor and has known filename ambiguity.", EvidenceKind.FACT, "Nite_DSP_RnD SLO V5 baseline audit", 0.98),
        Insight("Search trust is likely a stronger launch message than generic AI classification.", EvidenceKind.INFERENCE, "SLO benchmark limitations + Ableton workflow", 0.74),
        Insight("Show before/after retrieval examples using legally cleared fixtures.", EvidenceKind.STRATEGY, "Derived launch strategy", 0.82),
        Insight("A short browser demo comparing ambiguous names could be a compelling creative asset.", EvidenceKind.CREATIVE_IDEA, "Research hypothesis", 0.45),
    ]
    experiments = [
        Experiment("retrieval-proof", "A concrete search task outperforms abstract AI claims.", "qualified demo completion rate", "no claim beyond benchmark scope"),
        Experiment("vendor-honesty", "Explicitly stating supported corpus limits increases trust.", "landing-page quality score", "do not imply multi-vendor accuracy before validation"),
    ]
    return Campaign("SLO four-week launch research plan", "Validate qualified demand and trust messaging", audience, ["owned website", "Ableton community research", "email draft only"], insights, experiments)


def main() -> None:
    campaign = plan_slo_launch()
    payload = {"contract": ["marketing.launch.plan", "marketing.campaign.status", "marketing.content.plan", "marketing.market.research", "marketing.experiments.list"], "campaign": asdict(campaign), "external_writes": campaign.external_writes}
    Path(__file__).with_name("plan.json").write_text(json.dumps(payload, indent=2, default=lambda value: value.value), encoding="utf-8")
    print(json.dumps({"campaign": campaign.name, "insights": len(campaign.insights), "experiments": len(campaign.experiments), "external_writes": campaign.external_writes}, indent=2))


if __name__ == "__main__":
    main()
