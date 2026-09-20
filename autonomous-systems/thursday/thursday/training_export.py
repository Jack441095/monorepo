"""Read-only join of thursday.plan_memory + thursday.feedback into a clean,
redacted JSONL suitable as future fine-tuning input.

This is the terminal artifact of the execution-feedback-loop data-collection
pipeline: thursday.brain.decide() -> BrainDecision (route/model/confidence/
latency/failure_reason) -> thursday.orchestrator._record_plan_trace() ->
thursday.plan_memory (what Thursday decided) and thursday.feedback (how the
user reacted), joined here on plan_id.

Actually fine-tuning a model against this output is explicitly out of scope
for this module -- it only produces the dataset. Both source stores already
redact() sensitive fields at write time (see plan_memory.save_plan_trace and
feedback.record_feedback); the redaction applied here is a second pass, not
the only line of defense, in case a caller ever reads an older on-disk store
written before write-time redaction existed.

Never mutates plan_memory or feedback.jsonl, makes no network or model
calls, and is safe to run against an empty/fresh installation (returns an
empty list). Fails soft: any read/parse error on either store yields an
empty/partial result rather than raising, matching plan_memory.py's
philosophy.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from thursday.redaction import redact


def _redact_deep(obj: Any) -> Any:
    """Recursively redact() every string leaf in a JSON-shaped structure."""
    if isinstance(obj, str):
        return redact(obj)
    if isinstance(obj, dict):
        return {k: _redact_deep(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact_deep(v) for v in obj]
    return obj


def _load_feedback_by_plan_id(limit: int) -> dict[str, dict[str, Any]]:
    """Index feedback.jsonl records by plan_id (last one wins if duplicated).

    Uses feedback._load_feedback directly -- private (leading underscore)
    but same-package, and not worth promoting to a new public API for this
    one caller.
    """
    try:
        from thursday.feedback import _load_feedback
        records = _load_feedback(limit=limit)
    except Exception:
        return {}
    by_plan: dict[str, dict[str, Any]] = {}
    for rec in records:
        pid = rec.get("plan_id")
        if pid:
            by_plan[pid] = rec
    return by_plan


def export_training_records(*, limit: int = 10_000, since: str | None = None) -> list[dict[str, Any]]:
    """Join plan_memory rows onto their feedback.jsonl record (if any),
    sharing a plan_id, and return training-ready dicts. A plan with no
    matching feedback record gets user_signal=None rather than being
    dropped or raising.

    `since` is an ISO-8601 lower bound compared lexicographically against
    plan_memory's created_at (both are UTC isoformat strings, so this is a
    correct string comparison without needing to parse dates).
    """
    try:
        from thursday.plan_memory import list_plan_history
        plans = list_plan_history(limit=limit)
    except Exception:
        return []

    if since:
        plans = [p for p in plans if str(p.get("created_at") or "") >= since]

    feedback_by_plan = _load_feedback_by_plan_id(limit=limit)

    records: list[dict[str, Any]] = []
    for plan in plans:
        plan_id = plan.get("plan_id")
        fb = feedback_by_plan.get(plan_id) if plan_id else None
        user_signal = None
        if fb is not None:
            user_signal = {
                "explicit_rating": fb.get("explicit_rating"),
                "had_followup": fb.get("had_followup"),
                "followup_type": fb.get("followup_type"),
                "correction_from": fb.get("correction_from"),
                "correction_to": fb.get("correction_to"),
            }
        lesson = plan.get("lesson")
        records.append({
            "plan_id": plan_id,
            "created_at": plan.get("created_at"),
            "request": redact(str(plan.get("query") or "")),
            "decision": {
                "type": plan.get("decision_type"),
                "abstract": redact(str(plan.get("abstract") or "")),
                "steps": _redact_deep(plan.get("steps") or []),
                "confidence": plan.get("confidence"),
                "raw_step_count": plan.get("raw_step_count") or 0,
            },
            "model_meta": {
                "provider": plan.get("provider"),
                "model": plan.get("model"),
                "latency_s": plan.get("latency_s"),
            },
            "outcome": {
                "status": plan.get("status"),
                "failure_reason": plan.get("failure_reason"),
                "result_summary": redact(str(plan.get("result_summary") or "")),
                "executed_steps": _redact_deep(plan.get("executed_steps") or []),
            },
            "user_signal": user_signal,
            "lesson": redact(str(lesson)) if lesson else None,
        })
    return records


def write_training_jsonl(path: str | os.PathLike, *, limit: int = 10_000, since: str | None = None) -> int:
    """Write export_training_records(...) to `path` as one JSON object per
    line. Returns the number of records written. Uses an atomic write (temp
    file in the same directory, then os.replace) so a killed process never
    leaves a truncated export."""
    records = export_training_records(limit=limit, since=since)
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dest.with_suffix(dest.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    os.replace(tmp_path, dest)
    return len(records)
