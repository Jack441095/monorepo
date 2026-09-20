"""KENN autonomous maintenance scheduler — Stage G of docs/AUDIO_MVP_MASTER_PLAN.md.

This module is the ONLY place KENN's knowledge-base maintenance jobs run
unattended, on a schedule, with no human clicking anything first. It exists
to implement the narrow autonomy scope Stage G defines and nothing more:

    "autonomous only if it (a) touches KENN's own internal knowledge store,
    never a live answer directly, (b) is fully reversible, and (c) produces
    a durable, human-reviewable record of what it did."

Three jobs, matching Stage G's G1/G2/G3 exactly:

  * G1 — daily contradiction + low-trust/coverage-gap scan (detection only).
    Calls `scan_for_contradictions()` and `propose_maintenance()`, both of
    which are already read-only with respect to note content: contradictions
    only insert *detection* rows into `knowledge_contradictions`, they never
    touch a note file or a live answer.
  * G2 — weekly gap-clustering / suggested-note draft generation. Calls
    `run_clustering()`, which only ever writes to `suggested_notes` with
    `status='pending'` — inert until a human calls `approve_suggested_note()`.
  * G3 — retrospective, log-only cross-trace critique sweep. Reuses the same
    measurement-contradiction check `post_answer_critique()` already runs on
    every live answer, just applied in batch over stored reasoning traces.
    Findings are written to the same `knowledge_contradictions` table as G1
    (no new review surface) and no stored trace is ever mutated.

What this module will NEVER call, by design, per the plan doc's own
"Explicitly NOT autonomous" list:

  * `resolve_contradiction()` / `_deprecate_note()` (contradictions.py) —
    rewrites a note's `Status:` header on disk. Detection (G1) is autonomous;
    resolution stays a human running `main.py resolve-contradiction`.
  * `approve_suggested_note()` (business/app/suggested_notes_ops.py) — the
    only writer into the canonical Training_Data_Notes directory. Draft
    generation (G2) is autonomous; approval is not.
  * Any trust-score write (`record_correction()`, `set_source_trust()`,
    `ingest_correction()`) — per G4, an algorithm's guess about a conflict
    must never silently degrade a source's standing. Low-trust sources stay
    a reviewable proposal surfaced through `propose_maintenance()`.

Every run — success, failure, or skipped-due-to-rate-cap — writes a receipt
row to `knowledge_maintenance_runs`, a durable, human-reviewable record
surfaced via `python main.py maintenance-log`. This reuses KENN's existing
sqlite database (the same one `knowledge_contradictions` already lives in)
rather than inventing a new review surface, per the Stage G guardrail
summary ("writes only to review queues or detection tables KENN's existing
CLI/website surfaces already expose to a human").
"""

from __future__ import annotations

import datetime
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from kenn.knowledge.reasoning import _get_conn, init_db

logger = logging.getLogger("kenn.knowledge.maintenance_scheduler")

# Rate caps (hours). These are the kill-switch-adjacent safeguard the plan
# doc calls for: "skip the run if it already ran within N hours". They are
# deliberately conservative — daily/weekly, never per-request — per the
# Stage G guardrail summary.
G1_MIN_INTERVAL_HOURS = 20.0  # daily contradiction + coverage-gap scan
G2_MIN_INTERVAL_HOURS = 24.0 * 6.0  # weekly gap-clustering (matches the
# module's own "weekly job" docstring in gap_clustering.py)
G3_MIN_INTERVAL_HOURS = 20.0  # daily retrospective critique sweep

JOB_G1 = "contradiction_scan"
JOB_G2 = "gap_clustering"
JOB_G3 = "retrospective_critique"


def init_maintenance_db() -> None:
    """Create the maintenance-run receipts table if it doesn't exist yet."""
    init_db()
    try:
        with _get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_maintenance_runs (
                    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    summary TEXT NOT NULL
                )
                """
            )
    except (sqlite3.Error, OSError) as e:
        logger.warning(f"Failed to initialize maintenance runs table: {e}")


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _record_run(job: str, status: str, summary: dict[str, Any]) -> int | None:
    """Write a durable, human-reviewable receipt for a maintenance run."""
    init_maintenance_db()
    try:
        with _get_conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO knowledge_maintenance_runs (job, started_at, finished_at, status, summary)
                VALUES (?, ?, ?, ?, ?)
                """,
                (job, _now_iso(), _now_iso(), status, json.dumps(summary)),
            )
            return cur.lastrowid
    except (sqlite3.Error, OSError) as e:
        logger.warning(f"Failed to record maintenance run receipt for {job}: {e}")
        return None


def _hours_since_last_run(job: str) -> float | None:
    """Return hours since the job last ran (any status), or None if never run."""
    init_maintenance_db()
    try:
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT started_at FROM knowledge_maintenance_runs WHERE job = ? ORDER BY started_at DESC LIMIT 1",
                (job,),
            ).fetchone()
        if not row:
            return None
        last = datetime.datetime.fromisoformat(row["started_at"])
        delta = datetime.datetime.now(datetime.timezone.utc) - last
        return delta.total_seconds() / 3600.0
    except (sqlite3.Error, OSError, ValueError) as e:
        logger.warning(f"Failed to compute time since last run for {job}: {e}")
        return None


def list_maintenance_runs(limit: int = 50) -> list[dict[str, Any]]:
    """List recent maintenance-run receipts, most recent first."""
    init_maintenance_db()
    try:
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM knowledge_maintenance_runs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        results = []
        for row in rows:
            r = dict(row)
            try:
                r["summary"] = json.loads(r["summary"])
            except Exception:
                r["summary"] = {}
            results.append(r)
        return results
    except (sqlite3.Error, OSError) as e:
        logger.warning(f"Failed to list maintenance runs: {e}")
        return []


def _should_run(job: str, min_interval_hours: float, force: bool) -> bool:
    if force:
        return True
    hours = _hours_since_last_run(job)
    if hours is None:
        return True
    return hours >= min_interval_hours


# ---------------------------------------------------------------------------
# G1 — daily contradiction + low-trust/coverage-gap scan (detection only)
# ---------------------------------------------------------------------------

def run_contradiction_scan_job(notes_dir: Path | None = None, force: bool = False) -> dict[str, Any]:
    """Run the G1 detection sweep: scan_for_contradictions() + propose_maintenance().

    Both calls are read-only with respect to note content and live answers —
    scan_for_contradictions() only inserts detection rows via
    save_contradiction(); propose_maintenance() only reads and returns a
    list of proposal dicts. Neither is ever wired to resolve_contradiction()
    or _deprecate_note() from this module.
    """
    if not _should_run(JOB_G1, G1_MIN_INTERVAL_HOURS, force):
        summary = {"skipped": True, "reason": "rate_cap", "min_interval_hours": G1_MIN_INTERVAL_HOURS}
        _record_run(JOB_G1, "skipped", summary)
        return {"ok": True, **summary}

    if notes_dir is None:
        from kenn.core.chat_constants import NOTES_DIR
        notes_dir = NOTES_DIR

    try:
        from kenn.knowledge.contradictions import scan_for_contradictions
        from kenn.knowledge.reflection import propose_maintenance

        detected = scan_for_contradictions(notes_dir)
        proposals = propose_maintenance()
        summary = {
            "skipped": False,
            "contradictions_detected": len(detected),
            "proposals_count": len(proposals),
            "proposal_types": sorted({p.get("type", "unknown") for p in proposals}),
        }
        _record_run(JOB_G1, "ok", summary)
        return {"ok": True, **summary}
    except Exception as e:
        summary = {"skipped": False, "error": str(e)}
        _record_run(JOB_G1, "error", summary)
        logger.warning(f"G1 contradiction scan job failed: {e}")
        return {"ok": False, **summary}


# ---------------------------------------------------------------------------
# G2 — weekly gap-clustering / suggested-note draft generation
# ---------------------------------------------------------------------------

def run_gap_clustering_job(force: bool = False) -> dict[str, Any]:
    """Run the G2 weekly job: run_clustering().

    run_clustering() never writes to the canonical notes directory. Every
    draft lands in `suggested_notes` with status='pending' and is inert
    until a human calls approve_suggested_note() — a function this module
    never imports or calls.
    """
    if not _should_run(JOB_G2, G2_MIN_INTERVAL_HOURS, force):
        summary = {"skipped": True, "reason": "rate_cap", "min_interval_hours": G2_MIN_INTERVAL_HOURS}
        _record_run(JOB_G2, "skipped", summary)
        return {"ok": True, **summary}

    try:
        from kenn.adaptive.gap_clustering import run_clustering

        count = run_clustering()
        summary = {"skipped": False, "suggested_notes_drafted": count}
        _record_run(JOB_G2, "ok", summary)
        return {"ok": True, **summary}
    except Exception as e:
        summary = {"skipped": False, "error": str(e)}
        _record_run(JOB_G2, "error", summary)
        logger.warning(f"G2 gap clustering job failed: {e}")
        return {"ok": False, **summary}


# ---------------------------------------------------------------------------
# G3 — retrospective, log-only cross-trace critique sweep
# ---------------------------------------------------------------------------

def _cross_trace_contradictions(traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compare stored reasoning-trace conclusions pairwise for measurement
    mismatches, reusing the exact same detection logic post_answer_critique()
    already applies to a single new answer vs. past traces — just batched.

    Read-only: never mutates a trace, never touches a live answer.
    """
    from kenn.knowledge.reflection import extract_measurements

    found = []
    measurements_by_trace = []
    for trace in traces:
        conclusion = trace.get("conclusion", "") or ""
        measurements_by_trace.append((trace, extract_measurements(conclusion)))

    for i, (trace_a, meas_a) in enumerate(measurements_by_trace):
        if not meas_a:
            continue
        for trace_b, meas_b in measurements_by_trace[i + 1:]:
            if not meas_b:
                continue
            for unit, values_a in meas_a.items():
                if unit not in meas_b:
                    continue
                values_b = meas_b[unit]
                if values_a & values_b:
                    continue
                desc = (
                    f"Cross-trace {unit} mismatch: trace '{trace_a['trace_id'][:8]}' concluded "
                    f"{sorted(values_a)} {unit}, but trace '{trace_b['trace_id'][:8]}' concluded "
                    f"{sorted(values_b)} {unit}."
                )
                found.append(
                    {
                        "type": "cross_trace_measurement_mismatch",
                        "source_a": f"trace:{trace_a['trace_id']}",
                        "source_b": f"trace:{trace_b['trace_id']}",
                        "description": desc,
                        "conflicting_data": {
                            "unit": unit,
                            "values_a": sorted(values_a),
                            "values_b": sorted(values_b),
                        },
                    }
                )
    return found


def run_retrospective_critique_job(limit: int = 200, force: bool = False) -> dict[str, Any]:
    """Run the G3 batch sweep over stored reasoning traces.

    Strictly log-only: findings are appended to knowledge_contradictions via
    save_contradiction() (the same detection-record table G1 writes to) —
    no stored reasoning trace is ever altered, no live answer is touched.
    """
    if not _should_run(JOB_G3, G3_MIN_INTERVAL_HOURS, force):
        summary = {"skipped": True, "reason": "rate_cap", "min_interval_hours": G3_MIN_INTERVAL_HOURS}
        _record_run(JOB_G3, "skipped", summary)
        return {"ok": True, **summary}

    try:
        from kenn.knowledge.reasoning import list_reasoning_history
        from kenn.knowledge.contradictions import save_contradiction

        traces = list_reasoning_history(limit=limit)
        findings = _cross_trace_contradictions(traces)
        for f in findings:
            save_contradiction(f["type"], f["source_a"], f["source_b"], f["description"], f["conflicting_data"])

        summary = {
            "skipped": False,
            "traces_scanned": len(traces),
            "cross_trace_contradictions_found": len(findings),
        }
        _record_run(JOB_G3, "ok", summary)
        return {"ok": True, **summary}
    except Exception as e:
        summary = {"skipped": False, "error": str(e)}
        _record_run(JOB_G3, "error", summary)
        logger.warning(f"G3 retrospective critique job failed: {e}")
        return {"ok": False, **summary}


# ---------------------------------------------------------------------------
# Single scheduled entry point (what launchd / main.py actually calls)
# ---------------------------------------------------------------------------

def run_scheduled_maintenance(force: bool = False) -> dict[str, Any]:
    """Run all three Stage G autonomous jobs, each independently rate-capped.

    This is the single function a scheduler (launchd, cron, or a manual CLI
    invocation) should call. It is safe to invoke as often as once a minute
    — each job's own rate cap (daily for G1/G3, weekly for G2) is what
    actually controls execution frequency, matching the guardrail's
    "skip the run if it already ran within N hours" kill-switch pattern.
    `force=True` bypasses all rate caps (for manual/admin invocation and
    tests) but still never calls a gated operation.
    """
    g1 = run_contradiction_scan_job(force=force)
    g2 = run_gap_clustering_job(force=force)
    g3 = run_retrospective_critique_job(force=force)
    return {
        "ok": all(r.get("ok", False) for r in (g1, g2, g3)),
        JOB_G1: g1,
        JOB_G2: g2,
        JOB_G3: g3,
    }
