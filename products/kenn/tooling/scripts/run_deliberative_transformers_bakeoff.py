#!/usr/bin/env python3
"""Run KENN's repeated planner bake-off from one offline Transformers process.

This runner is intended for a shared GPU host where starting or restarting an
inference service is prohibited.  The caller selects GPUs with
CUDA_VISIBLE_DEVICES.  The model is loaded once, all artifacts stay below the
declared data root, and completed suite receipts are checkpointed atomically.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "backend" / "src"))

from kenn.core.deliberative_bakeoff import (  # noqa: E402
    aggregate_bakeoff_runs,
    write_bakeoff_checkpoint,
)
from kenn.core.deliberative_benchmark import (  # noqa: E402
    build_benchmark_context,
    evaluate_prediction_set,
    load_benchmark,
)
from kenn.core.deliberative_plan import hydrate_deliberative_plan_sketch  # noqa: E402
from kenn.core.deliberative_planner import (  # noqa: E402
    build_deliberative_sketch_prompt,
    complete_deliberative_sketch_contract,
    deliberative_preflight_plan,
    parse_deliberative_output,
)
from kenn.core.model_recovery_eval import evaluate_model_recovery_attacks  # noqa: E402


DEFAULT_BENCHMARKS = (
    ROOT / "packages" / "chat" / "evals" / "ableton_deliberative_holdout.json",
    ROOT / "packages" / "chat" / "evals" / "ableton_deliberative_adversarial.json",
)
EVIDENCE_BOUND_INPUTS = (
    ROOT / "tooling" / "scripts" / "run_deliberative_transformers_bakeoff.py",
    ROOT / "apps" / "backend" / "src" / "kenn" / "core" / "deliberative_plan.py",
    ROOT / "apps" / "backend" / "src" / "kenn" / "core" / "deliberative_planner.py",
    ROOT / "apps" / "backend" / "src" / "kenn" / "core" / "deliberative_benchmark.py",
    ROOT / "apps" / "backend" / "src" / "kenn" / "core" / "deliberative_bakeoff.py",
    ROOT / "apps" / "backend" / "src" / "kenn" / "core" / "model_recovery_eval.py",
)


def evidence_input_sha256(benchmarks: list[Path]) -> dict[str, str]:
    """Bind a receipt to every policy/evaluator/benchmark input it measures."""
    paths = [*EVIDENCE_BOUND_INPUTS, *benchmarks]
    return {
        str(path.resolve().relative_to(ROOT.resolve())): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
    }


class FatalInferenceError(RuntimeError):
    """A provider/runtime failure that invalidates the whole model comparison."""


def _is_fatal_inference_error(exc: Exception) -> bool:
    """Separate unavailable inference machinery from rejectable model output.

    JSON/contract errors are useful model-quality evidence and remain scoped to
    one case. Missing Python modules or model kernels mean no model inference
    occurred, so repeating them across the sealed suite would create a
    misleading completed bake-off.
    """
    return isinstance(exc, (ImportError, ModuleNotFoundError))


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def validate_data_paths(*, model_path: Path, output: Path, data_root: Path) -> tuple[Path, Path, Path]:
    root = data_root.resolve()
    model = model_path.resolve()
    destination = output.resolve()
    if not root.is_dir():
        raise ValueError(f"Data root does not exist: {root}")
    if not model.is_dir() or not _inside(model, root):
        raise ValueError("Model path must be an existing directory below the data root.")
    if not _inside(destination, root):
        raise ValueError("Output path must remain below the data root.")
    return model, destination, root


def _model_id(model_path: Path, explicit: str) -> str:
    return (str(explicit).strip() or model_path.name)[:128]


def _generation_inputs(encoded: Any, device: Any) -> tuple[dict[str, Any], int]:
    moved = encoded.to(device)
    if hasattr(moved, "keys"):
        if "input_ids" not in moved:
            raise ValueError("Tokenizer batch did not contain input_ids.")
        inputs = {key: moved[key] for key in moved.keys()}
    else:
        inputs = {"input_ids": moved}
    input_ids = inputs["input_ids"]
    shape = getattr(input_ids, "shape", None)
    if shape is None or len(shape) < 2:
        raise ValueError("Tokenizer returned invalid input_ids dimensions.")
    return inputs, int(shape[-1])


def _generate(model: Any, tokenizer: Any, torch: Any, prompt: str, max_output_tokens: int) -> str:
    messages = [{"role": "user", "content": prompt}]
    template_kwargs = {
        "tokenize": True,
        "add_generation_prompt": True,
        "return_tensors": "pt",
        "enable_thinking": False,
    }
    try:
        input_ids = tokenizer.apply_chat_template(messages, **template_kwargs)
    except TypeError:
        template_kwargs.pop("enable_thinking")
        input_ids = tokenizer.apply_chat_template(messages, **template_kwargs)
    model_inputs, input_length = _generation_inputs(input_ids, model.device)
    with torch.inference_mode():
        generated = model.generate(
            **model_inputs,
            max_new_tokens=max(128, min(2_048, int(max_output_tokens))),
            do_sample=False,
            use_cache=True,
            pad_token_id=tokenizer.eos_token_id,
        )
    return tokenizer.decode(generated[0, input_length:], skip_special_tokens=True).strip()


def _predict_suite(
    *,
    benchmark: dict[str, Any],
    model: Any,
    tokenizer: Any,
    torch: Any,
    model_id: str,
    max_output_tokens: int,
) -> dict[str, dict[str, Any]]:
    predictions: dict[str, dict[str, Any]] = {}
    cases = benchmark["cases"]
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
                raw = _generate(
                    model, tokenizer, torch,
                    build_deliberative_sketch_prompt(goal, context),
                    max_output_tokens,
                )
                sketch = complete_deliberative_sketch_contract(
                    parse_deliberative_output(raw)
                )
                plan = hydrate_deliberative_plan_sketch(
                    sketch,
                    goal=goal,
                    context=context,
                    model_provider="transformers",
                    model_id=model_id,
                )
            error = ""
        except Exception as exc:
            if _is_fatal_inference_error(exc):
                raise FatalInferenceError(
                    f"Inference runtime failed on case {case_id}: "
                    f"{type(exc).__name__}: {exc}"
                ) from exc
            plan = None
            error = f"{type(exc).__name__}: {exc}"[:1_000]
        latency_ms = round((time.perf_counter() - started) * 1_000, 3)
        predictions[case_id] = {
            "model_provider": "transformers",
            "model_id": model_id,
            "planner_source": planner_source,
            "latency_ms": latency_ms,
            "plan": plan,
            "sketch": sketch,
            "error": error,
            "raw_output": raw[:20_000],
        }
        print(f"[{position}/{len(cases)}] {case_id}: {'ok' if plan else error}", flush=True)
    return predictions


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--model-id", default="")
    parser.add_argument("--benchmark", action="append", type=Path, dest="benchmarks", default=[])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--max-output-tokens", type=int, default=320)
    parser.add_argument("--max-memory-per-gpu", default="22GiB")
    parser.add_argument("--expected-visible-gpus", type=int, default=4)
    parser.add_argument("--data-root", type=Path, default=Path("/mnt/data"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    model_path, output, data_root = validate_data_paths(
        model_path=args.model_path, output=args.output, data_root=args.data_root,
    )
    benchmarks = [path.resolve() for path in args.benchmarks] or list(DEFAULT_BENCHMARKS)
    input_sha256 = evidence_input_sha256(benchmarks)
    repeats = max(1, min(20, int(args.repeats)))
    expected_run_count = len(benchmarks) * repeats
    model_id = _model_id(model_path, args.model_id)
    runs: list[dict[str, Any]] = []

    def checkpoint(status: str, *, fatal_error: str = "") -> dict[str, Any]:
        result = aggregate_bakeoff_runs(runs)
        result.update({
            "provider": "transformers",
            "model_path": str(model_path),
            "data_root": str(data_root),
            "visible_gpu_ids": str(os.environ.get("CUDA_VISIBLE_DEVICES") or ""),
            "input_sha256": input_sha256,
        })
        if fatal_error:
            result["fatal_error"] = fatal_error[:2_000]
        write_bakeoff_checkpoint(
            output, result, status=status, expected_run_count=expected_run_count,
        )
        return result

    checkpoint("loading")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        visible_count = torch.cuda.device_count()
        if visible_count != int(args.expected_visible_gpus):
            raise RuntimeError(
                f"Expected {args.expected_visible_gpus} visible GPUs but found {visible_count}; "
                "refusing to widen or guess GPU scope."
            )
        max_memory = {
            index: str(args.max_memory_per_gpu) for index in range(visible_count)
        }
        tokenizer = AutoTokenizer.from_pretrained(
            model_path, local_files_only=True, trust_remote_code=False,
        )
        model = AutoModelForCausalLM.from_pretrained(
            model_path,
            local_files_only=True,
            trust_remote_code=False,
            device_map="auto",
            torch_dtype="auto",
            low_cpu_mem_usage=True,
            max_memory=max_memory,
        )
        model.eval()
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        checkpoint("failed", fatal_error=error)
        print(error, file=sys.stderr)
        return 2

    try:
        for repeat in range(1, repeats + 1):
            for benchmark in (load_benchmark(path) for path in benchmarks):
                predictions = _predict_suite(
                    benchmark=benchmark,
                    model=model,
                    tokenizer=tokenizer,
                    torch=torch,
                    model_id=model_id,
                    max_output_tokens=args.max_output_tokens,
                )
                evaluation = evaluate_prediction_set(benchmark, predictions)
                recovery = None
                case_ids = {
                    str(case.get("id") or "") for case in benchmark.get("cases", [])
                    if isinstance(case, dict)
                }
                if {"kick_bass_masking", "preference_not_diagnosis"} <= case_ids:
                    recovery = evaluate_model_recovery_attacks(benchmark, predictions)
                runs.append({
                    **evaluation,
                    "model_id": model_id,
                    "repeat": repeat,
                    "predictions": predictions,
                    **({"model_recovery": recovery} if recovery is not None else {}),
                })
                checkpoint("running")
                print(
                    f"{model_id} {benchmark.get('benchmark_id')} repeat {repeat}: "
                    f"{evaluation['passed_count']}/{evaluation['case_count']}",
                    flush=True,
                )
    except FatalInferenceError as exc:
        error = f"{type(exc).__name__}: {exc}"
        checkpoint("failed", fatal_error=error)
        print(error, file=sys.stderr)
        return 2

    result = checkpoint("complete")
    print(json.dumps({
        "status": "complete",
        "output": str(output),
        "run_count": result["run_count"],
        "recommended_model": result["recommended_model"],
    }, indent=2))
    return 0 if result["eligible_model_count"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
