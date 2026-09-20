"""Fine-tune readiness gate (Phase 5 prep -- NO training happens here).

 readiness_report() answers "is there enough clean data to fine-tune
yet?" from the live plan_memory + feedback stores via
training_export.export_training_records():

- Counts: total records, with user_signal (corrections/ratings), by
  decision type and status.
- Leak scan: every record re-serialized and passed through
  redaction.redact(); if redaction changes anything, a secret shape
  survived the export pipeline and the corpus FAILS closed (leaks > 0).
- Gate: MIN_RECORDS (50) Seasons-style floor -- below it the verdict is
  "insufficient: keep operating, re-check weekly". Never trains, never
  writes weights, never uploads anything.

Facts (prices, names, versions) must NEVER be trained into weights --
they are retrieved live (finance_ops, truth sheet). Fine-tuning covers
routing, tone, and SOP-following only; see docs/FINETUNE_LORA_SPEC_V1.md.
"""

from __future__ import annotations

import json
from typing import Any

from thursday import training_export as te
from thursday.redaction import get_logger as _get_redacting_logger, redact

logger = _get_redacting_logger(__name__)

MIN_RECORDS = 50


def _record_text(rec: dict[str, Any]) -> str:
    return json.dumps(rec, sort_keys=True)


def readiness_report(*, limit: int = 10_000) -> dict[str, Any]:
    """Build the readiness verdict. Never raises -- store failures come
    back as not-ready with the cause stated."""
    try:
        records = te.export_training_records(limit=limit)
    except Exception as exc:
        logger.warning("training_readiness: export failed: %s", exc)
        return {"ok": False, "ready": False, "total": 0,
                "error": f"Evidence missing — export failed: {exc}"}
    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    with_signal = 0
    leaks: list[str] = []
    for rec in records:
        dtype = str((rec.get("decision") or {}).get("type") or "unknown")
        by_type[dtype] = by_type.get(dtype, 0) + 1
        status = str((rec.get("outcome") or {}).get("status") or "unknown")
        by_status[status] = by_status.get(status, 0) + 1
        if rec.get("user_signal") is not None:
            with_signal += 1
        text = _record_text(rec)
        if redact(text) != text:
            leaks.append(str(rec.get("plan_id")))
    total = len(records)
    reasons = []
    if total < MIN_RECORDS:
        reasons.append(f"only {total}/{MIN_RECORDS} records -- keep operating, re-check weekly")
    if leaks:
        reasons.append(f"{len(leaks)} record(s) with surviving secret shapes -- FAIL CLOSED, fix redaction first")
    ready = not reasons
    return {
        "ok": True,
        "ready": ready,
        "total": total,
        "with_user_signal": with_signal,
        "by_decision_type": by_type,
        "by_status": by_status,
        "leak_plan_ids": leaks,
        "reasons": reasons or ["sufficient clean records -- see docs/FINETUNE_LORA_SPEC_V1.md; "
                               "founder approval still required before any training"],
        "error": None,
    }


def render_readiness(report: dict[str, Any]) -> str:
    if not report.get("ok"):
        return f"FINETUNE READINESS\n\n{report.get('error')}"
    lines = ["FINETUNE READINESS", "",
             f"  Records: {report['total']} (minimum {MIN_RECORDS})",
             f"  With user signal: {report['with_user_signal']}",
             f"  By type: {report['by_decision_type']}",
             f"  By status: {report['by_status']}",
             f"  Leaks: {len(report['leak_plan_ids'])}",
             "",
             f"  Verdict: {'READY (pending founder approval)' if report['ready'] else 'NOT READY'}"]
    for reason in report["reasons"]:
        lines.append(f"    - {reason}")
    return "\n".join(lines)
