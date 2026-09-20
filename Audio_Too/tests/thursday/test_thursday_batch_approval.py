"""Batch approval security and exactly-once tests.

Attack matrix (§35): step added / removed / reordered, argument mutated,
service substituted, expiry, replay, duplicate submission, partial
execution, crash mid-plan. Synthetic services only — no real writes.
"""

from __future__ import annotations

import time

import pytest

from thursday import action_receipts as receipts
from thursday.plan_approval import (
    ApprovalPlan,
    PlanStep,
    canonical_plan_bytes,
    execute_approved_plan,
    issue_batch_confirmation,
    plan_hash,
    verify_batch_confirmation,
)


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("THURSDAY_ACTION_RECEIPTS_DB", str(tmp_path / "r.sqlite3"))
    monkeypatch.setenv("THURSDAY_CONFIRMATION_SECRET", "batch-test-secret-entropy")


def make_plan(**overrides) -> ApprovalPlan:
    steps = overrides.get("steps") or (
        PlanStep("email.send", "send summary", {"to": "jack@nite.test"}),
        PlanStep("calendar.book", "book review", {"when": "friday 10am"}),
        PlanStep("file.export", "export stems", {"format": "wav"}),
    )
    return ApprovalPlan(
        plan_id=overrides.get("plan_id", "plan-1"),
        session_id=overrides.get("session_id", "owner"),
        steps=steps,
        created_at_epoch=time.time(),
    )


def test_plan_hash_is_stable_and_order_sensitive():
    p1 = make_plan()
    p2 = make_plan()
    assert plan_hash(p1) == plan_hash(p2)  # same semantic plan → same hash

    reordered = make_plan(steps=tuple(reversed(p1.steps)))
    assert plan_hash(reordered) != plan_hash(p1)

    canonical = canonical_plan_bytes(p1.steps)
    assert canonical == canonical_plan_bytes(make_plan().steps)


# ─── Mutation attacks invalidate the approval ───────────────────────────


def test_step_added_after_approval_rejected():
    plan = make_plan()
    token, _ = issue_batch_confirmation(plan)
    mutated = make_plan(steps=plan.steps + (PlanStep("payment.send", "extra", {}),))
    assert not verify_batch_confirmation(token, mutated)


def test_step_removed_after_approval_rejected():
    plan = make_plan()
    token, _ = issue_batch_confirmation(plan)
    mutated = make_plan(steps=plan.steps[:2])
    assert not verify_batch_confirmation(token, mutated)


def test_step_reordered_after_approval_rejected():
    plan = make_plan()
    token, _ = issue_batch_confirmation(plan)
    s = list(plan.steps)
    s[0], s[1] = s[1], s[0]
    assert not verify_batch_confirmation(token, make_plan(steps=tuple(s)))


def test_argument_mutation_rejected():
    plan = make_plan()
    token, _ = issue_batch_confirmation(plan)
    s = list(plan.steps)
    s[0] = PlanStep(s[0].service_id, s[0].text, {"to": "attacker@evil.test"})
    assert not verify_batch_confirmation(token, make_plan(steps=tuple(s)))


def test_service_substitution_rejected():
    plan = make_plan()
    token, _ = issue_batch_confirmation(plan)
    s = list(plan.steps)
    s[2] = PlanStep("shell.run", s[2].text, s[2].arguments)
    assert not verify_batch_confirmation(token, make_plan(steps=tuple(s)))


def test_cross_session_token_rejected():
    plan = make_plan(session_id="owner")
    token, _ = issue_batch_confirmation(plan)
    forged_session = make_plan(session_id="attacker")
    assert not verify_batch_confirmation(token, forged_session)


def test_expired_token_rejected(monkeypatch):
    plan = make_plan()
    token, _ = issue_batch_confirmation(plan, ttl_seconds=1)
    later = int(time.time()) + 10
    assert not verify_batch_confirmation(token, plan, now=later)


def test_forged_signature_rejected(monkeypatch):
    """A token minted under a different secret never verifies."""
    plan = make_plan()
    token, _ = issue_batch_confirmation(plan)
    monkeypatch.setenv("THURSDAY_CONFIRMATION_SECRET", "attacker-secret")
    assert not verify_batch_confirmation(token, plan)


def test_replay_of_valid_token_still_binds_to_same_plan_only():
    plan = make_plan()
    token, _ = issue_batch_confirmation(plan)
    # Same plan: verifies (idempotent check).
    assert verify_batch_confirmation(token, plan)
    # ANY other plan with the same token fails (covered by mutations above).


# ─── Execution: exactly-once per step + honest partial state ────────────


def test_happy_path_executes_all_steps_once():
    plan = make_plan()
    calls = []
    result = execute_approved_plan(
        plan,
        lambda svc, text, args: calls.append((svc, args)) or "done",
        session_id="owner",
    )
    assert result["partial"] is False
    assert result["executed_steps"] == [0, 1, 2]
    assert len(calls) == 3


def test_partial_execution_reports_exact_state():
    plan = make_plan()

    def executor(svc, text, args):
        if svc == "calendar.book":
            raise RuntimeError("provider down")
        return "ok"

    result = execute_approved_plan(plan, executor, session_id="owner")
    assert result["partial"] is True
    assert result["executed_steps"] == [0]
    assert result["not_executed_steps"] == [2]
    statuses = {s["index"]: s["status"] for s in result["steps"]}
    assert statuses == {0: "completed", 1: "failed"}


def test_crash_mid_plan_never_double_executes_on_retry():
    """Re-running the same approved plan after a mid-plan crash must NOT
    re-execute already-completed steps (receipt replay)."""
    plan = make_plan(plan_id="crashy")
    runs = {"n": 0}

    def executor(svc, text, args):
        runs["n"] += 1
        if svc == "calendar.book" and runs["n"] <= 3:
            raise RuntimeError("simulated crash")
        return f"ran-{svc}"

    first = execute_approved_plan(plan, executor, session_id="owner")
    assert first["executed_steps"] == [0]

    second = execute_approved_plan(plan, executor, session_id="owner")
    # Step 0 served from receipt (already_completed), NOT re-executed.
    step0 = next(s for s in second["steps"] if s["index"] == 0)
    assert step0["status"] == "already_completed"
    assert step0["response_text"] == "ran-email.send"


def test_duplicate_submission_shares_one_outcome():
    plan = make_plan(plan_id="dup")
    seen = set()
    def executor(svc, text, args):
        seen.add(svc)
        return f"did-{svc}"

    r1 = execute_approved_plan(plan, executor, session_id="owner")
    r2 = execute_approved_plan(plan, executor, session_id="owner")
    assert len(seen) == 3  # each service executed exactly once across both runs
    assert all(
        s["status"] == "already_completed" for s in r2["steps"]
    )
