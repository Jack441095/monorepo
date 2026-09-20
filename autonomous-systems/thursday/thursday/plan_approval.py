"""Exact-bound batch approval for multi-step plans.

A batch approval binds an owner's confirmation to ONE canonical plan:
ordered steps, each with its service and full arguments. The binding is a
SHA-256 over a deterministic canonical serialization, signed with the same
HMAC process-secret machinery as single-action confirmations
(`thursday.confirmation`). Any material mutation — step inserted, removed,
reordered, argument or service changed — changes the hash and invalidates
the approval.

Exactly-once semantics are preserved per step: every consequential step is
claimed through ``action_receipts`` before execution, so retries, replays,
duplicate submissions, or crashes can never double-execute an approved step.
Partial execution is reported honestly: steps that ran keep their receipts;
unexecuted steps are listed as not run. Nothing pretends to roll back.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

from thursday import confirmation as conf
from thursday import action_receipts as receipts


class BatchApprovalError(ValueError):
    """Batch plan approval failed verification."""


@dataclass(frozen=True)
class PlanStep:
    service_id: str
    text: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ApprovalPlan:
    plan_id: str
    session_id: str
    steps: tuple[PlanStep, ...]
    created_at_epoch: float


def canonical_plan_bytes(steps: tuple[PlanStep, ...]) -> bytes:
    """Deterministic canonical serialization of the ordered steps.

    Sorted keys, compact separators, explicit ordering — the same semantic
    plan always yields identical bytes.
    """
    payload = [
        {
            "service_id": s.service_id,
            "text": s.text,
            "arguments": _canonical_value(s.arguments),
        }
        for s in steps
    ]
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _canonical_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _canonical_value(value[k]) for k in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(v) for v in value]
    return value


def plan_hash(plan: ApprovalPlan) -> str:
    digest = hashlib.sha256()
    digest.update(plan.plan_id.encode("utf-8"))
    digest.update(b"\n")
    digest.update(canonical_plan_bytes(plan.steps))
    return digest.hexdigest()


def issue_batch_confirmation(
    plan: ApprovalPlan, *, ttl_seconds: int = conf.DEFAULT_TTL_SECONDS
) -> tuple[str, str]:
    """Return ``(token, plan_hash)``. The token signs the plan hash.

    Binding inputs: session, plan id, canonical plan hash, expiry. The nonce
    field stays empty — the hash already makes each issuance unique per plan
    content, and a fixed nonce keeps sign/verify consistent.
    """
    digest = plan_hash(plan)
    expires_at = int(time.time()) + max(1, int(ttl_seconds))
    message = "|".join(
        (plan.session_id, f"batch.{plan.plan_id}", digest, str(expires_at), "")
    ).encode("utf-8")
    from thursday.confirmation import _secret

    signature = conf.hmac.new(_secret(), message, conf.hashlib.sha256).hexdigest()[:32]
    token = f"v1.{expires_at:x}..{signature}"
    return token, digest


def verify_batch_confirmation(
    token: str, plan: ApprovalPlan, *, now: int | None = None
) -> bool:
    """Verify expiry AND that the submitted plan hashes to the signed value."""
    try:
        version, expiry_hex, nonce, supplied = token.split(".")
        expires_at = int(expiry_hex, 16)
    except (TypeError, ValueError):
        return False
    if version != "v1" or (now if now is not None else int(time.time())) > expires_at:
        return False
    submitted = plan_hash(plan)
    from thursday.confirmation import _secret

    message = "|".join(
        (plan.session_id, f"batch.{plan.plan_id}", submitted, str(expires_at), nonce)
    ).encode("utf-8")
    expected = conf.hmac.new(_secret(), message, conf.hashlib.sha256).hexdigest()[:32]
    return conf.hmac.compare_digest(supplied, expected)


def execute_approved_plan(
    plan: ApprovalPlan,
    executor: Any,
    *,
    session_id: str,
) -> dict[str, Any]:
    """Execute each approved step exactly once, stopping at first failure.

    ``executor(service_id, text, arguments, receipt_claimed) -> str`` runs one
    step; it is only called after the step's receipt is atomically claimed.
    Returns an honest partial-execution record.
    """
    results: list[dict[str, Any]] = []
    stopped_at: int | None = None

    for index, step in enumerate(plan.steps):
        receipt_id = receipts.receipt_id_for_token(
            f"{plan.plan_id}|{index}|{hashlib.sha256(canonical_plan_bytes((step,))).hexdigest()[:24]}"
        )
        claim = receipts.claim_action(
            receipt_id,
            session_id=session_id,
            service_id=step.service_id,
            text=step.text,
        )
        if not claim.claimed:
            if claim.receipt.status == "completed":
                results.append({
                    "index": index,
                    "service_id": step.service_id,
                    "status": "already_completed",
                    "response_text": claim.receipt.response_text,
                })
                continue
            results.append({
                "index": index,
                "service_id": step.service_id,
                "status": "in_progress_elsewhere",
            })
            stopped_at = index
            break

        try:
            output = executor(step.service_id, step.text, dict(step.arguments))
            receipts.complete_action(receipt_id, response_text=str(output))
            results.append({
                "index": index,
                "service_id": step.service_id,
                "status": "completed",
                "receipt_id": receipt_id,
                "response_text": str(output),
            })
        except Exception as exc:  # noqa: BLE001 — honest partial state
            results.append({
                "index": index,
                "service_id": step.service_id,
                "status": "failed",
                "error": str(exc),
                "receipt_id": receipt_id,
            })
            stopped_at = index
            break

    executed = [r["index"] for r in results if r["status"] == "completed"]
    not_run = list(range(stopped_at + 1, len(plan.steps))) if stopped_at is not None else []

    return {
        "plan_id": plan.plan_id,
        "executed_steps": executed,
        "not_executed_steps": not_run,
        "partial": stopped_at is not None,
        "steps": results,
    }


__all__ = [
    "PlanStep",
    "ApprovalPlan",
    "BatchApprovalError",
    "canonical_plan_bytes",
    "plan_hash",
    "issue_batch_confirmation",
    "verify_batch_confirmation",
    "execute_approved_plan",
]
