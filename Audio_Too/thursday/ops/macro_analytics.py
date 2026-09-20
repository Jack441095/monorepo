"""Macro execution analytics (D2.3 in docs/THURSDAY_IMPROVEMENT_PLAN.md).

Macros (thursday/macros/) had no structured execution log at all -- unlike
subagent dispatch (thursday/subagent_runtime.py's execution_traces.jsonl,
D1.2), there was no record of which macros fire, how often, or how they
resolve. This module is the observation layer: it's called from the two
execute_macro() call sites in thursday/orchestrator.py (fresh dispatch and
confirmation-resume), never from inside thursday/macros/__init__.py itself
-- that function is security-sensitive (real HMAC confirmation tokens,
replay-safe receipt claiming; see the P0-6 forensic-audit reference at its
top) and is deliberately left untouched here.

Outcome is inferred from execute_macro()'s existing, already-shipped
result-string conventions (D1.3's partial-success format) rather than
requiring any change to what it returns:
  - a step paused for confirmation says "It has not run. To approve..."
  - a failed step's message always contains "failed: <reason>."
  - anything else is a completed run.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)

MACRO_LOG_FILE = "macro_executions.jsonl"


def classify_outcome(results: list[str]) -> str:
    """Infer "completed" / "paused_for_confirmation" / "failed" from
    execute_macro()'s existing result-string conventions. Never raises --
    an unrecognized shape degrades to "completed" rather than guessing wrong
    in the more alarming direction.
    """
    if not results:
        return "completed"
    last = results[-1]
    if "It has not run." in last and "confirm " in last:
        return "paused_for_confirmation"
    if "failed:" in last:
        return "failed"
    return "completed"


def record_macro_execution(
    macro_name: str,
    results: list[str],
    elapsed_ms: float,
    *,
    resumed: bool = False,
) -> None:
    """Append one execution record. Best-effort: a logging failure must
    never surface to the user or interrupt the macro response they're
    waiting on (same contract as subagent_runtime._log_execution_trace).
    """
    try:
        from thursday.runtime_paths import runtime_dir

        analytics_dir = runtime_dir("analytics", "THURSDAY_ANALYTICS_DIR")
        analytics_dir.mkdir(parents=True, exist_ok=True)
        log_file = analytics_dir / MACRO_LOG_FILE

        record = {
            "timestamp": datetime.now().isoformat(),
            "macro_name": macro_name,
            "outcome": classify_outcome(results),
            "elapsed_ms": round(elapsed_ms, 1),
            "resumed": resumed,
            "step_count": len(results),
        }
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as exc:
        logger.warning("Failed to write macro execution record: %s", exc)


def _load_records(limit: int = 2000) -> list[dict]:
    from thursday.runtime_paths import runtime_dir

    analytics_dir = runtime_dir("analytics", "THURSDAY_ANALYTICS_DIR")
    log_file = analytics_dir / MACRO_LOG_FILE
    if not log_file.exists():
        return []
    records: list[dict] = []
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return records[-limit:]


def get_macro_stats() -> dict:
    """Aggregate recorded executions per macro: fire count, outcome
    breakdown, and average elapsed_ms for completed runs.
    """
    records = _load_records()
    if not records:
        return {"total_executions": 0, "macros": {}}

    per_macro: dict[str, dict] = {}
    for r in records:
        name = r.get("macro_name", "unknown")
        entry = per_macro.setdefault(name, {
            "fires": 0, "completed": 0, "failed": 0,
            "paused_for_confirmation": 0, "_elapsed_completed": [],
        })
        entry["fires"] += 1
        outcome = r.get("outcome", "completed")
        entry[outcome] = entry.get(outcome, 0) + 1
        if outcome == "completed" and isinstance(r.get("elapsed_ms"), (int, float)):
            entry["_elapsed_completed"].append(r["elapsed_ms"])

    macros_summary = {}
    for name, entry in per_macro.items():
        elapsed = entry.pop("_elapsed_completed")
        macros_summary[name] = {
            **entry,
            "success_rate": round(entry["completed"] / entry["fires"], 3) if entry["fires"] else 0.0,
            "avg_elapsed_ms": round(sum(elapsed) / len(elapsed), 1) if elapsed else None,
        }

    return {"total_executions": len(records), "macros": macros_summary}
