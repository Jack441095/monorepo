"""Durable, review-gated promotion evidence for the Live command planner."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any


PROMOTION_THRESHOLDS = {
    "shadow_to_propose": {
        "comparisons": 500,
        "observation_days": 14.0,
        "schema_acceptance_rate": 0.98,
        "deterministic_match_rate": 0.90,
    },
    "propose_to_active": {
        "proposals": 1000,
        "user_acceptance_rate": 0.95,
        "safety_violations": 0,
    },
}

PROMOTION_STATE_PATH = Path(
    os.environ.get(
        "KENN_LIVE_LLM_PROMOTION_STATE",
        str(Path(__file__).resolve().parents[1] / "data" / "live_llm_promotion.json"),
    )
).expanduser()
VALID_STAGES = ("shadow", "propose", "active")


def load_promotion_state(path: Path | None = None) -> dict[str, Any]:
    target = path or PROMOTION_STATE_PATH
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    stage = str(payload.get("stage") or "shadow")
    if stage not in VALID_STAGES:
        stage = "shadow"
    return {
        "schema": "kenn.ableton_llm_promotion_state.v1",
        "stage": stage,
        "stage_entered_at": payload.get("stage_entered_at"),
        "updated_at": payload.get("updated_at"),
        "last_assessment": payload.get("last_assessment"),
        "history": payload.get("history") if isinstance(payload.get("history"), list) else [],
    }


def _metric(metrics: dict[str, Any], name: str, default: float = 0.0) -> float:
    try:
        return float(metrics.get(name, default) or 0.0)
    except (TypeError, ValueError):
        return default


def assess_promotion(metrics: dict[str, Any], *, stage: str = "shadow") -> dict[str, Any]:
    """Evaluate one stage without changing runtime planner configuration."""
    if stage not in VALID_STAGES:
        raise ValueError(f"Unknown LLM promotion stage: {stage}")
    if stage == "active":
        return {"stage": stage, "eligible": False, "next_stage": None, "blockers": ["active is the final stage"]}
    transition = "shadow_to_propose" if stage == "shadow" else "propose_to_active"
    thresholds = PROMOTION_THRESHOLDS[transition]
    blockers: list[str] = []
    if stage == "shadow":
        checks = (
            ("comparisons", _metric(metrics, "comparisons"), thresholds["comparisons"], ">="),
            ("observation_days", _metric(metrics, "observation_days"), thresholds["observation_days"], ">="),
            ("schema_acceptance_rate", _metric(metrics, "schema_acceptance_rate"), thresholds["schema_acceptance_rate"], ">="),
            ("deterministic_match_rate", _metric(metrics, "deterministic_match_rate"), thresholds["deterministic_match_rate"], ">="),
        )
        next_stage = "propose"
    else:
        checks = (
            ("proposals", _metric(metrics, "proposals"), thresholds["proposals"], ">="),
            ("user_acceptance_rate", _metric(metrics, "user_acceptance_rate"), thresholds["user_acceptance_rate"], ">="),
            ("safety_violations", _metric(metrics, "safety_violations"), thresholds["safety_violations"], "=="),
        )
        next_stage = "active"
    for name, observed, required, operator in checks:
        passed = observed >= required if operator == ">=" else observed == required
        if not passed:
            blockers.append(f"{name} is {observed:g}; requires {operator} {required:g}")
    return {
        "transition": transition,
        "stage": stage,
        "next_stage": next_stage,
        "eligible": not blockers,
        "blockers": blockers,
        "metrics": dict(metrics),
        "thresholds": dict(thresholds),
        "live_activation_allowed": False,
    }


def record_promotion_assessment(
    metrics: dict[str, Any],
    *,
    path: Path | None = None,
    approve_transition: bool = False,
    reviewer: str = "",
) -> dict[str, Any]:
    """Persist evidence and optionally record an explicit reviewed transition."""
    target = path or PROMOTION_STATE_PATH
    state = load_promotion_state(target)
    assessment = assess_promotion(metrics, stage=state["stage"])
    now = time.time()
    transitioned = False
    if approve_transition:
        if not assessment["eligible"]:
            raise ValueError("Promotion thresholds are not satisfied: " + "; ".join(assessment["blockers"]))
        if not str(reviewer).strip():
            raise ValueError("An explicit reviewer identity is required to record a promotion transition.")
        previous = state["stage"]
        state["stage"] = str(assessment["next_stage"])
        state["stage_entered_at"] = now
        state["history"].append({
            "from": previous,
            "to": state["stage"],
            "reviewer": str(reviewer).strip()[:128],
            "recorded_at": now,
            "assessment": assessment,
        })
        transitioned = True
    state["updated_at"] = now
    state["last_assessment"] = assessment
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, prefix=".llm-promotion-", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(json.dumps(state, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, target)
    return {**state, "transitioned": transitioned}


__all__ = [
    "PROMOTION_THRESHOLDS",
    "PROMOTION_STATE_PATH",
    "assess_promotion",
    "load_promotion_state",
    "record_promotion_assessment",
]
