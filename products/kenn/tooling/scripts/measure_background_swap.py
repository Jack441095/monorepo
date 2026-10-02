#!/usr/bin/env python3
"""Measure isolated sequential background answers using the ask route's engine calls.

    measure_background_swap.py [--limit 30] [--cases PATH] [--receipt PATH]

This measures template timing, accepted upgrades and generation time for
KENN_PLAN.md. It does not qualify the HTTP/UI path or concurrent conversation.
The template and background generation share a chat identifier; only the
template records the question in memory.

Three numbers come out, and they answer different questions:

- **Template latency** -- what the producer waits for before anything is on screen. This is the number that has to be
  under 4 s, because it is the only one on the critical path of seeing an answer at all.
- **Swap rate** -- how often the model's answer is actually offered. `answer_upgrades` accepts only what KENN would
  have shown anyway (`llm_enhanced`), so this is the honest "does the brain's answer land" measure, not a count of
  generations.
- **Time to land** -- `accepted_p50_s`/`accepted_p95_s`, which is also what `route_latency_report.py` reads back out of
  the `answer_upgrade:*` route-log rows this writes. Both numbers are reported here and from that report, and they are
  computed from the same events, not from two different runs.

`answer_upgrades` permits one generation at a time. This benchmark asks the next
question after the previous upgrade settles. It cannot establish performance for
a producer who asks again while generation is busy.

Read-only against Live and it never writes to one: `answer_payload` with `allow_llm=False` reads the session snapshot
and nothing else, and the background call writes no more than the first.

Needs the knowledge index. `apps/backend/src/kenn/data/` is git-ignored, so run this from the main checkout -- in a
fresh worktree retrieval drops to BM25-only and every answer abstains.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

KENN_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KENN_ROOT / "apps" / "backend" / "src"))

DEFAULT_CASES = KENN_ROOT / "apps" / "backend" / "src" / "kenn" / "evals" / "questions.json"
CURRENT = KENN_ROOT / "apps" / "backend" / "src" / "kenn" / "data" / "index" / "CURRENT"

# The ask route hands the app 2000 ms to wait before its first poll, so a swap that "lands immediately" still costs the
# producer one poll interval. Reporting time-to-land without it would flatter the result by two seconds.
POLL_MS = 2000


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))]


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _drop_semantic_cache() -> None:
    """Empty every tier of the semantic answer cache so a rerun really re-asks the model."""
    from kenn.core import session_memory

    with session_memory._L1_LOCK:
        session_memory._L1_EXACT_CACHE.clear()
        session_memory._L2_MATRIX = None
        session_memory._L2_QUERIES.clear()
        session_memory._L2_SESSION_IDS.clear()
        session_memory._L2_VERSIONS.clear()
        session_memory._L2_EVENTS.clear()
        session_memory._L2_TIMESTAMPS.clear()
    try:
        conn = session_memory._get_db()
        conn.execute("DELETE FROM semantic_cache")
        conn.commit()
    except Exception:
        pass


def measure(cases: list[dict], *, allow_llm: bool = True, timeout_s: float = 300.0) -> dict:
    """Ask each question the way the ask route does, and wait for its swap to settle."""
    from kenn.core import answer_upgrades
    from kenn.core.chat_answer import answer_payload

    rows: list[dict] = []
    for case in cases:
        question = str(case.get("question") or "").strip()
        if not question:
            continue
        _drop_semantic_cache()
        session_id = f"swap-{uuid.uuid4().hex[:12]}"
        upgrade_turn = answer_upgrades.begin_turn(session_id)

        # First half of the ask route: the template the producer sees immediately, model off.
        template_started = time.perf_counter()
        try:
            template = answer_payload(question, session_id=session_id, allow_llm=False)
            template_error = None
        except Exception as exc:  # a failure is a measurement, not a crash
            template, template_error = {}, f"{type(exc).__name__}: {exc}"
        template_seconds = time.perf_counter() - template_started

        # Second half: the same question again with the model on, in the background.
        swap_seconds: float | None = None
        upgrade_id = None
        status = "not_started"
        error = template_error
        if allow_llm and not template_error and template.get("llm_available") and not template.get("proposal"):
            upgrade_id = answer_upgrades.start(
                lambda: answer_payload(question, history=[], session_id=session_id, record_session=False),
                session_id=session_id, turn_id=upgrade_turn,
            )
            if upgrade_id is None:
                # Admission is counted by start(); logging here would double-count
                # the same busy attempt in the landing-rate denominator.
                status = "busy"
            else:
                started = time.perf_counter()
                while time.perf_counter() - started < timeout_s:
                    settled = answer_upgrades.get(upgrade_id, session_id=session_id)
                    if settled.get("status") in {"accepted", "rejected", "expired"}:
                        status = str(settled["status"])
                        swap_seconds = time.perf_counter() - started
                        break
                    time.sleep(0.5)
                else:
                    status = "timeout"
                    error = f"swap did not settle within {timeout_s:.0f}s"

        rows.append({
            "id": str(case.get("id") or "unknown"),
            "category": str(case.get("category") or "uncategorized"),
            "template_seconds": round(template_seconds, 3),
            "template_found": bool(template.get("found")),
            "swap_status": status,
            "swap_seconds": round(swap_seconds, 3) if swap_seconds is not None else None,
            # What the producer actually waits for before the screen can change: the template, plus one poll interval
            # before the app looks, plus the write if it landed.
            "answer_visible_seconds": round(template_seconds + (swap_seconds if status == "accepted" else 0.0), 3),
            "upgrade_id": upgrade_id,
            "error": error,
        })

    started_rows = [r for r in rows if r["swap_status"] != "not_started"]
    accepted = [r for r in started_rows if r["swap_status"] == "accepted"]
    template_seconds = [r["template_seconds"] for r in rows]
    return {
        "schema": "kenn.background_swap.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": os.environ.get("KENN_LLM_MODEL", ""),
        "background": os.environ.get("KENN_LLM_BACKGROUND", "") or "(unset)",
        "poll_ms": POLL_MS,
        "index_version": CURRENT.read_text(encoding="utf-8").strip() if CURRENT.is_file() else "",
        "counts": {
            "asked": len(rows),
            "swaps_started": len(started_rows) - sum(1 for r in started_rows if r["swap_status"] == "busy"),
            "swaps_accepted": len(accepted),
            "swaps_rejected": sum(1 for r in started_rows if r["swap_status"] == "rejected"),
            "swaps_busy": sum(1 for r in started_rows if r["swap_status"] == "busy"),
            "swaps_timeout": sum(1 for r in started_rows if r["swap_status"] == "timeout"),
            "errors": sum(1 for r in rows if r["error"]),
        },
        "seconds": {
            "template_p50": _median(template_seconds),
            "template_p95": _percentile(template_seconds, 0.95),
            "swap_p50": _median([r["swap_seconds"] for r in accepted]),
            "swap_p95": _percentile([r["swap_seconds"] for r in accepted], 0.95),
            "visible_p50": _median([r["answer_visible_seconds"] for r in rows]),
            "visible_p95": _percentile([r["answer_visible_seconds"] for r in rows], 0.95),
        },
        "rows": rows,
    }


def render(report: dict) -> str:
    counts, seconds = report["counts"], report["seconds"]
    started = counts["swaps_started"]
    lines = [
        "Background swap on the M3 (template now, model's answer when it lands)",
        f"  model              {report['model'] or '(unset)'}",
        f"  KENN_LLM_BACKGROUND {report['background']}",
        f"  index              {report['index_version'] or '(none in this checkout)'}",
        f"  asked              {counts['asked']}",
        f"  swaps started      {started}",
        f"  swap accepted      {counts['swaps_accepted']}"
        + (f"  ({counts['swaps_accepted'] / started:.0%} of swaps)" if started else ""),
        f"  swap rejected      {counts['swaps_rejected']}",
        f"  busy (model still writing the last one)  {counts['swaps_busy']}",
    ]
    if counts["swaps_timeout"]:
        lines.append(f"  TIMED OUT          {counts['swaps_timeout']}")
    lines.append(
        f"  template shown     p50 {seconds['template_p50']}s   p95 {seconds['template_p95']}s"
    )
    if counts["swaps_accepted"]:
        landed = counts["swaps_accepted"] / counts["asked"]
        lines.append(f"  swap landed        p50 {seconds['swap_p50']}s   p95 {seconds['swap_p95']}s")
        lines.append(f"  swap rate vs asked  {landed:.0%}  (every question is asked; not all reach the model)")
    else:
        lines.append("  swap landed        (no answer was accepted)")
    lines.append(f"  answer on screen   p50 {seconds['visible_p50']}s   p95 {seconds['visible_p95']}s")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--templates-only", action="store_true",
                        help="measure the template half only, for the floor")
    parser.add_argument("--timeout", type=float, default=300.0, help="give up on a swap after this many seconds")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()

    if not args.cases.is_file():
        print(f"No cases at {args.cases}", file=sys.stderr)
        return 1
    if not CURRENT.is_file():
        print("background-swap=NOT_MEASURED no retrieval index in this checkout", file=sys.stderr)
        print("apps/backend/src/kenn/data/ is git-ignored, so a fresh worktree has none and every answer would "
              "abstain. Run from the main checkout.", file=sys.stderr)
        return 2

    # The script is the measurement, not the product: it sets the flag the ask route reads rather than requiring the
    # caller to remember it, because a run with the flag off silently measures nothing but templates.
    if not args.templates_only:
        os.environ["KENN_LLM_BACKGROUND"] = "1"

    cases = json.loads(args.cases.read_text(encoding="utf-8")).get("cases", [])[: args.limit]
    report = measure(cases, allow_llm=not args.templates_only, timeout_s=args.timeout)
    print(render(report))
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
        print(f"receipt written to {args.receipt}")
    return 1 if report["counts"]["errors"] or report["counts"]["swaps_timeout"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
