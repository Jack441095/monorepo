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


def _no_answer_cache() -> None:
    # KENN serves repeat questions from its semantic answer cache; after the template pass every model run would
    # just read the template answers back (first attempt measured 0.0 s and no model answers at all).
    from kenn.core import session_memory

    session_memory.get_semantic_cache_hit = lambda *_a, **_k: None
    session_memory.save_to_semantic_cache = lambda *_a, **_k: None


# Measured on the owner's M3 / 16 GB with Live running (26 Sept): Qwen3 8B reads the prompt at ~75 tokens/s and writes
# at ~17 tokens/s. The box GPU is much faster, so its seconds say little about the Mac; the token counts do.
MAC_READ_TOKENS_PER_S = 75.0
MAC_WRITE_TOKENS_PER_S = 17.0


def run(label: str, cases: list[dict]) -> dict:
    from eval_chat_coverage import _check_dimensions, _expects_public_abstention
    from kenn.core.chat_answer import answer_payload
    from kenn.llm import llm_rewrite

    _no_answer_cache()
    tokens: list[tuple[int, int]] = []
    original = llm_rewrite._chat_completion

    def counting(messages, task, **kwargs):
        text, usage = original(messages, task, **kwargs)
        if task == "rewrite" and usage is not None:
            tokens.append((int(usage.prompt_tokens or 0), int(usage.completion_tokens or 0)))
        return text, usage

    llm_rewrite._chat_completion = counting

    rows = []
    for case in cases:
        started = time.perf_counter()
        try:
            payload = answer_payload(str(case["question"]))
            error = None
        except Exception as exc:  # a crash is a failed answer, never a skipped one
            payload, error = {}, f"{type(exc).__name__}: {exc}"
        seconds = time.perf_counter() - started
        prompt_tokens, output_tokens = tokens[-1] if tokens else (0, 0)
        tokens.clear()
        dims = _check_dimensions(case, payload, expected_abstention=_expects_public_abstention(case)) if payload else {}
        failures = [f for values in dims.values() for f in values] if payload else [error or "no payload"]
        rows.append({"id": case["id"], "passed": not failures, "failures": failures,
                     "llm_used": bool(payload.get("llm_enhanced")), "seconds": round(seconds, 2),
                     "prompt_tokens": prompt_tokens, "output_tokens": output_tokens,
                     "mac_seconds_estimate": round(prompt_tokens / MAC_READ_TOKENS_PER_S
                                                   + output_tokens / MAC_WRITE_TOKENS_PER_S, 1),
                     "answer": str(payload.get("answer") or "")[:3000]})
    llm_rewrite._chat_completion = original  # leave the module as we found it for the next model
    times = sorted(r["seconds"] for r in rows)
    used = [r for r in rows if r["llm_used"]]
    called = sorted(r["mac_seconds_estimate"] for r in rows if r["prompt_tokens"])
    prompts = sorted(r["prompt_tokens"] for r in rows if r["prompt_tokens"])
    return {
        "label": label, "cases": len(rows), "passed": sum(r["passed"] for r in rows),
        "llm_used": len(used), "llm_used_passed": sum(r["passed"] for r in used),
        "p50_s": round(statistics.median(times), 2), "p95_s": round(times[int(0.95 * (len(times) - 1))], 2),
        "prompt_tokens_p50": statistics.median(prompts) if prompts else None,
        "mac_p50_s_estimate": statistics.median(called) if called else None,
        "mac_p95_s_estimate": called[int(0.95 * (len(called) - 1))] if called else None,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", required=True, help="Ollama OpenAI-compatible URL, e.g. http://127.0.0.1:11437/v1")
    parser.add_argument("--model", action="append", default=[], help="Ollama model name (repeat for several)")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--no-template", action="store_true", help="skip the no-LLM baseline pass")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    from eval_chat_coverage import _expects_public_abstention

    cases = [c for c in json.loads(CASES.read_text(encoding="utf-8"))["cases"] if not _expects_public_abstention(c)]
    cases = cases[: args.limit] if args.limit else cases
    reports = []
    for model in ([] if args.no_template else [None]) + args.model:
        _configure(args.base_url, model)
        report = run(model or "template (no LLM)", cases)
        reports.append(report)
        mac = (f"  prompt {report['prompt_tokens_p50']} tok, Mac est p50 {report['mac_p50_s_estimate']}s "
               f"p95 {report['mac_p95_s_estimate']}s") if report["prompt_tokens_p50"] else ""
        print(f"{report['label']:28} passed {report['passed']}/{report['cases']}  model answer used "
              f"{report['llm_used']} (passed {report['llm_used_passed']})  p50 {report['p50_s']}s  p95 {report['p95_s']}s{mac}",
              flush=True)
    args.out.write_text(json.dumps({"schema": "kenn.chat_brain_comparison.v1", "cases": len(cases), "reports": reports},
                                   indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
