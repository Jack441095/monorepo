#!/usr/bin/env python3
"""Cost accounting for a local brain answer: prompt tokens, and decode against a competing CPU load.

    measure_answer_cost.py [--receipt PATH] [--tokens-only] [--live-seconds 5.0] [--load-seconds 0] [--decode-tokens 300]

Three numbers that decide whether a 4 s answer latency is reachable, none of which `measure_chat_latency.py` records:

**Prompt tokens, exactly.** `measure_chat_latency.py` measures wall-clock; this reads Ollama's own `prompt_eval_count`,
so the D2 "tokens before and after" figure is a count and not a character estimate. It builds KENN's real synthesis
prompt through `_build_synthesis_messages` and sends it with `num_predict: 1` so the answer never runs and the prompt
is counted as the model actually tokenises it, not as Python counts characters.

**Prefill, against prompt size.** The claim that shortening the prompt cannot help is an arithmetic claim: if prefill
is small at both ends of the range, then it is small in between. Measured at three prompt sizes, with `prompt_eval_count`
and `prompt_eval_duration` from the same responses.

**Decode, idle and under load.** The question Track D exists to answer is whether Live is competing for the machine,
and the answer needs both halves measured the same way: the same generation, with and without a CPU load the size of
Live's. Live itself is never touched -- this runs a synthetic burner, because quitting the owner's DAW to take a
measurement is not ours to do, and because a controlled load is the more useful number anyway (it can be varied).

Only ever POSTs to a local Ollama. Read-only against Live and it never writes to one.

Needs the knowledge index for the token figures. `apps/backend/src/kenn/data/` is git-ignored, so run this from the
main checkout -- in a fresh worktree retrieval drops to BM25-only and the prompt is not the prompt KENN sends.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

KENN_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KENN_ROOT / "apps" / "backend" / "src"))

OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
CURRENT = KENN_ROOT / "apps" / "backend" / "src" / "kenn" / "data" / "index" / "CURRENT"
DEFAULT_CASES = KENN_ROOT / "apps" / "backend" / "src" / "kenn" / "evals" / "questions.json"


def _post(path: str, payload: dict, timeout: float = 900.0) -> dict:
    request = urllib.request.Request(f"{OLLAMA}{path}", json.dumps(payload).encode(),
                                     {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def _burn(stop) -> None:
    """A CPU load to stand in for Live. Busy-waits because the point is to occupy the same cores, not to allocate."""
    while not stop.is_set():
        sum(i * i for i in range(30_000))


def prompt_tokens(model: str, prompt: str) -> dict:
    """Ollama's own token count for a prompt, with the answer suppressed so only the prompt is paid for."""
    result = _post("/api/generate", {"model": model, "prompt": prompt, "stream": False,
                                     "options": {"num_predict": 1, "num_ctx": 8192}})
    return {
        "prompt_tokens": int(result.get("prompt_eval_count") or 0),
        "prefill_seconds": round(float(result.get("prompt_eval_duration", 0)) / 1e9, 4),
    }


def generate(model: str, decode_tokens: int, prompt_tokens_wanted: int) -> dict:
    """One fixed-length generation, so idle and loaded runs are comparable token for token."""
    prompt = "Explain sidechain compression to a mixing engineer. " * max(1, prompt_tokens_wanted // 7)
    started = time.perf_counter()
    result = _post("/api/generate", {"model": model, "prompt": prompt, "stream": False, "think": False,
                                     "options": {"num_predict": decode_tokens, "num_ctx": 8192}})
    wall = time.perf_counter() - started
    eval_ns = float(result.get("eval_duration") or 0)
    tokens = int(result.get("eval_count") or 0)
    return {
        "decode_tokens": tokens,
        "decode_seconds": round(eval_ns / 1e9, 3),
        "wall_seconds": round(wall, 3),
        "prefill_tokens": int(result.get("prompt_eval_count") or 0),
        "tokens_per_second": round(tokens / (eval_ns / 1e9), 2) if eval_ns else None,
    }


def live_cpu_seconds(seconds: float) -> dict:
    """How much CPU Ableton Live itself used over a window, read from process times rather than the lifetime average.

    `ps -o %cpu` on macOS reports the average since the process started, which for a DAW left open all day says more
    about when it was launched than about whether it is competing right now. The CPU time delta across a short window
    is the instantaneous figure, and it is the one that can be compared with a synthetic load of the same size.
    """
    needle = "Ableton Live"
    before: dict[int, float] = {}
    output = _ps_snapshot()
    for pid, (_, _, _, command) in output.items():
        if needle in command:
            before[pid] = _cpu_seconds(output[pid][2])
    if not before:
        return {"live_running": False}

    time.sleep(seconds)
    after = _ps_snapshot()
    used = {pid: _cpu_seconds(after[pid][2]) - before[pid]
            for pid in before if pid in after}
    # Live spawns helper processes; the main process is the one that decides whether the model is slowed.
    worst = max(used.values()) if used else 0.0
    return {
        "live_running": True,
        "window_seconds": seconds,
        "live_cpu_seconds": round(worst, 3),
        "live_percent_of_one_core": round(100 * worst / seconds, 1),
        "per_process_percent": {str(pid): round(100 * value / seconds, 1) for pid, value in used.items()},
    }


def _ps_snapshot() -> dict[int, tuple[str, str, str, str]]:
    import subprocess

    raw = subprocess.run(["ps", "-Ao", "pid,pcpu,time,comm"], capture_output=True, text=True).stdout
    rows: dict[int, tuple[str, str, str, str]] = {}
    for line in raw.splitlines()[1:]:
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        rows[int(parts[0])] = (parts[1], parts[2], parts[2], parts[3])
    return rows


def _cpu_seconds(ps_time: str) -> float:
    """`ps -o time` is [[dd-]hh:]mm:ss, so days and hours have to be handled before it is a float."""
    chunks = ps_time.strip().split(":")
    seconds = 0.0
    for chunk in chunks:
        seconds = seconds * 60 + float(chunk)
    return seconds


def measure(*, tokens_only: bool, decode_tokens: int, live_seconds: float, load_seconds: float,
            cases: list[dict]) -> dict:
    from kenn.core import session_memory
    from kenn.core.chat_retrieval import display_results, load_chunks, load_terms, search
    from kenn.llm.llm_rewrite import _build_synthesis_messages, config

    model = os.environ.get("KENN_LLM_MODEL", "")
    context_chars = os.environ.get("KENN_LLM_CONTEXT_CHARS")
    draft_chars = os.environ.get("KENN_LLM_DRAFT_CHARS")
    report: dict = {
        "schema": "kenn.answer_cost.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "index_version": CURRENT.read_text(encoding="utf-8").strip() if CURRENT.is_file() else "",
        "context_chars": context_chars or "(default 1200)",
        "draft_chars": draft_chars or "(default 300)",
        "interactive_timeout_seconds": config("rewrite")["timeout"],
    }
    if not model:
        report["error"] = "KENN_LLM_MODEL is not set"
        return report

    prompts: list[dict] = []
    chunks, terms = load_chunks(), load_terms()
    for case in cases:
        question = str(case.get("question") or "").strip()
        if not question:
            continue
        results = search(question, chunks, terms, limit=4)
        shown = display_results(question, results, limit=4)
        messages = _build_synthesis_messages(
            question,
            "Template answer used only as a structure reference in this measurement.",
            shown or results,
            [],
            "",
            lambda chunk: str(chunk.get("source") or "note")[:60],
            lambda history: [],
            answer_mode="chat",
            route="chat",
        )
        counted = prompt_tokens(model, "\n".join(str(m["content"]) for m in messages))
        by_role = {m["role"]: prompt_tokens(model, str(m["content"]))["prompt_tokens"] for m in messages}
        prompts.append({
            "id": str(case.get("id") or "unknown"),
            "question": question,
            "prompt_tokens": counted["prompt_tokens"],
            "system_tokens": by_role.get("system", 0),
            "user_tokens": by_role.get("user", 0),
        })

    report["prompts"] = prompts
    if prompts:
        totals = [p["prompt_tokens"] for p in prompts]
        report["prompt_tokens"] = {
            "mean": round(statistics.mean(totals), 1),
            "min": min(totals),
            "max": max(totals),
            "system_tokens": prompts[0]["system_tokens"],
            "user_tokens": prompts[0]["user_tokens"],
        }
    report["tokens_only"] = tokens_only
    if tokens_only:
        return report

    # Prefill across a wide prompt range: the claim is that prompt length does not move the needle, and that needs
    # measuring at both ends rather than argued from one point.
    prefill = []
    for wanted in (356, 1028):
        text = "Explain sidechain compression to a mixing engineer. " * max(1, wanted // 7)
        counted = prompt_tokens(model, text)
        prefill.append({"prompt_tokens": counted["prompt_tokens"], "prefill_seconds": counted["prefill_seconds"],
                        "requested_tokens": wanted})
    report["prefill"] = prefill

    # Warm the model in first, or the first decode pays a 3-4 s load and the idle figure is not comparable.
    generate(model, 16, 356)
    idle = generate(model, decode_tokens, 356)
    report["decode_idle"] = idle

    if load_seconds:
        stop = mp.Event()
        burners = [mp.Process(target=_burn, args=(stop,)) for _ in range(max(1, round(load_seconds)))]
        for process in burners:
            process.start()
        time.sleep(3)
        try:
            loaded = generate(model, decode_tokens, 356)
        finally:
            stop.set()
            for process in burners:
                process.join()
        report["decode_loaded"] = loaded
        report["load_cores"] = max(1, round(load_seconds))
        if idle["tokens_per_second"] and loaded["tokens_per_second"]:
            report["slowdown_ratio"] = round(idle["tokens_per_second"] / loaded["tokens_per_second"], 3)
    else:
        report["load_cores"] = 0
        report["note"] = "no --load-seconds given, so the loaded half of the Live split was not measured"

    report["live_cpu"] = live_cpu_seconds(live_seconds)
    return report


def render(report: dict) -> str:
    lines = ["Where an answer's time goes, and whether Live is competing for the machine",
             f"  model              {report.get('model') or '(unset)'}",
             f"  index              {report.get('index_version') or '(none in this checkout)'}",
             f"  context/draft chars {report.get('context_chars')} / {report.get('draft_chars')}",
             f"  ask-path timeout   {report.get('interactive_timeout_seconds')}s"]
    if report.get("error"):
        lines.append(f"  NOT MEASURED       {report['error']}")
        return "\n".join(lines)

    tokens = report.get("prompt_tokens") or {}
    if tokens:
        lines.append(f"  prompt tokens      mean {tokens['mean']}  (min {tokens['min']}, max {tokens['max']})"
                     f"  system {tokens['system_tokens']} + user {tokens['user_tokens']}")
    for row in report.get("prefill") or []:
        lines.append(f"  prefill            {row['prompt_tokens']:>5} tokens -> {row['prefill_seconds']}s")
    idle = report.get("decode_idle")
    if idle:
        lines.append(f"  decode idle        {idle['decode_tokens']} tokens in {idle['decode_seconds']}s"
                     f" = {idle['tokens_per_second']} tok/s")
    loaded = report.get("decode_loaded")
    if loaded:
        lines.append(f"  decode under load  {loaded['decode_tokens']} tokens in {loaded['decode_seconds']}s"
                     f" = {loaded['tokens_per_second']} tok/s"
                     f"  ({report['load_cores']} core(s), {report.get('slowdown_ratio')}x)")
    else:
        lines.append(f"  decode under load  not measured ({report.get('note')})")
    live = report.get("live_cpu") or {}
    if live.get("live_running"):
        lines.append(f"  Live CPU           {live['live_percent_of_one_core']}% of one core"
                     f" over a {live['window_seconds']}s window")
    else:
        lines.append("  Live CPU           Live is not running")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--limit", type=int, default=5, help="how many real KENN prompts to tokenise")
    parser.add_argument("--tokens-only", action="store_true", help="skip the decode and Live measurements")
    parser.add_argument("--decode-tokens", type=int, default=300)
    parser.add_argument("--live-seconds", type=float, default=5.0)
    parser.add_argument("--load-seconds", type=float, default=1.0,
                        help="cores of synthetic load; 0 skips the loaded half of the Live split")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()

    if not args.tokens_only and not CURRENT.is_file():
        print("answer-cost=NOT_MEASURED no retrieval index in this checkout", file=sys.stderr)
        print("apps/backend/src/kenn/data/ is git-ignored, so a fresh worktree has none and the prompt measured "
              "would not be the prompt KENN sends. Run from the main checkout.", file=sys.stderr)
        return 2

    cases = json.loads(args.cases.read_text(encoding="utf-8")).get("cases", [])[: args.limit]
    report = measure(tokens_only=args.tokens_only, decode_tokens=args.decode_tokens,
                     live_seconds=args.live_seconds, load_seconds=args.load_seconds, cases=cases)
    print(render(report))
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
        print(f"receipt written to {args.receipt}")
    return 1 if report.get("error") else 0


if __name__ == "__main__":
    try:
        urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=5)
    except urllib.error.URLError as exc:
        print(f"answer-cost=NOT_MEASURED cannot reach Ollama at {OLLAMA}: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
    raise SystemExit(main())