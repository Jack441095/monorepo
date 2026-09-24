#!/usr/bin/env python3
"""Compare KENN retrieval modes against fixed expected-source fixtures."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tooling" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "packages" / "chat"))
sys.path.insert(0, str(REPO_ROOT / "apps" / "backend" / "src"))
from eval_chat_coverage import _expects_public_abstention  # noqa: E402
from kenn.core.chat_retrieval import load_chunks, load_terms  # noqa: E402
from kenn.retrieval import retrieval  # noqa: E402
from kenn.retrieval.index_store import active_version_id  # noqa: E402


SCHEMA = "kenn.retrieval_mode_comparison.v1"
DEFAULT_CASES = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "evals" / "questions.json"


def _source_matches(chunk: dict[str, Any], expected: list[str]) -> bool:
    identity = " ".join(str(chunk.get(key) or "") for key in ("source", "title")).casefold()
    return all(str(term).casefold() in identity for term in expected)


def _rank(expected: list[str], results: list[tuple[float, dict[str, Any]]]) -> int | None:
    unique_sources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _score, chunk in results:
        identity = str(chunk.get("source") or chunk.get("title") or chunk.get("id") or "").casefold()
        if identity in seen:
            continue
        seen.add(identity)
        unique_sources.append(chunk)
    ranks = [
        next((index for index, chunk in enumerate(unique_sources, start=1) if _source_matches(chunk, [term])), None)
        for term in expected
    ]
    return max(ranks) if ranks and all(rank is not None for rank in ranks) else None


def _summary(rows: list[dict[str, Any]], *, cutoff: int) -> dict[str, Any]:
    count = len(rows)
    ranks = [row["rank"] for row in rows if isinstance(row.get("rank"), int)]
    latencies = [float(row["latency_ms"]) for row in rows]
    return {
        "cases": count,
        "top1": round(sum(rank == 1 for rank in ranks) / count, 4) if count else 0.0,
        f"recall_at_{cutoff}": round(sum(rank <= cutoff for rank in ranks) / count, 4) if count else 0.0,
        "mrr": round(sum(1.0 / rank for rank in ranks) / count, 4) if count else 0.0,
        "median_latency_ms": round(statistics.median(latencies), 3) if latencies else None,
        "max_latency_ms": round(max(latencies), 3) if latencies else None,
    }


def evaluate(
    *,
    cases_path: Path = DEFAULT_CASES,
    cutoff: int = 4,
    searchers: dict[str, Callable[[str, int], list[tuple[float, dict[str, Any]]]]] | None = None,
) -> dict[str, Any]:
    raw = cases_path.read_bytes()
    fixtures = [
        case for case in json.loads(raw).get("cases", [])
        if isinstance(case, dict) and case.get("source_must_include") and not _expects_public_abstention(case)
    ]
    if searchers is None:
        chunks, terms = load_chunks(), load_terms()
        embedding_index = retrieval.load_embedding_index()
        # Personal feedback is intentionally excluded from this fixed baseline.
        original_feedback = retrieval.load_source_feedback_scores
        retrieval.load_source_feedback_scores = lambda: {}
        searchers = {
            "bm25": lambda query, limit: retrieval.bm25_search(query, chunks, terms, limit=limit),
            "hybrid": lambda query, limit: retrieval.hybrid_search(
                query, chunks, terms, limit=limit, embedding_index=embedding_index
            ),
        }
    else:
        original_feedback = None
    modes: dict[str, Any] = {}
    try:
        for name, searcher in searchers.items():
            rows = []
            for case in fixtures:
                started = time.perf_counter()
                error = None
                try:
                    results = searcher(str(case.get("question") or ""), max(cutoff * 4, 16))
                    if case.get("source_any_include"):
                        # Any one acceptable source counts (e.g. the device note or a manual chunk titled with it).
                        ranks = [_rank([str(term)], results) for term in case["source_any_include"]]
                        rank = min((r for r in ranks if r is not None), default=None)
                    else:
                        rank = _rank([str(term) for term in case["source_must_include"]], results)
                except Exception as exc:
                    rank = None
                    error = f"{type(exc).__name__}: {exc}"[:256]
                rows.append({
                    "id": str(case.get("id") or "unknown"),
                    "rank": rank,
                    "hit": rank is not None and rank <= cutoff,
                    "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                    "error": error,
                })
            modes[name] = {"summary": _summary(rows, cutoff=cutoff), "rows": rows}
    finally:
        if original_feedback is not None:
            retrieval.load_source_feedback_scores = original_feedback
    baseline = modes.get("bm25", {}).get("summary", {})
    candidate = modes.get("hybrid", {}).get("summary", {})
    recall_key = f"recall_at_{cutoff}"
    no_quality_regression = bool(candidate) and (
        candidate.get(recall_key, 0) >= baseline.get(recall_key, 0)
        and candidate.get("mrr", 0) >= baseline.get("mrr", 0)
    )
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "corpus_sha256": hashlib.sha256(raw).hexdigest(),
        "index_version": active_version_id() or "unknown",
        "cutoff": cutoff,
        "fixture_count": len(fixtures),
        "modes": modes,
        "decision": {
            "candidate": "hybrid",
            "baseline": "bm25",
            "no_quality_regression": no_quality_regression,
            "deploy_candidate": no_quality_regression,
            "learned_reranker": "not_evaluated_missing_model_artifact",
        },
        "privacy": {"stores_questions": False, "stores_source_text": False},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--cutoff", type=int, default=4)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.cutoff < 1 or args.cutoff > 20:
        parser.error("cutoff must be between 1 and 20")
    receipt = evaluate(cases_path=args.cases.expanduser().resolve(), cutoff=args.cutoff)
    rendered = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output:
        target = args.output.expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if receipt["decision"]["no_quality_regression"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
