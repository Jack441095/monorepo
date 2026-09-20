#!/usr/bin/env python3
"""Deterministically score KENN's causal-diagnosis contract."""
from __future__ import annotations
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "studio/kenn/kenn/evals/diagnostic_reasoning_cases.json"

def run() -> dict:
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "studio/kenn"))
    from kenn.core.chat import answer_payload
    from kenn.core.evidence import from_mix_review_context, from_plugin_context, history_turn
    from kenn.core.session_memory import clear_session
    data = json.loads(CASES.read_text(encoding="utf-8"))
    rows = []
    for case in data["cases"]:
        history = []
        plugin_context = case.get("plugin_context")
        if isinstance(plugin_context, dict):
            packet = from_plugin_context(plugin_context)
            if packet:
                history.append(history_turn(packet))
        mix_review_context = case.get("mix_review_context")
        if isinstance(mix_review_context, dict):
            packet = from_mix_review_context(mix_review_context)
            if packet:
                history.append(history_turn(packet))
        turns = case.get("turns")
        if isinstance(turns, list) and all(isinstance(turn, str) and turn.strip() for turn in turns):
            session_id = f"kenn-diagnostic-eval-{case['id']}-{uuid.uuid4().hex}"
            try:
                answer = ""
                for turn in turns:
                    answer = answer_payload(turn, allow_llm=False, session_id=session_id).get("answer", "")
            finally:
                clear_session(session_id)
        else:
            answer = answer_payload(case["question"], allow_llm=False, session_id="", history=history).get("answer", "")
        lowered = answer.lower()
        required = [item for item in case.get("must_include", []) if item.lower() not in lowered]
        alternatives = case.get("must_include_any", [])
        alternative_ok = not alternatives or any(item.lower() in lowered for item in alternatives)
        forbidden = [item for item in case.get("must_not_include", []) if item.lower() in lowered]
        ordered = case.get("must_appear_before", [])
        ordering_failures = [pair for pair in ordered if len(pair) != 2 or lowered.find(pair[0].lower()) < 0 or lowered.find(pair[1].lower()) < 0 or lowered.find(pair[0].lower()) >= lowered.find(pair[1].lower())]
        rows.append({"id": case["id"], "ok": not required and alternative_ok and not forbidden and not ordering_failures, "missing": required, "forbidden": forbidden, "ordering_failures": ordering_failures})
    return {"total": len(rows), "passed": sum(row["ok"] for row in rows), "rows": rows}

if __name__ == "__main__":
    report = run(); print(json.dumps(report, indent=2)); raise SystemExit(0 if report["passed"] == report["total"] else 1)
