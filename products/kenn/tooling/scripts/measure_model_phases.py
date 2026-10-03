#!/usr/bin/env python3
"""Measure model phases and an optional answer cap on both chat surfaces.

Run with the handoff's real-model environment and fake Live. Session storage and
answer samples go into a new temporary directory; the receipt contains no prose.
Native terminal metrics are unknown when the prefix guard closes a stream early.
This diagnostic cannot certify the release gate, which needs supervised Live.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path

from scripts import measure_chat_latency as latency

CASE_IDS = (
    "bass-processing", "sidechain-release-time", "reverb-send",
    "gain-staging", "streaming-loudness",
)
_CAP_ACTIVE = ContextVar("measurement_answer_cap", default=False)


def phases(call: dict) -> dict:
    prefill = call.get("prompt_eval_duration_ns")
    decode = call.get("eval_duration_ns")
    count = call.get("completion_tokens")
    return {
        **call,
        "prefill_seconds": prefill / 1e9 if prefill is not None else None,
        "decode_seconds": decode / 1e9 if decode is not None else None,
        "decode_tokens_per_second": count * 1e9 / decode
        if count is not None and decode is not None and decode > 0 else None,
    }


def gate_counts(rows: list[dict]) -> dict:
    # Never-attempted and rejected requests remain in the eligible denominator.
    hits = sum(row["accepted"] and not row["error_type"] and row["seconds"] <= 15 for row in rows)
    return {
        "eligible": len(rows),
        "attempted": sum(row["attempted"] for row in rows),
        "accepted": sum(row["accepted"] for row in rows),
        "accepted_within_15_seconds": hits,
        "fraction": hits / len(rows) if rows else None,
    }


def answer_outcome(payload: dict, usages, surface: str) -> dict:
    validation = payload.get("generation_validation") or {}
    # Payload delivery exposes the accepted rewrite through llm_enhanced; only
    # streams carry the final grounding verdict. Provider attempts cover both.
    return {
        "attempted": bool(validation.get("attempted")) or any(
            usage.task == "rewrite" and usage.provider_attempted for usage in usages
        ),
        "accepted": bool(payload.get("llm_enhanced")) if surface == "payload"
        else bool(validation.get("accepted")),
        "warnings": validation.get("warnings"),
    }


@contextmanager
def observe_generation(llm, output_cap: int | None):
    """Observe candidates without draining a stream the grounding guard closed."""
    calls = []
    native, compatible = llm._build_native_ollama_payload, llm._build_payload
    streaming, completion = llm.chat_completion_stream, llm._chat_completion

    def native_payload(*args, **kwargs):
        payload = native(*args, **kwargs)
        if output_cap is not None and _CAP_ACTIVE.get():
            payload["options"]["num_predict"] = min(output_cap, payload["options"]["num_predict"])
        return payload

    def compatible_payload(*args, **kwargs):
        payload = compatible(*args, **kwargs)
        if output_cap is not None and _CAP_ACTIVE.get():
            payload["max_tokens"] = min(output_cap, payload["max_tokens"])
        return payload

    def start(task, kwargs):
        eligible = task == "rewrite" and kwargs.get("answer_mode", "") not in {
            "action_preview", "action_receipt", "command",
        } and not kwargs.get("json_mode") and kwargs.get("json_schema") is None
        token = _CAP_ACTIVE.set(eligible)
        row = {"task": task, "answer_mode": kwargs.get("answer_mode", ""),
               "generation_ttft_seconds": None, "candidate": ""}
        calls.append(row)
        return token, row, time.perf_counter()

    def stream(messages, task="rewrite", **kwargs):
        token, row, started = start(task, kwargs)
        generator = streaming(messages, task=task, **kwargs)
        try:
            for chunk, usage in generator:
                if chunk:
                    if row["generation_ttft_seconds"] is None:
                        row["generation_ttft_seconds"] = time.perf_counter() - started
                    row["candidate"] += chunk
                yield chunk, usage
        finally:
            # Closing here preserves interrupted-attempt telemetry and avoids extra decode.
            generator.close()
            _CAP_ACTIVE.reset(token)

    def nonstream(messages, task="rewrite", **kwargs):
        token, row, _started = start(task, kwargs)
        try:
            answer, usage = completion(messages, task=task, **kwargs)
            row["candidate"] = answer
            return answer, usage
        finally:
            _CAP_ACTIVE.reset(token)

    llm._build_native_ollama_payload, llm._build_payload = native_payload, compatible_payload
    llm.chat_completion_stream, llm._chat_completion = stream, nonstream
    try:
        yield calls
    finally:
        llm._build_native_ollama_payload, llm._build_payload = native, compatible
        llm.chat_completion_stream, llm._chat_completion = streaming, completion


def _command(*args) -> str:
    result = subprocess.run(args, capture_output=True, text=True, timeout=10, check=False)
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def mac_state() -> dict:
    commands = _command("ps", "-axo", "comm=").splitlines()
    apps = sorted({line.split("/Applications/", 1)[1].split(".app/", 1)[0]
                   for line in commands if "/Applications/" in line and ".app/" in line})
    return {
        "at": datetime.now(timezone.utc).isoformat(),
        "cpu": _command("sysctl", "-n", "machdep.cpu.brand_string"),
        "memory_bytes": _command("sysctl", "-n", "hw.memsize"),
        "applications": apps,
        "live_process_present": any("Ableton Live" in line for line in commands),
        "vm_stat": _command("vm_stat"),
        "swap_usage": _command("sysctl", "-n", "vm.swapusage"),
        "ollama_version": _command("ollama", "--version"),
        "ollama_residency": _command("ollama", "ps"),
    }


def measure(cases: list[dict], runtime: Path, output_cap: int | None) -> dict:
    from kenn.core import chat_answer
    from kenn.llm import llm_rewrite as llm

    before = mac_state()
    configs = {task: {key: llm.config(task)[key] for key in ("enabled", "provider", "model", "timeout")}
               for task in ("rewrite", "route", "paraphrase", "followups")}
    rows = []
    with observe_generation(llm, output_cap) as generations:
        for surface in ("stream", "payload"):
            for case in cases:
                first_call = len(generations)
                started = time.perf_counter()
                with llm.capture_usage() as usages:
                    try:
                        payload, events, ttft = latency._ask(
                            chat_answer, case["question"], allow_llm=True, surface=surface,
                        )
                        error_type = None
                    except Exception as exc:
                        payload, events, ttft = {}, 0, None
                        error_type = type(exc).__name__
                seconds = time.perf_counter() - started
                observed = generations[first_call:]
                row = {
                    "id": case["id"], "surface": surface, "seconds": seconds,
                    "delivered_ttft_seconds": ttft, "stream_events": events,
                    **answer_outcome(payload, usages, surface), "error_type": error_type,
                    "provider_calls": [phases(usage.to_dict()) for usage in usages],
                    "generation_calls": [{k: v for k, v in call.items() if k != "candidate"}
                                         for call in observed],
                }
                rows.append(row)
                with (runtime / "answers.jsonl").open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps({"id": case["id"], "surface": surface,
                                             "accepted": row["accepted"], "generations": observed,
                                             "delivered_answer": payload.get("answer") or ""}) + "\n")
                print(json.dumps(row), flush=True)
    return {
        "schema": "kenn.model_phases.v1", "generated_at": datetime.now(timezone.utc).isoformat(),
        "code_commit": _command("git", "rev-parse", "HEAD"),
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "questions_sha256": hashlib.sha256(json.dumps(cases, sort_keys=True).encode()).hexdigest(),
        "index_version": latency._index_version(), "output_cap": output_cap,
        "task_configs": configs, "context_chars": llm.resolve_context_chars(),
        "thinking_off": llm._ollama_think_off(llm.config(), None),
        "default_output_tokens": llm.DEFAULT_MAX_TOKENS,
        "keep_alive": llm.KEEP_ALIVE_DURATION,
        "mac_before": before, "mac_after": mac_state(),
        "release_gate_evaluated": False,
        "limits": ["Fake Live; five selected knowledge questions per surface, one pass",
                   "Warm residency and Ollama prompt cache are not reset",
                   "Generation TTFT starts at the completion function; delivered TTFT starts at chat entry",
                   "Payload TTFT and interrupted native phase timings remain unknown"],
        "counts": {surface: gate_counts([r for r in rows if r["surface"] == surface])
                   for surface in ("stream", "payload")},
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output-cap", type=int)
    parser.add_argument("--runtime-dir", type=Path)
    args = parser.parse_args()
    if args.output_cap is not None and args.output_cap <= 0:
        parser.error("--output-cap must be positive")
    required = {"KENN_LLM_ENABLED": "1", "KENN_LLM_PROVIDER": "ollama",
                "KENN_LLM_MODEL": "kenn-brain-qwen3-8b", "KENN_LLM_CACHE": "0",
                "KENN_LIVE_BACKEND": "fake"}
    if any(os.environ.get(key) != value for key, value in required.items()):
        parser.error("use the handoff real-model environment with response caching off and fake Live")
    if not latency._index_version():
        parser.error("existing retrieval index required; this harness never rebuilds it")
    runtime = args.runtime_dir
    if runtime is None:
        runtime = Path(tempfile.mkdtemp(prefix="kenn-model-phases-"))
    else:
        runtime.mkdir(parents=True, exist_ok=False)
    os.environ["KENN_CHATS_DIR"] = str(runtime / "chats")
    os.environ["KENN_DB_PATH"] = str(runtime / "kenn.db")
    from kenn.llm import llm_rewrite as llm

    for task in ("rewrite", "route", "paraphrase", "followups"):
        cfg = llm.config(task)
        if cfg["provider"] != "ollama" or cfg["model"] != required["KENN_LLM_MODEL"] or llm.mlx_selected(task):
            parser.error(f"{task} must use the handoff Ollama model without a backend override")
    if not llm._ollama_think_off(llm.config(), None):
        parser.error("the baseline requires the existing thinking-off setting")
    corpus = json.loads(latency.DEFAULT_CASES.read_text(encoding="utf-8"))["cases"]
    by_id = {case["id"]: case for case in corpus}
    cases = [by_id[case_id] for case_id in CASE_IDS]
    report = measure(cases, runtime, args.output_cap)
    (runtime / "receipt.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"counts": report["counts"], "runtime_dir": str(runtime)}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
