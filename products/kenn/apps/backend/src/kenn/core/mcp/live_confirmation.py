"""The identity-bound write path and the receipt journal it undoes against.

Every handler here was lifted verbatim out of ``KennMCPFacade._dispatch``.
``facade`` is the facade that called it, so the injected client, coordinator,
and stores stay the single owner of Live and of the task ledger.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - import cycle broken for type checking only
    from kenn.core.mcp_facade import KennMCPFacade


def apply_live_proposal(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    proposal = args.get("proposal")
    if not isinstance(proposal, dict) or not proposal:
        raise ValueError("proposal must be a non-empty object")
    confirm_token = str(args.get("confirm_token", "")).strip()
    session_id = str(args.get("session_id", "")).strip()
    idempotency_key = str(args.get("idempotency_key") or "").strip()
    task_id, step_id = facade._assistant_binding_ids(args)
    if not confirm_token or not session_id or not idempotency_key:
        raise ValueError("confirm_token, session_id, and idempotency_key are required")
    result = facade.client.post(
        "/api/ableton/command",
        {
            "command": "apply confirmed KENN Live proposal",
            "session_id": session_id,
            "proposal": proposal,
            "confirm_token": confirm_token,
            "idempotency_key": idempotency_key,
        },
    )
    # The command gateway's public response uses ``status`` and
    # ``changed`` as its authoritative outcome fields, but older and
    # test HTTP clients may omit the convenience ``ok`` boolean.
    # Normalize it here so assistant trajectories have one stable
    # contract for both successful applies and replay rejection.
    if isinstance(result, dict) and "ok" not in result:
        result = {
            **result,
            "ok": result.get("status") == "applied" and result.get("changed") is True,
        }
    if task_id and step_id:
        receipt = result.get("receipt") if isinstance(result.get("receipt"), dict) else None
        if receipt is None:
            binding = {"ok": False, "errors": ["Applied response did not include a typed receipt."]}
        else:
            try:
                binding = facade.coordinator.record_evidence(
                    task_id=task_id,
                    step_id=step_id,
                    evidence=receipt,
                    context=facade._assistant_context(session_id),
                )
            except Exception as exc:
                # The Live result is already known. Never obscure its
                # receipt because optional assistant bookkeeping failed.
                binding = {
                    "ok": False,
                    "error_kind": "assistant_sync_failed",
                    "errors": [f"{type(exc).__name__}: {exc}"],
                    "recovery_tool": "record_assistant_live_receipt",
                }
        result = {**result, "assistant_task": binding}
    return result


def undo_live_receipt(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    receipt = args.get("receipt")
    if not isinstance(receipt, dict) or not receipt:
        raise ValueError("receipt must be a non-empty object")
    session_id = str(args.get("session_id", "")).strip()
    if not session_id:
        raise ValueError("session_id is required")
    proposal = args.get("proposal")
    if proposal is None:
        result = facade.client.post(
            "/api/ableton/osc/undo",
            {"receipt": receipt, "session_id": session_id},
        )
        if result.get("ok") and isinstance(result.get("proposal"), dict):
            return {
                **result,
                "status": "confirmation_required",
                "changed": False,
                "confirmation_required": True,
            }
        return result
    if not isinstance(proposal, dict) or not proposal:
        raise ValueError("proposal must be a non-empty object when applying an undo")
    confirm_token = str(args.get("confirm_token", "")).strip()
    idempotency_key = str(args.get("idempotency_key") or "").strip()
    if not confirm_token or not idempotency_key:
        raise ValueError("confirm_token and idempotency_key are required when applying an undo")
    result = facade.client.post(
        "/api/ableton/osc/undo",
        {
            "receipt": receipt,
            "proposal": proposal,
            "session_id": session_id,
            "confirm_token": confirm_token,
            "idempotency_key": idempotency_key,
        },
    )
    if result.get("ok"):
        return {**result, "status": "applied", "changed": True}
    return {**result, "status": "failed", "changed": False}


def live_receipts(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    session_id = str(args.get("session_id", "")).strip()
    try:
        limit = int(args.get("limit", 20))
    except (TypeError, ValueError):
        raise ValueError("limit must be an integer between 1 and 200") from None
    if not 1 <= limit <= 200:
        raise ValueError("limit must be an integer between 1 and 200")
    return facade.client.get(
        "/api/ableton/receipts",
        {"session_id": session_id, "limit": limit},
    )
