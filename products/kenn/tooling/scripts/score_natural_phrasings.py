#!/usr/bin/env python3
"""Score natural phrasings through the whole command gateway (Stage 1 gate: >= 95% correct on >= 500 phrasings).

Each phrasing goes through ``handle_command`` on a fresh demo set, the same path the app uses (rule parser,
corrections, recipes), so nothing touches Live. With ``--model``, every phrasing the rules asked about is also given
to that planner model directly (as planner_bakeoff does), which shows what "rules first, planner when the rules ask"
would add. That never changes KENN's own planner stage, which only the promotion review sets. Every result is one of:

  right      the proposal (or answer) has the expected action, track and value
  asked      KENN asked instead of acting on something it could have done: safe, but counts against the 95%
  wrong      KENN proposed something other than what was meant, or acted when it should have asked

A wrong plan is the number that matters most: a producer who presses Apply on one gets a change they didn't ask for.

    score_natural_phrasings.py                        # both holdout files, rule path only
    score_natural_phrasings.py --model kenn-c6-run9b  # plus the planner on what the rules asked about
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

KENN_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(KENN_ROOT / "apps" / "backend" / "src"), str(KENN_ROOT / "tooling" / "scripts")]
DATA = KENN_ROOT / "tooling" / "data"
DEFAULT_SOURCES = [DATA / "natural_holdout.jsonl", DATA / "natural_holdout_candidates.jsonl"]
VALUE_TOLERANCE = 0.005  # normalized, as score_owner_tests: about 0.2 dB near 0 dB, 0.5% of pan
_ASKED = {"clarification_required", "refused", "unsupported", "invalid", "blocked"}


def _isolate(model: str | None) -> None:
    tmp = Path(tempfile.mkdtemp(prefix="kenn-phrasings-"))
    os.environ.update({"KENN_LIVE_RECEIPT_JOURNAL": str(tmp / "receipts.jsonl"),
                       "KENN_LIVE_LLM_SHADOW_LOG": str(tmp / "shadow.jsonl"), "KENN_DB_PATH": str(tmp / "kenn.db"),
                       "KENN_SESSION_FILE": str(tmp / "session.json"), "KENN_CHATS_DIR": str(tmp / "chats"),
                       "KENN_ROUTE_LOG": str(tmp / "routes.jsonl"), "KENN_ALLOW_DAW_CONTROL": "1"})
    for name in ("KENN_LIVE_LLM_ENABLED", "KENN_LLM_ENABLED", "KENN_LLM_ENABLED_COMMAND", "KENN_LIVE_LLM_MODE"):
        os.environ.pop(name, None)
    if model:
        # Enables the planner call below; the gateway still runs with allow_llm=False and the stage stays as reviewed.
        os.environ.update({"KENN_LIVE_LLM_ENABLED": "1", "KENN_LLM_ENABLED": "1", "KENN_LLM_ENABLED_COMMAND": "1",
                           "KENN_LLM_PROVIDER_COMMAND": "ollama",
                           "KENN_LLM_MODEL_COMMAND": model, "KENN_LLM_THINK": "off", "KENN_LLM_CACHE": "0"})


def load(sources: list[Path]) -> list[dict[str, Any]]:
    rows = []
    for source in sources:
        rows += [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows


def outcome(result: dict[str, Any]) -> dict[str, Any]:
    """What the gateway would do: an action with its track and value, or "clarify"."""
    proposal = result.get("proposal") if isinstance(result.get("proposal"), dict) else None
    if proposal:
        recipe = "recipe" in str(proposal.get("schema") or "") or proposal.get("steps")
        action = "recipe" if recipe else proposal.get("action") or proposal.get("operation")
        after = proposal.get("after")
        # A locator carries its name; a rename's "after" is the new track name, a new track's is a dict.
        name = proposal.get("locator_name") or (after if isinstance(after, str) else
                                                (after or {}).get("name") if isinstance(after, dict) else None)
        return {"action": action, "track": proposal.get("track_name"), "device": proposal.get("device_name"),
                "value": proposal.get("after"), "name": name}
    status = str(result.get("status") or "")
    intent = result.get("intent") if isinstance(result.get("intent"), dict) else {}
    if status in _ASKED or not intent.get("action") or intent.get("missing_fields"):
        return {"action": "clarify", "track": None, "value": None, "answer": str(result.get("answer") or "")[:400]}
    # Reads and view changes (inspect, focus) answer directly without a proposal.
    action = _SAME_READ.get(str(intent.get("action")), intent.get("action"))
    return {"action": action, "track": (intent.get("track") or {}).get("name"), "value": None, "read_only": True,
            "answer": str(result.get("answer") or "")[:400]}


# Different names for the same read in the gateway and the planner schema.
_SAME_READ = {"inspect_chain_contents": "inspect_devices"}


def expected_value(case: dict[str, Any], snapshot: dict[str, Any]) -> Any:
    from score_owner_tests import expected_value as fader_value

    if "expected_on" in case:
        return bool(case["expected_on"])
    return fader_value(case, snapshot)


def verdict(case: dict[str, Any], got: dict[str, Any], want: Any) -> str:
    expected = case["expected_action"]
    if got["action"] == "clarify":
        if expected.startswith("focus_") and "already focused" in str(got.get("answer")):
            return "right"  # "That track is already focused": nothing to do, and KENN says so
        return "right" if expected == "clarify" else "asked"
    if expected == "clarify":
        # "Asks" really means "proposes no change": an honest read-only answer ("KENN can't change the tempo yet;
        # it's 120 BPM") is fine, a proposal is not.
        return "right" if got.get("read_only") else "wrong"
    if expected == "set_eq_band_gain" and got["action"] == "set_device_parameter" and got.get("device") == "EQ Eight":
        expected = "set_device_parameter"  # the gateway sends EQ band gains as a device parameter on EQ Eight
    if got["action"] != expected:
        return "wrong"
    if case.get("expected_track") and got["track"] != case["expected_track"]:
        # Some reads don't echo the track in the intent; their answer names it ("'Drum Bus' has: Compressor.").
        named = got.get("read_only") and got["track"] is None and case["expected_track"] in str(got.get("answer"))
        if not named:
            return "wrong"
    if case.get("expected_name") and got.get("name") != case["expected_name"]:
        return "wrong"  # a locator or track given the wrong name ("Build here") is a wrong plan too
    if want is None:
        return "right"
    value = got["value"]
    if isinstance(want, bool):
        return "right" if value is want else "wrong"
    ok = isinstance(value, (int, float)) and not isinstance(value, bool) and abs(float(value) - want) <= VALUE_TOLERANCE
    return "right" if ok else "wrong"


def planner_fallback(case: dict[str, Any], want: Any, service: Any, snapshot: dict[str, Any]) -> dict[str, Any]:
    """What the planner would propose where the rules asked; a plan it can't validate counts as asking."""
    from kenn.core import live_command
    from kenn.core.live_intent import parse_request

    planner_snapshot = live_command._llm_planner_snapshot(service, snapshot, parse_request(case["query"], snapshot))
    plan, meta = live_command._generate_llm_plan(case["query"], planner_snapshot)
    if not plan or plan.get("action") == "clarify":
        got = {"action": "clarify", "track": None, "value": None}
    else:
        got = {"action": plan.get("action"), "track": plan.get("track_name"), "device": plan.get("device_name"),
               "value": plan.get("value"), "name": plan.get("new_track_name") or plan.get("locator_name")}
    return {"got": got, "verdict": verdict(case, got, want), "status": meta.get("status")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sources", nargs="*", type=Path, default=DEFAULT_SOURCES)
    parser.add_argument("--model", help="also ask this Ollama planner model wherever the rules asked")
    parser.add_argument("--show", choices=["wrong", "asked", "all", "none"], default="wrong")
    parser.add_argument("--out", type=Path, help="write every row as JSON")
    args = parser.parse_args()

    _isolate(args.model)
    from kenn.core.fake_live import FakeLiveBackend
    from kenn.core.live_action_service import LiveActionService
    from kenn.core.live_command import handle_command

    cases = load(args.sources)
    snapshot = FakeLiveBackend().query_session_state()
    rows = []
    for number, case in enumerate(cases):
        service = LiveActionService(FakeLiveBackend())
        result = handle_command(case["query"], session_id=f"phrasing-{number}", service=service, allow_llm=False)
        got = outcome(result)
        want = expected_value(case, snapshot)
        row = {"id": case.get("id"), "query": case["query"], "category": case.get("category"),
               "expected": case["expected_action"], "expected_track": case.get("expected_track"),
               "want": want, "got": got, "verdict": verdict(case, got, want),
               "answer": "" if result.get("proposal") else str(result.get("answer") or "")[:160]}
        intent = result.get("intent") if isinstance(result.get("intent"), dict) else {}
        # The same test the gateway uses in propose mode: the planner only gets requests where the rules found no
        # action, didn't refuse, and didn't ask something specific.
        planner_may_answer = (not intent.get("action") and intent.get("mode") != "refuse"
                              and not set(intent.get("missing_fields") or []) - {"action", "track"})
        if args.model and got["action"] == "clarify" and planner_may_answer:
            row["planner"] = planner_fallback(case, want, service, snapshot)
        rows.append(row)

    counts = collections.Counter(row["verdict"] for row in rows)
    by_category: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for row in rows:
        by_category[str(row["category"])][row["verdict"]] += 1
    for row in rows:
        if args.show == "all" or row["verdict"] == args.show:
            got = row["got"]
            want = "" if row["want"] is None else f" = {row['want']}"
            value = "" if got["value"] is None else f" = {got['value']}"
            answer = f" | {row['answer']}" if row["answer"] else ""
            print(f"{row['verdict']:5} | {row['query']:58} | want {row['expected']} {row['expected_track'] or ''}{want}"
                  f" | got {got['action']} {got['track'] or ''}{value}{answer}")
    print()
    for category, tally in sorted(by_category.items()):
        print(f"  {category:22} right {tally['right']:3}  asked {tally['asked']:3}  wrong {tally['wrong']:3}")
    total = len(rows)
    print(f"\n{total} phrasings (rule path): right {counts['right']} ({100 * counts['right'] / total:.1f}%), "
          f"asked {counts['asked']}, wrong {counts['wrong']}")
    if args.model:
        # Where the rules asked, the planner's answer replaces theirs: it can turn an "asked" into a right plan, or a
        # correct question ("which track?") into a wrong plan.
        final = collections.Counter(row["planner"]["verdict"] if "planner" in row else row["verdict"] for row in rows)
        for row in rows:
            if "planner" in row and row["planner"]["verdict"] == "wrong":
                got = row["planner"]["got"]
                print(f"  planner wrong | {row['query']:56} | want {row['expected']} {row['expected_track'] or ''}"
                      f" | got {got['action']} {got['track'] or ''} {'' if got['value'] is None else got['value']}")
        print(f"rules, then {args.model} where the rules asked: right {final['right']} "
              f"({100 * final['right'] / total:.1f}%), asked {final['asked']}, wrong {final['wrong']}")
    if args.out:
        args.out.write_text(json.dumps({"schema": "kenn.natural_phrasing_score.v1", "model": args.model,
                                        "counts": dict(counts), "rows": rows}, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
