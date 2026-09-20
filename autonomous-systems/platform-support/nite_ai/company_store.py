"""Local company-state store (Phase 6B).

Smallest durable persistence for Thursday's future company-AI role.
SQLite via stdlib ``sqlite3``; parameterised SQL only; versioned schema with
atomic migrations; test-configurable path; never touches production data.

Entities mirror ``nite_ai.domain``: goals, projects, tasks, decisions, risks,
agent_runs. No conversation dumps, no secrets, no audio.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from nite_ai.domain import Goal, GoalKind, ItemStatus, Project, Task
from nite_ai.errors import ValidationError

SCHEMA_VERSION = 2

_MIGRATION_1 = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL,
    applied_at_epoch REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS goals (
    goal_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    parent_goal_id TEXT,
    progress REAL NOT NULL DEFAULT 0,
    owner TEXT NOT NULL DEFAULT '',
    target_date_epoch REAL,
    depends_on TEXT NOT NULL DEFAULT '',
    blocked_by TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at_epoch REAL NOT NULL,
    updated_at_epoch REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    goal_id TEXT NOT NULL REFERENCES goals(goal_id),
    status TEXT NOT NULL,
    progress REAL NOT NULL DEFAULT 0,
    created_at_epoch REAL NOT NULL,
    updated_at_epoch REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    status TEXT NOT NULL,
    due_epoch REAL,
    priority INTEGER NOT NULL DEFAULT 0,
    blocked_by TEXT NOT NULL DEFAULT '',
    created_at_epoch REAL NOT NULL,
    updated_at_epoch REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS decisions (
    decision_id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    basis_refs TEXT NOT NULL DEFAULT '',
    created_at_epoch REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS risks (
    risk_id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'medium',
    active INTEGER NOT NULL DEFAULT 1,
    created_at_epoch REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_runs (
    run_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    task_id TEXT,
    status TEXT NOT NULL,
    trace_id TEXT NOT NULL DEFAULT '',
    started_at_epoch REAL,
    finished_at_epoch REAL,
    result_ref TEXT NOT NULL DEFAULT '',
    blocker TEXT NOT NULL DEFAULT '',
    created_at_epoch REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_goals_status ON goals(status);
"""

_MIGRATION_2 = """
CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    action_level TEXT NOT NULL,
    capability_id TEXT NOT NULL,
    summary TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    requested_by TEXT NOT NULL DEFAULT '',
    reversibility TEXT NOT NULL DEFAULT 'reversible',
    payload_ref TEXT NOT NULL DEFAULT '',
    created_at_epoch REAL NOT NULL,
    decided_at_epoch REAL,
    decided_by TEXT NOT NULL DEFAULT ''
);
"""

_MIGRATIONS: dict[int, str] = {1: _MIGRATION_1, 2: _MIGRATION_2}


@dataclass(frozen=True)
class StorePaths:
    db_path: Path


def connect(db_path: Path | str) -> sqlite3.Connection:
    """Open (creating if needed) a company store with schema migration applied."""
    path = Path(db_path)
    if str(path.parent) not in ("", "."):
        path.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: the local runtime serves requests from its own
    # thread against this single-owner store. Access remains serialized by the
    # GIL plus explicit commits; heavy concurrent writers are out of scope V1.
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _migrate(conn)
    return conn


def schema_version(conn: sqlite3.Connection) -> int:
    exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    ).fetchone()
    if not exists:
        return 0
    row = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
    return int(row["v"]) if row and row["v"] is not None else 0


def _migrate(conn: sqlite3.Connection) -> None:
    current = schema_version(conn)
    if current > SCHEMA_VERSION:
        raise ValidationError(
            f"company store schema v{current} is newer than supported v{SCHEMA_VERSION}"
        )
    while current < SCHEMA_VERSION:
        current += 1
        script = _MIGRATIONS[current]
        try:
            conn.execute("BEGIN")
            conn.executescript(script)
            conn.execute(
                "INSERT INTO schema_version (version, applied_at_epoch) VALUES (?, ?)",
                (current, time.time()),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise


def _now() -> float:
    return time.time()


def _csv(values) -> str:
    return ",".join(values)


class CompanyStore:
    """Explicit repository API — no generic ORM layer."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ------------------------------------------------------------- goals
    def create_goal(self, goal: Goal) -> Goal:
        now = _now()
        self._conn.execute(
            "INSERT INTO goals (goal_id, kind, title, status, parent_goal_id, progress,"
            " owner, target_date_epoch, depends_on, blocked_by, notes,"
            " created_at_epoch, updated_at_epoch) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                goal.goal_id, goal.kind.value, goal.title, goal.status.value,
                goal.parent_goal_id, goal.progress, goal.owner, goal.target_date_epoch,
                _csv(goal.depends_on), _csv(goal.blocked_by), goal.notes, now, now,
            ),
        )
        self._conn.commit()
        return goal

    def update_goal_status(self, goal_id: str, status: ItemStatus,
                           progress: float | None = None) -> None:
        if progress is not None and not 0.0 <= progress <= 1.0:
            raise ValidationError("progress must be within [0, 1]")
        cur = self._conn.execute(
            "UPDATE goals SET status = ?, progress = COALESCE(?, progress),"
            " updated_at_epoch = ? WHERE goal_id = ?",
            (status.value, progress, _now(), goal_id),
        )
        if cur.rowcount == 0:
            raise ValidationError(f"unknown goal: {goal_id}")
        self._conn.commit()

    def list_goals(self, status: ItemStatus | None = None) -> list[Goal]:
        rows = self._conn.execute(
            "SELECT * FROM goals" + (" WHERE status = ?" if status else "")
            + " ORDER BY goal_id",
            (status.value,) if status else (),
        ).fetchall()
        return [
            Goal(
                goal_id=r["goal_id"], kind=GoalKind(r["kind"]), title=r["title"],
                status=ItemStatus(r["status"]), parent_goal_id=r["parent_goal_id"],
                progress=r["progress"], owner=r["owner"],
                target_date_epoch=r["target_date_epoch"],
                depends_on=tuple(filter(None, r["depends_on"].split(","))),
                blocked_by=tuple(filter(None, r["blocked_by"].split(","))),
                notes=r["notes"],
            )
            for r in rows
        ]

    # ---------------------------------------------------------- projects
    def create_project(self, project: Project) -> Project:
        now = _now()
        self._conn.execute(
            "INSERT INTO projects (project_id, title, goal_id, status, progress,"
            " created_at_epoch, updated_at_epoch) VALUES (?,?,?,?,?,?,?)",
            (project.project_id, project.title, project.goal_id,
             project.status.value, project.progress, now, now),
        )
        self._conn.commit()
        return project

    def list_projects(self) -> list[Project]:
        rows = self._conn.execute("SELECT * FROM projects ORDER BY project_id").fetchall()
        return [
            Project(project_id=r["project_id"], title=r["title"], goal_id=r["goal_id"],
                    status=ItemStatus(r["status"]), progress=r["progress"])
            for r in rows
        ]

    # ------------------------------------------------------------- tasks
    def create_task(self, task: Task) -> Task:
        now = _now()
        self._conn.execute(
            "INSERT INTO tasks (task_id, title, project_id, status, due_epoch, priority,"
            " blocked_by, created_at_epoch, updated_at_epoch) VALUES (?,?,?,?,?,?,?,?,?)",
            (task.task_id, task.title, task.project_id, task.status.value,
             task.due_epoch, task.priority, _csv(task.blocked_by), now, now),
        )
        self._conn.commit()
        return task

    def update_task_status(self, task_id: str, status: ItemStatus) -> None:
        cur = self._conn.execute(
            "UPDATE tasks SET status = ?, updated_at_epoch = ? WHERE task_id = ?",
            (status.value, _now(), task_id),
        )
        if cur.rowcount == 0:
            raise ValidationError(f"unknown task: {task_id}")
        self._conn.commit()

    def list_tasks(self, status: ItemStatus | None = None) -> list[Task]:
        rows = self._conn.execute(
            "SELECT * FROM tasks" + (" WHERE status = ?" if status else "")
            + " ORDER BY priority DESC, due_epoch ASC",
            (status.value,) if status else (),
        ).fetchall()
        return [
            Task(task_id=r["task_id"], title=r["title"], project_id=r["project_id"],
                 status=ItemStatus(r["status"]), due_epoch=r["due_epoch"],
                 priority=r["priority"],
                 blocked_by=tuple(filter(None, r["blocked_by"].split(","))))
            for r in rows
        ]

    # ------------------------------------------------- decisions & risks
    def record_decision(self, decision_id: str, description: str,
                        basis_refs: tuple[str, ...] = ()) -> None:
        self._conn.execute(
            "INSERT INTO decisions (decision_id, description, status, basis_refs,"
            " created_at_epoch) VALUES (?, ?, 'open', ?, ?)",
            (decision_id, description, _csv(basis_refs), _now()),
        )
        self._conn.commit()

    def resolve_decision(self, decision_id: str) -> None:
        cur = self._conn.execute(
            "UPDATE decisions SET status = 'resolved' WHERE decision_id = ?",
            (decision_id,),
        )
        if cur.rowcount == 0:
            raise ValidationError(f"unknown decision: {decision_id}")
        self._conn.commit()

    def list_open_decisions(self) -> list[dict]:
        return [dict(r) for r in self._conn.execute(
            "SELECT * FROM decisions WHERE status = 'open' ORDER BY created_at_epoch"
        ).fetchall()]

    def record_risk(self, risk_id: str, description: str, severity: str = "medium") -> None:
        self._conn.execute(
            "INSERT INTO risks (risk_id, description, severity, active, created_at_epoch)"
            " VALUES (?, ?, ?, 1, ?)",
            (risk_id, description, severity, _now()),
        )
        self._conn.commit()

    def retire_risk(self, risk_id: str) -> None:
        self._conn.execute("UPDATE risks SET active = 0 WHERE risk_id = ?", (risk_id,))
        self._conn.commit()

    def list_active_risks(self) -> list[dict]:
        return [dict(r) for r in self._conn.execute(
            "SELECT * FROM risks WHERE active = 1 ORDER BY created_at_epoch"
        ).fetchall()]

    # -------------------------------------------------------- agent runs
    def record_agent_run(self, run_id: str, agent_id: str, status: str,
                         task_id: str | None = None, trace_id: str = "",
                         started_at_epoch: float | None = None,
                         finished_at_epoch: float | None = None,
                         result_ref: str = "", blocker: str = "") -> None:
        self._conn.execute(
            "INSERT INTO agent_runs (run_id, agent_id, task_id, status, trace_id,"
            " started_at_epoch, finished_at_epoch, result_ref, blocker, created_at_epoch)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (run_id, agent_id, task_id, status, trace_id, started_at_epoch,
             finished_at_epoch, result_ref, blocker, _now()),
        )
        self._conn.commit()

    def recent_agent_runs(self, limit: int = 20) -> list[dict]:
        return [dict(r) for r in self._conn.execute(
            "SELECT * FROM agent_runs ORDER BY created_at_epoch DESC LIMIT ?", (limit,)
        ).fetchall()]

    # -------------------------------------------------------- approvals
    def record_approval(self, approval_id: str, action_level: str, capability_id: str,
                        summary: str, requested_by: str = "",
                        reversibility: str = "reversible",
                        payload_ref: str = "") -> None:
        self._conn.execute(
            "INSERT INTO approvals (approval_id, action_level, capability_id, summary,"
            " status, requested_by, reversibility, payload_ref, created_at_epoch)"
            " VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?)",
            (approval_id, action_level, capability_id, summary, requested_by,
             reversibility, payload_ref, _now()),
        )
        self._conn.commit()

    def list_pending_approvals(self) -> list[dict]:
        return [dict(r) for r in self._conn.execute(
            "SELECT * FROM approvals WHERE status = 'pending' ORDER BY created_at_epoch"
        ).fetchall()]

    def decide_approval(self, approval_id: str, approved: bool, decided_by: str) -> dict:
        if not decided_by:
            raise ValidationError("decided_by must identify the human decider")
        cur = self._conn.execute(
            "UPDATE approvals SET status = ?, decided_at_epoch = ?, decided_by = ?"
            " WHERE approval_id = ? AND status = 'pending'",
            ("approved" if approved else "rejected", _now(), decided_by, approval_id),
        )
        if cur.rowcount == 0:
            raise ValidationError(
                f"no pending approval with id: {approval_id}"
            )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)
        ).fetchone()
        # NOTE: deciding an approval changes internal state only. Executing the
        # underlying action is a separate, separately-permissioned operation.
        return dict(row)



def open_store(db_path):
    conn = connect(db_path)
    return conn, CompanyStore(conn)


__all__ = ["CompanyStore", "SCHEMA_VERSION", "StorePaths", "connect", "open_store",
           "schema_version"]
