#!/usr/bin/env python3
"""Capture route-specific answer delivery, provenance and model-gate outcomes.

Local stream/payload and foreground/background HTTP runs stay separate. Missing
native phases, displayed-answer timing, memory pressure and build identities are
reported as unknown. Cache conditions record what this caller can actually clear;
an HTTP caller cannot establish the server's cache state.

Use stubs while inference work is active. Real-model runs require the finished
build and its existing local index; this script never builds an index or writes
to Live. Offline review consumes the saved capture without rerunning inference.
"""

from __future__ import annotations

import argparse
import hashlib
import platform
import subprocess
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


def _index_version() -> str:
    """Whatever retrieval index this checkout points at, read fresh.

    Read per answer rather than once for the run: an index rebuild midway through a 30-question capture is
    exactly the drift that makes the recorded evidence unreplayable, and a single run-level stamp would
    report one version for rows that never saw it.
    """
    pointer = KENN_ROOT / "apps/backend/src/kenn/data/index/CURRENT"
    return pointer.read_text(encoding="utf-8").strip() if pointer.is_file() else ""


def gate_evidence(results: list[tuple[float, dict]]) -> tuple[str, list[tuple[float, dict, str]]]:
    """The evidence the grounding gate reads for these results, taken from the list both sides share.

    This used to render the captured field from display_results(query, results, 3) and chunk["text"], which
    stopped being what the gate reads when the evidence rework landed on 2 Oct 2026. 14 of the 22 rows in that
    day's capture disagreed, and an offline leak check run against the field reported 8 of 18 accepted answers
    citing a measurement the gate had in front of it; against the gate's own evidence the same check reported
    0 of 18. Use model_evidence() and the gate's resolved budget so overrides change the captured excerpts too.
    """
    from kenn.core.chat_retrieval import source_label
    from kenn.llm.llm_rewrite import model_evidence, resolve_context_chars

    return model_evidence(results, source_label, max_chars=resolve_context_chars())


def gate_evidence_text(shown: list[tuple[float, dict, str]]) -> str:
    """The gate's evidence string for a list of (score, chunk, body): title, source and the body as shown.

    Title and source rather than source_label() because that is the triple generated_answer_validation joins.
    The label reaches the model inside the <source_excerpt label="..."> attribute rather than as excerpt text,
    so putting it here would vouch for words the gate never counts.
    """
    return " ".join(
        " ".join((str(chunk.get("title") or ""), str(chunk.get("source") or ""), body))
        for _score, chunk, body in shown
    )


# Set by _install_capture. The gate is not reached on every answer -- chat_answer.py:1731 empties the
# candidate when the streaming prefix guard trips, so generated_answer_validation never runs for exactly the
# unsupported-measurement rejections that dominated 8 of 9 rejections on 2 Oct 2026. A capture built only
# from inside the gate therefore omits the failure the phase exists to measure: the 2 Oct 2026 abstain run
# wrote 14 of 28 attempted answers, biased toward the ones that did not fabricate.
_CAPTURE_PATH: Path | None = None
# Set by the capture wrapper on every call. A flag rather than a set of questions, because the gate is handed
# relevance_query and the harness holds the original question, and those two are not always the same string.
_CAPTURE_HIT = False
_LAST_CAPTURE_ROW: dict | None = None
_CAPTURE_CASE_ID: str | None = None


def _write_capture_row(row: dict) -> None:
    global _LAST_CAPTURE_ROW
    _LAST_CAPTURE_ROW = {**row, "case_id": _CAPTURE_CASE_ID}
    if _CAPTURE_PATH is None:
        return
    with _CAPTURE_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_LAST_CAPTURE_ROW) + "\n")


def _install_capture(path: Path | None) -> None:
    """Record every candidate answer so a rejection can be re-scored offline.

    The payload cannot supply this: when the grounding gate rejects the brain's answer, the streaming
    path swaps in the template and reports that as the answer, so the rejected text is gone before
    metadata is built. generated_answer_validation is the last place it exists, and reading it out of a
    wrapper is how the dominant rejection was originally identified. Point --capture-answers at a
    git-ignored path: this holds the model's prose, which the receipt itself must never carry.

    Each row carries the index version and the evidence budget it was written under, because a row cannot be
    checked against today's gate unless someone can tell what today's gate looked like when the row was made.
    The 22-row capture from 2 Oct 2026 recorded neither, which is why its acceptance figures needed re-measuring
    before anyone could quote them.
    """
    from kenn.core import chat_answer
    from kenn.core.chat_retrieval import source_label
    from kenn.knowledge.reasoning import get_chunk_id
    from kenn.llm.llm_rewrite import resolve_context_chars

    global _CAPTURE_PATH, _CAPTURE_HIT
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
    _CAPTURE_PATH = path
    _CAPTURE_HIT = False
    real = chat_answer.generated_answer_validation

    def capture(query, results, answer, **kwargs):
        global _CAPTURE_HIT
        _CAPTURE_HIT = True
        validation = real(query, results, answer, **kwargs)
        block, shown = gate_evidence(results)
        _write_capture_row({
                "question": query,
                # The question as typed by the producer this turn, before history expansion.
                # The live gate takes accepted figures from this, not the expanded search query.
                "typed_question": str(kwargs.get("question") or ""),
                "answer": answer,
                "accepted": bool(validation["accepted"]),
                "warnings": [str(w) for w in validation.get("warnings") or []],
                "unsupported_measurements": list(validation.get("unsupported_measurements") or []),
                "fabricated_sources": list(validation.get("fabricated_sources") or []),
                "evidence_text": gate_evidence_text(shown),
                # Per-source snapshots let an independent reviewer check citation truth without
                # consulting today's index or treating the production verdict as a gold label.
                "evidence_sources": [
                    {"id": get_chunk_id(chunk), "label": source_label(chunk),
                     "title": str(chunk.get("title") or ""),
                     "source": str(chunk.get("source") or ""), "text": body}
                    for _score, chunk, body in shown
                ],
                "prompt_evidence": block,
                "evidence_chunks_shown": len(shown),
                "gate_ran": True,
                "candidate_text_available": True,
                # Both readers now resolve the budget through resolve_context_chars(), so the two numbers
                # cannot diverge. They were separate fields because the gate used to ignore
                # KENN_LLM_CONTEXT_CHARS and read model_evidence()'s 1200 default while the prompt honoured
                # the override: at 300 the model saw 1 excerpt and the gate judged 3, the same defect that
                # took acceptance 41% -> 27% on 2 Oct 2026. Kept as two fields because a future split would
                # show up here as two different values rather than needing a new field to detect it.
                "evidence_budget_chars": int(resolve_context_chars()),
                "prompt_context_chars": int(resolve_context_chars()),
                "index_version": _index_version(),
                "additional_evidence_text": kwargs.get("additional_evidence_text") or "",
                "timeline_context": kwargs.get("timeline_context") or "",
                # Phase 7's own outputs. Without these a capture records only whether the gate cleared the
                # answer, which on a must-abstain item cannot tell an honest abstention from a confident
                # fabrication -- the two are different failures and only one of them is the gate's target.
                "abstained": bool(validation.get("abstained")),
                "abstain_gap": str(validation.get("abstain_gap") or ""),
                "claim_citations": validation.get("claim_citations") or {},
        })
        return validation

    chat_answer.generated_answer_validation = capture


def _ask(chat_answer, question: str, *, allow_llm: bool, surface: str) -> tuple[dict, int, float | None]:
    """Return the final metadata dict, how many token events arrived, and seconds to the first one.

    The third value is what Phase 2 exists to move. Before it, the consumer was handed every token only after
    generation and validation had both finished, so time-to-first-token equalled the whole answer and no
    complete-answer figure could say whether streaming had helped.
    """
    if surface == "stream":
        final: dict = {}
        tokens = 0
        started = time.perf_counter()
        ttft: float | None = None
        for event in chat_answer.answer_payload_stream(
            question, session_id=f"latency-{uuid.uuid4().hex[:12]}", allow_llm=allow_llm
        ):
            if event.get("event") == "token":
                tokens += 1
                if ttft is None:
                    ttft = time.perf_counter() - started
            elif event.get("event") == "metadata":
                final = event.get("data") or {}
        return final, tokens, ttft
    return chat_answer.answer_payload(
        question, session_id=f"latency-{uuid.uuid4().hex[:12]}", allow_llm=allow_llm
    ), 0, None


def run_provenance(manifest: dict | None = None) -> dict:
    """Identify this checkout; externally measured model, corpus and hardware fields stay unknown."""
    def git(*arguments):
        result = subprocess.run(["git", *arguments], cwd=KENN_ROOT, capture_output=True, check=False)
        return result.stdout if result.returncode == 0 else b""

    sources = hashlib.sha256()
    paths = set(git("ls-files", "--", "apps/backend/src/kenn", "tooling/scripts").decode().splitlines())
    # New files affect the tested build before a commit exists, so they belong in its identity too.
    paths.update(git("ls-files", "--others", "--exclude-standard", "--", "apps/backend/src/kenn", "tooling/scripts").decode().splitlines())
    for name in sorted(paths):
        path = KENN_ROOT / name
        if path.is_file():
            sources.update(name.encode() + b"\0" + path.read_bytes())
    identity = {
        "source_revision": git("rev-parse", "HEAD").decode().strip() or None,
        "dirty_diff_sha256": hashlib.sha256(git("diff", "HEAD", "--", ".")).hexdigest(),
        "source_files_sha256": sources.hexdigest(),
        "model_name": os.environ.get("KENN_LLM_MODEL") or None,
        "model_digest": None, "resolved_prompt_sha256": None,
        "index_version": _index_version() or None, "index_sha256": None, "corpus_sha256": None,
        "hardware": {"architecture": platform.machine(), "processor": None, "memory_bytes": None},
        "cache_settings": {"KENN_LLM_CACHE": os.environ.get("KENN_LLM_CACHE"),
                           "KENN_LLM_CACHE_SIZE": os.environ.get("KENN_LLM_CACHE_SIZE"),
                           "KENN_LLM_CACHE_TTL": os.environ.get("KENN_LLM_CACHE_TTL")},
        "manifest": manifest or {},
    }
    # The manifest supplements measured identities rather than replacing this checkout's code hash.
    return identity


def _ask_http(question: str, *, surface: str, endpoint: str, timeout: float) -> tuple[dict, int, None]:
    """Measure actual HTTP delivery; receiving an answer does not prove browser paint or usefulness."""
    from kenn.core.mcp_facade import KennHTTPClient

    client = KennHTTPClient(endpoint, timeout=timeout)
    session = f"latency-{uuid.uuid4().hex}"
    initial = client.post("/api/ask", {"question": question, "session_id": session})
    if surface == "foreground":
        return initial, 0, None
    job = initial.get("answer_upgrade") or {}
    if not job.get("id"):
        # No job can mean busy, superseded or ineligible. The current HTTP contract does not distinguish them.
        return {**initial, "delivery_outcome": "not_attempted", "fallback_reason": "No background job; admission reason unavailable"}, 0, None
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        result = client.get("/api/ask/upgrade", {"id": job["id"], "session_id": session})
        if result.get("status") != "pending":
            status = result.get("status")
            if status not in {"accepted", "rejected", "failed"}:
                # Missing, cancelled and expired jobs do not establish that inference was attempted.
                return {**result, "delivery_outcome": "not_attempted", "fallback_reason": status or "Unknown job state"}, 0, None
            accepted = status == "accepted" and not result.get("abstained")
            return {**result, "delivery_outcome": "accepted" if accepted else "rejected",
                    "generation_validation": {"attempted": True, "accepted": accepted,
                                              "abstained": bool(result.get("abstained")),
                                              "warnings": [result.get("reason") or result.get("error") or status]}}, 0, None
        time.sleep(0.05)  # 50 ms polling is a harness setting, never a service inference setting.
    return {"delivery_outcome": "timeout", "fallback_reason": "Background polling deadline"}, 0, None


def answer_capture(report: dict) -> dict:
    """Export every requested case for offline review, including missing and rejected answers."""
    return {"schema": "kenn.answer_capture.v1", "provenance": report["provenance"],
            "cases": [{"case_id": row["id"], "question": row["question"], "answer": row["candidate"] if row.get("candidate") is not None else row["answer"],
                       "delivered_answer": row["answer"], "family": row["category"], "split": row["split"], "delivery": row["delivery"],
                       "evidence": row["captured_evidence"], "eligible": row["eligible"],
                       "candidate_available": row["candidate_available"]} for row in report["rows"]]}


def measure(cases: list[dict], *, allow_llm: bool = True, surface: str = "stream",
            cache_condition: str = "cold", endpoint: str | None = None, timeout: float = 90.0,
            manifest: dict | None = None) -> dict:
    global _CAPTURE_HIT, _LAST_CAPTURE_ROW, _CAPTURE_CASE_ID
    from kenn.core import chat_answer
    from kenn.llm.llm_rewrite import capture_usage

    if surface not in {"stream", "payload", "foreground", "background"} or cache_condition not in {"cold", "warm"}:
        raise ValueError("Unknown delivery surface or cache condition")
    identities = [str(case.get("id") or case.get("case_id") or "") for case in cases]
    if not identities or any(not item for item in identities) or len(set(identities)) != len(identities):
        raise ValueError("Cases require unique IDs")
    provenance = run_provenance(manifest)
    provenance.update(surface=surface, cache_condition=cache_condition)
    rows: list[dict] = []
    for case in cases:
        question = str(case.get("question") or "").strip()
        if not question:
            raise ValueError("Empty questions cannot be omitted from a qualification run")
        # The semantic answer cache will otherwise serve a previous run's answer for an identical question, which
        # makes a rerun look like a 0.1 s answer that never called the model. Measured: three questions took
        # 57/54/73 s on the first pass and 0.1/0.1/1.5 s on the second, with "never attempted" nowhere in sight.
        if cache_condition == "cold" and not endpoint:
            _drop_semantic_cache()
        _CAPTURE_HIT = False
        _LAST_CAPTURE_ROW = None
        _CAPTURE_CASE_ID = str(case.get("id") or case.get("case_id"))
        started = time.perf_counter()
        # Replayed metadata can contain an earlier call's usage. Collect actual calls in this
        # context, including route/retry/failure/guard-close, rather than copying that metadata.
        with capture_usage() as provider_calls:
            try:
                payload, tokens, ttft = (_ask_http(question, surface=surface, endpoint=endpoint, timeout=timeout)
                                        if surface in {"foreground", "background"} else
                                        _ask(chat_answer, question, allow_llm=allow_llm, surface=surface))
                error = None
            except Exception as exc:  # a failure is a measurement, not a crash
                payload, error, tokens, ttft = {}, f"{type(exc).__name__}: {exc}", 0, None
        seconds = time.perf_counter() - started
        validation = dict(payload.get("generation_validation") or {})
        # The gate is skipped when the streaming prefix guard trips, so those answers never reach the capture
        # wrapper above. They still happened and still reject, and they are the unsupported-measurement class,
        # so the row is written here from the payload. The model's own text is not recoverable on this path --
        # chat_answer drops it -- which is recorded rather than papered over.
        if (
            validation.get("attempted")
            and not _CAPTURE_HIT
        ):
            _write_capture_row({
                "question": question,
                "answer": str(payload.get("answer") or ""),
                "accepted": bool(validation.get("accepted")),
                "warnings": [str(w) for w in (validation.get("warnings") or [])],
                "unsupported_measurements": [str(m) for m in (validation.get("unsupported_measurements") or [])],
                "fabricated_sources": [str(s) for s in (validation.get("fabricated_sources") or [])],
                "evidence_text": "",
                "evidence_sources": None,
                "prompt_evidence": None,
                "evidence_chunks_shown": None,
                "gate_ran": False,
                "candidate_text_available": False,
                "index_version": _index_version(),
                "additional_evidence_text": "",
                "timeline_context": "",
                "abstained": bool(validation.get("abstained")),
                "abstain_gap": str(validation.get("abstain_gap") or ""),
                "claim_citations": {},
            })
        delivery = payload.get("delivery_outcome") or (
            "timeout" if error and ("Timeout" in error or "did not complete" in error) else
            "accepted" if validation.get("accepted") and not validation.get("abstained") else
            "rejected" if validation.get("attempted") else "not_attempted")
        calls = [usage.to_dict() for usage in provider_calls]
        def native_seconds(field):
            values = [call.get(field) for call in calls]
            return sum(values) / 1e9 if values and all(value is not None for value in values) else None
        rows.append({
            "id": str(case.get("id") or case.get("case_id")),
            "question": question, "answer": str(payload.get("answer") or ""),
            "split": str(case.get("split") or "regression"), "eligible": case.get("eligible", True) is True,
            "delivery": delivery, "candidate_available": bool((_LAST_CAPTURE_ROW or {}).get("candidate_text_available")) or delivery == "accepted",
            "captured_evidence": (_LAST_CAPTURE_ROW or {}).get("evidence_sources", payload.get("sources")),
            "candidate": (_LAST_CAPTURE_ROW or {}).get("answer") if (_LAST_CAPTURE_ROW or {}).get("candidate_text_available") else None,
            "fallback_reason": payload.get("fallback_reason") or error or validation.get("warnings"),
            "first_useful_answer_seconds": None, "final_displayed_answer_seconds": None,
            "final_received_answer_seconds": round(seconds, 3),
            "memory_pressure": None, "swap_bytes": None,
            "phase_seconds": {"admission": None, "queue": None, "context_retrieval": None,
                              "prefill": native_seconds("prompt_eval_duration_ns"),
                              "generation": native_seconds("eval_duration_ns"), "verification": None},
            "category": str(case.get("category") or "uncategorized"),
            "seconds": round(seconds, 3),
            "ttft_seconds": round(ttft, 3) if ttft is not None else None,
            "stream_events": tokens,
            "cache_dropped": cache_condition == "cold" and not endpoint,
            "server_cache_condition_verified": False if endpoint else None,
            "surface": surface,
            "provider_calls": [usage.to_dict() for usage in provider_calls],
            "attempted": bool(validation.get("attempted")),
            # The gate accepts a named-gap decline, but a decline is not a correct model answer, so it stays out of
            # "accepted" (which feeds the 70% gate and the accepted-only timings) and out of "rejected" too.
            "accepted": bool(validation.get("accepted")) and not validation.get("abstained"),
            "abstained": bool(validation.get("accepted")) and bool(validation.get("abstained")),
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
    abstained = [r for r in attempted if r["abstained"]]
    rejected = [r for r in attempted if not r["accepted"] and not r["abstained"]]
    reasons = Counter(w for r in rejected for w in r["warnings"])
    top_reason, top_count = reasons.most_common(1)[0] if reasons else ("", 0)
    calls = [call for row in rows for call in row["provider_calls"]]
    return {
        "schema": "kenn.chat_latency.v2",
        "provenance": provenance,
        "qualification": "unqualified; delivery is not correctness or displayed-answer timing",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": os.environ.get("KENN_LLM_MODEL", ""),
        "index_version": _index_version(),
        "counts": {
            "asked": len(rows),
            "eligible": sum(r["eligible"] for r in rows),
            "delivery": dict(Counter(r["delivery"] for r in rows)),
            "eligible_accepted_within_15_seconds": sum(r["eligible"] and r["delivery"] == "accepted" and r["seconds"] <= 15 for r in rows),
            "llm_attempted": len(attempted),
            "llm_accepted": len(accepted),
            "llm_abstained": len(abstained),
            "llm_rejected": len(rejected),
            "errors": sum(1 for r in rows if r["error"]),
            "provider_attempts": sum(call["provider_attempted"] for call in calls),
            "provider_failures": sum(call["status"] == "failed" for call in calls),
            "provider_interruptions": sum(call["status"] == "interrupted" for call in calls),
            "provider_incomplete": sum(call["status"] == "incomplete" for call in calls),
            "response_cache_hits": sum(call["cache_hit"] for call in calls),
        },
        "seconds": {
            "all_median": _median([r["seconds"] for r in rows]),
            "all_p95": _percentile([r["seconds"] for r in rows], 0.95),
            "attempted_median": _median([r["seconds"] for r in attempted]),
            "accepted_median": _median([r["seconds"] for r in accepted]),
            "accepted_p95": _percentile([r["seconds"] for r in accepted], 0.95),
            # Reported beside the completion figures because they answer different questions. A streaming change
            # can leave the median answer untouched and still move when the producer first sees text.
            "ttft_median": _median([r["ttft_seconds"] for r in rows if r.get("ttft_seconds") is not None]),
            "ttft_p95": _percentile([r["ttft_seconds"] for r in rows if r.get("ttft_seconds") is not None], 0.95),
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
        "Chat answer latency, local brain (Stage 1 open item; gate is 70% accepted within 15 s)",
        f"  model              {report['model'] or '(unset)'}",
        f"  surface            {surface_of(report)}",
        f"  index              {report['index_version'] or '(none in this checkout)'}",
        f"  asked              {counts['asked']}",
        f"  brain attempted    {attempted}",
        f"  brain accepted     {counts['llm_accepted']}"
        + (f"  ({100 * counts['llm_accepted'] / attempted:.0f}% of attempts)" if attempted else ""),
        # .get: receipts written before 7 Oct 2026 have no llm_abstained and still get rendered.
        f"  brain abstained    {counts.get('llm_abstained', 0)}",
        f"  brain rejected     {counts['llm_rejected']}",
        f"  errors             {counts['errors']}",
        f"  all answers        median {seconds['all_median']}s   p95 {seconds['all_p95']}s",
    ]
    if seconds.get("ttft_median") is not None:
        lines.append(
            f"  first token        median {seconds['ttft_median']}s   p95 {seconds['ttft_p95']}s"
        )
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
    parser.add_argument("--surface", choices=("stream", "payload", "foreground", "background"), default="stream",
                        help="stream = kenn.core.chat / chat_cli; payload = the browser companion's non-streaming call")
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--capture-answers", type=Path, metavar="PATH",
                        help="append every candidate answer to PATH as JSONL, including rejected ones, so a "
                             "gate can be re-scored offline. Must be git-ignored: it holds model prose.")
    parser.add_argument("--endpoint", help="loopback companion URL for foreground/background HTTP measurements")
    parser.add_argument("--cache-condition", choices=("cold", "warm"), default="cold")
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--build-manifest", type=Path, help="exact model/prompt/index/corpus/hardware and supervision identity JSON")
    parser.add_argument("--review-capture", type=Path, help="all-case offline capture JSON; keep outside git")
    args = parser.parse_args()
    if args.surface in {"foreground", "background"} and not args.endpoint:
        parser.error("HTTP delivery requires --endpoint")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")

    if not args.cases.is_file():
        print(f"No cases at {args.cases}", file=sys.stderr)
        return 1
    current = KENN_ROOT / "apps/backend/src/kenn/data/index/CURRENT"
    if not current.is_file() and not args.endpoint:
        print("chat-latency=NOT_MEASURED no retrieval index in this checkout", file=sys.stderr)
        print("apps/backend/src/kenn/data/ is git-ignored, so a fresh worktree has none and every answer would "
              "abstain. Run from the main checkout.", file=sys.stderr)
        return 2

    cases = json.loads(args.cases.read_text(encoding="utf-8")).get("cases", [])[: args.limit]
    if args.capture_answers or (args.review_capture and not args.endpoint):
        _install_capture(args.capture_answers)
    report = measure(cases, allow_llm=not args.templates_only, surface=args.surface,
                     cache_condition=args.cache_condition, endpoint=args.endpoint, timeout=args.timeout,
                     manifest=json.loads(args.build_manifest.read_text()) if args.build_manifest else None)
    report["provenance"]["cases_sha256"] = hashlib.sha256(args.cases.read_bytes()).hexdigest()
    if args.review_capture:
        args.review_capture.parent.mkdir(parents=True, exist_ok=True)
        args.review_capture.write_text(json.dumps(answer_capture(report), indent=2) + "\n")
    print(render(report))
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
        print(f"receipt written to {args.receipt}")
    return 1 if report["counts"]["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
