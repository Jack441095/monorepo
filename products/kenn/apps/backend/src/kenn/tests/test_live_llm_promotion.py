"""Evidence gates for staged Live-command model promotion."""

from __future__ import annotations

import pytest

from kenn.core.live_llm_promotion import assess_promotion, load_promotion_state, record_promotion_assessment


def test_shadow_promotion_requires_volume_duration_acceptance_and_match() -> None:
    blocked = assess_promotion({
        "comparisons": 499,
        "observation_days": 13.9,
        "schema_acceptance_rate": 0.979,
        "deterministic_match_rate": 0.899,
    })
    assert blocked["eligible"] is False
    assert len(blocked["blockers"]) == 4

    eligible = assess_promotion({
        "comparisons": 500,
        "observation_days": 14,
        "schema_acceptance_rate": 0.98,
        "deterministic_match_rate": 0.90,
    })
    assert eligible["eligible"] is True
    assert eligible["next_stage"] == "propose"
    assert eligible["live_activation_allowed"] is False


def test_propose_to_active_requires_zero_safety_violations() -> None:
    result = assess_promotion({
        "proposals": 1200,
        "user_acceptance_rate": 0.99,
        "safety_violations": 1,
    }, stage="propose")
    assert result["eligible"] is False
    assert "safety_violations" in result["blockers"][0]


def test_durable_transition_requires_eligibility_and_explicit_reviewer(tmp_path) -> None:
    path = tmp_path / "promotion.json"
    metrics = {
        "comparisons": 500,
        "observation_days": 14,
        "schema_acceptance_rate": 0.98,
        "deterministic_match_rate": 0.90,
    }
    assessment = record_promotion_assessment(metrics, path=path)
    assert assessment["stage"] == "shadow"
    assert assessment["transitioned"] is False

    with pytest.raises(ValueError, match="reviewer"):
        record_promotion_assessment(metrics, path=path, approve_transition=True)

    promoted = record_promotion_assessment(metrics, path=path, approve_transition=True, reviewer="demo-owner")
    assert promoted["stage"] == "propose"
    assert promoted["transitioned"] is True
    assert isinstance(promoted["stage_entered_at"], float)
    assert load_promotion_state(path)["history"][0]["reviewer"] == "demo-owner"
