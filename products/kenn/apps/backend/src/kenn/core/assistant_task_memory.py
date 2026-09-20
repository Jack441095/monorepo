"""Evidence-linked persistence for multi-turn KENN assistant tasks.

This ledger is intentionally separate from conversational session summaries.
It stores validated inert plans and compact evidence identities, never hidden
reasoning, arbitrary tool payloads, confirmation tokens, or raw audio.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any
from uuid import uuid4

from kenn.core.deliberative_plan import validate_deliberative_plan
from kenn.core.session_memory import DB_PATH
from kenn.core.session_context import assistant_context_binding, validate_session_context


TASK_SCHEMA = "kenn.assistant_task.v1"
EVIDENCE_SCHEMA = "kenn.assistant_step_evidence.v1"
MAX_TASKS_PER_SESSION = 64
MAX_ACTIVE_TASKS_PER_SESSION = 8
MAX_REPLAN_DEPTH = 8
TERMINAL_STATUSES = frozenset({"completed", "cancelled", "failed"})
ACTIVE_STATUSES = frozenset({"active", "waiting_for_user", "waiting_for_job", "waiting_for_confirmation"})

_LIVE_RECEIPTS = frozenset({
    "kenn.ableton_action_receipt.v1",
    "kenn.ableton_midi_clip_receipt.v1",
    "kenn.ableton_recipe_receipt.v1",
})
_LIVE_PROPOSALS = frozenset({
    "kenn.ableton_action_proposal.v1",
    "kenn.ableton_midi_clip_proposal.v1",
    "kenn.ableton_recipe_proposal.v1",
    "kenn.ableton_device_insertion_proposal.v1",
    "kenn.ableton_device_removal_proposal.v1",
    "kenn.ableton_eq_band_tuning_gain_proposal.v1",
})
_INSPECTION_EVIDENCE = frozenset({
    "kenn.session_context.v1",
    "kenn.session_world_delta.v1",
    "kenn.ableton_device_matrix.v1",
    "kenn.mix_review.local_receipt.v2",
    "kenn.mix_review.local_engine.v1",
    "kenn.audiogen_artifact_inspection.v1",
    "kenn.audiogen_audio_candidate.v1",
    "kenn.audiogen_audio_comparison.v1",
})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS assistant_tasks (
            task_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            status TEXT NOT NULL,
            state_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS assistant_tasks_session_updated "
        "ON assistant_tasks(session_id, updated_at DESC)"
    )
    return conn


def _safe_evidence_identity(evidence: dict[str, Any]) -> dict[str, Any]:
    identity = {
        "schema": EVIDENCE_SCHEMA,
        "evidence_schema": str(evidence.get("schema") or "")[:128],
        "recorded_at": _now(),
    }
    for key in (
        "receipt_id", "feedback_id", "job_id", "project_id", "action_id", "id", "status", "verified",
        "snapshot_fingerprint", "verdict", "action", "kind",
    ):
        if key in evidence and isinstance(evidence[key], (str, int, float, bool, type(None))):
            identity[key] = evidence[key] if not isinstance(evidence[key], str) else evidence[key][:256]
    return identity


def _evidence_acceptance(step: dict[str, Any], evidence: Any) -> tuple[bool, str]:
    if not isinstance(evidence, dict):
        return False, "Step evidence must be a typed object."
    schema = str(evidence.get("schema") or "")
    kind = str(step.get("kind") or "")
    if kind == "inspection":
        if schema not in _INSPECTION_EVIDENCE:
            return False, "Inspection steps require a recognized observation or analysis receipt."
        action = str(step.get("action") or "")
        accepted_for_action = {
            "inspect_live": {"kenn.session_context.v1", "kenn.session_world_delta.v1"},
            "inspect_device_capabilities": {"kenn.session_context.v1", "kenn.ableton_device_matrix.v1"},
            "review_generated_asset": {"kenn.session_context.v1", "kenn.audiogen_artifact_inspection.v1", "kenn.audiogen_audio_candidate.v1"},
            "compare_offline_candidate": {"kenn.session_context.v1", "kenn.mix_review.local_receipt.v2", "kenn.mix_review.local_engine.v1", "kenn.audiogen_audio_comparison.v1"},
        }.get(action, set())
        if schema not in accepted_for_action:
            return False, f"Inspection evidence does not satisfy action {action!r}."
        if schema == "kenn.session_context.v1" and not str(evidence.get("snapshot_fingerprint") or "").startswith("sha256:"):
            return False, "Session-context evidence requires a snapshot fingerprint."
        if schema == "kenn.session_context.v1" and not validate_session_context(evidence).get("ok"):
            return False, "Session-context evidence is invalid or stale."
        if schema == "kenn.session_context.v1":
            if action == "inspect_device_capabilities" and not isinstance(evidence.get("device_capability_matrix"), dict):
                return False, "Device-capability inspection requires a capability matrix."
            if action == "review_generated_asset" and not any(
                isinstance(item, dict) and item.get("status") in {"completed", "success"}
                for item in evidence.get("generated_jobs", [])
            ):
                return False, "Generated-asset review requires a completed generated job in context."
            if action == "compare_offline_candidate" and not (
                any(isinstance(item, dict) for item in evidence.get("mix_reviews", []))
                or any(isinstance(item, dict) for item in evidence.get("offline_jobs", []))
            ):
                return False, "Offline comparison requires a review or offline-job receipt in context."
        if schema == "kenn.session_world_delta.v1" and (
            evidence.get("read_only") is not True or not isinstance(evidence.get("events"), list)
        ):
            return False, "World-delta evidence must be a read-only typed event list."
        if schema == "kenn.ableton_device_matrix.v1" and not isinstance(evidence.get("entries"), list):
            return False, "Device-matrix evidence requires bounded entries."
        if schema.startswith("kenn.mix_review.") and evidence.get("status") not in {"completed", "success"}:
            return False, "Mix-review evidence must be completed."
        return True, ""
    if kind == "live_proposal":
        if schema not in _LIVE_RECEIPTS:
            return False, "A Live proposal is not completion evidence; a supported execution receipt is required."
        if evidence.get("verified") is not True or evidence.get("status") not in {"applied", "completed", "success"}:
            return False, "Live-step evidence must be a verified applied receipt."
        if not str(evidence.get("receipt_id") or ""):
            return False, "Live-step evidence requires a receipt_id."
        return True, ""
    if kind == "generation_job":
        if not schema.startswith("kenn.audiogen_") or evidence.get("status") not in {"completed", "success"}:
            return False, "Generation steps require a completed typed AudioGen job."
        if not str(evidence.get("job_id") or evidence.get("id") or ""):
            return False, "Generation evidence requires a job identity."
        return True, ""
    if kind == "offline_render":
        if schema != "kenn.automix.local_receipt.v1" or evidence.get("status") != "completed":
            return False, "Offline-render steps require a completed AutoMix receipt."
        return True, ""
    if kind == "clarification":
        if schema != "kenn.user_response.v1" or not str(evidence.get("response") or "").strip():
            return False, "Clarification steps require an explicit non-empty user response."
        return True, ""
    if kind == "refusal":
        if schema != "kenn.policy_refusal.v1" or evidence.get("status") != "refused":
            return False, "Refusal steps require a typed policy-refusal record."
        return True, ""
    return False, f"Unsupported task step kind {kind!r}."


def _progress_status(step: dict[str, Any], evidence: Any) -> str:
    if not isinstance(evidence, dict):
        return ""
    kind = str(step.get("kind") or "")
    schema = str(evidence.get("schema") or "")
    status = str(evidence.get("status") or "")
    if (
        kind == "live_proposal"
        and schema in _LIVE_PROPOSALS
        and evidence.get("requires_confirmation") is True
        and str(evidence.get("action_id") or evidence.get("id") or "")
    ):
        return "waiting_for_confirmation"
    if (
        kind == "generation_job"
        and schema.startswith("kenn.audiogen_")
        and status in {"queued", "pending", "running"}
        and str(evidence.get("job_id") or evidence.get("id") or "")
    ):
        return "waiting_for_job"
    if (
        kind == "offline_render"
        and schema == "kenn.automix.local_receipt.v1"
        and status in {"queued", "pending", "running"}
        and str(evidence.get("job_id") or evidence.get("project_id") or evidence.get("id") or "")
    ):
        return "waiting_for_job"
    return ""


def _link_key(kind: str, evidence: dict[str, Any]) -> str:
    if kind == "live_proposal":
        return str(evidence.get("action_id") or evidence.get("id") or "")
    if kind == "generation_job":
        return str(evidence.get("job_id") or evidence.get("id") or "")
    if kind == "offline_render":
        return str(evidence.get("job_id") or evidence.get("project_id") or evidence.get("id") or "")
    return ""


def _next_status(plan: dict[str, Any], completed: list[str]) -> tuple[str, str]:
    completed_set = set(completed)
    for step in plan.get("steps", []):
        step_id = str(step.get("step_id") or "")
        if step_id in completed_set:
            continue
        kind = step.get("kind")
        status = {
            "clarification": "waiting_for_user",
        }.get(kind, "active")
        return status, step_id
    return "completed", ""


def _new_task_state(
    *,
    plan: dict[str, Any],
    context: dict[str, Any],
    parent_task_id: str = "",
    replan_depth: int = 0,
) -> dict[str, Any]:
    task_id = f"task-{uuid4().hex}"
    created_at = _now()
    status, current_step_id = _next_status(plan, [])
    state = {
        "schema": TASK_SCHEMA,
        "task_id": task_id,
        "session_id": str(plan["session_id"])[:128],
        "goal": str(plan["goal"])[:1_024],
        "status": status,
        "current_step_id": current_step_id,
        "completed_step_ids": [],
        "evidence": [],
        "plan": deepcopy(plan),
        "context_binding": assistant_context_binding(context),
        "context_rebindings": [],
        "created_at": created_at,
        "updated_at": created_at,
    }
    if parent_task_id:
        state["parent_task_id"] = str(parent_task_id)[:128]
        state["replan_depth"] = int(replan_depth)
    return state


class AssistantTaskStore:
    """Persist validated plans and advance them only with typed evidence."""

    def __init__(self, db_path: Path | str = DB_PATH):
        self.db_path = Path(db_path)

    def start(self, *, plan: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        checked = validate_deliberative_plan(plan, context)
        if not checked.get("ok"):
            return {"ok": False, "errors": checked.get("errors", [])}
        if not str(plan.get("session_id") or "").strip():
            return {"ok": False, "errors": ["Assistant tasks require a non-empty session_id."]}
        state = _new_task_state(plan=plan, context=context)
        conn = _connect(self.db_path)
        try:
            active_count = conn.execute(
                "SELECT COUNT(*) FROM assistant_tasks WHERE session_id = ? "
                "AND status IN ('active', 'waiting_for_user', 'waiting_for_job', 'waiting_for_confirmation')",
                (state["session_id"],),
            ).fetchone()[0]
            if int(active_count) >= MAX_ACTIVE_TASKS_PER_SESSION:
                return {
                    "ok": False,
                    "errors": [f"Session already has {MAX_ACTIVE_TASKS_PER_SESSION} active assistant tasks."],
                }
            conn.execute(
                "INSERT INTO assistant_tasks(task_id, session_id, status, state_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    state["task_id"], state["session_id"], state["status"],
                    json.dumps(state, sort_keys=True), state["created_at"], state["updated_at"],
                ),
            )
            conn.execute(
                """
                DELETE FROM assistant_tasks
                WHERE task_id IN (
                    SELECT task_id FROM assistant_tasks
                    WHERE session_id = ? AND status IN ('completed', 'cancelled', 'failed')
                    ORDER BY updated_at DESC LIMIT -1 OFFSET ?
                )
                """,
                (state["session_id"], MAX_TASKS_PER_SESSION),
            )
            conn.commit()
        finally:
            conn.close()
        return {"ok": True, "task": state}

    def replace_for_replan(
        self,
        *,
        source_task_id: str,
        plan: dict[str, Any],
        context: dict[str, Any],
        reason: str,
    ) -> dict[str, Any]:
        """Atomically supersede a safe-to-abandon task with a fresh plan."""
        checked = validate_deliberative_plan(plan, context)
        if not checked.get("ok"):
            return {"ok": False, "errors": checked.get("errors", [])}
        source = self.load(str(source_task_id)[:128])
        if source is None:
            return {"ok": False, "errors": ["Assistant task was not found."]}
        if str(source.get("session_id") or "") != str(context.get("session_id") or ""):
            return {"ok": False, "errors": ["Assistant task belongs to another session."]}
        if source.get("status") in {"waiting_for_job", "waiting_for_confirmation"}:
            return {
                "ok": False,
                "errors": ["A task waiting for an identity-bound job or confirmation must be resolved before replanning."],
            }
        depth = int(source.get("replan_depth") or 0) + 1
        if depth > MAX_REPLAN_DEPTH:
            return {"ok": False, "errors": ["Assistant task reached the bounded replan limit."]}
        replacement = _new_task_state(
            plan=plan,
            context=context,
            parent_task_id=str(source.get("task_id") or ""),
            replan_depth=depth,
        )
        prior_source_json = json.dumps(source, sort_keys=True)
        source_status = str(source.get("status") or "")
        if source_status in ACTIVE_STATUSES:
            source["status"] = "cancelled"
            source["current_step_id"] = ""
        source["superseded_by_task_id"] = replacement["task_id"]
        source["superseded_reason"] = str(reason or "Fresh context required a replacement plan.")[:512]
        source["updated_at"] = _now()

        conn = _connect(self.db_path)
        try:
            conn.execute("BEGIN IMMEDIATE")
            active_count = conn.execute(
                "SELECT COUNT(*) FROM assistant_tasks WHERE session_id = ? "
                "AND task_id != ? AND status IN ('active', 'waiting_for_user', 'waiting_for_job', 'waiting_for_confirmation')",
                (replacement["session_id"], source["task_id"]),
            ).fetchone()[0]
            if int(active_count) >= MAX_ACTIVE_TASKS_PER_SESSION:
                conn.rollback()
                return {
                    "ok": False,
                    "errors": [f"Session already has {MAX_ACTIVE_TASKS_PER_SESSION} other active assistant tasks."],
                }
            cursor = conn.execute(
                "UPDATE assistant_tasks SET status = ?, state_json = ?, updated_at = ? "
                "WHERE task_id = ? AND state_json = ?",
                (
                    source["status"], json.dumps(source, sort_keys=True), source["updated_at"],
                    source["task_id"], prior_source_json,
                ),
            )
            if cursor.rowcount != 1:
                conn.rollback()
                return {"ok": False, "errors": ["Assistant task changed concurrently; reload it before replanning."]}
            conn.execute(
                "INSERT INTO assistant_tasks(task_id, session_id, status, state_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    replacement["task_id"], replacement["session_id"], replacement["status"],
                    json.dumps(replacement, sort_keys=True), replacement["created_at"], replacement["updated_at"],
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return {"ok": True, "source_task": source, "task": replacement}

    def load(self, task_id: str) -> dict[str, Any] | None:
        conn = _connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT state_json FROM assistant_tasks WHERE task_id = ?", (str(task_id),),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        try:
            state = json.loads(row["state_json"])
        except (json.JSONDecodeError, TypeError):
            return None
        return state if isinstance(state, dict) and state.get("schema") == TASK_SCHEMA else None

    def resume(self, session_id: str) -> dict[str, Any] | None:
        conn = _connect(self.db_path)
        try:
            placeholders = ",".join("?" for _ in ACTIVE_STATUSES)
            row = conn.execute(
                f"SELECT state_json FROM assistant_tasks WHERE session_id = ? AND status IN ({placeholders}) "
                "ORDER BY updated_at DESC LIMIT 1",
                (str(session_id), *sorted(ACTIVE_STATUSES)),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        try:
            state = json.loads(row["state_json"])
        except (json.JSONDecodeError, TypeError):
            return None
        return state if isinstance(state, dict) and state.get("schema") == TASK_SCHEMA else None

    def record_step_evidence(self, *, task_id: str, step_id: str, evidence: dict[str, Any]) -> dict[str, Any]:
        state = self.load(task_id)
        if state is None:
            return {"ok": False, "error": "Assistant task was not found."}
        if state.get("status") in TERMINAL_STATUSES:
            return {"ok": False, "error": f"Assistant task is already {state.get('status')}."}
        if step_id != state.get("current_step_id"):
            return {"ok": False, "error": "Evidence must belong to the task's current step."}
        step = next((item for item in state["plan"]["steps"] if item.get("step_id") == step_id), None)
        if step is None:
            return {"ok": False, "error": "Current task step is missing from its bound plan."}
        prior_state_json = json.dumps(state, sort_keys=True)
        progress_status = _progress_status(step, evidence)
        if progress_status:
            kind = str(step.get("kind") or "")
            current_key = _link_key(kind, evidence)
            prior_progress = next((
                item for item in reversed(state.get("evidence") or [])
                if item.get("step_id") == step_id and item.get("progress_only") is True
            ), None)
            prior_key = _link_key(kind, prior_progress or {})
            if prior_key and current_key != prior_key:
                return {
                    "ok": False,
                    "error": "Progress evidence cannot replace this step's bound action or job identity.",
                    "task": state,
                }
            state["status"] = progress_status
            state["evidence"] = [*(state.get("evidence") or []), {
                "step_id": step_id,
                "progress_only": True,
                **_safe_evidence_identity(evidence),
            }][-64:]
            state["updated_at"] = _now()
            conn = _connect(self.db_path)
            try:
                cursor = conn.execute(
                    "UPDATE assistant_tasks SET status = ?, state_json = ?, updated_at = ? "
                    "WHERE task_id = ? AND state_json = ? AND status NOT IN ('completed', 'cancelled', 'failed')",
                    (
                        state["status"], json.dumps(state, sort_keys=True), state["updated_at"],
                        task_id, prior_state_json,
                    ),
                )
                conn.commit()
            finally:
                conn.close()
            if cursor.rowcount != 1:
                return {"ok": False, "error": "Assistant task changed concurrently; reload it before retrying."}
            return {"ok": True, "completed": False, "task": state}
        accepted, error = _evidence_acceptance(step, evidence)
        if not accepted:
            return {"ok": False, "error": error, "task": state}
        kind = str(step.get("kind") or "")
        if kind in {"live_proposal", "generation_job", "offline_render"}:
            progress = next((
                item for item in reversed(state.get("evidence") or [])
                if item.get("step_id") == step_id and item.get("progress_only") is True
            ), None)
            expected_key = _link_key(kind, progress or {})
            actual_key = _link_key(kind, evidence)
            if not expected_key:
                return {"ok": False, "error": "Task has no recorded proposal or queued-job identity for this step.", "task": state}
            if actual_key != expected_key:
                return {"ok": False, "error": "Completion evidence does not match this step's recorded action or job identity.", "task": state}

        completed = list(state.get("completed_step_ids") or [])
        if step_id not in completed:
            completed.append(step_id)
        state["completed_step_ids"] = completed
        state["evidence"] = [*(state.get("evidence") or []), {
            "step_id": step_id,
            **_safe_evidence_identity(evidence),
        }][-64:]
        state["status"], state["current_step_id"] = _next_status(state["plan"], completed)
        state["updated_at"] = _now()

        conn = _connect(self.db_path)
        try:
            cursor = conn.execute(
                "UPDATE assistant_tasks SET status = ?, state_json = ?, updated_at = ? "
                "WHERE task_id = ? AND state_json = ? AND status NOT IN ('completed', 'cancelled', 'failed')",
                (
                    state["status"], json.dumps(state, sort_keys=True), state["updated_at"],
                    task_id, prior_state_json,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        if cursor.rowcount != 1:
            return {"ok": False, "error": "Assistant task changed concurrently; reload it before retrying."}
        return {"ok": True, "completed": True, "task": state}

    def record_step_failure(self, *, task_id: str, step_id: str, evidence: dict[str, Any]) -> dict[str, Any]:
        """Terminate a queued job step only from matching typed failure evidence."""
        state = self.load(task_id)
        if state is None:
            return {"ok": False, "error": "Assistant task was not found."}
        if state.get("status") in TERMINAL_STATUSES:
            return {"ok": False, "error": f"Assistant task is already {state.get('status')}."}
        if step_id != state.get("current_step_id"):
            return {"ok": False, "error": "Failure evidence must belong to the task's current step."}
        step = next((item for item in state["plan"]["steps"] if item.get("step_id") == step_id), None)
        if step is None or not isinstance(evidence, dict):
            return {"ok": False, "error": "Current task step and typed failure evidence are required."}
        kind = str(step.get("kind") or "")
        schema = str(evidence.get("schema") or "")
        status = str(evidence.get("status") or "")
        if kind == "generation_job":
            valid_failure = schema.startswith("kenn.audiogen_") and status == "failed"
        elif kind == "offline_render":
            valid_failure = schema == "kenn.automix.local_receipt.v1" and status == "failed"
        else:
            valid_failure = False
        if not valid_failure:
            return {"ok": False, "error": "Only a typed failed job can terminate a queued job step.", "task": state}
        progress = next((
            item for item in reversed(state.get("evidence") or [])
            if item.get("step_id") == step_id and item.get("progress_only") is True
        ), None)
        expected_key = _link_key(kind, progress or {})
        actual_key = _link_key(kind, evidence)
        if not expected_key or actual_key != expected_key:
            return {"ok": False, "error": "Failure evidence does not match this step's queued-job identity.", "task": state}

        prior_state_json = json.dumps(state, sort_keys=True)
        state["status"] = "failed"
        state["current_step_id"] = ""
        state["evidence"] = [*(state.get("evidence") or []), {
            "step_id": step_id,
            "failed": True,
            **_safe_evidence_identity(evidence),
        }][-64:]
        state["updated_at"] = _now()
        conn = _connect(self.db_path)
        try:
            cursor = conn.execute(
                "UPDATE assistant_tasks SET status = ?, state_json = ?, updated_at = ? "
                "WHERE task_id = ? AND state_json = ? AND status NOT IN ('completed', 'cancelled', 'failed')",
                ("failed", json.dumps(state, sort_keys=True), state["updated_at"], task_id, prior_state_json),
            )
            conn.commit()
        finally:
            conn.close()
        if cursor.rowcount != 1:
            return {"ok": False, "error": "Assistant task changed concurrently; reload it before retrying."}
        return {"ok": True, "failed": True, "task": state}

    def rebind_after_evidence(
        self,
        *,
        task_id: str,
        step_id: str,
        context: dict[str, Any],
        domain: str,
        evidence_id: str,
    ) -> dict[str, Any]:
        """Rebind only when one exact async evidence identity explains all drift."""
        if domain not in {"generation", "offline"}:
            return {"ok": False, "error": "Only generation or offline evidence can rebind a task."}
        checked = validate_session_context(context)
        if not checked.get("ok"):
            return {"ok": False, "error": "Fresh session context is invalid or stale."}
        identity = str(evidence_id or "").strip()[:128]
        if not identity:
            return {"ok": False, "error": "Evidence-scoped rebinding requires an exact identity."}
        state = self.load(task_id)
        if state is None:
            return {"ok": False, "error": "Assistant task was not found."}
        if state.get("status") != "active":
            return {"ok": False, "error": "Only an active task can be rebound for its next step.", "task": state}
        if str(state.get("session_id") or "") != str(context.get("session_id") or ""):
            return {"ok": False, "error": "Assistant task belongs to another session.", "task": state}
        if step_id not in (state.get("completed_step_ids") or []):
            return {"ok": False, "error": "The evidence-producing step is not completed.", "task": state}
        previous = state.get("context_binding") if isinstance(state.get("context_binding"), dict) else None
        current = assistant_context_binding(context)
        if previous is None:
            return {"ok": False, "error": "Task predates scoped context binding and must be replanned.", "task": state}

        for fixed_domain in ("live", "services", "measurements", "audition", "profile"):
            if previous.get(fixed_domain) != current.get(fixed_domain):
                return {"ok": False, "error": f"Unrelated {fixed_domain} context changed; replan is required.", "task": state}
        other_domain = "offline" if domain == "generation" else "generation"
        if previous.get(other_domain) != current.get(other_domain):
            return {"ok": False, "error": f"Unrelated {other_domain} evidence changed; replan is required.", "task": state}
        previous_scope = previous.get(domain) if isinstance(previous.get(domain), dict) else {}
        current_scope = current.get(domain) if isinstance(current.get(domain), dict) else {}
        previous_entries = dict(previous_scope.get("identified") or {})
        current_entries = dict(current_scope.get("identified") or {})
        if identity not in current_entries:
            return {"ok": False, "error": "Bound evidence identity is absent from the fresh context.", "task": state}
        previous_entries.pop(identity, None)
        current_entries.pop(identity, None)
        if (
            previous_entries != current_entries
            or previous_scope.get("unidentified") != current_scope.get("unidentified")
        ):
            return {"ok": False, "error": f"Unrelated {domain} evidence changed; replan is required.", "task": state}

        rebound_plan = deepcopy(state["plan"])
        rebound_plan["snapshot_fingerprint"] = context["snapshot_fingerprint"]
        plan_check = validate_deliberative_plan(rebound_plan, context)
        if not plan_check.get("ok"):
            return {"ok": False, "error": "Remaining plan is invalid in the refreshed context.", "errors": plan_check.get("errors", []), "task": state}
        prior_state_json = json.dumps(state, sort_keys=True)
        state["plan"] = rebound_plan
        state["context_binding"] = current
        state["context_rebindings"] = [*(state.get("context_rebindings") or []), {
            "step_id": str(step_id)[:64],
            "domain": domain,
            "evidence_id": identity,
            "rebound_at": _now(),
        }][-8:]
        state["updated_at"] = _now()
        conn = _connect(self.db_path)
        try:
            cursor = conn.execute(
                "UPDATE assistant_tasks SET state_json = ?, updated_at = ? "
                "WHERE task_id = ? AND state_json = ? AND status = 'active'",
                (json.dumps(state, sort_keys=True), state["updated_at"], task_id, prior_state_json),
            )
            conn.commit()
        finally:
            conn.close()
        if cursor.rowcount != 1:
            return {"ok": False, "error": "Assistant task changed concurrently; reload it before retrying."}
        return {"ok": True, "task": state, "rebound": True}


__all__ = [
    "ACTIVE_STATUSES", "AssistantTaskStore", "EVIDENCE_SCHEMA", "MAX_ACTIVE_TASKS_PER_SESSION", "MAX_REPLAN_DEPTH", "TASK_SCHEMA",
    "TERMINAL_STATUSES",
]
