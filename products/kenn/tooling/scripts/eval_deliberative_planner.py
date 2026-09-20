#!/usr/bin/env python3
"""Emit provider-neutral prompts or score KENN deliberative-plan predictions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "backend" / "src"))

from kenn.core.deliberative_benchmark import (  # noqa: E402
    build_prompt_pack,
    evaluate_prediction_set,
    load_benchmark,
)


DEFAULT_BENCHMARK = ROOT / "packages" / "chat" / "evals" / "ableton_deliberative_holdout.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--emit-prompt-pack", type=Path)
    mode.add_argument("--predictions", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    benchmark = load_benchmark(args.benchmark)
    if args.emit_prompt_pack:
        rows = build_prompt_pack(benchmark)
        args.emit_prompt_pack.parent.mkdir(parents=True, exist_ok=True)
        args.emit_prompt_pack.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        print(json.dumps({"status": "prompt_pack_written", "path": str(args.emit_prompt_pack), "case_count": len(rows)}, indent=2))
        return 0

    raw = json.loads(args.predictions.read_text(encoding="utf-8"))
    predictions = raw.get("predictions") if isinstance(raw, dict) and isinstance(raw.get("predictions"), dict) else raw
    if not isinstance(predictions, dict):
        raise SystemExit("Predictions must be an object keyed by case ID.")
    result = evaluate_prediction_set(benchmark, predictions)
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
