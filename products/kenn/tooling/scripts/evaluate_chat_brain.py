#!/usr/bin/env python3
"""Compare local Qwen "brains" on KENN's own answer path (Stage 1: choosing the conversation model).

Each question in the chat fixture goes through ``answer_payload``, the pipeline the desktop app uses, once with the
LLM off (the template answer) and once per model. For every answer we record the fixture's content checks (the same
``_check_dimensions`` the coverage receipt uses), whether the model's rewrite was actually used or KENN fell back to
the template, and how long it took. Answers are kept so a person can read a sample: keyword checks alone don't say
whether an answer is good.

    evaluate_chat_brain.py --base-url http://127.0.0.1:11437/v1 --model qwen3:8b --model qwen3:14b --out brain.json
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

KENN_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(KENN_ROOT / "apps" / "backend" / "src"), str(KENN_ROOT / "tooling"), str(KENN_ROOT / "tooling" / "scripts")]

CASES = KENN_ROOT / "apps" / "backend" / "src" / "kenn" / "evals" / "questions.json"


def _configure(base_url: str, model: str | None) -> None:
    os.environ.update({"KENN_USE_MLX": "0", "KENN_LLM_CACHE": "0", "AUDIO_TOO_LLM_TIMEOUT": "90"})
    if model is None:
        os.environ["KENN_LLM_ENABLED"] = "0"
        return
    os.environ.update({"KENN_LLM_ENABLED": "1", "KENN_LLM_PROVIDER": "ollama", "KENN_LLM_BASE_URL": base_url,
                       "KENN_LLM_MODEL": model})


def run(label: str, cases: list[dict]) -> dict:
    from eval_chat_coverage import _check_dimensions, _expects_public_abstention
    from kenn.core.chat_answer import answer_payload

    rows = []
    for case in cases:
        started = time.perf_counter()
        try:
            payload = answer_payload(str(case["question"]))
            error = None
        except Exception as exc:  # a crash is a failed answer, never a skipped one
            payload, error = {}, f"{type(exc).__name__}: {exc}"
        seconds = time.perf_counter() - started
        dims = _check_dimensions(case, payload, expected_abstention=_expects_public_abstention(case)) if payload else {}
        failures = [f for values in dims.values() for f in values] if payload else [error or "no payload"]
        rows.append({"id": case["id"], "passed": not failures, "failures": failures,
                     "llm_used": bool(payload.get("llm_enhanced")), "seconds": round(seconds, 2),
                     "answer": str(payload.get("answer") or "")[:3000]})
    times = sorted(r["seconds"] for r in rows)
    used = [r for r in rows if r["llm_used"]]
    return {
        "label": label, "cases": len(rows), "passed": sum(r["passed"] for r in rows),
        "llm_used": len(used), "llm_used_passed": sum(r["passed"] for r in used),
        "p50_s": round(statistics.median(times), 2), "p95_s": round(times[int(0.95 * (len(times) - 1))], 2),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", required=True, help="Ollama OpenAI-compatible URL, e.g. http://127.0.0.1:11437/v1")
    parser.add_argument("--model", action="append", default=[], help="Ollama model name (repeat for several)")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    from eval_chat_coverage import _expects_public_abstention

    cases = [c for c in json.loads(CASES.read_text(encoding="utf-8"))["cases"] if not _expects_public_abstention(c)]
    cases = cases[: args.limit] if args.limit else cases
    reports = []
    for model in [None, *args.model]:
        _configure(args.base_url, model)
        report = run(model or "template (no LLM)", cases)
        reports.append(report)
        print(f"{report['label']:28} passed {report['passed']}/{report['cases']}  model answer used "
              f"{report['llm_used']} (passed {report['llm_used_passed']})  p50 {report['p50_s']}s  p95 {report['p95_s']}s",
              flush=True)
    args.out.write_text(json.dumps({"schema": "kenn.chat_brain_comparison.v1", "cases": len(cases), "reports": reports},
                                   indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
