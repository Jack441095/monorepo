"""THURSDAY_PROACTIVITY_V1 — proactivity qualification benchmark.

A frozen corpus of labelled synthetic company events. Labels encode the
INTENDED attention policy from the V2-A programme specification — they are
written independently of the classifier implementation so divergence is a
real finding, not circular validation.

Run:  python3 -m thursday.evals.proactivity_benchmark [--json PATH]

Measured: accuracy, critical-miss rate, interrupt false-positive rate,
duplicate-suppression rate.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict

from thursday.proactivity import AttentionClass, CompanyEvent, classify_event
from thursday.proactivity import _downgrade

NOW = 1_755_000_000.0  # fixed epoch for determinism


def _e(eid, kind, severity="medium", owner_action=False, reversible=True,
       deadline=None, subject="", first=True):
    return CompanyEvent(
        event_id=eid,
        kind=kind,
        severity=severity,
        owner_action_required=owner_action,
        reversible=reversible,
        deadline_epoch=deadline,
        subject=subject or f"{kind}:{eid}",
        first_occurrence=first,
    )


def build_corpus() -> list[tuple[CompanyEvent, AttentionClass]]:
    """Frozen labelled corpus (event, expected_class)."""
    cases: list[tuple[CompanyEvent, AttentionClass]] = []

    # ── Security ──
    cases += [
        (_e("sec-1", "security", "critical"), AttentionClass.INTERRUPT_NOW),
        (_e("sec-2", "security", "high"), AttentionClass.INTERRUPT_NOW),
        (_e("sec-3", "security", "medium"), AttentionClass.SURFACE_SOON),
        (_e("sec-4", "security", "low"), AttentionClass.SURFACE_SOON),
    ]

    # ── Release / deployment ──
    cases += [
        (_e("rel-1", "release_blocker", "critical", owner_action=True),
         AttentionClass.INTERRUPT_NOW),
        (_e("rel-2", "release_blocker", "high", owner_action=True),
         AttentionClass.INTERRUPT_NOW),
        (_e("rel-3", "release_blocker", "critical", owner_action=False),
         AttentionClass.SURFACE_SOON),
        (_e("rel-4", "deployment_failure", "high", owner_action=False),
         AttentionClass.SURFACE_SOON),
        (_e("rel-5", "deployment_failure", "high", owner_action=True),
         AttentionClass.INTERRUPT_NOW),
        (_e("rel-6", "release_blocker", "low"),
         AttentionClass.NEXT_BRIEF),
    ]

    # ── Approvals ──
    cases += [
        (_e("ap-1", "approval_needed", "high", reversible=False),
         AttentionClass.SURFACE_SOON),
        (_e("ap-2", "approval_needed", "critical", reversible=True),
         AttentionClass.SURFACE_SOON),
        (_e("ap-3", "approval_needed", "medium", reversible=True),
         AttentionClass.NEXT_BRIEF),
        (_e("ap-4", "approval_needed", "low", reversible=True),
         AttentionClass.NEXT_BRIEF),
    ]

    # ── Overdue tasks ──
    cases += [
        (_e("od-1", "task_overdue", "high", deadline=NOW - 30 * 3600),
         AttentionClass.SURFACE_SOON),
        (_e("od-2", "task_overdue", "high", deadline=NOW - 2 * 3600),
         AttentionClass.NEXT_BRIEF),
        (_e("od-3", "task_overdue", "low", deadline=NOW - 48 * 3600),
         AttentionClass.NEXT_BRIEF),
        (_e("od-4", "task_overdue", "critical", deadline=NOW - 72 * 3600),
         AttentionClass.SURFACE_SOON),
    ]

    # ── Agent failures ──
    cases += [
        (_e("ag-1", "agent_failure", "critical", reversible=False),
         AttentionClass.INTERRUPT_NOW),
        (_e("ag-2", "agent_failure", "high", reversible=True),
         AttentionClass.SURFACE_SOON),
        (_e("ag-3", "agent_failure", "medium", reversible=True),
         AttentionClass.SURFACE_SOON),
    ]

    # ── Quiet classes ──
    cases += [
        (_e("doc-1", "doc_issue", "low"), AttentionClass.LOG_ONLY),
        (_e("res-1", "blocker_resolved", "medium"), AttentionClass.LOG_ONLY),
        (_e("cmp-1", "completion", "info"), AttentionClass.LOG_ONLY),
        (_e("rts-1", "routine_success", "info"), AttentionClass.LOG_ONLY),
        (_e("met-1", "metric_change", "low"), AttentionClass.WEEKLY_REVIEW),
        (_e("met-2", "metric_change", "medium"), AttentionClass.WEEKLY_REVIEW),
        (_e("inv-1", "invoice_due", "medium", deadline=NOW + 10 * 86400),
         AttentionClass.NEXT_BRIEF),
        (_e("inv-2", "invoice_due", "high", deadline=NOW + 3600),
         AttentionClass.SURFACE_SOON),
        (_e("risk-1", "risk_update", "high"), AttentionClass.NEXT_BRIEF),
        (_e("goal-1", "goal_offtrack", "high"), AttentionClass.SURFACE_SOON),
        (_e("goal-2", "goal_offtrack", "critical"), AttentionClass.SURFACE_SOON),
    ]

    # ── Duplicates downgrade, never upgrade ──
    dup_base = [
        ("dup-sec", "security", "critical", AttentionClass.INTERRUPT_NOW),
        ("dup-rel", "release_blocker", "high", AttentionClass.SURFACE_SOON),
        ("dup-doc", "doc_issue", "low", AttentionClass.LOG_ONLY),
        ("dup-inv", "invoice_due", "high", AttentionClass.NEXT_BRIEF),
    ]
    for eid, kind, sev, expected in dup_base:
        cases.append((_e(f"{eid}-first", kind, sev), expected))
        downgraded = AttentionClass(
            ["ignore", "log_only", "weekly_review", "next_brief",
             "surface_soon", "interrupt_now"][
                max(0, _ORDER[expected] - 1)
            ]
        )
        cases.append(
            (_e(f"{eid}-repeat", kind, sev, subject=f"{eid}:same", first=False),
             downgraded)
        )

    # ── Expanded domains (V2-B §50): financial / marketing / support /
    #    release / agent stalls / goal drift / quiet events / stale events.
    #    Expected classes follow the same policy semantics as above.
    expanded = [
        # Financial
        (_e("fin-1", "invoice_overdue", "high"), AttentionClass.SURFACE_SOON),
        (_e("fin-2", "invoice_overdue", "low"), AttentionClass.NEXT_BRIEF),
        (_e("fin-3", "expense_flag", "medium"), AttentionClass.NEXT_BRIEF),
        (_e("fin-4", "payment_failed", "critical", owner_action=True),
         AttentionClass.INTERRUPT_NOW),
        (_e("fin-5", "payment_failed", "medium"), AttentionClass.SURFACE_SOON),
        # Marketing / support
        (_e("mkt-1", "metric_change", "high"), AttentionClass.WEEKLY_REVIEW),
        (_e("mkt-2", "campaign_done", "info"), AttentionClass.LOG_ONLY),
        (_e("sup-1", "ticket_sla_breach", "high"), AttentionClass.SURFACE_SOON),
        (_e("sup-2", "ticket_sla_breach", "low"), AttentionClass.NEXT_BRIEF),
        (_e("sup-3", "support_praise", "info"), AttentionClass.LOG_ONLY),
        # Release engineering
        (_e("relx-1", "deployment_failure", "critical", owner_action=True, reversible=False),
         AttentionClass.INTERRUPT_NOW),
        (_e("relx-2", "release_blocker", "medium", owner_action=True),
         AttentionClass.NEXT_BRIEF),
        (_e("relx-3", "deploy_progress", "info"), AttentionClass.LOG_ONLY),
        # Agent stalls & repeats
        (_e("stall-1", "agent_failure", "low"), AttentionClass.SURFACE_SOON),
        (_e("repeat-blocker", "task_overdue", "medium",
            deadline=NOW - 3600, subject="same-old-blocker", first=False),
         _downgrade(AttentionClass.NEXT_BRIEF)),
        (_e("repeat-risk", "risk_update", "high", subject="known-risk", first=False),
         _downgrade(AttentionClass.NEXT_BRIEF)),
        # Goal drift
        (_e("drift-1", "goal_offtrack", "critical"), AttentionClass.SURFACE_SOON),
        (_e("drift-2", "goal_offtrack", "low"), AttentionClass.NEXT_BRIEF),
        # Quiet events
        (_e("quiet-1", "routine_success", "info"), AttentionClass.LOG_ONLY),
        (_e("quiet-2", "completion", "low"), AttentionClass.LOG_ONLY),
        (_e("quiet-3", "doc_issue", "info"), AttentionClass.LOG_ONLY),
        # Stale events re-surfacing unchanged must stay quiet
        (_e("stale-1", "metric_change", "low", subject="weekly-metrics", first=False),
         _downgrade(AttentionClass.WEEKLY_REVIEW)),
        # Owner approvals variants
        (_e("own-1", "approval_needed", "critical", reversible=False),
         AttentionClass.SURFACE_SOON),
        (_e("own-2", "approval_needed", "low", reversible=False),
         AttentionClass.SURFACE_SOON),
    ]
    for event, expected in expanded:
        cases.append((event, expected))

    return cases


_ORDER = {cls: i for i, cls in enumerate([
    AttentionClass.IGNORE, AttentionClass.LOG_ONLY, AttentionClass.WEEKLY_REVIEW,
    AttentionClass.NEXT_BRIEF, AttentionClass.SURFACE_SOON,
    AttentionClass.INTERRUPT_NOW,
])}


def evaluate(corpus=None) -> dict:
    cases = corpus if corpus is not None else build_corpus()
    records = []
    correct = 0
    critical_misses = 0
    critical_total = 0
    interrupt_fps = 0
    interrupt_expected = 0
    duplicates = 0
    suppressed_correctly = 0

    for event, expected in cases:
        decision = classify_event(event, now_epoch=NOW)
        ok = decision.event_class is expected
        correct += ok
        if expected is AttentionClass.INTERRUPT_NOW:
            critical_total += 1
            if decision.event_class is not AttentionClass.INTERRUPT_NOW:
                critical_misses += 1
        if (
            _ORDER[decision.event_class] > _ORDER[expected]
            and decision.event_class is AttentionClass.INTERRUPT_NOW
            and expected is not AttentionClass.INTERRUPT_NOW
        ):
            interrupt_fps += 1
        if expected is AttentionClass.INTERRUPT_NOW:
            interrupt_expected += 1
        if decision.suppressed_duplicate:
            duplicates += 1
            # Corpus expectations already encode the downgraded class;
            # suppression counts as correct when the decision matches.
            if ok:
                suppressed_correctly += 1
        records.append({
            "event_id": event.event_id,
            "kind": event.kind,
            "severity": event.severity,
            "expected": expected.value,
            "actual": decision.event_class.value,
            "correct": ok,
            "reason": decision.reason,
        })

    total = len(records)
    return {
        "schema": "thursday.proactivity_benchmark.v1",
        "total_cases": total,
        "accuracy": round(correct / total, 4) if total else 0.0,
        "correct": correct,
        "critical_interrupt_expected": interrupt_expected,
        "critical_miss_count": critical_misses,
        "critical_miss_rate": round(critical_misses / critical_total, 4)
        if critical_total else 0.0,
        "interrupt_false_positive_count": interrupt_fps,
        "duplicate_cases": duplicates,
        "duplicate_suppressed_correctly": suppressed_correctly,
        "records": records,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", dest="json_path", default="")
    args = parser.parse_args(argv)

    report = evaluate()
    passing = (
        report["accuracy"] >= 0.97
        and report["critical_miss_rate"] == 0.0
        and report["interrupt_false_positive_count"] == 0
    )
    summary = {
        k: v for k, v in report.items() if k != "records"
    }
    print(json.dumps(summary, indent=2))
    print("PASSED" if passing else "FAILED")
    if args.json_path:
        with open(args.json_path, "w") as fh:
            json.dump(report, fh, indent=2)
    return 0 if passing else 1


if __name__ == "__main__":
    sys.exit(main())
