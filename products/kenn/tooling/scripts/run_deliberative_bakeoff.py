#!/usr/bin/env python3
"""Run repeated KENN planner holdout/adversarial evaluations by model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "backend" / "src"))

from kenn.core.deliberative_bakeoff import (  # noqa: E402
    aggregate_bakeoff_runs,
    write_bakeoff_checkpoint,
)
from kenn.core.deliberative_benchmark import evaluate_prediction_set, load_benchmark  # noqa: E402
from kenn.core.model_recovery_eval import evaluate_model_recovery_attacks  # noqa: E402
from kenn.core.ollama_deliberative import validate_ollama_base_url  # noqa: E402


DEFAULT_BENCHMARKS = (
    ROOT / "packages" / "chat" / "evals" / "ableton_deliberative_holdout.json",
    ROOT / "packages" / "chat" / "evals" / "ableton_deliberative_adversarial.json",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", action="append", dest="models", default=[])
    parser.add_argument("--benchmark", action="append", type=Path, dest="benchmarks", default=[])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    models = [str(item).strip()[:128] for item in args.models if str(item).strip()]
    if not models:
        models = ["qwen2.5:7b-instruct"]
    benchmarks = [path.resolve() for path in args.benchmarks] or list(DEFAULT_BENCHMARKS)
    repeats = max(1, min(20, int(args.repeats)))
    base_url = validate_ollama_base_url(args.base_url)
    runs: list[dict] = []
    expected_run_count = len(models) * len(benchmarks) * repeats

    def checkpoint(status: str) -> dict:
        current = aggregate_bakeoff_runs(runs)
        write_bakeoff_checkpoint(
            args.output,
            current,
            status=status,
            expected_run_count=expected_run_count,
        )
        return current

    checkpoint("running")

    with tempfile.TemporaryDirectory(prefix="kenn-bakeoff-") as directory:
        temporary = Path(directory)
        for model in models:
            for benchmark_path in benchmarks:
                benchmark = load_benchmark(benchmark_path)
                for repeat in range(1, repeats + 1):
                    prediction_path = temporary / f"predictions-{len(runs)}.json"
                    command = [
                        sys.executable,
                        "tooling/scripts/run_deliberative_ollama.py",
                        "--benchmark", str(benchmark_path),
                        "--model", model,
                        "--base-url", base_url,
                        "--timeout-seconds", str(max(1.0, args.timeout_seconds)),
                        "--output", str(prediction_path),
                    ]
                    completed = subprocess.run(
                        command, cwd=ROOT, capture_output=True, text=True, check=False,
                        timeout=max(60.0, args.timeout_seconds * len(benchmark["cases"]) + 60.0),
                    )
                    if completed.returncode != 0 or not prediction_path.is_file():
                        runs.append({
                            "schema": "kenn.deliberative_benchmark_result.v1",
                            "benchmark_id": benchmark.get("benchmark_id", "unknown"),
                            "model_id": model,
                            "repeat": repeat,
                            "passed": False,
                            "pass_rate": 0.0,
                            "mean_score": 0.0,
                            "contract_valid_rate": 0.0,
                            "safety_pass_rate": 0.0,
                            "latency": {"mean_ms": None},
                            "runner_error": (completed.stderr or completed.stdout or "runner failed")[-2_000:],
                        })
                        checkpoint("running")
                        continue
                    prediction_set = json.loads(prediction_path.read_text(encoding="utf-8"))
                    evaluation = evaluate_prediction_set(
                        benchmark, prediction_set.get("predictions") or {},
                    )
                    recovery = None
                    benchmark_case_ids = {
                        str(case.get("id") or "") for case in benchmark.get("cases", [])
                        if isinstance(case, dict)
                    }
                    if {"kick_bass_masking", "preference_not_diagnosis"} <= benchmark_case_ids:
                        recovery = evaluate_model_recovery_attacks(
                            benchmark, prediction_set.get("predictions") or {},
                            temporary / f"recovery-{len(runs)}",
                        )
                    runs.append({
                        **evaluation,
                        "model_id": model,
                        "repeat": repeat,
                        "predictions": prediction_set.get("predictions") or {},
                        **({"model_recovery": recovery} if recovery is not None else {}),
                    })
                    checkpoint("running")
                    print(
                        f"{model} {benchmark.get('benchmark_id')} repeat {repeat}: "
                        f"{evaluation['passed_count']}/{evaluation['case_count']}",
                        flush=True,
                    )

    result = checkpoint("complete")
    print(json.dumps({
        "status": "complete",
        "output": str(args.output),
        "model_count": result["model_count"],
        "run_count": result["run_count"],
        "recommended_model": result["recommended_model"],
    }, indent=2))
    return 0 if result["eligible_model_count"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
