#!/usr/bin/env python3
"""Evaluate KENN's engine-level grounding and answer-quality hard cases."""

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
import app  # noqa: E402
from eval_chat_coverage import _expects_public_abstention  # noqa: E402


SCHEMA = "kenn.chat_hard_case_benchmark.v1"
ENGINE_ASSERTIONS = ("grounding_mode", "min_grounding_score", "min_answer_quality")
DEFAULT_CASES = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "evals" / "questions.json"


def _engine_answer(question: str) -> dict[str, Any]:
    """Run the same retrieval-only boundary while retaining internal scores."""
    allowed, route, reason = app._scope_reason(question, [])
    if not allowed:
        return {"public": app._abstention_payload(question, reason, route), "engine": {}}
    mode = app.classify_answer_mode(question, route, history=[])
    payload = app._scoped_answer_payload(question, [], mode)
    expanded_query = app._expanded_retrieval_query(question)
    if expanded_query:
        expanded = app._scoped_answer_payload(expanded_query, [], mode)
        if expanded.get("found") and not expanded.get("weak_match") and expanded.get("sources"):
            expanded["question"] = question
            payload = expanded
    if not payload.get("found") or payload.get("weak_match") or not payload.get("sources"):
        public = app._abstention_payload(
            question,
            "KENN found no sufficiently strong approved source match, so it abstained.",
            route,
        )
    else:
        public = app._public_payload(payload)
    return {"public": public, "engine": payload}


def _check_engine_assertions(case: dict[str, Any], engine: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    expected_mode = case.get("grounding_mode")
    actual_mode = str(engine.get("grounding_mode") or "none")
    if expected_mode is not None and actual_mode != str(expected_mode):
        failures.append(f"grounding_mode:{actual_mode}!={expected_mode}")
    grounding_score = int((engine.get("grounding") or {}).get("score", 0) or 0)
    minimum_grounding = int(case.get("min_grounding_score", 0) or 0)
    if grounding_score < minimum_grounding:
        failures.append(f"grounding_score:{grounding_score}<{minimum_grounding}")
    quality_score = int((engine.get("answer_quality") or {}).get("score", 0) or 0)
    minimum_quality = int(case.get("min_answer_quality", 0) or 0)
    if quality_score < minimum_quality:
        failures.append(f"answer_quality:{quality_score}<{minimum_quality}")
    self_check = engine.get("answer_self_check") or {}
    if self_check and self_check.get("passed") is not True:
        failures.append("answer_self_check_failed")
    return failures


def evaluate(
    *,
    cases_path: Path = DEFAULT_CASES,
    answerer: Callable[[str], dict[str, Any]] = _engine_answer,
) -> dict[str, Any]:
    raw = cases_path.read_bytes()
    data = json.loads(raw)
    cases = [
        case for case in data.get("cases", [])
        if isinstance(case, dict)
        and any(field in case for field in ENGINE_ASSERTIONS)
        and not _expects_public_abstention(case)
    ]
    rows: list[dict[str, Any]] = []
    for case in cases:
        started = time.perf_counter()
        error = None
        try:
            result = answerer(str(case.get("question") or ""))
            public = result.get("public") or {}
            engine = result.get("engine") or {}
            failures = _check_engine_assertions(case, engine)
        except Exception as exc:
            public, engine = {}, {}
            error = f"{type(exc).__name__}: {exc}"[:256]
            failures = [f"error:{error}"]
        rows.append({
            "id": str(case.get("id") or "unknown"),
            "passed": not failures,
            "failures": failures,
            "found": bool(public.get("found")),
            "source_count": len(public.get("sources") or []),
            "grounding_mode": engine.get("grounding_mode", "none"),
            "grounding_score": int((engine.get("grounding") or {}).get("score", 0) or 0),
            "answer_quality_score": int((engine.get("answer_quality") or {}).get("score", 0) or 0),
            "answer_self_check_passed": (engine.get("answer_self_check") or {}).get("passed"),
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "error": error,
        })
    latencies = [row["latency_ms"] for row in rows]
    failed = sum(not row["passed"] for row in rows)
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "corpus_sha256": hashlib.sha256(raw).hexdigest(),
        "case_count": len(rows),
        "passed": len(rows) - failed,
        "failed": failed,
        "qualified": bool(rows) and failed == 0,
        "latency_ms": {
            "median": round(statistics.median(latencies), 3) if latencies else None,
            "max": max(latencies) if latencies else None,
        },
        "rows": rows,
        "privacy": {
            "stores_questions": False,
            "stores_answers": False,
            "stores_source_text": False,
        },
        "limitations": [
            "Automated corpus evidence does not replace independent human technical review.",
            "This benchmark evaluates deterministic retrieval-grounded answers with LLM rewriting disabled.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    receipt = evaluate(cases_path=args.cases.expanduser().resolve())
    rendered = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output:
        target = args.output.expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if receipt["qualified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
