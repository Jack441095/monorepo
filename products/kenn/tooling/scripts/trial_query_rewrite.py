#!/usr/bin/env python3
"""Trial: does one local query-rewrite call lift recall on the device-purpose fixtures?

KENN_PLAN.md, C3 "Query-rewriting trial". Retrieval stays exactly as shipped (hybrid when the index has
embeddings, BM25 otherwise); only the string handed to it changes. Three conditions per fixture case, all scored by the same rank code as
evaluate_retrieval_modes.py:

  raw           the fixture question as asked (today's behaviour for a standalone question)
  rewrite       one model call turns the question into a retrieval query, no history
  followup_*    the fixture question is the previous turn and a fixed elliptical follow-up ("and how do
                I set that up?") is the new one. `followup_history` is what production does today
                (chat_routing.search_query_with_history); `followup_rewrite` has the model resolve it.

The follow-ups are templates, not owner-written turns, so this measures whether the rewrite recovers
a topic the history already carries. It cannot show that a rewrite survives a real topic change.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
import urllib.request
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tooling" / "scripts"))
sys.path.insert(0, str(ROOT / "apps" / "backend" / "src"))

import evaluate_retrieval_modes as modes  # noqa: E402
from kenn.core.chat_retrieval import load_chunks, load_terms  # noqa: E402
from kenn.core.chat_routing import search_query_with_history  # noqa: E402
from kenn.core.ollama_deliberative import open_loopback_ollama, validate_ollama_base_url  # noqa: E402
from kenn.retrieval import retrieval  # noqa: E402

FIXTURES = ("device_purpose_sealed_holdout.json", "device_purpose_sealed_qwen8b.json")
EVALS = ROOT / "apps" / "backend" / "src" / "kenn" / "evals"

# Cycled by case position so a rerun asks the same follow-up of the same case. None names a device.
FOLLOWUPS = (
    "and how do I set that up?",
    "why would I want that?",
    "what settings should I use for it?",
    "is there a shortcut for that?",
    "what about doing it faster?",
    "can you explain that a bit more?",
)

SYSTEM = (
    "You rewrite a producer's last message into one search query for an Ableton Live and audio production "
    "knowledge base. If it refers back to the previous question (that, it, this), name the thing it refers to. "
    "Say what the person is trying to do and, if the message hides it, the Ableton feature or device that does it. "
    "Reply with the query only, under 25 words, no quotes."
)


def rewrite(base: str, model: str, last: str, previous: str | None, keep_alive: str) -> str:
    """One chat call; returns the model's query, or the unchanged last message if it answers nothing."""
    content = f"Previous question: {previous}\nLast message: {last}" if previous else f"Last message: {last}"
    body = {
        "model": model, "stream": False, "think": False, "keep_alive": keep_alive,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}],
        # Greedy and bounded: a rerun must reproduce the same query, and 64 tokens is ~2x the 25-word ask.
        "options": {"temperature": 0, "seed": 0, "num_predict": 64},
    }
    request = urllib.request.Request(base + "/api/chat", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
    with open_loopback_ollama(request, timeout=120) as response:
        text = (json.load(response).get("message") or {}).get("content") or ""
    text = " ".join(text.split()).strip(" \"'")
    # An empty reply would score as a zero-recall miss caused by the harness, so fall back to the input and
    # let the receipt count the fallback.
    return text or last


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="kenn-brain-qwen3-8b", help="Ollama tag; the shipped rewrite model.")
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--limit", type=int, default=0, help="Only the first N cases per fixture (smoke runs).")
    parser.add_argument("--cutoff", type=int, default=4)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base = validate_ollama_base_url(args.base_url)

    chunks, terms = load_chunks(), load_terms()
    embedding_index = retrieval.load_embedding_index()
    # The 14 Oct index in the main checkout ships no embeddings and sentence_transformers is not installed, so the
    # hybrid path the 0.616 -> 0.736 receipt measured cannot run here (KENN_PLAN.md, 14 Oct side finding). We fall back
    # to plain BM25 and say so in the receipt, because BM25 numbers are not comparable with that receipt.
    retrieval_mode = "hybrid" if embedding_index is not None else "bm25_only"
    original_feedback = retrieval.load_source_feedback_scores
    # Same exclusion as evaluate_retrieval_modes: personal feedback must not move a fixed baseline.
    retrieval.load_source_feedback_scores = lambda: {}
    limit = max(args.cutoff * 4, 16)
    receipt: dict = {"schema": "kenn.query_rewrite_trial.v1", "generated_at": datetime.now(timezone.utc).isoformat(),
                     "model": args.model, "cutoff": args.cutoff, "retrieval": retrieval_mode, "fixtures": {}, "rewrite_fallbacks": 0}
    try:
        for name in FIXTURES:
            raw_bytes = (EVALS / name).read_bytes()
            cases, skipped = modes._select_cases(raw_bytes)
            if args.limit:
                cases = cases[: args.limit]
            queries: dict[str, dict[str, str]] = {"raw": {}, "rewrite": {}, "followup_history": {}, "followup_rewrite": {}}
            started = time.perf_counter()
            for position, case in enumerate(cases):
                question = str(case["question"])
                followup = FOLLOWUPS[position % len(FOLLOWUPS)]
                history = [{"role": "user", "content": question}, {"role": "assistant", "content": "Here is how."}]
                queries["raw"][question] = question
                queries["followup_history"][question] = search_query_with_history(followup, history)
                for key, last, previous in (("rewrite", question, None), ("followup_rewrite", followup, question)):
                    out = rewrite(base, args.model, last, previous, "1m")
                    receipt["rewrite_fallbacks"] += out == last
                    queries[key][question] = out
            elapsed = time.perf_counter() - started
            def search(query: str, n: int):
                if retrieval_mode == "hybrid":
                    return retrieval.hybrid_search(query, chunks, terms, limit=n, embedding_index=embedding_index)
                return retrieval.bm25_search(query, chunks, terms, limit=n)

            # Each searcher is keyed by the fixture question, which is how the rows below look their query up.
            searchers = {key: (lambda question, n, table=table: search(table[question], n)) for key, table in queries.items()}
            # evaluate_retrieval_modes.evaluate() always rereads the whole fixture and names its modes bm25/hybrid,
            # so we score here with its rank and summary helpers instead (same rank rule, same recall@N).
            result = {"modes": {}}
            for key, searcher in searchers.items():
                rows = []
                for case in cases:
                    found = searcher(str(case["question"]), limit)
                    if case.get("source_any_include"):
                        ranks = [modes._rank([str(t)], found) for t in case["source_any_include"]]
                        rank = min((r for r in ranks if r is not None), default=None)
                    else:
                        rank = modes._rank([str(t) for t in case["source_must_include"]], found)
                    rows.append({"id": str(case["id"]), "rank": rank, "hit": rank is not None and rank <= args.cutoff,
                                 "latency_ms": 0.0})  # Retrieval latency is not what this trial measures.
                result["modes"][key] = {"summary": modes._summary(rows, cutoff=args.cutoff), "rows": rows}
            # Ids and ranks only; the questions live in the fixtures and the rewrites are not worth keeping.
            receipt["fixtures"][name] = {
                "cases_scored": len(cases), "cases_skipped": len(skipped), "rewrite_seconds": round(elapsed, 1),
                "modes": {key: {"summary": value["summary"], "ranks": {r["id"]: r["rank"] for r in value["rows"]}}
                          for key, value in result["modes"].items()},
            }
    finally:
        retrieval.load_source_feedback_scores = original_feedback
        # The trial pinned the model for 1 minute per call to avoid 800 reloads; release it now. The plan asks that
        # eval runs leave nothing resident beside a KENN session.
        unload = urllib.request.Request(base + "/api/generate", data=json.dumps(
            {"model": args.model, "prompt": "", "keep_alive": "0"}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            open_loopback_ollama(unload, timeout=30).close()
        except OSError:
            pass  # Best effort: the model's own 1 minute expiry releases it anyway.
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    for name, fixture in receipt["fixtures"].items():
        print(name)
        for key, value in fixture["modes"].items():
            s = value["summary"]
            print(f"  {key:18} recall@{args.cutoff} {s[f'recall_at_{args.cutoff}']:.3f}  mrr {s['mrr']:.3f}  top1 {s['top1']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
