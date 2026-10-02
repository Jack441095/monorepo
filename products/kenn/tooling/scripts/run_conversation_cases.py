#!/usr/bin/env python3
"""Run scripted multi-turn conversations through the stream surface and record what each turn did.

    run_conversation_cases.py [--cases PATH] [--only ID] [--receipt PATH] [--answers PATH]

History is built the way the browser companion builds it: every earlier user turn and the answer KENN gave.
The receipt holds numbers and flags only. --answers writes the answer text as JSON, which must stay in scratch
because it is model prose.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

KENN_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KENN_ROOT / "apps" / "backend" / "src"))

DEFAULT_CASES = KENN_ROOT / "apps" / "backend" / "src" / "kenn" / "evals" / "five_turn_conversations.json"


def _ask(question: str, history: list[dict], session_id: str) -> tuple[dict, float, float | None]:
    from kenn.core import chat_answer

    started = time.perf_counter()
    ttft: float | None = None
    final: dict = {}
    for event in chat_answer.answer_payload_stream(question, history=history, session_id=session_id):
        if event.get("event") == "token" and ttft is None:
            ttft = time.perf_counter() - started
        elif event.get("event") == "metadata":
            final = event.get("data") or {}
    return final, time.perf_counter() - started, ttft


def run_conversation(conversation: dict) -> tuple[dict, list[dict]]:
    session_id = f"conv-{uuid.uuid4().hex[:12]}"
    history: list[dict] = []
    turns: list[dict] = []
    answers: list[dict] = []
    for number, question in enumerate(conversation["turns"], 1):
        try:
            final, seconds, ttft = _ask(question, list(history), session_id)
            error = None
        except Exception as exc:  # a crashed turn is a result, not a reason to stop the run
            final, seconds, ttft, error = {}, 0.0, None, f"{type(exc).__name__}: {exc}"
        validation = dict(final.get("generation_validation") or {})
        answer = str(final.get("answer") or "")
        turns.append({
            "turn": number,
            "seconds": round(seconds, 2),
            "ttft_seconds": round(ttft, 2) if ttft is not None else None,
            "route": final.get("route"),
            "answer_mode": final.get("answer_mode"),
            "used_history": bool(final.get("used_history")),
            "search_query_has_history": bool(final.get("search_query")) and final.get("search_query") != question,
            "attempted": bool(validation.get("attempted")),
            "accepted": bool(validation.get("accepted")),
            "llm_enhanced": bool(final.get("llm_enhanced")),
            "warnings": [str(w) for w in (validation.get("warnings") or [])],
            "sources": len(final.get("sources") or []),
            "confidence": final.get("confidence"),
            "found": bool(final.get("found")),
            "error": error,
        })
        answers.append({"turn": number, "question": question, "search_query": final.get("search_query"),
                        "answer": answer})
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": answer})
    return {"id": conversation["id"], "tests": conversation.get("tests", ""), "turns": turns}, answers


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--only", action="append", default=[], help="run just this conversation id (repeatable)")
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--answers", type=Path)
    args = parser.parse_args()

    conversations = json.loads(args.cases.read_text(encoding="utf-8"))["conversations"]
    if args.only:
        conversations = [c for c in conversations if c["id"] in args.only]
    results: list[dict] = []
    captured: dict[str, list[dict]] = {}
    for conversation in conversations:
        result, answers = run_conversation(conversation)
        results.append(result)
        captured[conversation["id"]] = answers
        print(f"{conversation['id']}: " + " ".join(
            ("A" if t["accepted"] else "F" if t["attempted"] else "-") + f"{t['seconds']:.0f}s" for t in result["turns"]
        ), flush=True)

    turns = [t for r in results for t in r["turns"]]
    report = {
        "schema": "kenn.conversation_cases.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "counts": {
            "conversations": len(results),
            "turns": len(turns),
            "attempted": sum(t["attempted"] for t in turns),
            "accepted": sum(t["accepted"] for t in turns),
            "errors": sum(bool(t["error"]) for t in turns),
        },
        "conversations": results,
    }
    print(json.dumps(report["counts"]))
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    if args.answers:
        args.answers.write_text(json.dumps(captured, indent=1) + "\n", encoding="utf-8")
    return 1 if report["counts"]["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
