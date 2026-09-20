"""Offline advisor replay harness tests."""

from __future__ import annotations

from dataclasses import asdict

from scripts.eval.automix_advisor_replay import plan_from_dict, replay_cases
from audio_analysis.integration.kenn_advisor import CONTRACT_SCHEMA, mix_plan_revision
from audio_analysis.mixdown.mix_decision_engine import BusMixConfig, MixPlan, StemMixConfig


def _plan() -> MixPlan:
    return MixPlan(
        stems=[
            StemMixConfig(
                stem_name="stem-01",
                instrument="vocal",
                compressor={"ratio": 3.0},
            )
        ],
        bus=BusMixConfig(),
        genre="pop",
        target_lufs=-14.0,
        musical_roles=[{
            "schema": "audio-too.musical-role.v1",
            "stem_name": "stem-01",
            "role": "focal_element",
            "ambiguous": False,
        }],
        arrangement={"schema": "audio-too.arrangement.v1", "sections": []},
        relationships=[{"schema": "audio-too.relationship.v1", "applies_automatically": False}],
    )


def _proposal(plan: MixPlan, correlation_id: str, *, value: float) -> dict:
    return {
        "schema": CONTRACT_SCHEMA,
        "source_plan_revision": mix_plan_revision(plan),
        "model_version": "replay-fixture-v1",
        "prompt_version": "advisor-v1",
        "correlation_id": correlation_id,
        "operations": [
            {
                "stem_id": "stem-01",
                "operation": "gain_delta",
                "value": value,
                "unit": "dB",
                "evidence_source_ids": ["source-01"],
                "confidence": 0.9,
                "reason": "Reviewed replay fixture.",
            }
        ],
    }


def test_plan_round_trip_preserves_revision() -> None:
    plan = _plan()
    restored = plan_from_dict(asdict(plan))
    assert restored == plan
    assert mix_plan_revision(restored) == mix_plan_revision(plan)


def test_replay_scores_valid_rejected_and_human_ratings() -> None:
    plan = _plan()
    cases = [
        {
            "id": "anon-valid-01",
            "plan": asdict(plan),
            "correlation_id": "automix-replay:anon-valid-01",
            "proposal": _proposal(plan, "automix-replay:anon-valid-01", value=1.5),
            "expected_status": "valid",
            "human_ratings": {
                "usefulness": 4,
                "audible_improvement": 3,
                "explanation_quality": 5,
            },
        },
        {
            "id": "anon-rejected-01",
            "plan": asdict(plan),
            "correlation_id": "automix-replay:anon-rejected-01",
            "proposal": _proposal(plan, "automix-replay:anon-rejected-01", value=9.0),
            "expected_status": "rejected",
        },
    ]
    report = replay_cases(cases)
    assert report["summary"]["status_counts"]["valid"] == 1
    assert report["summary"]["status_counts"]["rejected"] == 1
    assert report["summary"]["schema_valid_rate"] == 0.5
    assert report["summary"]["expected_status_accuracy"] == 1.0
    assert report["summary"]["human_rating_coverage"]["usefulness"] == 0.5
    assert report["summary"]["human_rating_means"]["explanation_quality"] == 5.0
    assert report["results"][0]["would_change"][0]["delta"] == 1.5
