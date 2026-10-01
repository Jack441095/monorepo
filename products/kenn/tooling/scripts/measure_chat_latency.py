#!/usr/bin/env python3
"""Measure the local brain's answer latency and how often its answer is actually used.

    measure_chat_latency.py [--limit 30] [--cases PATH] [--surface stream|payload] [--receipt PATH]

Stage 1's open item was blocked on recorded speed. The figures that block it were wrong, so this measures the real
ones: the median and p95 of accepted answers, and the rate plus top reason for rejection, by asking real knowledge
questions through KENN's own answer path against the local Ollama brain.

**Two surfaces, and the difference matters.** `stream` is `answer_payload_stream`, what `kenn.core.chat` and
`chat_cli` use. `payload` is the non-streaming `answer_payload` the browser companion calls. Both reach
`make_answer()` and both can have the model write the answer, but only when `should_use_llm_rewrite()` clears the
retrieval-confidence gate. Measured 1 Oct: on the streaming path the brain wrote 2 answers in 10; on the companion
path it wrote none, and the ~20 s spent there is `post_answer_critique()` grading KENN's own template. So a
companion-only measurement answers a different question than a streaming one, which is why the surface is a flag
rather than a detail.

**Why it captures the verdict in flight.** The grounding verdict is never persisted: `save_reasoning_trace` is
called without a metadata payload, so `generation_validation` -- which holds `attempted`, `accepted` and the warnings
-- exists only in the dict `_answer_payload_stream_raw` yields, and `answer_payload` does not return it. The accepted
rate cannot be read back from any store after the fact. That is a gap in its own right and it is why this script
exists rather than a log query.

**Run it with `KENN_LLM_CACHE=0`.** Two caches will otherwise serve a previous run's answer and report
`attempted=True` for a question no model ever saw. `KENN_LLM_CACHE` (on by default, 512 entries, 24 h TTL in
`llm_rewrite.py`) replays the model's response for an identical prompt; the semantic answer cache in
`session_memory` replays whole answer events. This script drops the semantic cache before every question, but it
cannot reach the response cache from here, so that one is the caller's job. Measured: with it on, all 10 questions
reported `attempted=True` at a 0.08 s median with no model call at all.

Read-only against Live, and it never writes to one: `answer_payload` only reads the session snapshot.

Needs the knowledge index. `apps/backend/src/kenn/data/` is git-ignored, so run this from the main checkout -- in a
fresh worktree retrieval silently drops to BM25-only and every answer abstains.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

KENN_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KENN_ROOT / "apps" / "backend" / "src"))

DEFAULT_CASES = KENN_ROOT / "apps" / "backend" / "src" / "kenn" / "evals" / "questions.json"


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return ordered[index]


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _drop_semantic_cache() -> None:
    """Empty every tier of the semantic answer cache so each question really goes to the model."""
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


def _install_capture(path: Path) -> None:
    """Record every candidate answer so a rejection can be re-scored offline.

    The payload cannot supply this: when the grounding gate rejects the brain's answer, the streaming
    path swaps in the template and reports that as the answer, so the rejected text is gone before
    metadata is built. generated_answer_validation is the last place it exists, and reading it out of a
    wrapper is how the dominant rejection was originally identified. Point --capture-answers at a
    git-ignored path: this holds the model's prose, which the receipt itself must never carry.
    """
    from kenn.core import chat_answer
    from kenn.core.chat_retrieval import display_results

    path.parent.mkdir(parents=True, exist_ok=True)
    real = chat_answer.generated_answer_validation

    def capture(query, results, answer, **kwargs):
        validation = real(query, results, answer, **kwargs)
        evidence = " ".join(
            " ".join((str(c.get("title") or ""), str(c.get("source") or ""), str(c.get("text") or "")))
            for _score, c in display_results(query, results, 3)
        )
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "question": query,
                "answer": answer,
                "accepted": bool(validation["accepted"]),
                "warnings": [str(w) for w in validation.get("warnings") or []],
                "unsupported_measurements": list(validation.get("unsupported_measurements") or []),
                "fabricated_sources": list(validation.get("fabricated_sources") or []),
                "evidence_text": evidence,
                "additional_evidence_text": kwargs.get("additional_evidence_text") or "",
                "timeline_context": kwargs.get("timeline_context") or "",
            }) + "\n")
        return validation

    chat_answer.generated_answer_validation = capture


def _ask(chat_answer, question: str, *, allow_llm: bool, surface: str) -> tuple[dict, int]:
    """Return the final metadata dict and how many token events the answer took to arrive."""
    if surface == "stream":
        final: dict = {}
        tokens = 0
        for event in chat_answer.answer_payload_stream(
            question, session_id=f"latency-{uuid.uuid4().hex[:12]}", allow_llm=allow_llm
        ):
            if event.get("event") == "token":
                tokens += 1
            elif event.get("event") == "metadata":
                final = event.get("data") or {}
        return final, tokens
    return chat_answer.answer_payload(
        question, session_id=f"latency-{uuid.uuid4().hex[:12]}", allow_llm=allow_llm
    ), 0


def measure(cases: list[dict], *, allow_llm: bool = True, surface: str = "stream") -> dict:
    from kenn.core import chat_answer

    rows: list[dict] = []
    for case in cases:
        question = str(case.get("question") or "").strip()
        if not question:
            continue
        # The semantic answer cache will otherwise serve a previous run's answer for an identical question, which
        # makes a rerun look like a 0.1 s answer that never called the model. Measured: three questions took
        # 57/54/73 s on the first pass and 0.1/0.1/1.5 s on the second, with "never attempted" nowhere in sight.
        _drop_semantic_cache()
        started = time.perf_counter()
        try:
            payload, tokens = _ask(chat_answer, question, allow_llm=allow_llm, surface=surface)
            error = None
        except Exception as exc:  # a failure is a measurement, not a crash
            payload, error, tokens = {}, f"{type(exc).__name__}: {exc}", 0
        seconds = time.perf_counter() - started
        validation = dict(payload.get("generation_validation") or {})
        rows.append({
            "id": str(case.get("id") or "unknown"),
            "category": str(case.get("category") or "uncategorized"),
            "seconds": round(seconds, 3),
            "stream_events": tokens,
            "cache_dropped": True,
            "surface": surface,
            "attempted": bool(validation.get("attempted")),
            "accepted": bool(validation.get("accepted")),
            "warnings": [str(w) for w in (validation.get("warnings") or [])],
            # The warning names the class of fault but not the value, so a measure built on these receipts could
            # count rejections without saying which measurement or citation was at fault. Both are regex-extracted.
            "unsupported_measurements": [str(m) for m in (validation.get("unsupported_measurements") or [])],
            "fabricated_sources": [str(s) for s in (validation.get("fabricated_sources") or [])],
            "llm_enhanced": bool(payload.get("llm_enhanced")),
            "found": bool(payload.get("found")),
            "sources": len(payload.get("sources") or []),
            "error": error,
        })

    attempted = [r for r in rows if r["attempted"]]
    accepted = [r for r in rows if r["accepted"]]
    rejected = [r for r in attempted if not r["accepted"]]
    reasons = Counter(w for r in rejected for w in r["warnings"])
    top_reason, top_count = reasons.most_common(1)[0] if reasons else ("", 0)
    return {
        "schema": "kenn.chat_latency.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": os.environ.get("KENN_LLM_MODEL", ""),
        "index_version": (KENN_ROOT / "apps/backend/src/kenn/data/index/CURRENT").read_text(
            encoding="utf-8").strip() if (KENN_ROOT / "apps/backend/src/kenn/data/index/CURRENT").is_file() else "",
        "counts": {
            "asked": len(rows),
            "llm_attempted": len(attempted),
            "llm_accepted": len(accepted),
            "llm_rejected": len(rejected),
            "errors": sum(1 for r in rows if r["error"]),
        },
        "seconds": {
            "all_median": _median([r["seconds"] for r in rows]),
            "all_p95": _percentile([r["seconds"] for r in rows], 0.95),
            "attempted_median": _median([r["seconds"] for r in attempted]),
            "accepted_median": _median([r["seconds"] for r in accepted]),
            "accepted_p95": _percentile([r["seconds"] for r in accepted], 0.95),
        },
        "top_rejection_reason": {"reason": top_reason, "answers": top_count},
        "rows": rows,
    }


def surface_of(report: dict) -> str:
    """Which answer surface a report describes, read off the rows rather than a top-level field.

    The surface is recorded per question, so a receipt stays readable even if the summary block
    is trimmed, and a receipt that somehow mixed surfaces would show as "mixed" rather than
    quietly reporting one of them.
    """
    if report.get("surface"):
        return str(report["surface"])
    seen = {str(row.get("surface")) for row in report.get("rows") or []}
    return seen.pop() if len(seen) == 1 else "mixed"


def render(report: dict) -> str:
    counts, seconds = report["counts"], report["seconds"]
    attempted = counts["llm_attempted"]
    lines = [
        "Chat answer latency, local brain (Stage 1 open item; gate is p95 <= 4 s)",
        f"  model              {report['model'] or '(unset)'}",
        f"  surface            {surface_of(report)}",
        f"  index              {report['index_version'] or '(none in this checkout)'}",
        f"  asked              {counts['asked']}",
        f"  brain attempted    {attempted}",
        f"  brain accepted     {counts['llm_accepted']}"
        + (f"  ({100 * counts['llm_accepted'] / attempted:.0f}% of attempts)" if attempted else ""),
        f"  brain rejected     {counts['llm_rejected']}",
        f"  errors             {counts['errors']}",
        f"  all answers        median {seconds['all_median']}s   p95 {seconds['all_p95']}s",
    ]
    if attempted:
        lines.append(f"  attempted only     median {seconds['attempted_median']}s")
    lines.append(
        f"  accepted only      median {seconds['accepted_median']}s   p95 {seconds['accepted_p95']}s"
        if counts["llm_accepted"] else "  accepted only      (no answer was accepted)"
    )
    top = report["top_rejection_reason"]
    lines.append(f"  top rejection      {top['reason']!r} on {top['answers']} answers"
                 if top["reason"] else "  top rejection      none recorded")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--templates-only", action="store_true", help="skip the model, for the floor")
    parser.add_argument("--surface", choices=("stream", "payload"), default="stream",
                        help="stream = kenn.core.chat / chat_cli; payload = the browser companion's non-streaming call")
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--capture-answers", type=Path, metavar="PATH",
                        help="append every candidate answer to PATH as JSONL, including rejected ones, so a "
                             "gate can be re-scored offline. Must be git-ignored: it holds model prose.")
    args = parser.parse_args()

    if not args.cases.is_file():
        print(f"No cases at {args.cases}", file=sys.stderr)
        return 1
    current = KENN_ROOT / "apps/backend/src/kenn/data/index/CURRENT"
    if not current.is_file():
        print("chat-latency=NOT_MEASURED no retrieval index in this checkout", file=sys.stderr)
        print("apps/backend/src/kenn/data/ is git-ignored, so a fresh worktree has none and every answer would "
              "abstain. Run from the main checkout.", file=sys.stderr)
        return 2

    cases = json.loads(args.cases.read_text(encoding="utf-8")).get("cases", [])[: args.limit]
    if args.capture_answers:
        _install_capture(args.capture_answers)
    report = measure(cases, allow_llm=not args.templates_only, surface=args.surface)
    print(render(report))
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
        print(f"receipt written to {args.receipt}")
    return 1 if report["counts"]["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())