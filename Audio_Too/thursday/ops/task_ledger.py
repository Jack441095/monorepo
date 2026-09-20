"""Persistent, founder-facing task ledger.

Deliberately a new, separate module rather than an extension of
thursday/taskgraph.py or thursday/orchestration_models.py: taskgraph.py's
own docstring scopes it narrowly to in-process subagent-swarm dependency
graphs ("not the brain-plan executor... out of scope here"), and
orchestration_models.py's SpecialistTask/TaskStatus state machine
(CREATED->VALIDATED->QUEUED->DISPATCHED->RUNNING->...) models internal
dispatch execution, not a founder-visible operational to-do list that
persists across sessions. Conflating either with this would tangle
internal execution state with external planning state.

This also does not replace thursday's existing, already-qualified
approval/confirmation system (confirmation.py, action_receipts.py,
approval_ergonomics.py -- HMAC-signed tokens, replay-safe claiming, TTL
expiry). A task's ``approval_required`` flag here is the founder-facing
"this needs a decision" marker on a planning item; it is not, and must
never become, a substitute for the real confirmation-token gate that
actually authorizes a mutating action.

Storage: a single JSON file (whole-document read/modify/atomic-write, the
same pattern thursday/feedback.py uses for habits/suggestions), not
JSONL -- unlike an execution log, a task's status changes in place over
its lifetime.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime

from thursday.atomic_io import atomic_write
from thursday.runtime_paths import DATA_DIR

TASK_LEDGER_FILE = DATA_DIR / "task_ledger.json"

WORKSTREAMS = {
    "daily_status", "marketing", "advertising", "product", "engineering",
    "qa", "infrastructure", "finance_admin", "funding", "grants",
    "investment", "launch", "documentation", "support", "research",
    "strategy",
}

# Matches the lifecycle the founder-facing list/filter commands use
# (list_tasks, active_tasks, tasks_by_workstream, tasks_requiring_approval).
STATUSES = {
    "proposed", "planned", "active", "waiting_for_founder",
    "waiting_for_external", "blocked", "done", "cancelled",
}
OPEN_STATUSES = {"proposed", "planned", "active", "waiting_for_founder", "waiting_for_external"}

PRIORITIES = {"low", "medium", "high", "urgent"}
RISK_LEVELS = {"low", "medium", "high"}


@dataclass
class TaskRecord:
    task_id: str
    created_at: str
    updated_at: str
    workstream: str
    objective: str
    status: str = "proposed"
    priority: str = "medium"
    risk_level: str = "low"
    approval_required: bool = False
    owner: str = "thursday"
    evidence: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    next_action: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class InvalidWorkstream(ValueError):
    pass


class InvalidStatus(ValueError):
    pass


class TaskNotFound(KeyError):
    pass


def _load() -> dict:
    """Return {"next_id": int, "tasks": {task_id: dict}}."""
    if TASK_LEDGER_FILE.exists():
        try:
            data = json.loads(TASK_LEDGER_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "tasks" in data:
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {"next_id": 1, "tasks": {}}


def _save(data: dict) -> None:
    TASK_LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        atomic_write(TASK_LEDGER_FILE, json.dumps(data, indent=2))
    except OSError:
        pass


def create_task(
    workstream: str,
    objective: str,
    *,
    priority: str = "medium",
    risk_level: str = "low",
    approval_required: bool = False,
    owner: str = "thursday",
    evidence: list[str] | None = None,
    next_action: str = "",
) -> TaskRecord:
    if workstream not in WORKSTREAMS:
        raise InvalidWorkstream(f"unknown workstream: {workstream!r}")
    if priority not in PRIORITIES:
        raise ValueError(f"unknown priority: {priority!r}")
    if risk_level not in RISK_LEVELS:
        raise ValueError(f"unknown risk_level: {risk_level!r}")

    data = _load()
    # Deterministic given the ledger's own history: task-<workstream>-<n>,
    # n from a monotonic counter persisted alongside the tasks themselves
    # (not a random/UUID id -- a re-run against the same ledger state
    # produces the same next id).
    task_id = f"task-{workstream}-{data['next_id']}"
    data["next_id"] += 1

    now = datetime.now().isoformat()
    record = TaskRecord(
        task_id=task_id,
        created_at=now,
        updated_at=now,
        workstream=workstream,
        objective=objective,
        priority=priority,
        risk_level=risk_level,
        approval_required=approval_required,
        owner=owner,
        evidence=list(evidence or []),
        next_action=next_action,
    )
    data["tasks"][task_id] = record.to_dict()
    _save(data)
    return record


def _get_raw(data: dict, task_id: str) -> dict:
    if task_id not in data["tasks"]:
        raise TaskNotFound(task_id)
    return data["tasks"][task_id]


def update_task(task_id: str, **fields) -> TaskRecord:
    """Merge-update a task's mutable fields. Raises TaskNotFound /
    InvalidStatus rather than silently no-op-ing on a bad call -- a ledger
    a founder relies on for status must fail loudly, not swallow mistakes.
    """
    data = _load()
    raw = _get_raw(data, task_id)

    if "status" in fields and fields["status"] not in STATUSES:
        raise InvalidStatus(f"unknown status: {fields['status']!r}")
    if "workstream" in fields and fields["workstream"] not in WORKSTREAMS:
        raise InvalidWorkstream(f"unknown workstream: {fields['workstream']!r}")

    raw.update(fields)
    raw["updated_at"] = datetime.now().isoformat()
    data["tasks"][task_id] = raw
    _save(data)
    return TaskRecord(**raw)


def complete_task(task_id: str, *, evidence: list[str] | None = None) -> TaskRecord:
    fields: dict = {"status": "done", "blockers": []}
    if evidence:
        data = _load()
        existing = list(_get_raw(data, task_id).get("evidence") or [])
        fields["evidence"] = existing + list(evidence)
    return update_task(task_id, **fields)


def block_task(task_id: str, blocker: str) -> TaskRecord:
    data = _load()
    existing = list(_get_raw(data, task_id).get("blockers") or [])
    return update_task(task_id, status="blocked", blockers=existing + [blocker])


def get_task(task_id: str) -> TaskRecord:
    data = _load()
    return TaskRecord(**_get_raw(data, task_id))


def list_tasks(*, status: str | None = None, workstream: str | None = None) -> list[TaskRecord]:
    data = _load()
    records = [TaskRecord(**raw) for raw in data["tasks"].values()]
    if status is not None:
        records = [r for r in records if r.status == status]
    if workstream is not None:
        records = [r for r in records if r.workstream == workstream]
    records.sort(key=lambda r: r.created_at)
    return records


def active_tasks() -> list[TaskRecord]:
    return [r for r in list_tasks() if r.status in OPEN_STATUSES]


def blocked_tasks() -> list[TaskRecord]:
    return list_tasks(status="blocked")


def tasks_by_workstream(workstream: str) -> list[TaskRecord]:
    return list_tasks(workstream=workstream)


def tasks_requiring_approval() -> list[TaskRecord]:
    return [r for r in list_tasks() if r.approval_required and r.status in OPEN_STATUSES]


# ── Natural-language task creation ──────────────────────────────────────

_WORKSTREAM_ALIASES = {
    "finance": "finance_admin",
    "admin": "finance_admin",
    "finance admin": "finance_admin",
    "investor": "investment",
    "investors": "investment",
    "grant": "grants",
    "ads": "advertising",
    "advert": "advertising",
    "adverts": "advertising",
    "eng": "engineering",
    "infra": "infrastructure",
    "docs": "documentation",
    "doc": "documentation",
}

# "create task marketing: draft this week's post"
# "add task for advertising - prepare campaign brief"
# "new task engineering: fix the crash on export"
_CREATE_TASK_PATTERN = re.compile(
    r"^\s*(?:create|add|new)\s+task\s+(?:for\s+)?([a-z_ ]+?)\s*[:\-]\s*(.+?)\s*$",
    re.IGNORECASE,
)


class UnrecognizedWorkstream(ValueError):
    """Raised by parse_create_task_command when the named workstream isn't
    a known one or a recognized alias -- carries the raw text so a caller
    can show the founder what was typed and the valid options.
    """

    def __init__(self, raw: str):
        self.raw = raw
        super().__init__(f"unrecognized workstream: {raw!r}")


def parse_create_task_command(text: str) -> tuple[str, str] | None:
    """Parse "create/add/new task <workstream>: <objective>" into
    (workstream, objective). Returns None if the text doesn't match the
    command shape at all (caller should treat that as "not a task-creation
    command", not an error). Raises UnrecognizedWorkstream if the shape
    matches but the named workstream isn't one Thursday knows -- that's a
    real user-facing error, not a silent fallback to a wrong workstream.
    """
    m = _CREATE_TASK_PATTERN.match(text)
    if not m:
        return None

    raw_workstream = m.group(1).strip().lower()
    objective = m.group(2).strip()

    normalized = raw_workstream.replace(" ", "_")
    if normalized in WORKSTREAMS:
        workstream = normalized
    elif raw_workstream in _WORKSTREAM_ALIASES:
        workstream = _WORKSTREAM_ALIASES[raw_workstream]
    elif normalized in _WORKSTREAM_ALIASES:
        workstream = _WORKSTREAM_ALIASES[normalized]
    else:
        raise UnrecognizedWorkstream(raw_workstream)

    if not objective:
        raise ValueError("empty objective")

    return workstream, objective
