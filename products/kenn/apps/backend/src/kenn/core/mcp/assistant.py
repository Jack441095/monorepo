"""Deliberative planning and the assistant task ledger.

Every handler here was lifted verbatim out of ``KennMCPFacade._dispatch``.
``facade`` is the facade that called it, so the injected client, coordinator,
and stores stay the single owner of Live and of the task ledger.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from kenn.core.deliberative_planner import deliberative_preflight_plan, run_shadow_sketch
from kenn.core.diagnostic_framework import plan_for as diagnostic_plan_for

if TYPE_CHECKING:  # pragma: no cover - import cycle broken for type checking only
    from kenn.core.mcp_facade import KennMCPFacade


def plan_assistant_goal(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    goal = str(args.get("goal", "")).strip()[:1_024]
    session_id = str(args.get("session_id", "")).strip()[:128]
    if not goal or not session_id:
        raise ValueError("goal and session_id are required")
    if diagnostic_plan_for(goal) is not None:
        result = facade._dispatch(
            "start_production_diagnosis",
            {"goal": goal, "session_id": session_id},
        )
        return {
            **result,
            "schema": "kenn.planned_assistant_goal.v1",
            "workflow": "diagnostic",
            "execution_authorized": False,
        }
    result = facade._dispatch(
        "plan_assistant_task",
        {"goal": goal, "session_id": session_id},
    )
    return {
        **result,
        "schema": "kenn.planned_assistant_goal.v1",
        "workflow": "deliberative_task",
        "execution_authorized": False,
    }


def plan_assistant_task(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    goal = str(args.get("goal", "")).strip()[:1_024]
    session_id = str(args.get("session_id", "")).strip()[:128]
    if not goal or not session_id:
        raise ValueError("goal and session_id are required")
    context = facade._assistant_context(session_id)
    planning_started = time.perf_counter()
    if facade.planner is None:
        preflight = deliberative_preflight_plan(goal, context)
        if preflight is None:
            return {
                "ok": False,
                "status": "planner_unavailable",
                "errors": ["No local deliberative planner is configured for this MCP process."],
                "planning_latency_ms": round((time.perf_counter() - planning_started) * 1_000, 3),
                "execution_authorized": False,
            }
        shadow = {
            "accepted": True,
            "planner_source": "deterministic_preflight",
            "plan": preflight,
        }
    else:
        shadow = run_shadow_sketch(
            goal=goal,
            context=context,
            generator=facade.planner,
            model_provider=facade.planner_provider,
            model_id=facade.planner_id,
        )
    if not shadow.get("accepted") or not isinstance(shadow.get("plan"), dict):
        return {
            "ok": False,
            "status": "planning_rejected",
            "errors": shadow.get("errors", ["The deliberative plan was rejected."]),
            "planning_latency_ms": round((time.perf_counter() - planning_started) * 1_000, 3),
            "execution_authorized": False,
        }
    started = facade.coordinator.start(plan=shadow["plan"], context=context)
    return {
        **started,
        "schema": "kenn.planned_assistant_task.v1",
        "planner_source": shadow.get("planner_source", "unknown"),
        "planning_latency_ms": round((time.perf_counter() - planning_started) * 1_000, 3),
        "execution_authorized": False,
    }


def start_assistant_task(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    plan = args.get("plan")
    session_id = str(args.get("session_id", "")).strip()[:128]
    if not isinstance(plan, dict) or not session_id:
        raise ValueError("plan and session_id are required")
    return facade.coordinator.start(plan=plan, context=facade._assistant_context(session_id))


def resume_assistant_task(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    task_id = str(args.get("task_id", "")).strip()[:128]
    session_id = str(args.get("session_id", "")).strip()[:128]
    if not task_id or not session_id:
        raise ValueError("task_id and session_id are required")
    return facade.coordinator.resume(task_id=task_id, context=facade._assistant_context(session_id))


def replan_assistant_task(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    task_id = str(args.get("task_id", "")).strip()[:128]
    session_id = str(args.get("session_id", "")).strip()[:128]
    follow_up = str(args.get("follow_up", "")).strip()[:1_000]
    if not task_id or not session_id:
        raise ValueError("task_id and session_id are required")
    source = facade.coordinator.store.load(task_id)
    if source is None:
        return {"ok": False, "errors": ["Assistant task was not found."], "execution_authorized": False}
    if str(source.get("session_id") or "") != session_id:
        return {"ok": False, "errors": ["Assistant task belongs to another session."], "execution_authorized": False}
    if source.get("status") in {"waiting_for_job", "waiting_for_confirmation"}:
        return {
            "ok": False,
            "errors": ["A task waiting for an identity-bound job or confirmation must be resolved before replanning."],
            "execution_authorized": False,
        }
    ended_with_clarification = bool(
        source.get("status") == "completed"
        and source.get("plan", {}).get("steps")
        and source["plan"]["steps"][-1].get("kind") == "clarification"
    )
    if (source.get("status") == "waiting_for_user" or ended_with_clarification) and not follow_up:
        return {
            "ok": False,
            "errors": ["The producer's follow-up is required to continue a clarification task."],
            "execution_authorized": False,
        }
    original_goal = str(source.get("goal") or source.get("plan", {}).get("goal") or "").strip()[:1_024]
    planning_goal = original_goal
    if follow_up:
        planning_goal = (original_goal + "\nProducer follow-up: " + follow_up)[:1_024]
    context = facade._assistant_context(session_id)
    planning_started = time.perf_counter()
    if facade.planner is None:
        preflight = deliberative_preflight_plan(planning_goal, context)
        if preflight is None:
            return {
                "ok": False,
                "status": "planner_unavailable",
                "errors": ["No local deliberative planner is configured for this MCP process."],
                "planning_latency_ms": round((time.perf_counter() - planning_started) * 1_000, 3),
                "execution_authorized": False,
            }
        shadow = {"accepted": True, "planner_source": "deterministic_preflight", "plan": preflight}
    else:
        shadow = run_shadow_sketch(
            goal=planning_goal,
            context=context,
            generator=facade.planner,
            model_provider=facade.planner_provider,
            model_id=facade.planner_id,
        )
    if not shadow.get("accepted") or not isinstance(shadow.get("plan"), dict):
        return {
            "ok": False,
            "status": "planning_rejected",
            "errors": shadow.get("errors", ["The replacement plan was rejected."]),
            "planning_latency_ms": round((time.perf_counter() - planning_started) * 1_000, 3),
            "execution_authorized": False,
        }
    replaced = facade.coordinator.store.replace_for_replan(
        source_task_id=task_id,
        plan=shadow["plan"],
        context=context,
        reason=("Producer clarification supplied." if follow_up else "Fresh session context required replanning."),
    )
    if not replaced.get("ok"):
        return {**replaced, "execution_authorized": False}
    replacement = replaced["task"]
    return {
        "ok": True,
        "schema": "kenn.replanned_assistant_task.v1",
        "planner_source": shadow.get("planner_source", "unknown"),
        "planning_latency_ms": round((time.perf_counter() - planning_started) * 1_000, 3),
        "source_task_id": task_id,
        "task": replacement,
        "next_step": facade.coordinator.next_step(task=replacement, context=context),
        "execution_authorized": False,
    }


def record_assistant_observation(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    task_id = str(args.get("task_id", "")).strip()[:128]
    step_id = str(args.get("step_id", "")).strip()[:64]
    session_id = str(args.get("session_id", "")).strip()[:128]
    if not task_id or not step_id or not session_id:
        raise ValueError("task_id, step_id, and session_id are required")
    context = facade._assistant_context(session_id)
    return facade.coordinator.record_evidence(
        task_id=task_id, step_id=step_id, evidence=context, context=context,
    )


def record_assistant_user_response(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    task_id = str(args.get("task_id", "")).strip()[:128]
    step_id = str(args.get("step_id", "")).strip()[:64]
    session_id = str(args.get("session_id", "")).strip()[:128]
    response = str(args.get("response", "")).strip()[:1_000]
    if not task_id or not step_id or not session_id or not response:
        raise ValueError("task_id, step_id, session_id, and response are required")
    return facade.coordinator.record_evidence(
        task_id=task_id,
        step_id=step_id,
        evidence={"schema": "kenn.user_response.v1", "response": response},
        context=facade._assistant_context(session_id),
    )


def record_assistant_live_receipt(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    task_id = str(args.get("task_id", "")).strip()[:128]
    step_id = str(args.get("step_id", "")).strip()[:64]
    session_id = str(args.get("session_id", "")).strip()[:128]
    receipt_id = str(args.get("receipt_id", "")).strip()[:128]
    if not task_id or not step_id or not session_id or not receipt_id:
        raise ValueError("task_id, step_id, session_id, and receipt_id are required")
    journal = facade.client.get(
        "/api/ableton/receipts", {"session_id": session_id, "limit": 200},
    )
    rows = journal.get("receipts") if isinstance(journal.get("receipts"), list) else []
    row = next((
        item for item in rows
        if isinstance(item, dict)
        and item.get("session_id") == session_id
        and isinstance(item.get("receipt"), dict)
        and item["receipt"].get("receipt_id") == receipt_id
    ), None)
    if row is None:
        return {"ok": False, "errors": ["Receipt was not found in this session's KENN journal."]}
    return facade.coordinator.record_evidence(
        task_id=task_id,
        step_id=step_id,
        evidence=row["receipt"],
        context=facade._assistant_context(session_id),
    )
