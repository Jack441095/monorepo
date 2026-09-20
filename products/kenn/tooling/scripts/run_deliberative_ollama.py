#!/usr/bin/env python3
"""Collect sealed KENN deliberative-plan predictions from local Ollama."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "backend" / "src"))

from kenn.core.deliberative_benchmark import build_benchmark_context, load_benchmark  # noqa: E402
from kenn.core.deliberative_plan import (  # noqa: E402
    deliberative_plan_sketch_json_schema,
    hydrate_deliberative_plan_sketch,
)
from kenn.core.deliberative_planner import (  # noqa: E402
    build_deliberative_sketch_prompt,
    complete_deliberative_sketch_contract,
    deliberative_preflight_plan,
    parse_deliberative_output,
)
from kenn.core.ollama_deliberative import open_loopback_ollama, validate_ollama_base_url  # noqa: E402


DEFAULT_BENCHMARK = ROOT / "packages" / "chat" / "evals" / "ableton_deliberative_holdout.json"


def _generate(
    *, base_url: str, model: str, prompt: str, timeout: float,
    max_output_tokens: int, max_plan_steps: int, max_list_items: int,
    allowed_actions: list[str],
) -> str:
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/chat",
        data=json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": deliberative_plan_sketch_json_schema(
                max_steps=max_plan_steps, max_list_items=max_list_items,
                allowed_actions=allowed_actions, allow_clarification=False,
            ),
            "options": {
                "temperature": 0,
                "seed": 0,
                "num_ctx": 8192,
                "num_predict": max_output_tokens,
            },
            "keep_alive": "10m",
        }, separators=(",", ":")).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with open_loopback_ollama(request, timeout=timeout) as response:
        payload = json.load(response)
    message = payload.get("message") if isinstance(payload, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Ollama returned no assistant content")
    return content


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    parser.add_argument("--model", default="qwen2.5:7b-instruct")
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--max-output-tokens", type=int, default=320)
    parser.add_argument("--max-plan-steps", type=int, default=3)
    parser.add_argument("--max-list-items", type=int, default=4)
    parser.add_argument("--case-id", action="append", default=[], help="Run only selected case IDs (repeatable).")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.base_url = validate_ollama_base_url(args.base_url)

    benchmark = load_benchmark(args.benchmark)
    cases = benchmark["cases"]
    if args.case_id:
        selected = set(args.case_id)
        cases = [case for case in cases if case["id"] in selected]
        missing = selected - {case["id"] for case in cases}
        if missing:
            raise SystemExit("Unknown benchmark case IDs: " + ", ".join(sorted(missing)))
    predictions: dict[str, dict] = {}
    for position, case in enumerate(cases, start=1):
        case_id = str(case["id"])
        context = build_benchmark_context(case)
        goal = str(case.get("goal") or "")
        started = time.perf_counter()
        raw = ""
        sketch = None
        planner_source = "model_sketch"
        try:
            plan = deliberative_preflight_plan(goal, context)
            if plan is not None:
                planner_source = "deterministic_preflight"
            else:
                prompt = build_deliberative_sketch_prompt(goal, context)
                raw = _generate(
                    base_url=args.base_url,
                    model=args.model,
                    prompt=prompt,
                    timeout=max(1.0, args.timeout_seconds),
                    max_output_tokens=max(128, min(2_048, args.max_output_tokens)),
                    max_plan_steps=max(1, min(8, args.max_plan_steps)),
                    max_list_items=max(1, min(8, args.max_list_items)),
                    allowed_actions=[str(action) for action in context.get("available_actions") or []],
                )
                sketch = complete_deliberative_sketch_contract(
                    parse_deliberative_output(raw)
                )
                plan = hydrate_deliberative_plan_sketch(
                    sketch,
                    goal=goal,
                    context=context,
                    model_provider="ollama",
                    model_id=str(args.model),
                )
            error = ""
        except (ValueError, TimeoutError, OSError, urllib.error.URLError) as exc:
            plan = None
            error = f"{type(exc).__name__}: {exc}"[:1_000]
        latency_ms = round((time.perf_counter() - started) * 1_000, 3)
        predictions[case_id] = {
            "model_provider": "ollama",
            "model_id": str(args.model)[:128],
            "planner_source": planner_source,
            "latency_ms": latency_ms,
            "plan": plan,
            "sketch": sketch,
            "error": error,
            "raw_output": raw[:20_000],
        }
        print(f"[{position}/{len(cases)}] {case_id}: {'ok' if plan else error}", flush=True)

    output = {
        "schema": "kenn.deliberative_prediction_set.v1",
        "benchmark_id": benchmark.get("benchmark_id", "unknown"),
        "model_provider": "ollama",
        "model_id": str(args.model)[:128],
        "predictions": predictions,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "predictions_written", "path": str(args.output), "case_count": len(predictions)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
