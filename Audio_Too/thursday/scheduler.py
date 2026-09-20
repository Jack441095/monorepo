#!/usr/bin/env python3
"""Thursday Agent Scheduler - Cron-like scheduling for autonomous agents.

This module enables time-based triggers for agents:
- Daily invoice follow-ups
- Weekly lead nurturing
- Monthly reports
- Custom scheduled workflows

Integration points:
- Reads from thursday/config/schedules.yaml
- Calls agents via SubagentRuntime
- Logs all scheduled actions
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

# Ensure business app is importable for db
if str(Path(__file__).parent.parent / "business" / "app") not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent / "business" / "app"))

# Now import db
from db import connect, now

from thursday.runtime_paths import DATA_DIR


# Default schedule configuration
DEFAULT_SCHEDULES = {
    "daily": [
        {"name": "invoice_followups", "time": "09:00", "agent": "FollowupAgent", "method": "check_invoice_followups"},
        {"name": "archive_cold_leads", "time": "02:00", "agent": "FollowupAgent", "method": "archive_cold_leads"},
    ],
    "weekly": [
        {"name": "lead_nurturing", "day": "monday", "time": "10:00", "agent": "FollowupAgent", "method": "score_and_nurture_leads"},
        {"name": "knowledge_flywheel", "day": "sunday", "time": "03:00", "agent": "KnowledgeFlywheelAgent", "method": "run_knowledge_flywheel"},
    ],
    "monthly": [
        {"name": "revenue_forecast", "day": 1, "time": "08:00", "agent": "RevenueAgent", "method": "monthly_forecast"},
    ],
}


def load_schedules() -> dict[str, Any]:
    """Load schedule configuration from file or return defaults."""
    schedule_path = Path(__file__).parent / "config" / "schedules.yaml"
    
    # For now, return defaults - can be extended to parse YAML
    if schedule_path.exists():
        # TODO: Parse YAML config
        pass
    
    return DEFAULT_SCHEDULES


def should_run(schedule: dict[str, Any]) -> bool:
    """Check if a scheduled task should run now."""
    tz = ZoneInfo("Europe/London")
    now_dt = datetime.now(tz)
    
    # Parse target time
    target_time = time.fromisoformat(schedule["time"])
    
    # Check if we're within the hour window
    current_time = now_dt.time()
    time_diff = abs(
        (current_time.hour * 60 + current_time.minute) -
        (target_time.hour * 60 + target_time.minute)
    )
    
    # Run if within 5 minutes of target time
    if time_diff > 5:
        return False
    
    # Check day for weekly/monthly schedules
    if "day" in schedule:
        if schedule.get("day") != now_dt.strftime("%A").lower():
            return False
    
    return True


def _occurrence_key(task: dict[str, Any], now_dt: datetime) -> str:
    """A deterministic identity for *this specific* scheduled occurrence.

    Distinguishes "invoice_followups on 2026-08-20" from "invoice_followups
    on 2026-08-21" (daily), a given weekday's occurrence within its ISO week
    (weekly), or a given calendar month (monthly) -- i.e. exactly the window
    `should_run()`'s 5-minute check is trying to catch, not just the task
    name. Two overlapping `run_scheduled_tasks()` polls within the same
    occurrence window compute the identical key.
    """
    if "day" in task:
        day = task["day"]
        if isinstance(day, int):
            # Monthly: one occurrence per calendar month.
            return f"{task['name']}:{now_dt.strftime('%Y-%m')}"
        # Weekly: one occurrence per ISO week (the weekday is fixed by config).
        iso = now_dt.isocalendar()
        return f"{task['name']}:{iso.year}-W{iso.week:02d}"
    # Daily: one occurrence per calendar date.
    return f"{task['name']}:{now_dt.strftime('%Y-%m-%d')}"


def _claims_db_path() -> Path:
    configured = os.environ.get("THURSDAY_SCHEDULER_CLAIMS_DB", "").strip()
    if configured:
        return Path(configured).expanduser()
    return DATA_DIR / "scheduler_claims.sqlite3"


import threading

_claims_lock = threading.Lock()
_claims_init_done = False


def _claims_connect() -> sqlite3.Connection:
    global _claims_init_done
    path = _claims_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10.0, isolation_level=None)
    conn.execute("PRAGMA busy_timeout=10000")
    
    if not _claims_init_done:
        with _claims_lock:
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                _claims_init_done = True
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower():
                    raise
                    
    conn.execute(
        """CREATE TABLE IF NOT EXISTS scheduled_task_claims (
               task_name TEXT NOT NULL,
               occurrence_key TEXT NOT NULL,
               status TEXT NOT NULL DEFAULT 'processing'
                   CHECK (status IN ('processing', 'completed', 'failed')),
               result_json TEXT,
               claimed_at TEXT NOT NULL,
               completed_at TEXT,
               PRIMARY KEY (task_name, occurrence_key)
           )"""
    )
    return conn


def claim_occurrence(task_name: str, occurrence_key: str) -> bool:
    """Atomically claim one scheduled occurrence.

    Backed by a SQLite `PRIMARY KEY (task_name, occurrence_key)` -- the
    INSERT itself is the atomic operation (SQLite serializes writers at the
    database-file level), so two schedulers racing to claim the exact same
    occurrence cannot both succeed: exactly one INSERT wins, the other hits
    a UNIQUE/PRIMARY KEY violation and must skip. This replaces the
    previous "evaluate `should_run()` in a bare time window, no lock, no
    unique constraint" design (docs/audits/2026-08-20-thursday-nitedsp-
    forensic-audit.md, P0-10) that let two overlapping poll cycles dispatch
    the same scheduled task (e.g. a duplicate invoice follow-up email)
    twice.

    Returns True if this call won the claim (the caller must now run the
    task), False if the occurrence was already claimed (by this process or
    another) -- the caller must skip it.
    """
    conn = _claims_connect()
    try:
        conn.execute(
            """INSERT INTO scheduled_task_claims
                   (task_name, occurrence_key, status, claimed_at)
               VALUES (?, ?, 'processing', ?)""",
            (task_name, occurrence_key, now()),
        )
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def complete_occurrence(task_name: str, occurrence_key: str, result: dict[str, Any]) -> None:
    """Record the outcome of a claimed occurrence exactly once.

    Deterministic failure behaviour: a raised exception inside
    `dispatch_agent` is already caught there and returned as
    `{"ok": False, "error": ...}` -- that failure is still recorded as
    `status='failed'` here (the claim is NOT released), so a failed run is
    not silently retried on the next poll within the same occurrence window.
    A genuinely new attempt requires the next distinct occurrence (the next
    calendar day/week/month), matching the existing (pre-this-fix) single-
    attempt-per-window behaviour rather than introducing new retry semantics
    -- retry/backoff policy for scheduled tasks is explicitly out of scope
    for this Phase-0 pass (see docs/thursday/PHASE_0_HARDENING_REPORT.md).
    """
    conn = _claims_connect()
    try:
        conn.execute(
            """UPDATE scheduled_task_claims
                   SET status = ?, result_json = ?, completed_at = ?
                   WHERE task_name = ? AND occurrence_key = ? AND status = 'processing'""",
            (
                "completed" if result.get("ok") else "failed",
                json.dumps(result),
                now(),
                task_name,
                occurrence_key,
            ),
        )
    finally:
        conn.close()


def dispatch_agent(agent_name: str, method_name: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Dispatch a scheduled task to an agent.
    
    Uses Thursday's SubagentRuntime for in-process execution.
    """
    # Import here to avoid circular imports
    agents_shared = Path(__file__).parent.parent / "business" / "agents" / "Shared"
    if str(agents_shared) not in sys.path:
        sys.path.insert(0, str(agents_shared))
    
    
    # Load agent module
    agent_path = Path(__file__).parent.parent / "business" / "agents" / agent_name
    if str(agent_path) not in sys.path:
        sys.path.insert(0, str(agent_path))
    
    try:
        if agent_name == "FollowupAgent":
            from followup_agent_implementation import FollowupAgent
            agent = FollowupAgent()
        elif agent_name == "KnowledgeFlywheelAgent":
            # Placeholder - create this next
            return {"ok": False, "error": "KnowledgeFlywheelAgent not yet implemented"}
        elif agent_name == "RevenueAgent":
            # Placeholder - create this next
            return {"ok": False, "error": "RevenueAgent not yet implemented"}
        else:
            return {"ok": False, "error": f"Unknown agent: {agent_name}"}
        
        # Call the method
        method = getattr(agent, method_name, None)
        if not method:
            return {"ok": False, "error": f"Method {method_name} not found on {agent_name}"}
        
        result = method(**(params or {}))
        
        return {
            "ok": True,
            "agent": agent_name,
            "method": method_name,
            "result": result,
            "ran_at": now(),
        }
    except Exception as e:
        return {
            "ok": False,
            "agent": agent_name,
            "method": method_name,
            "error": str(e),
            "ran_at": now(),
        }


def _run_if_due_and_unclaimed(task: dict[str, Any], now_dt: datetime, results: list[dict[str, Any]]) -> None:
    """Claim-then-dispatch one task's current occurrence, if due.

    The claim happens strictly before dispatch, and dispatch only runs for
    the caller that won it -- this is the exactly-once invariant. A task
    that is due but whose occurrence was already claimed (by this process on
    an earlier overlapping poll, or by a concurrent scheduler process) is
    recorded as skipped, not silently dropped, so the double-fire race is
    observable rather than merely absent.
    """
    if not should_run(task):
        return
    occurrence_key = _occurrence_key(task, now_dt)
    if not claim_occurrence(task["name"], occurrence_key):
        results.append({**task, "run_result": {"ok": True, "skipped": "already_claimed", "occurrence": occurrence_key}})
        return
    result = dispatch_agent(task["agent"], task["method"])
    complete_occurrence(task["name"], occurrence_key, result)
    results.append({**task, "run_result": result, "occurrence": occurrence_key})


def run_scheduled_tasks() -> dict[str, Any]:
    """Run all tasks that should run now.

    Each due task's specific occurrence (see `_occurrence_key`) is atomically
    claimed via `claim_occurrence()` before it is dispatched, so two
    concurrent/overlapping calls to this function (e.g. two scheduler
    processes, or two poll cycles racing before the first finishes) cannot
    both run the same occurrence -- exactly one wins the claim and runs it;
    the other observes the claim and skips.
    """
    schedules = load_schedules()
    now_dt = datetime.now(ZoneInfo("Europe/London"))
    results: list[dict[str, Any]] = []

    for task in schedules.get("daily", []):
        _run_if_due_and_unclaimed(task, now_dt, results)

    for task in schedules.get("weekly", []):
        _run_if_due_and_unclaimed(task, now_dt, results)

    for task in schedules.get("monthly", []):
        _run_if_due_and_unclaimed(task, now_dt, results)

    return {
        "ok": True,
        "tasks_run": len(results),
        "results": results,
    }


def log_task_execution(task: dict[str, Any], result: dict[str, Any]) -> None:
    """Log scheduled task execution to database."""
    conn = connect()
    try:
        conn.execute(
            """
            INSERT INTO scheduled_task_log 
            (task_name, agent, method, ran_at, success, result_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                task["name"],
                task["agent"],
                task["method"],
                now(),
                result.get("ok", False),
                json.dumps(result),
            ),
        )
        conn.commit()
    finally:
        conn.close()


# CLI for manual testing
if __name__ == "__main__":
    print("=== Thursday Scheduler Check ===")
    print(f"Time: {now()}")
    
    results = run_scheduled_tasks()
    print(f"\nTasks run: {results['tasks_run']}")
    for r in results.get("results", []):
        status = "✓" if r["run_result"].get("ok") else "✗"
        print(f"  {status} {r['name']}: {r['agent']}.{r['method']}")