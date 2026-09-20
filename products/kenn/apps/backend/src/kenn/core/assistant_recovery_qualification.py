"""Deterministic multi-turn qualification for KENN assistant recovery."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
from typing import Any, Callable

from kenn.core.assistant_coordinator import AssistantCoordinator
from kenn.core.assistant_task_memory import AssistantTaskStore
from kenn.core.deliberative_plan import DeliberativePlan, DeliberativeStep
from kenn.core.diagnostic_loop import record_diagnostic_result, start_diagnostic_loop
from kenn.core.diagnostic_loop_store import DiagnosticLoopStore
from kenn.core.session_context import build_session_context


RESULT_SCHEMA = "kenn.assistant_recovery_qualification.v1"


def _context(
    session_id: str,
    *,
    track_name: str = "Bass",
    generated_jobs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return build_session_context(
        session_id=session_id,
        snapshot={
            "status": "connected",
            "tempo": 124.0,
            "is_playing": False,
            "tracks": [{"index": 0, "name": track_name, "type": "midi", "devices": []}],
        },
        audiogen_available=True,
        audiogen_jobs=generated_jobs or [],
    )


def _live_plan(context: dict[str, Any]) -> dict[str, Any]:
    return DeliberativePlan.create(
        goal="Inspect the bass and prepare a small supported adjustment.",
        context=context,
        status="ready",
        steps=[
            DeliberativeStep.create(
                step_id="inspect",
                kind="inspection",
                action="inspect_live",
                objective="Inspect the current bass track.",
                rationale="Use fresh Live evidence.",
                expected_evidence=["fresh Live snapshot"],
            ),
            DeliberativeStep.create(
                step_id="propose",
                kind="live_proposal",
                action="create_live_proposal",
                objective="Prepare the smallest supported bass adjustment.",
                rationale="Require exact confirmation before applying it.",
                depends_on=["inspect"],
                expected_evidence=["typed confirmation-gated proposal"],
            ),
        ],
    ).to_dict()


def _generation_plan(context: dict[str, Any]) -> dict[str, Any]:
    return DeliberativePlan.create(
        goal="Generate and review one candidate.",
        context=context,
        status="ready",
        steps=[
            DeliberativeStep.create(
                step_id="generate",
                kind="generation_job",
                action="create_generation_job",
                objective="Generate one candidate.",
                rationale="Create an artifact before reviewing it.",
                expected_evidence=["accepted generation-job receipt"],
            ),
            DeliberativeStep.create(
                step_id="review",
                kind="inspection",
                action="review_generated_asset",
                objective="Review the completed candidate.",
                rationale="Audition before deciding whether to use it.",
                depends_on=["generate"],
                expected_evidence=["verified completed generation artifact"],
            ),
        ],
    ).to_dict()


def _case_stale_context_requires_replan(root: Path) -> tuple[bool, str]:
    initial = _context("stale-context")
    coordinator = AssistantCoordinator(AssistantTaskStore(root / "stale.db"))
    task = coordinator.start(plan=_live_plan(initial), context=initial)["task"]
    directive = coordinator.resume(
        task_id=task["task_id"], context=_context("stale-context", track_name="Renamed Bass"),
    )["next_step"]
    return directive.get("mode") == "replan" and directive.get("execution_authorized") is False, str(directive.get("reason") or "")


def _case_replan_preserves_lineage(root: Path) -> tuple[bool, str]:
    initial = _context("replan-lineage")
    changed = _context("replan-lineage", track_name="Renamed Bass")
    store = AssistantTaskStore(root / "lineage.db")
    source = store.start(plan=_live_plan(initial), context=initial)["task"]
    replaced = store.replace_for_replan(
        source_task_id=source["task_id"],
        plan=_live_plan(changed),
        context=changed,
        reason="Live target changed.",
    )
    old = store.load(source["task_id"])
    new = replaced.get("task") or {}
    passed = bool(
        replaced.get("ok")
        and old and old.get("status") == "cancelled"
        and old.get("superseded_by_task_id") == new.get("task_id")
        and new.get("parent_task_id") == source["task_id"]
    )
    return passed, "Replacement must cancel and link the superseded active task."


def _waiting_confirmation(store: AssistantTaskStore, context: dict[str, Any]) -> dict[str, Any]:
    task = store.start(plan=_live_plan(context), context=context)["task"]
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
    return task


def _case_pending_confirmation_cannot_be_abandoned(root: Path) -> tuple[bool, str]:
    context = _context("pending-confirmation")
    store = AssistantTaskStore(root / "pending.db")
    task = _waiting_confirmation(store, context)
    replaced = store.replace_for_replan(
        source_task_id=task["task_id"], plan=_live_plan(context), context=context, reason="unsafe",
    )
    current = store.load(task["task_id"])
    return replaced.get("ok") is False and current and current.get("status") == "waiting_for_confirmation", str((replaced.get("errors") or [""])[0])


def _case_receipt_replay_is_rejected(root: Path) -> tuple[bool, str]:
    context = _context("receipt-replay")
    store = AssistantTaskStore(root / "receipt.db")
    task = _waiting_confirmation(store, context)
    receipt = {
        "schema": "kenn.ableton_action_receipt.v1",
        "status": "applied",
        "verified": True,
        "receipt_id": "receipt-1",
        "action_id": "action-1",
    }
    first = store.record_step_evidence(task_id=task["task_id"], step_id="propose", evidence=receipt)
    replay = store.record_step_evidence(task_id=task["task_id"], step_id="propose", evidence=receipt)
    return first.get("ok") is True and replay.get("ok") is False, str(replay.get("error") or "")


def _case_wrong_job_identity_is_rejected(root: Path) -> tuple[bool, str]:
    context = _context("wrong-job")
    store = AssistantTaskStore(root / "wrong-job.db")
    task = store.start(plan=_generation_plan(context), context=context)["task"]
    store.record_step_evidence(
        task_id=task["task_id"], step_id="generate",
        evidence={"schema": "kenn.audiogen_render_job.v1", "job_id": "job-1", "status": "queued"},
    )
    wrong = store.record_step_evidence(
        task_id=task["task_id"], step_id="generate",
        evidence={"schema": "kenn.audiogen_render_job.v1", "job_id": "job-2", "status": "completed"},
    )
    current = store.load(task["task_id"])
    return wrong.get("ok") is False and current and current.get("status") == "waiting_for_job", str(wrong.get("error") or "")


def _case_scoped_job_rebind_advances_review(root: Path) -> tuple[bool, str]:
    initial = _context("job-rebind")
    completed_context = _context("job-rebind", generated_jobs=[{
        "schema": "kenn.audiogen_render_job.v1",
        "job_id": "job-1",
        "status": "completed",
        "artifact": {"kind": "audio", "content_hash": "sha256:" + ("a" * 64)},
    }])
    coordinator = AssistantCoordinator(AssistantTaskStore(root / "rebind.db"))
    task = coordinator.start(plan=_generation_plan(initial), context=initial)["task"]
    coordinator.record_evidence(
        task_id=task["task_id"], step_id="generate",
        evidence={"schema": "kenn.audiogen_render_job.v1", "job_id": "job-1", "status": "queued"},
        context=initial,
    )
    advanced = coordinator.record_evidence(
        task_id=task["task_id"], step_id="generate",
        evidence={"schema": "kenn.audiogen_render_job.v1", "job_id": "job-1", "status": "completed"},
        context=completed_context,
    )
    return bool(
        advanced.get("context_rebind", {}).get("rebound")
        and advanced.get("next_step", {}).get("action") == "review_generated_asset"
    ), str(advanced.get("context_rebind") or {})


def _diagnostic(root: Path) -> tuple[DiagnosticLoopStore, dict[str, Any]]:
    context = _context("diagnostic-ledger")
    loop = start_diagnostic_loop(
        goal="The mix gets muddy in the busiest section.", context=context,
    )["loop"]
    store = DiagnosticLoopStore(root / "diagnostic.db")
    store.start(loop)
    return store, loop


def _diagnostic_result(loop: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "kenn.diagnostic_test_result.v1",
        "hypothesis_id": loop["active_hypothesis_id"],
        "verdict": "contradicts",
        "source": "user_observation",
        "observation": "The bounded listening test did not change the symptom.",
        "source_turn_id": "qualification-turn",
    }


def _case_diagnostic_restart_recovers_authority(root: Path) -> tuple[bool, str]:
    store, loop = _diagnostic(root)
    reloaded = DiagnosticLoopStore(store.db_path).load(loop["loop_id"])
    return reloaded == loop, "Reloaded loop must exactly match the authoritative state."


def _case_diagnostic_concurrent_replay_is_rejected(root: Path) -> tuple[bool, str]:
    store, loop = _diagnostic(root)
    updated = record_diagnostic_result(loop, _diagnostic_result(loop))["loop"]
    first = store.update(expected=loop, updated=updated)
    replay = store.update(expected=loop, updated=updated)
    return first.get("ok") is True and replay.get("ok") is False, str((replay.get("errors") or [""])[0])


CASES: tuple[tuple[str, bool, Callable[[Path], tuple[bool, str]]], ...] = (
    ("stale_context_requires_replan", True, _case_stale_context_requires_replan),
    ("replan_preserves_lineage", True, _case_replan_preserves_lineage),
    ("pending_confirmation_cannot_be_abandoned", True, _case_pending_confirmation_cannot_be_abandoned),
    ("receipt_replay_is_rejected", True, _case_receipt_replay_is_rejected),
    ("wrong_job_identity_is_rejected", True, _case_wrong_job_identity_is_rejected),
    ("scoped_job_rebind_advances_review", False, _case_scoped_job_rebind_advances_review),
    ("diagnostic_restart_recovers_authority", True, _case_diagnostic_restart_recovers_authority),
    ("diagnostic_concurrent_replay_is_rejected", True, _case_diagnostic_concurrent_replay_is_rejected),
)


def run_assistant_recovery_qualification(root: Path | None = None) -> dict[str, Any]:
    """Run bounded persisted trajectories without Ableton or model mutation."""
    if root is None:
        with tempfile.TemporaryDirectory(prefix="kenn-recovery-") as directory:
            return run_assistant_recovery_qualification(Path(directory))
    root.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for case_id, safety_critical, run in CASES:
        try:
            passed, details = run(root)
            error = ""
        except Exception as exc:  # qualification must report every case
            passed = False
            details = ""
            error = f"{type(exc).__name__}: {exc}"[:1_000]
        results.append({
            "case_id": case_id,
            "safety_critical": safety_critical,
            "passed": bool(passed),
            "details": str(details)[:1_000],
            "error": error,
        })
    safety = [item for item in results if item["safety_critical"]]
    return {
        "schema": RESULT_SCHEMA,
        "case_count": len(results),
        "passed_count": sum(item["passed"] for item in results),
        "safety_case_count": len(safety),
        "safety_passed_count": sum(item["passed"] for item in safety),
        "passed": all(item["passed"] for item in results),
        "execution_authorized": False,
        "cases": results,
    }


__all__ = ["CASES", "RESULT_SCHEMA", "run_assistant_recovery_qualification"]
