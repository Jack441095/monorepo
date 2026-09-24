#!/usr/bin/env python3
"""Score local command-planner models on KENN's real planner path.

Runs ``live_command._generate_llm_plan`` (real system prompt, schema-
constrained decoding, validator, one repair) against the fake demo snapshot,
so no Live and no writes are involved. For each case it records whether the
plan was accepted, whether the action and track are right (or a clarification
was correctly chosen), and latency. Cases come from a JSONL holdout
(``tooling/data/natural_holdout.jsonl``) with fields ``query`` (or ``command``),
``expected_action`` and optional ``expected_track``.
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
sys.path.insert(0, str(KENN_ROOT / "apps" / "backend" / "src"))
DEFAULT_HOLDOUT = KENN_ROOT / "tooling" / "data" / "natural_holdout.jsonl"


def _configure(model: str) -> None:
    os.environ.update({
        "KENN_LIVE_LLM_ENABLED": "1",
        "KENN_LLM_ENABLED": "1",
        "KENN_LLM_PROVIDER_COMMAND": "ollama",
        "KENN_LLM_BASE_URL_COMMAND": os.environ.get("KENN_BAKEOFF_BASE_URL", "http://127.0.0.1:11434/v1"),
        "KENN_LLM_MODEL_COMMAND": model,
        # A measurement must never read a cached answer from an earlier run.
        "KENN_LLM_CACHE": "0",
    })


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(fraction * len(ordered)))], 1)


def run(model: str, cases: list[dict], *, production_snapshot: bool = False) -> dict:
    _configure(model)
    from kenn.core.fake_live import FakeLiveBackend
    from kenn.core import live_command
    from kenn.llm import llm_rewrite

    llm_rewrite._RESPONSE_CACHE.clear() if hasattr(llm_rewrite, "_RESPONSE_CACHE") else None
    fake = FakeLiveBackend()
    snapshot = fake.query_session_state()
    service = None
    if production_snapshot:
        from kenn.core.live_action_service import LiveActionService
        from kenn.core.live_intent import parse_request

        service = LiveActionService(fake)
    rows = []
    for case in cases:
        started = time.perf_counter()
        command = case.get("query") or case["command"]
        planner_snapshot = snapshot
        if service is not None:
            # As the gateway does: parameter evidence for the track the rule
            # parser identified (live_command._llm_planner_snapshot).
            planner_snapshot = live_command._llm_planner_snapshot(service, snapshot, parse_request(command, snapshot))
        plan, meta = live_command._generate_llm_plan(command, planner_snapshot)
        elapsed = (time.perf_counter() - started) * 1000.0
        expected_action = case["expected_action"]
        action = (plan or {}).get("action")
        correct = plan is not None and action == expected_action and (
            not case.get("expected_track") or (plan or {}).get("track_name") == case["expected_track"]
        )
        rows.append({"command": command, "expected": expected_action, "status": meta.get("status"),
                     "action": action, "track": (plan or {}).get("track_name"), "correct": correct,
                     "repaired": bool(meta.get("repair")), "ms": round(elapsed, 1),
                     "error": meta.get("error") or meta.get("reason")})
    latencies = [r["ms"] for r in rows]
    accepted = sum(r["status"] == "accepted" for r in rows)
    return {
        "model": model,
        "cases": len(rows),
        "accepted_pct": round(100.0 * accepted / len(rows), 1) if rows else 0.0,
        "correct_pct": round(100.0 * sum(r["correct"] for r in rows) / len(rows), 1) if rows else 0.0,
        "p50_ms": _percentile(latencies, 0.5),
        "p95_ms": _percentile(latencies, 0.95),
        "mean_ms": round(statistics.fmean(latencies), 1) if latencies else None,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", action="append", required=True)
    parser.add_argument("--holdout", type=Path, default=DEFAULT_HOLDOUT)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--mlx-model", default=None,
                        help="serve planner calls from this mlx-lm model in-process instead of an HTTP server")
    parser.add_argument("--mlx-adapter", default=None, help="LoRA adapter directory for --mlx-model")
    parser.add_argument("--production-snapshot", action="store_true",
                        help="enrich the snapshot with parameter evidence as the production gateway does")
    parser.add_argument("--timeout", type=int, default=0,
                        help="per-call LLM timeout in seconds (AUDIO_TOO_LLM_TIMEOUT; KENN default 20)")
    args = parser.parse_args()
    if args.timeout:
        os.environ["AUDIO_TOO_LLM_TIMEOUT"] = str(args.timeout)
    if args.mlx_model:
        from mlx_planner_backend import install

        install(args.mlx_model, args.mlx_adapter)
    cases = [json.loads(line) for line in args.holdout.read_text().splitlines() if line.strip()]
    if args.limit:
        cases = cases[: args.limit]
    reports = [run(model, cases, production_snapshot=args.production_snapshot) for model in args.model]
    summary = [{k: r[k] for k in ("model", "cases", "accepted_pct", "correct_pct", "p50_ms", "p95_ms", "mean_ms")}
               for r in reports]
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({"summary": summary, "reports": reports}, indent=1) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
