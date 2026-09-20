"""Safe next-step coordination for resumable KENN assistant tasks.

The coordinator deliberately does not execute tools. It turns the current
validated task state into one typed directive, re-checks the fresh Ableton
context before work continues, and records only evidence accepted by the task
ledger. Mutating work is represented solely as a proposal-preparation pause.
"""

from __future__ import annotations

from typing import Any

from kenn.core.assistant_task_memory import AssistantTaskStore, TERMINAL_STATUSES
from kenn.core.session_context import assistant_context_binding, validate_session_context


DIRECTIVE_SCHEMA = "kenn.assistant_next_step.v1"

_ACTIVE_MODES = {
    "inspection": "inspect",
    "generation_job": "start_generation_job",
    "offline_render": "start_offline_render",
    "live_proposal": "prepare_live_proposal",
    "clarification": "request_user",
    "refusal": "refuse",
}
_WAITING_MODES = {
    "waiting_for_user": "request_user",
    "waiting_for_job": "wait_for_job",
    "waiting_for_confirmation": "wait_for_confirmation",
}

_CONTEXT_DOMAIN_LABELS = (
    ("live", "Live session"),
    ("services", "service availability"),
    ("measurements", "measurements"),
    ("audio_classification", "SLO audio classification"),
    ("audition", "audition feedback"),
    ("profile", "producer memory"),
    ("generation", "AudioGen jobs"),
    ("offline", "offline render evidence"),
)


def _changed_context_domains(task: dict[str, Any], context: dict[str, Any]) -> list[str]:
    """Explain stale-plan drift without exposing raw prior session state."""
    previous = task.get("context_binding")
    if not isinstance(previous, dict):
        return ["session context"]
    current = assistant_context_binding(context)
    return [
        label for key, label in _CONTEXT_DOMAIN_LABELS
        if previous.get(key) != current.get(key)
    ]


def _directive(
    *,
    task: dict[str, Any],
    mode: str,
    step: dict[str, Any] | None = None,
    reason: str = "",
    changed_domains: list[str] | None = None,
) -> dict[str, Any]:
    current = step or {}
    return {
        "ok": True,
        "schema": DIRECTIVE_SCHEMA,
        "task_id": str(task.get("task_id") or "")[:128],
        "session_id": str(task.get("session_id") or "")[:128],
        "task_status": str(task.get("status") or "")[:64],
        "mode": mode,
        "step_id": str(current.get("step_id") or "")[:64],
        "kind": str(current.get("kind") or "")[:64],
        "action": str(current.get("action") or "")[:96],
        "objective": str(current.get("objective") or "")[:1_024],
        "rationale": str(current.get("rationale") or "")[:1_024],
        "expected_evidence": [str(item)[:256] for item in (current.get("expected_evidence") or [])[:8]],
        "reason": str(reason or "")[:1_024],
        "context_changed_domains": [str(item)[:96] for item in (changed_domains or [])[:8]],
        "execution_authorized": False,
    }


class AssistantCoordinator:
    """Coordinate one safe assistant task step at a time."""

    def __init__(self, store: AssistantTaskStore):
        self.store = store

    def start(self, *, plan: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        started = self.store.start(plan=plan, context=context)
        if not started.get("ok"):
            return started
        return {
            "ok": True,
            "task": started["task"],
            "next_step": self.next_step(task=started["task"], context=context),
        }

    def resume(self, *, task_id: str, context: dict[str, Any]) -> dict[str, Any]:
        task = self.store.load(str(task_id)[:128])
        if task is None:
            return {"ok": False, "errors": ["Assistant task was not found."]}
        return {"ok": True, "task": task, "next_step": self.next_step(task=task, context=context)}

    def record_evidence(
        self,
        *,
        task_id: str,
        step_id: str,
        evidence: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        recorded = self.store.record_step_evidence(
            task_id=str(task_id)[:128],
            step_id=str(step_id)[:64],
            evidence=evidence,
        )
        if not recorded.get("ok"):
            return recorded
        task = recorded["task"]
        rebind_result: dict[str, Any] | None = None
        if recorded.get("completed") is True and task.get("status") == "active":
            step = next((
                item for item in task.get("plan", {}).get("steps", [])
                if isinstance(item, dict) and item.get("step_id") == str(step_id)[:64]
            ), None)
            kind = str((step or {}).get("kind") or "")
            domain = {"generation_job": "generation", "offline_render": "offline"}.get(kind)
            if domain:
                evidence_id = str(
                    evidence.get("job_id") or evidence.get("project_id") or evidence.get("id") or ""
                )[:128]
                rebind_result = self.store.rebind_after_evidence(
                    task_id=str(task_id)[:128],
                    step_id=str(step_id)[:64],
                    context=context,
                    domain=domain,
                    evidence_id=evidence_id,
                )
                if rebind_result.get("ok"):
                    task = rebind_result["task"]
        response = {
            "ok": True,
            "completed_step": recorded.get("completed") is True,
            "task": task,
            "next_step": self.next_step(task=task, context=context),
        }
        if rebind_result is not None:
            response["context_rebind"] = {
                "ok": bool(rebind_result.get("ok")),
                "rebound": rebind_result.get("rebound") is True,
                "error": rebind_result.get("error", ""),
            }
        return response

    def record_failure(
        self,
        *,
        task_id: str,
        step_id: str,
        evidence: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        recorded = self.store.record_step_failure(
            task_id=str(task_id)[:128],
            step_id=str(step_id)[:64],
            evidence=evidence,
        )
        if not recorded.get("ok"):
            return recorded
        return {
            "ok": True,
            "failed_step": True,
            "task": recorded["task"],
            "next_step": self.next_step(task=recorded["task"], context=context),
        }

    @staticmethod
    def next_step(*, task: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        checked = validate_session_context(context)
        if not checked.get("ok"):
            return {"ok": False, "errors": checked.get("errors", []), "execution_authorized": False}
        if str(task.get("session_id") or "") != str(context.get("session_id") or ""):
            return {
                "ok": False,
                "errors": ["Assistant task belongs to another session."],
                "execution_authorized": False,
            }
        status = str(task.get("status") or "")
        if status in TERMINAL_STATUSES:
            mode = {"completed": "complete", "failed": "failed", "cancelled": "cancelled"}.get(status, "complete")
            return _directive(task=task, mode=mode, reason=f"Task is {status}.")

        plan = task.get("plan") if isinstance(task.get("plan"), dict) else {}
        steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
        current_step_id = str(task.get("current_step_id") or "")
        step = next(
            (item for item in steps if isinstance(item, dict) and item.get("step_id") == current_step_id),
            None,
        )
        if step is None:
            return {
                "ok": False,
                "errors": ["Current assistant step is missing from its bound plan."],
                "execution_authorized": False,
            }

        # An already-created proposal or queued job remains an identity-bound
        # wait. Its own completion path performs stricter receipt/job matching.
        # For new active work, a changed world invalidates the old plan.
        if status == "active" and plan.get("snapshot_fingerprint") != context.get("snapshot_fingerprint"):
            changed_domains = _changed_context_domains(task, context)
            domain_text = ", ".join(changed_domains) if changed_domains else "unclassified session state"
            return _directive(
                task=task,
                step=step,
                mode="replan",
                changed_domains=changed_domains,
                reason=(
                    "The Ableton session changed after this plan was created "
                    f"({domain_text}); build a fresh context-bound plan."
                ),
            )

        if status in _WAITING_MODES:
            return _directive(task=task, step=step, mode=_WAITING_MODES[status])
        kind = str(step.get("kind") or "")
        mode = _ACTIVE_MODES.get(kind)
        if kind == "offline_render" and step.get("action") == "bind_offline_render":
            mode = "bind_offline_render"
        if mode is None:
            return {
                "ok": False,
                "errors": [f"Unsupported assistant step kind {kind!r}."],
                "execution_authorized": False,
            }
        return _directive(task=task, step=step, mode=mode)


__all__ = ["AssistantCoordinator", "DIRECTIVE_SCHEMA"]
