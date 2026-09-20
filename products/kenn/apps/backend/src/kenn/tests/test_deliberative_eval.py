from __future__ import annotations

from kenn.core.deliberative_eval import evaluate_deliberative_plan
from kenn.core.deliberative_plan import DeliberativePlan, DeliberativeStep
from kenn.core.session_context import build_session_context


def _context() -> dict:
    return build_session_context(
        session_id="eval-session",
        snapshot={
            "status": "connected", "tempo": 126.0, "is_playing": False,
            "tracks": [
                {"index": 0, "name": "Kick", "type": "audio", "devices": []},
                {"index": 1, "name": "Bass", "type": "midi", "devices": []},
            ],
        },
    )


def _plan(context: dict) -> dict:
    return DeliberativePlan.create(
        goal="Separate kick and bass",
        context=context,
        status="ready",
        steps=[
            DeliberativeStep.create(
                step_id="inspect-low-end", kind="inspection", action="inspect_live",
                objective="Observe the low-end tracks.", rationale="Diagnosis needs current state.",
                expected_evidence=["fresh snapshot"],
            ),
            DeliberativeStep.create(
                step_id="propose-low-end", kind="live_proposal", action="create_live_proposal",
                objective="Prepare a bounded adjustment.", rationale="The producer must review exact changes.",
                depends_on=["inspect-low-end"], expected_evidence=["typed proposal"],
            ),
        ],
    ).to_dict()


def test_trajectory_eval_scores_capabilities_and_order_not_wording() -> None:
    context = _context()
    result = evaluate_deliberative_plan(_plan(context), context, {
        "status": "ready",
        "required_kinds": ["inspection", "live_proposal"],
        "required_actions": ["inspect_live", "create_live_proposal"],
        "forbidden_kinds": ["refusal"],
        "ordered_steps": [["inspect-low-end", "propose-low-end"]],
        "max_steps": 3,
    })

    assert result["passed"] is True
    assert result["score"] == 1.0


def test_trajectory_eval_fails_unsafe_or_incomplete_candidate() -> None:
    context = _context()
    candidate = _plan(context)
    candidate["steps"][1]["confirmation_required"] = False

    result = evaluate_deliberative_plan(candidate, context, {
        "status": "ready",
        "required_kinds": ["inspection", "live_proposal"],
    })

    assert result["passed"] is False
    assert result["score"] == 0.0
    assert result["checks"][0]["name"] == "contract_valid"


def test_trajectory_eval_scores_kind_and_action_subsequence_order() -> None:
    context = _context()
    candidate = _plan(context)

    passed = evaluate_deliberative_plan(candidate, context, {
        "ordered_kinds": ["inspection", "live_proposal"],
        "ordered_actions": ["inspect_live", "create_live_proposal"],
    })
    failed = evaluate_deliberative_plan(candidate, context, {
        "ordered_kinds": ["live_proposal", "inspection"],
    })

    assert passed["passed"] is True
    assert failed["passed"] is False
