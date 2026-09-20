from __future__ import annotations

from kenn.core.assistant_task_memory import AssistantTaskStore, MAX_ACTIVE_TASKS_PER_SESSION, TASK_SCHEMA
from kenn.core.deliberative_plan import DeliberativePlan, DeliberativeStep
from kenn.core.session_context import build_session_context, refresh_session_context_fingerprint


def _context() -> dict:
    return build_session_context(
        session_id="song-1",
        snapshot={
            "status": "connected", "tempo": 122.0, "is_playing": False,
            "tracks": [{"index": 0, "name": "Bass", "type": "midi", "devices": []}],
        },
    )


def _plan(context: dict) -> dict:
    inspect = DeliberativeStep.create(
        step_id="inspect", kind="inspection", action="inspect_live",
        objective="Inspect the bass.", rationale="Use current evidence.",
        expected_evidence=["fresh context"],
    )
    propose = DeliberativeStep.create(
        step_id="propose", kind="live_proposal", action="create_live_proposal",
        objective="Prepare a bass adjustment.", rationale="Review the exact change first.",
        depends_on=["inspect"], expected_evidence=["verified Live receipt"],
    )
    return DeliberativePlan.create(
        goal="Make the bass sit better", context=context, status="ready", steps=[inspect, propose],
    ).to_dict()


def test_task_survives_store_restart_and_resumes_current_step(tmp_path) -> None:
    path = tmp_path / "memory.db"
    context = _context()
    started = AssistantTaskStore(path).start(plan=_plan(context), context=context)

    resumed = AssistantTaskStore(path).resume("song-1")

    assert started["ok"] is True
    assert resumed["schema"] == TASK_SCHEMA
    assert resumed["task_id"] == started["task"]["task_id"]
    assert resumed["current_step_id"] == "inspect"
    assert resumed["status"] == "active"


def test_replan_atomically_supersedes_active_task_and_preserves_lineage(tmp_path) -> None:
    store = AssistantTaskStore(tmp_path / "memory.db")
    context = _context()
    original = store.start(plan=_plan(context), context=context)["task"]
    replacement = store.replace_for_replan(
        source_task_id=original["task_id"],
        plan=_plan(context),
        context=context,
        reason="Fresh session context required replanning.",
    )

    assert replacement["ok"] is True
    assert replacement["task"]["parent_task_id"] == original["task_id"]
    assert replacement["task"]["replan_depth"] == 1
    superseded = store.load(original["task_id"])
    assert superseded["status"] == "cancelled"
    assert superseded["superseded_by_task_id"] == replacement["task"]["task_id"]
    assert store.resume("song-1")["task_id"] == replacement["task"]["task_id"]


def test_replan_cannot_abandon_identity_bound_confirmation(tmp_path) -> None:
    store = AssistantTaskStore(tmp_path / "memory.db")
    context = _context()
    task = store.start(plan=_plan(context), context=context)["task"]
    store.record_step_evidence(task_id=task["task_id"], step_id="inspect", evidence=context)
    store.record_step_evidence(
        task_id=task["task_id"],
        step_id="propose",
        evidence={
            "schema": "kenn.ableton_action_proposal.v1",
            "status": "confirmation_required",
            "requires_confirmation": True,
            "action_id": "action-1",
        },
    )

    blocked = store.replace_for_replan(
        source_task_id=task["task_id"],
        plan=_plan(context),
        context=context,
        reason="Try to abandon it.",
    )

    assert blocked["ok"] is False
    assert "must be resolved" in blocked["errors"][0]
    assert store.load(task["task_id"])["status"] == "waiting_for_confirmation"


def test_task_advances_only_with_evidence_appropriate_to_each_step(tmp_path) -> None:
    store = AssistantTaskStore(tmp_path / "memory.db")
    context = _context()
    task = store.start(plan=_plan(context), context=context)["task"]

    rejected = store.record_step_evidence(
        task_id=task["task_id"], step_id="inspect",
        evidence={"schema": "kenn.user_response.v1", "response": "yes"},
    )
    inspected = store.record_step_evidence(
        task_id=task["task_id"], step_id="inspect", evidence=context,
    )

    assert rejected["ok"] is False
    assert store.load(task["task_id"])["completed_step_ids"] == ["inspect"]
    assert inspected["task"]["current_step_id"] == "propose"
    assert inspected["task"]["status"] == "active"


def test_inspection_evidence_must_match_the_specific_inspection_action(tmp_path) -> None:
    store = AssistantTaskStore(tmp_path / "memory.db")
    context = _context()
    step = DeliberativeStep.create(
        step_id="devices", kind="inspection", action="inspect_device_capabilities",
        objective="Inspect device capabilities.", rationale="Use exact device evidence.",
        expected_evidence=["device capability matrix"],
    )
    # This action is unavailable unless a capability matrix was observed.
    context["device_capability_matrix"] = {
        "schema": "kenn.ableton_device_matrix.v1", "entries": [],
    }
    context["available_actions"].append("inspect_device_capabilities")
    refresh_session_context_fingerprint(context)
    plan = DeliberativePlan.create(
        goal="Inspect devices", context=context, status="ready", steps=[step],
    ).to_dict()
    task = store.start(plan=plan, context=context)["task"]

    rejected = store.record_step_evidence(
        task_id=task["task_id"], step_id="devices",
        evidence={
            "schema": "kenn.audiogen_audio_comparison.v1",
            "status": "completed",
        },
    )
    accepted = store.record_step_evidence(
        task_id=task["task_id"], step_id="devices",
        evidence={"schema": "kenn.ableton_device_matrix.v1", "entries": []},
    )

    assert rejected["ok"] is False
    assert "does not satisfy" in rejected["error"]
    assert accepted["ok"] is True


def test_live_proposal_records_progress_but_is_not_completion_evidence(tmp_path) -> None:
    store = AssistantTaskStore(tmp_path / "memory.db")
    context = _context()
    task = store.start(plan=_plan(context), context=context)["task"]
    store.record_step_evidence(task_id=task["task_id"], step_id="inspect", evidence=context)

    proposal = store.record_step_evidence(
        task_id=task["task_id"], step_id="propose",
        evidence={
            "schema": "kenn.ableton_action_proposal.v1", "status": "confirmation_required",
            "requires_confirmation": True, "action_id": "action-1", "action": "set_volume",
            "confirmation_token": "never-store",
        },
    )
    unverified = store.record_step_evidence(
        task_id=task["task_id"], step_id="propose",
        evidence={"schema": "kenn.ableton_action_receipt.v1", "receipt_id": "r1", "status": "applied", "verified": False},
    )

    assert proposal["ok"] is True
    assert proposal["completed"] is False
    assert proposal["task"]["status"] == "waiting_for_confirmation"
    assert proposal["task"]["completed_step_ids"] == ["inspect"]
    assert "never-store" not in str(store.load(task["task_id"])["evidence"])
    assert unverified["ok"] is False
    assert store.load(task["task_id"])["status"] == "waiting_for_confirmation"


def test_progress_identity_cannot_be_replaced_mid_step(tmp_path) -> None:
    store = AssistantTaskStore(tmp_path / "memory.db")
    context = _context()
    task = store.start(plan=_plan(context), context=context)["task"]
    store.record_step_evidence(task_id=task["task_id"], step_id="inspect", evidence=context)
    first = store.record_step_evidence(
        task_id=task["task_id"], step_id="propose",
        evidence={
            "schema": "kenn.ableton_action_proposal.v1", "status": "confirmation_required",
            "requires_confirmation": True, "action_id": "action-1",
        },
    )
    replacement = store.record_step_evidence(
        task_id=task["task_id"], step_id="propose",
        evidence={
            "schema": "kenn.ableton_action_proposal.v1", "status": "confirmation_required",
            "requires_confirmation": True, "action_id": "action-2",
        },
    )

    assert first["ok"] is True
    assert replacement["ok"] is False
    assert "cannot replace" in replacement["error"]
    stored = store.load(task["task_id"])
    assert stored["evidence"][-1]["action_id"] == "action-1"


def test_failed_generation_job_terminates_only_its_bound_task(tmp_path) -> None:
    store = AssistantTaskStore(tmp_path / "memory.db")
    context = build_session_context(
        session_id="song-1",
        snapshot={"status": "connected", "tracks": []},
        audiogen_available=True,
    )
    step = DeliberativeStep.create(
        step_id="generate", kind="generation_job", action="create_generation_job",
        objective="Generate one candidate.", rationale="Review it before use.",
        expected_evidence=["completed AudioGen job"],
    )
    plan = DeliberativePlan.create(
        goal="Generate a candidate", context=context, status="ready", steps=[step],
    ).to_dict()
    task = store.start(plan=plan, context=context)["task"]
    store.record_step_evidence(
        task_id=task["task_id"], step_id="generate",
        evidence={
            "schema": "kenn.audiogen_render_job.v1", "job_id": "job-1", "status": "queued",
        },
    )

    wrong = store.record_step_failure(
        task_id=task["task_id"], step_id="generate",
        evidence={
            "schema": "kenn.audiogen_render_job.v1", "job_id": "job-other", "status": "failed",
        },
    )
    failed = store.record_step_failure(
        task_id=task["task_id"], step_id="generate",
        evidence={
            "schema": "kenn.audiogen_render_job.v1", "job_id": "job-1", "status": "failed",
        },
    )

    assert wrong["ok"] is False
    assert "does not match" in wrong["error"]
    assert failed["ok"] is True
    assert failed["task"]["status"] == "failed"
    assert failed["task"]["completed_step_ids"] == []
    assert failed["task"]["evidence"][-1]["failed"] is True
    assert store.resume("song-1") is None


def test_verified_live_receipt_completes_task_and_only_identity_is_persisted(tmp_path) -> None:
    store = AssistantTaskStore(tmp_path / "memory.db")
    context = _context()
    task = store.start(plan=_plan(context), context=context)["task"]
    store.record_step_evidence(task_id=task["task_id"], step_id="inspect", evidence=context)
    store.record_step_evidence(
        task_id=task["task_id"], step_id="propose",
        evidence={
            "schema": "kenn.ableton_action_proposal.v1", "status": "confirmation_required",
            "requires_confirmation": True, "action_id": "action-1", "confirmation_token": "must-not-persist",
        },
    )
    completed = store.record_step_evidence(
        task_id=task["task_id"], step_id="propose",
        evidence={
            "schema": "kenn.ableton_action_receipt.v1", "receipt_id": "receipt-1",
            "action_id": "action-1", "status": "applied", "verified": True, "action": "set_volume",
            "confirmation_token": "must-not-persist", "payload": {"secret": "must-not-persist"},
        },
    )

    assert completed["ok"] is True
    assert completed["task"]["status"] == "completed"
    assert completed["task"]["current_step_id"] == ""
    assert completed["task"]["completed_step_ids"] == ["inspect", "propose"]
    stored = str(store.load(task["task_id"])["evidence"])
    assert "receipt-1" in stored
    assert "must-not-persist" not in stored
    assert store.resume("song-1") is None


def test_receipt_from_another_action_cannot_complete_task(tmp_path) -> None:
    store = AssistantTaskStore(tmp_path / "memory.db")
    context = _context()
    task = store.start(plan=_plan(context), context=context)["task"]
    store.record_step_evidence(task_id=task["task_id"], step_id="inspect", evidence=context)
    store.record_step_evidence(
        task_id=task["task_id"], step_id="propose",
        evidence={
            "schema": "kenn.ableton_action_proposal.v1", "status": "confirmation_required",
            "requires_confirmation": True, "action_id": "expected-action",
        },
    )

    result = store.record_step_evidence(
        task_id=task["task_id"], step_id="propose",
        evidence={
            "schema": "kenn.ableton_action_receipt.v1", "receipt_id": "receipt-other",
            "action_id": "different-action", "status": "applied", "verified": True,
        },
    )

    assert result["ok"] is False
    assert "does not match" in result["error"]
    assert store.load(task["task_id"])["status"] == "waiting_for_confirmation"


def test_invalid_or_stale_plan_never_enters_task_memory(tmp_path) -> None:
    store = AssistantTaskStore(tmp_path / "memory.db")
    context = _context()
    plan = _plan(context)
    plan["snapshot_fingerprint"] = "sha256:stale"

    result = store.start(plan=plan, context=context)

    assert result["ok"] is False
    assert any("snapshot_fingerprint" in error for error in result["errors"])


def test_active_tasks_are_bounded_per_session(tmp_path) -> None:
    store = AssistantTaskStore(tmp_path / "memory.db")
    context = _context()
    for _ in range(MAX_ACTIVE_TASKS_PER_SESSION):
        assert store.start(plan=_plan(context), context=context)["ok"] is True

    rejected = store.start(plan=_plan(context), context=context)

    assert rejected["ok"] is False
    assert "active assistant tasks" in rejected["errors"][0]
