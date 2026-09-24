#!/usr/bin/env python3
"""Score owner-written test commands against KENN's planners (the independent C6 check).

Input is the review page's `tests` collection exported as JSON files (one
document per file, e.g. ArtifactData with ``out_dir``) or a JSONL file with
``query``, ``expected_action`` and optional ``expected_track``. Every command
runs through the rule parser (what KENN does today) and, with ``--model``,
through the LLM planner on the demo snapshot the way the gateway calls it
(parameter evidence for device requests). Nothing touches Live.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

KENN_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KENN_ROOT / "apps" / "backend" / "src"))


def load_tests(source: Path, kind: str = "owner_written") -> list[dict[str, Any]]:
    if source.is_dir():
        rows = []
        for path in sorted(source.rglob("*.json")):
            doc = json.loads(path.read_text(encoding="utf-8"))
            rows.append(doc.get("data", doc))
    else:
        rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [r for r in rows if r.get("source", "owner_written") == kind and r.get("query")]


def rule_parser_result(query: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    from kenn.core.live_intent import parse_natural_recipe, parse_request

    # As the gateway does: a supported multi-step request is a recipe first.
    recipe = parse_natural_recipe(query, snapshot)
    if recipe is not None:
        ok = not recipe.get("ambiguity") and bool(recipe.get("steps") or recipe.get("step_intents"))
        return {"action": "recipe" if ok else "clarify", "track": None, "detail": recipe.get("ambiguity") or ""}
    parsed = parse_request(query, snapshot)
    unresolved = bool(parsed.get("missing_fields") or parsed.get("ambiguity")) or not parsed.get("action")
    return {"action": "clarify" if unresolved else parsed.get("action"),
            "track": (parsed.get("track") or {}).get("name"), "detail": parsed.get("ambiguity") or ""}


def describe_plan(plan: dict[str, Any] | None) -> str:
    if not plan:
        return ""
    parts = [str(plan.get("action"))]
    if plan.get("track_name"):
        parts.append(str(plan["track_name"]))
    if plan.get("value") is not None:
        unit = plan.get("unit") or ""
        parts.append(f"{'by ' if plan.get('relative') else ''}{plan['value']}{(' ' + unit) if unit else ''}")
    if plan.get("clarification"):
        parts.append(f"asks: {plan['clarification']}")
    return " · ".join(parts)


def matches(expected: dict[str, Any], action: str | None, track: str | None) -> bool:
    if action != expected["expected_action"]:
        return False
    return not expected.get("expected_track") or expected["expected_action"] == "clarify" or track == expected["expected_track"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source_path", type=Path, help="exported tests directory or JSONL file")
    parser.add_argument("--model", help="also score this Ollama planner model (e.g. kenn-c6-run4)")
    parser.add_argument("--compact-prompt", action="store_true", help="use the compact planner prompt (fine-tunes)")
    parser.add_argument("--source", default="owner_written",
                        help="which commands to score: owner_written (independent) or claude_written")
    args = parser.parse_args()

    tests = load_tests(args.source_path, args.source)
    from kenn.core.fake_live import FakeLiveBackend

    fake = FakeLiveBackend()
    snapshot = fake.query_session_state()
    if args.model:
        os.environ.update({"KENN_LIVE_LLM_ENABLED": "1", "KENN_LLM_ENABLED_COMMAND": "1", "KENN_LLM_PROVIDER_COMMAND": "ollama",
                           "KENN_LLM_MODEL_COMMAND": args.model, "KENN_LLM_THINK": "off", "KENN_LLM_CACHE": "0",
                           "AUDIO_TOO_LLM_TIMEOUT": os.environ.get("AUDIO_TOO_LLM_TIMEOUT", "60")})
        if args.compact_prompt:
            os.environ["KENN_LLM_COMMAND_PROMPT"] = "compact"
        from kenn.core import live_command
        from kenn.core.live_action_service import LiveActionService
        from kenn.core.live_intent import parse_request

        service = LiveActionService(fake)

    results = []
    for test in tests:
        row = {"query": test["query"], "expected": test["expected_action"], "expected_track": test.get("expected_track"),
               "note": test.get("note")}
        rule = rule_parser_result(test["query"], snapshot)
        row["rule"] = {**rule, "pass": matches(test, rule["action"], rule["track"])}
        if args.model:
            planner_snapshot = live_command._llm_planner_snapshot(service, snapshot, parse_request(test["query"], snapshot))
            plan, meta = live_command._generate_llm_plan(test["query"], planner_snapshot)
            row["model"] = {"status": meta.get("status"), "plan": plan, "summary": describe_plan(plan),
                            "error": meta.get("error") or meta.get("reason"),
                            "pass": plan is not None and matches(test, plan.get("action"), plan.get("track_name"))}
        results.append(row)

    for row in results:
        target = row["expected"] + (f" on {row['expected_track']}" if row["expected_track"] else "")
        print(f"\n“{row['query']}”  → expected: {target}" + (f"  (note: {row['note']})" if row["note"] else ""))
        rule = row["rule"]
        print(f"  rule parser: {'PASS' if rule['pass'] else 'FAIL'}  {rule['action']}" + (f" on {rule['track']}" if rule["track"] else ""))
        if "model" in row:
            model = row["model"]
            detail = model["summary"] or f"{model['status']}: {model['error']}"
            print(f"  {args.model}: {'PASS' if model['pass'] else 'FAIL'}  {detail}")
    total = len(results)
    if total:
        print(f"\nRule parser: {sum(r['rule']['pass'] for r in results)}/{total}"
              + (f" · {args.model}: {sum(r['model']['pass'] for r in results)}/{total}" if args.model else ""))
    else:
        print(f"No {args.source} tests found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
