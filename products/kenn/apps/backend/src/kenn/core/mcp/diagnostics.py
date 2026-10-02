"""The evidence-first production diagnosis loop.

Every handler here was lifted verbatim out of ``KennMCPFacade._dispatch``.
``facade`` is the facade that called it, so the injected client, coordinator,
and stores stay the single owner of Live and of the task ledger.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from kenn.core.diagnostic_loop import next_diagnostic_plan, record_diagnostic_result, start_diagnostic_loop

if TYPE_CHECKING:  # pragma: no cover - import cycle broken for type checking only
    from kenn.core.mcp_facade import KennMCPFacade


def start_production_diagnosis(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    goal = str(args.get("goal", "")).strip()[:1_024]
    session_id = str(args.get("session_id", "")).strip()[:128]
    if not goal or not session_id:
        raise ValueError("goal and session_id are required")
    context = facade._dispatch(
        "kenn_context",
        {
            "session_id": session_id,
            "include_device_matrix": True,
            "include_device_parameters": False,
        },
    )
    started = start_diagnostic_loop(goal=goal, context=context)
    if not started.get("ok"):
        return started
    persisted = facade.diagnostic_store.start(started["loop"])
    if not persisted.get("ok"):
        return {**persisted, "execution_authorized": False}
    planned = next_diagnostic_plan(started["loop"], context)
    if not planned.get("ok"):
        return planned
    return {
        "ok": True,
        "schema": "kenn.production_diagnosis.v1",
        "loop": started["loop"],
        "next_plan": planned["plan"],
        "execution_authorized": False,
    }


def record_diagnostic_test_result(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    supplied_loop = args.get("loop")
    result = args.get("result")
    if supplied_loop is not None and not isinstance(supplied_loop, dict):
        raise ValueError("loop must be an object when supplied")
    if not isinstance(result, dict):
        raise ValueError("result must be an object")
    loop_id = str(args.get("loop_id") or (supplied_loop or {}).get("loop_id") or "").strip()[:128]
    if not loop_id:
        raise ValueError("loop_id or a loop containing loop_id is required")
    loop = facade.diagnostic_store.load(loop_id)
    if loop is None:
        return {
            "ok": False,
            "errors": ["Diagnostic loop was not found in KENN's authoritative ledger."],
            "execution_authorized": False,
        }
    if supplied_loop is not None and supplied_loop != loop:
        return {
            "ok": False,
            "status": "diagnostic_state_mismatch",
            "errors": ["Caller-supplied diagnostic state differs from KENN's authoritative loop."],
            "loop": loop,
            "execution_authorized": False,
        }
    if result.get("source") != "user_observation":
        return {
            "ok": False,
            "errors": ["MCP diagnostic continuation accepts only an explicit user_observation; measurements and receipts must be resolved by KENN."],
            "execution_authorized": False,
        }
    session_id = str(loop.get("session_id", "")).strip()[:128]
    if not session_id:
        return {"ok": False, "errors": ["Diagnostic loop requires a session_id."]}
    context = facade._dispatch(
        "kenn_context",
        {
            "session_id": session_id,
            "include_device_matrix": True,
            "include_device_parameters": False,
        },
    )
    freshness = next_diagnostic_plan(loop, context)
    if not freshness.get("ok"):
        return {
            "ok": False,
            "schema": "kenn.production_diagnosis.v1",
            "loop": loop,
            "continuation_ready": False,
            "requires_restart": True,
            "errors": freshness.get("errors", []),
            "execution_authorized": False,
        }
    recorded = record_diagnostic_result(loop, result)
    if not recorded.get("ok"):
        return recorded
    updated_loop = recorded["loop"]
    stored = facade.diagnostic_store.update(expected=loop, updated=updated_loop)
    if not stored.get("ok"):
        return {**stored, "execution_authorized": False}
    planned = next_diagnostic_plan(updated_loop, context)
    if not planned.get("ok"):
        return {
            "ok": True,
            "schema": "kenn.production_diagnosis.v1",
            "loop": updated_loop,
            "continuation_ready": False,
            "requires_restart": True,
            "errors": planned.get("errors", []),
            "execution_authorized": False,
        }
    return {
        "ok": True,
        "schema": "kenn.production_diagnosis.v1",
        "loop": updated_loop,
        "continuation_ready": True,
        "requires_restart": False,
        "next_plan": planned["plan"],
        "execution_authorized": False,
    }
