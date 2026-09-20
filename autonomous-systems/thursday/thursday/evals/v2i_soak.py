#!/usr/bin/env python3
"""Thursday V2-I long-horizon soak — 90 simulated days of persistent operation.

One evolving synthetic company, one persistent history: daily cycles with
seeded events (commits, regressions, blockers, priorities, dependency
landings, resource contention and injected crashes), continuous integrity
tracking, bounded-state verification and brief-quality monitoring.

This is persistent accumulating state — not a million stateless calls.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from thursday.event_injection import EventSchedule, seeded_events
from thursday.long_horizon_runner import LongHorizonRunner


def run_soak(days: int = 90, seed: int = 20260901,
             threshold: float = 0.3) -> dict:
    print(f"\nTHURSDAY V2-I SOAK: {days} simulated days (seed={seed}, "
          f"threshold={threshold})", flush=True)
    t0 = time.monotonic()

    r = LongHorizonRunner(seed=seed, auto_approve_threshold=threshold)
    # Seeded world evolution + ~2 crashes/week at varying phases.
    events = seeded_events(seed, days)
    for i, day in enumerate(range(3, days, 4)):
        events.append(__import__("thursday.event_injection", fromlist=["Event"]).Event(
            f"crash-{i}", day, "PROCESS_CRASH",
            {"phase": ["observe", "execute", "approval_wait",
                       "reconcile"][i % 4]},
            provenance=f"seeded:{seed}"))
    r.schedule = EventSchedule(events=events)

    totals = {
        "candidates_discovered": 0,
        "duplicate_requests_suppressed": 0,
        "proposals_made": 0,
        "integrations": 0,
        "failures_recorded": 0,
        "failure_escalations": 0,
        "approval_requests": 0,
        "approvals_batched": 0,
        "stale_authority_blocked": 0,
        "oscillations": 0,
        "crashes_injected": 0,
        "restarts_completed": 0,
        "brief_quality_failures": 0,
    }
    state_sizes: list[int] = []
    brief_sizes: list[int] = []

    for day in range(1, days + 1):
        res = r.run_day(day)
        totals["candidates_discovered"] += res.candidates_new
        totals["duplicate_requests_suppressed"] += res.requests_suppressed
        totals["proposals_made"] += res.proposals_made
        totals["integrations"] += res.integrations
        totals["rollbacks"] = totals.get("rollbacks", 0) + res.rollbacks
        totals["failures_recorded"] += res.failures_recorded
        totals["failure_escalations"] += res.escalations
        totals["approval_requests"] += res.approvals_requested
        totals["approvals_batched"] += res.approvals_batched
        totals["stale_authority_blocked"] += res.stale_authority_blocked
        totals["oscillations"] += res.oscillation_events
        totals["crashes_injected"] += res.crashes_injected
        totals["restarts_completed"] += res.restarts_completed
        if not res.brief_quality_pass:
            totals["brief_quality_failures"] += 1
        if day % 7 == 0 or day == days:
            blob = json.dumps({
                "history": r.history.to_state(),
                "truth": r.truth.to_state(),
            })
            state_sizes.append(len(blob.encode("utf-8")))
            brief_sizes.append(res.brief_lines)
        if day % 15 == 0:
            print(f"  day {day:>3}: integrations={totals['integrations']}, "
                  f"requests={totals['approval_requests']}, "
                  f"suppressed={totals['duplicate_requests_suppressed']}, "
                  f"crashes={totals['crashes_injected']}", flush=True)

    elapsed = time.monotonic() - t0
    ergo = r.tracker.metrics()
    integrity = r.integrity.as_dict()
    clean = all(v == 0 for v in integrity.values())

    growth_per_day = (
        (state_sizes[-1] - state_sizes[0]) / max(1, len(state_sizes) - 1))

    result = {
        "soak": "THURSDAY_V2I_SOAK",
        "seed": seed,
        "simulated_days": days,
        "elapsed_seconds": round(elapsed, 2),
        "cycles_total": sum(totals.values()),
        "counters": totals,
        "owner_ergonomics": ergo,
        "integrity_counters": integrity,
        "integrity_clean": clean,
        "state_growth": {
            "weekly_state_bytes": state_sizes,
            "bytes_at_start": state_sizes[0],
            "bytes_at_end": state_sizes[-1],
            "growth_bytes_per_day_of_window": round(growth_per_day, 1),
            "brief_lines_weekly_max": max(brief_sizes) if brief_sizes else 0,
        },
        "briefs_composed": len(r.briefs),
        "qualified": bool(clean and totals["brief_quality_failures"] == 0),
    }

    print(f"\n  Soak complete in {elapsed:.1f}s")
    print(f"  Integrations: {totals['integrations']}   "
          f"Failures: {totals['failures_recorded']}   "
          f"Escalations: {totals['failure_escalations']}")
    print(f"  Approval requests: {totals['approval_requests']}   "
          f"Suppressed duplicates: {totals['duplicate_requests_suppressed']}   "
          f"Batches: {totals['approvals_batched']}")
    print(f"  Crashes injected/recovered: "
          f"{totals['crashes_injected']}/{totals['restarts_completed']}")
    print(f"  Stale authority blocked: {totals['stale_authority_blocked']}")
    print(f"  Priority oscillations: {totals['oscillations']}")
    print(f"  State bytes first→last sample: {state_sizes[0]} → {state_sizes[-1]}")
    print(f"  Integrity clean: {clean}   Brief quality failures: "
          f"{totals['brief_quality_failures']}")
    return result


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=90)
    p.add_argument("--seed", type=int, default=20260901)
    p.add_argument("--threshold", type=float, default=0.3)
    p.add_argument("--out", default="")
    a = p.parse_args()
    result = run_soak(a.days, a.seed, a.threshold)
    if a.out:
        Path(a.out).write_text(json.dumps(result, indent=2) + "\n",
                               encoding="utf-8")
        print(f"\nSoak results written to {a.out}")
    sys.exit(0 if result["qualified"] else 1)
