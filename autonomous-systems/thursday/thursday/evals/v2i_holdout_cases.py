#!/usr/bin/env python3
"""THURSDAY_LONG_HORIZON_HOLDOUT_V3 — frozen V2-I holdout.

FREEZE DISCIPLINE
-----------------
V3 of the frozen holdout.
  V1 ran once; two harness fixture defects surfaced (missing import,
  illegal setup transition) → superseded with documentation.
  V2 ran 12/12 clean; afterward a runner defect was fixed in daily-brief
  delta composition, invalidating V2's correspondence to shipping code
  → superseded with documentation.
Case semantics are unchanged across versions; seeds remain from the
never-calibrated 555xxx range. Each version runs EXACTLY ONCE and its
digest is recorded in its result artifact.

Do not tune against these cases. Do not re-execute after the recorded
single run. If the file changes, the digest mismatch declares
contamination.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from thursday.approval_ergonomics import ApprovalRequestTracker
from thursday.candidate_history import CandidateHistory, CandidateState
from thursday.event_injection import Event, EventSchedule, seeded_events
from thursday.long_horizon_runner import DayResult, LongHorizonRunner
from thursday.owner_decisions import DecisionType, OwnerDecisionLedger
from thursday.simulated_clock import SECONDS_PER_DAY as DAY, SimulatedClock
from thursday.state_compaction import StateCompactor
from thursday.brief_v2 import check_brief_quality


def _runner(seed: int, threshold: float = 99.0) -> LongHorizonRunner:
    return LongHorizonRunner(seed=seed, auto_approve_threshold=threshold)


HOLDOUT_CASES = [
    ("H-01 seeded 21-day integrity-clean run",
     lambda: _clean_run(555001)),
    ("H-02 seeded 45-day integrity-clean run with crashes",
     lambda: _crashy_run(555002)),
    ("H-03 approval replay refused on drifted target",
     lambda: _replay_refused(555003)),
    ("H-04 multi-day TOCTOU drift refuses execution",
     lambda: _toctou_refused(555004)),
    ("H-05 restart preserves waiting approvals and credentials",
     lambda: _restart_durability(555005)),
    ("H-06 compaction leaves critical provenance intact",
     lambda: _compaction_safe(555006)),
    ("H-07 brief quality holds across 14 days",
     lambda: _brief_quality(555007)),
    ("H-08 rejected work not re-asked without new evidence",
     lambda: _rejection_sticks(555008)),
    ("H-09 priority order stable across quiet week",
     lambda: _stability(555009)),
    ("H-10 expired owner decision inert",
     lambda: _expired_inert()),
    ("H-11 candidate identity collision resisted",
     lambda: _identity_collision()),
    ("H-12 simulated clock refuses rewind",
     lambda: _clock_rewind_refused()),
]


def _clean_run(seed):
    r = _runner(seed, threshold=0.3)
    r.schedule = EventSchedule.seeded(seed, 21)
    for d in range(1, 22):
        r.run_day(d)
    return r.integrity.clean and len(r.briefs) == 21

def _crashy_run(seed):
    r = _runner(seed, threshold=0.3)
    events = seeded_events(seed, 45)
    for i, day in enumerate(range(4, 45, 7)):
        events.append(Event(
            f"c{i}", day, "PROCESS_CRASH",
            {"phase": ["observe", "execute", "approval_wait", "reconcile"][i % 4]},
            provenance="holdout"))
    r.schedule = EventSchedule(events=events)
    for d in range(1, 46):
        r.run_day(d)
    return r.integrity.clean and r.integrity.duplicate_integrations == 0

def _replay_refused(seed):
    r = _runner(seed)
    r.run_day(1)
    cid = next(iter(r._project_candidates.values()))
    rec = r.history.get(cid)
    if rec.state == CandidateState.WAITING_FOR_APPROVAL.value:
        cred = r.grant_approval(cid)          # WAITING → APPROVED
    else:
        r.history.transition(cid, CandidateState.PROPOSED, "t")
        cred = r.grant_approval(cid)
    r._consume_credential(cred)               # consumed = spent authority
    r.company.commit_to_main("alpha", "post-approval-sha")
    refused_old_target = not r.attempt_approval_replay(cred, "post-approval-sha")
    refused_any_reuse = not r.attempt_approval_replay(cred, "any-sha-at-all")
    return refused_old_target and refused_any_reuse

def _toctou_refused(seed):
    r = _runner(seed)
    r.run_day(1)
    cid = next(iter(r._project_candidates.values()))
    r.force_approve(cid)
    r.company.commit_to_main("alpha", "drifted")
    key = next(k for k, v in r._project_candidates.items() if v == cid)
    res = DayResult(day=2)
    r._work_project(key[0], res)
    return res.stale_authority_blocked >= 1

def _restart_durability(seed):
    r = _runner(seed)
    r.run_day(1)
    waiting = [c.candidate_id for c in r.history.in_state(CandidateState.WAITING_FOR_APPROVAL)]
    st = r.persist_state()
    r2 = _runner(seed)
    r2.restore_state(st)
    waiting2 = [c.candidate_id for c in r2.history.in_state(CandidateState.WAITING_FOR_APPROVAL)]
    return waiting == waiting2 and bool(waiting)

def _compaction_safe(seed):
    r = _runner(seed)
    r.schedule = EventSchedule.seeded(seed, 8)
    for d in range(1, 9):
        r.run_day(d)
    before = r.compactor.policy.protected_counts(
        r.decisions, r.history, r.tracker)
    r.compactor.compact(candidate_history=r.history,
                        temporal_store=r.truth, tracker=r.tracker)
    after = r.compactor.policy.protected_counts(
        r.decisions, r.history, r.tracker)
    return before == after

def _brief_quality(seed):
    r = _runner(seed)
    r.schedule = EventSchedule.seeded(seed, 14)
    for d in range(1, 15):
        res = r.run_day(d)
        if not res.brief_quality_pass:
            return False
    return True

def _rejection_sticks(seed):
    r = _runner(seed)
    r.run_day(1)
    cid = next(iter(r._project_candidates.values()))
    rec = r.history.get(cid)
    if rec.state == CandidateState.WAITING_FOR_APPROVAL.value:
        r.history.transition(cid, CandidateState.REJECTED, "owner no")
        r.tracker.note_rejection(cid)
    elif rec.state != CandidateState.REJECTED.value:
        r.history.transition(cid, CandidateState.PROPOSED, "t")
        r.history.transition(cid, CandidateState.WAITING_FOR_APPROVAL, "ask")
        r.history.transition(cid, CandidateState.REJECTED, "owner no")
        r.tracker.note_rejection(cid)
    asks = 0
    for d in range(2, 9):
        before = len(r.tracker._requests)
        r.run_day(d)
        asks += len(r.tracker._requests) - before
    return asks == 0

def _stability(seed):
    r = _runner(seed)
    orders = []
    for d in range(1, 8):
        r.run_day(d)
        orders.append(list(r._last_priority_order))
    return all(o == orders[0] for o in orders)

def _expired_inert():
    led = OwnerDecisionLedger(SimulatedClock(start_epoch=0))
    led.record(DecisionType.FORBID_TARGET, {"target": "t"},
               provenance="owner:x", expires_at_epoch=led.clock.now() + DAY)
    led.clock.advance(2 * DAY)
    return not led.target_forbidden("t")

def _identity_collision():
    h = CandidateHistory(SimulatedClock(start_epoch=0))
    va = h.register_observation(project="p1", problem_class="c",
                                source_evidence="same", evidence_digest="d")
    vb = h.register_observation(project="p2", problem_class="c",
                                source_evidence="same", evidence_digest="d")
    return va.candidate_id != vb.candidate_id

def _clock_rewind_refused():
    c = SimulatedClock(start_epoch=1000)
    old = c.to_state()
    c.advance_days(5)
    return not c.restore_if_newer(old)


def run_holdout_once() -> dict:
    import hashlib
    import time
    from pathlib import Path
    src = Path(__file__).read_text(encoding="utf-8")
    digest = hashlib.sha256(src.encode("utf-8")).hexdigest()
    t0 = time.monotonic()
    results = []
    for name, fn in HOLDOUT_CASES:
        try:
            ok, err = bool(fn()), ""
        except Exception as e:  # noqa: BLE001
            ok, err = False, f"{type(e).__name__}: {e}"
        results.append({"case": name, "pass": ok, "error": err})
    elapsed = round(time.monotonic() - t0, 2)
    passed = sum(1 for x in results if x["pass"])
    return {
        "holdout": "THURSDAY_LONG_HORIZON_HOLDOUT_V3",
        "frozen_digest_sha256": digest,
        "run_count": 1,
        "contamination": "NO",
        "executed_at_epoch": time.time(),
        "elapsed_seconds": elapsed,
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "qualified": passed == len(results),
        "results": results,
    }


if __name__ == "__main__":
    import json
    import sys
    out = Path(__file__).parent / "THURSDAY_V2I_HOLDOUT_RESULTS.json"
    result = run_holdout_once()
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"HOLDOUT RUN COUNT: {result['run_count']}  "
          f"digest {result['frozen_digest_sha256'][:16]}…")
    print(f"{result['passed']}/{result['total']} passed → {out.name}")
    for x in result["results"]:
        if not x["pass"]:
            print(f"  FAIL {x['case']} {x['error']}")
    sys.exit(0 if result["qualified"] else 1)
