#!/usr/bin/env python3
"""Ask a running KENN companion hard questions and record what actually answered each one.

    probe_advanced_questions.py [--endpoint http://127.0.0.1:8090] [--cases PATH] [--output BASE]
                                [--category NAME] [--only ID ...] [--only-file PATH] [--wait-upgrade 90]
                                [--allow-template] [--note TEXT]

Needs the companion already running with the model on (KENN_LLM_ENABLED=1, and KENN_LLM_BACKGROUND=1 for the
browser path). Run it with KENN_LLM_CACHE=0 on the server so a cached reply cannot pass as a model answer.

**Why it records who wrote the answer.** On 3 Oct the companion was answering from the grounded template with the
model off, and a template reply looks like a real one. Every row says whether the model was attempted and whether its
text was the one delivered, and the run stops after three questions if the model never runs.

**Two ways a model answer arrives.** With the background upgrade on, /api/ask returns the template at once and an
`answer_upgrade` id; the model's text turns up on /api/ask/upgrade. Without it the model runs inside /api/ask and the
verdict is in `generation_validation`. The probe follows both and keeps the template time and the final time apart.

Each case gets a fresh chat so one answer cannot colour the next, except a `follow_up_of` case, which reuses the chat
of the one it follows. A reply identical to an earlier reply to a different question is flagged, and so is a reply that names something
the case lists in `must_not_name` (a plugin brand the user never mentioned).

**The 15 s local-delivery gate.** A row passes when it expects an answer, the model's text was delivered and it landed
within 15 s of asking. Errors, rejections and timeouts count against it, so the rate is over every answer-expected row.
The summary gives the count and rate against the 0.70 target; whether three runs in a row clear it is for a person to
judge. Acceptance over only the rows where the model was attempted is reported apart from the gate.

Writes three files next to --output: `.jsonl` and `.review.md` hold answer prose for hand grading and stay out of git;
`.summary.json` is numbers only. This sends chat questions and nothing else, so it never writes to Live.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
import sys
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES = REPO_ROOT / "tooling" / "evaluation" / "advanced_questions.json"
# /api/ask allows 30 a minute per client; 2.5 s between questions stays under it with room for retries.
DEFAULT_PAUSE = 2.5
MODEL_CHECK_AFTER = 3
GATE_SECONDS = 15.0
GATE_TARGET_RATE = 0.70
# The server suggests 2000 ms between upgrade polls, which put every final time on a 2 s step: an answer done at
# 14.2 s was recorded at 16.1 s and failed the gate. This is a local probe, so we poll faster than the browser does.
POLL_SECONDS = 0.5


def post_json(url: str, body: dict, timeout: float) -> dict:
    request = Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def get_json(url: str, timeout: float) -> dict:
    with urlopen(url, timeout=timeout) as response:
        return json.load(response)


def concept_hits(answer: str, must_name: list[str]) -> tuple[list[str], list[str]]:
    """Split the expected ideas into those the answer names and those it misses. Entries split on | are alternatives."""
    text = answer.lower()
    hit, missed = [], []
    for entry in must_name:
        (hit if any(option.strip().lower() in text for option in entry.split("|")) else missed).append(entry)
    return hit, missed


def forbidden_named(answer: str, must_not_name: list[str]) -> list[str]:
    """Things the answer must not mention because the user never did, such as a plugin brand it made up."""
    text = answer.lower()
    return [entry for entry in must_not_name if any(option.strip().lower() in text for option in entry.split("|"))]


def is_abstention(answer: str) -> bool:
    try:
        from kenn.llm.llm_rewrite import ABSTAIN_PREFIX
    except Exception:
        return False
    return any(line.strip().lower().startswith(ABSTAIN_PREFIX.lower()) for line in answer.splitlines())


def follow_upgrade(endpoint: str, session_id: str, upgrade: dict, wait: float, started: float) -> dict:
    """Poll the background upgrade until it settles or the wait runs out."""
    url = f"{endpoint}/api/ask/upgrade?id={quote(str(upgrade.get('id', '')))}&session_id={quote(session_id)}"
    deadline = time.perf_counter() + wait
    result: dict = {"status": "pending"}
    while time.perf_counter() < deadline:
        time.sleep(POLL_SECONDS)
        try:
            result = get_json(url, timeout=10)
        except (URLError, OSError, ValueError) as exc:
            result = {"status": "error", "error": type(exc).__name__}
            break
        if result.get("status") != "pending":
            break
    result["seconds_from_ask"] = round(time.perf_counter() - started, 2)
    return result


def rejection_reason(payload: dict, upgrade: dict, delivered_by_model: bool) -> str:
    if delivered_by_model:
        return ""
    # The template's own `warnings` are empty on the background path, which is why 34 rejected rows on 4 Oct
    # said nothing. The reason lives on the upgrade.
    if upgrade.get("status") == "rejected":
        return str(upgrade.get("reason") or upgrade.get("error") or "no reason given")
    # A poll that broke says nothing about the model, but it still cost the row, so it gets counted too.
    if upgrade.get("status") == "error":
        return f"probe poll failed: {upgrade.get('error') or 'unknown'}"
    if upgrade:
        return f"upgrade still {upgrade.get('status') or 'unknown'} when the wait ran out"
    # No upgrade: KENN_LLM_BACKGROUND=0, or a route that never offers one.
    warnings = (payload.get("generation_validation") or {}).get("warnings") or []
    return str(payload.get("generation_outcome") or (warnings[0] if warnings else ""))


def ask(endpoint: str, session_id: str, case: dict, wait: float) -> dict:
    started = time.perf_counter()
    started_at = time.time()
    row: dict = {"id": case["id"], "category": case["category"], "expect": case["expect"],
                 "question": case["question"], "session_id": session_id}
    try:
        payload = post_json(f"{endpoint}/api/ask", {"question": case["question"], "session_id": session_id},
                            timeout=180)
    except (URLError, OSError, ValueError) as exc:
        return {**row, "error": f"{type(exc).__name__}: {exc}"[:200], "answer": "", "delivered_by": "none"}
    template_seconds = round(time.perf_counter() - started, 2)
    template = str(payload.get("answer") or "")
    validation = payload.get("generation_validation") or {}
    upgrade_meta = payload.get("answer_upgrade") or {}
    upgrade: dict = {}
    if upgrade_meta.get("id"):
        upgrade = follow_upgrade(endpoint, session_id, upgrade_meta, wait, started)
    upgrade_accepted = upgrade.get("status") == "accepted" and bool(upgrade.get("answer"))
    inline_accepted = bool(payload.get("llm_enhanced")) or bool(validation.get("accepted"))
    answer = str(upgrade["answer"]) if upgrade_accepted else template
    # A decline the server kept (honest "Insufficient context: <gap>") arrives accepted but flagged. It is its own
    # delivery: not a correct model answer, which would inflate the gate, and not a template, which it replaced.
    if upgrade_accepted:
        declined = bool(upgrade.get("abstained"))
    else:
        declined = bool(payload.get("answer_abstained")) or (bool(validation.get("accepted")) and bool(validation.get("abstained")))
    model_answered = (upgrade_accepted or inline_accepted) and not declined
    attempted = (bool(validation.get("attempted")) or bool(upgrade_meta.get("id"))
                 or upgrade.get("status") in {"accepted", "rejected"})
    return {
        **row,
        "answer": answer,
        "delivered_by": "abstain" if declined else "model" if model_answered else "template",
        "model_attempted": attempted,
        "llm_available": bool(payload.get("llm_available")),
        "upgrade_status": upgrade.get("status", ""),
        "rejection_reason": rejection_reason(payload, upgrade, model_answered or declined),
        "warnings": list(validation.get("warnings") or [])[:4],
        "unsupported_measurements": len(validation.get("unsupported_measurements") or []),
        "fabricated_sources": len(validation.get("fabricated_sources") or []),
        "template_seconds": template_seconds,
        "final_seconds": upgrade.get("seconds_from_ask", template_seconds),
        # The server's own clock for when the model finished, free of our polling step. /api/ask/upgrade drops
        # `at` from its reply today, so this stays None until it doesn't; `model_seconds` is the server's timing
        # of the model run alone, which it does return. final_seconds is still the gate measure.
        "server_final_seconds": (round(float(upgrade["at"]) - started_at, 2)
                                 if upgrade.get("at") is not None else None),
        "model_seconds": upgrade.get("seconds"),
        "route": str(payload.get("route") or ""),
        "answer_mode": str(payload.get("answer_mode") or ""),
        "confidence": str(payload.get("confidence") or ""),
        "weak_match": bool(payload.get("weak_match")),
        "source_count": len(payload.get("sources") or []),
        "sources": [str((s.get("title") or s.get("path") or s) if isinstance(s, dict) else s)[:80]
                    for s in (payload.get("sources") or [])[:4]],
        "abstained": is_abstention(answer),
    }


def judge(row: dict, case: dict, seen: dict[str, str]) -> None:
    hit, missed = concept_hits(row.get("answer", ""), case.get("must_name", []))
    row["concepts_named"], row["concepts_missed"] = hit, missed
    expected = len(hit) + len(missed)
    row["concept_recall"] = round(len(hit) / expected, 2) if expected else None
    if case.get("expect") == "abstain_or_clarify":
        # A model answer that replaced the template's clarifying reply doesn't count: the template was right, the
        # upgrade is what we're checking. Recall only means something when the case was answered instead.
        template_clarified = bool(row.get("weak_match")) and row.get("delivered_by") == "template"
        row["handled_as_expected"] = bool(row.get("abstained")) or template_clarified
        if row["handled_as_expected"]:
            row["concept_recall"] = None
    else:
        row["handled_as_expected"] = None
    row["forbidden_named"] = forbidden_named(row.get("answer", ""), case.get("must_not_name", []))
    fingerprint = " ".join(row.get("answer", "").lower().split())
    row["repeats_answer_of"] = seen.get(fingerprint) if fingerprint else None
    if fingerprint and fingerprint not in seen:
        seen[fingerprint] = row["id"]


def summarise(rows: list[dict], endpoint: str, cases_path: Path, provenance: dict | None = None) -> dict:
    def group(subset: list[dict]) -> dict:
        scored = [r for r in subset if not r.get("context_only")]
        eligible = [r for r in scored if r.get("expect") == "answer"]
        in_time = sum(r.get("delivered_by") == "model" and r.get("final_seconds", float("inf")) <= GATE_SECONDS
                      for r in eligible)
        attempted = [r for r in scored if r.get("model_attempted")]
        accepted = sum(r.get("delivered_by") == "model" for r in attempted)
        recalls = [r["concept_recall"] for r in subset if r.get("concept_recall") is not None]
        seconds = [r["final_seconds"] for r in subset if "final_seconds" in r]
        asked_to_abstain = [r for r in subset if r.get("handled_as_expected") is not None]
        extra = ({"expected_abstain_handled":
                  f"{sum(bool(r['handled_as_expected']) for r in asked_to_abstain)} of {len(asked_to_abstain)}"}
                 if asked_to_abstain else {})
        return {
            **extra,
            "questions": len(subset),
            "delivered_by_model": sum(r.get("delivered_by") == "model" for r in subset),
            "delivered_by_abstain": sum(r.get("delivered_by") == "abstain" for r in subset),
            "delivered_by_template": sum(r.get("delivered_by") == "template" for r in subset),
            "model_attempted": sum(bool(r.get("model_attempted")) for r in subset),
            "abstained": sum(bool(r.get("abstained")) for r in subset),
            "weak_match": sum(bool(r.get("weak_match")) for r in subset),
            "repeats_an_earlier_answer": sum(bool(r.get("repeats_answer_of")) for r in subset),
            "named_something_forbidden": sum(bool(r.get("forbidden_named")) for r in subset),
            "errors": sum("error" in r for r in subset),
            "gate_eligible": len(eligible),
            "gate_model_within_15s": in_time,
            "gate_rate": round(in_time / len(eligible), 3) if eligible else None,
            "model_accepted_when_attempted": f"{accepted} of {len(attempted)}",
            "model_acceptance_rate_when_attempted": round(accepted / len(attempted), 3) if attempted else None,
            "mean_concept_recall": round(statistics.mean(recalls), 2) if recalls else None,
            "median_final_seconds": round(statistics.median(seconds), 2) if seconds else None,
            "rejection_reasons": dict(Counter(r["rejection_reason"] for r in subset
                                              if r.get("rejection_reason")).most_common()),
        }
    categories = sorted({r["category"] for r in rows})
    return {
        "schema": "kenn.advanced_probe.v1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "endpoint": endpoint,
        "cases_file": str(cases_path.name),
        "provenance": provenance or {},
        "overall": {**group(rows), "gate_target_rate": GATE_TARGET_RATE},
        "by_category": {name: group([r for r in rows if r["category"] == name]) for name in categories},
        "note": "Concept recall is a keyword check, not a grade. Read the review sheet before drawing conclusions.",
    }


def power_source() -> str | None:
    """The first line of `pmset -g batt` on a Mac. Runs on 4 and 5 Oct were on battery, and the timings were useless."""
    if sys.platform != "darwin":
        return None
    try:
        output = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return output.splitlines()[0].strip() if output.strip() else None


def provenance(cases_path: Path, health: dict, note: str | None) -> dict:
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parent,
                                capture_output=True, text=True, timeout=5).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        commit = None
    # delivered_by and model_attempted on each row show whether the model ran; answer_model says which one. Older
    # companions don't report it, so it comes through as None rather than failing the run.
    subsystems = health.get("subsystems") or {}
    index = subsystems.get("knowledge_index") or {}
    return {
        "probe_commit": commit,
        "cases_sha256": hashlib.sha256(cases_path.read_bytes()).hexdigest(),
        "index": {key: index.get(key) for key in
                  ("index_version", "active_mode", "semantic_model_state", "degraded", "fallback_reason")},
        "answer_model": subsystems.get("answer_model"),
        "power_source": power_source(),
        "note": note,
    }


def review_sheet(rows: list[dict]) -> str:
    lines = ["# KENN advanced question review", "",
             "Grade each answer: 0 wrong or empty, 1 partly right, 2 right and useful. Note any invented specifics.", ""]
    for row in rows:
        lines += [f"## {row['id']} ({row['category']})", "", f"**Q:** {row['question']}", "",
                  f"Delivered by {row.get('delivered_by')} in {row.get('final_seconds', '?')} s; "
                  f"route {row.get('route') or '?'}; confidence {row.get('confidence') or '?'}; "
                  f"sources {row.get('source_count', 0)}: {'; '.join(row.get('sources', [])) or 'none'}",
                  f"Concepts missed: {', '.join(row.get('concepts_missed', [])) or 'none'}"]
        if row.get("rejection_reason"):
            lines.append(f"Model answer rejected: {row['rejection_reason']}")
        if row.get("repeats_answer_of"):
            lines.append(f"**Same answer as {row['repeats_answer_of']}.**")
        if row.get("forbidden_named"):
            lines.append(f"**Named what the user never mentioned: {', '.join(row['forbidden_named'])}.**")
        lines += ["", row.get("answer") or "(no answer)", "", "Grade: ", "Notes: ", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--endpoint", default="http://127.0.0.1:8090")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path,
                        default=Path.home() / f"kenn-advanced-probe-{datetime.now():%Y%m%d-%H%M%S}")
    parser.add_argument("--category")
    parser.add_argument("--only", nargs="+")
    parser.add_argument("--only-file", type=Path, help="case ids to run, one per line, such as a held-out list")
    parser.add_argument("--wait-upgrade", type=float, default=90.0,
                        help="seconds to wait for the background model answer after the template")
    parser.add_argument("--pause", type=float, default=DEFAULT_PAUSE)
    parser.add_argument("--allow-template", action="store_true",
                        help="keep going even if the model never runs (measures the template path)")
    parser.add_argument("--note", help="free text kept in the summary, such as 'Live open'")
    args = parser.parse_args()

    endpoint = args.endpoint.rstrip("/")
    cases = json.loads(args.cases.read_text(encoding="utf-8"))["cases"]
    by_id = {case["id"]: case for case in cases}
    only = set(args.only or [])
    if args.only_file:
        only.update(line.strip() for line in args.only_file.read_text(encoding="utf-8").splitlines() if line.strip())
    selected = [c for c in cases if (not args.category or c["category"] == args.category)
                and (not only or c["id"] in only)]
    context_only: set[str] = set()
    if only:
        # A follow-up is meaningless without the question it follows. The parent is asked for its context only:
        # the 300-case held-out list pulls in four of them, and counting those put 76 rows in the gate instead of 72.
        for case in list(selected):
            parent = case.get("follow_up_of")
            if parent and parent in by_id and by_id[parent] not in selected:
                selected.insert(0, by_id[parent])
                context_only.add(parent)
    if not selected:
        print("No cases selected.", file=sys.stderr)
        return 2
    try:
        health = get_json(f"{endpoint}/api/health", timeout=10)
    except (URLError, OSError, ValueError) as exc:
        print(f"Companion not reachable at {endpoint}: {exc}", file=sys.stderr)
        return 2
    print(f"health ok={health.get('ok')}; {len(selected)} questions", flush=True)

    run_id = uuid.uuid4().hex[:8]
    sessions: dict[str, str] = {}
    seen: dict[str, str] = {}
    rows: list[dict] = []
    for case in selected:
        parent = case.get("follow_up_of")
        session_id = sessions.get(parent) if parent else None
        session_id = session_id or f"probe-{run_id}-{case['id']}"
        sessions[case["id"]] = session_id
        row = ask(endpoint, session_id, case, args.wait_upgrade)
        if case["id"] in context_only:
            row["context_only"] = True
        judge(row, case, seen)
        rows.append(row)
        print(f"{case['id']:<28} {row.get('delivered_by', '?'):<8} {row.get('final_seconds', '?')!s:>6} s  "
              f"recall {row.get('concept_recall')}", flush=True)
        if (len(rows) == MODEL_CHECK_AFTER and not args.allow_template
                and not any(r.get("model_attempted") for r in rows)):
            print("\nThe model never ran for the first three questions, so every answer is the grounded template.\n"
                  "Start the companion with KENN_LLM_ENABLED=1 (and KENN_LLM_BACKGROUND=1 for the browser path),\n"
                  "or pass --allow-template to measure the template path on purpose.", file=sys.stderr)
            return 3
        time.sleep(args.pause)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.with_suffix(".jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    args.output.with_suffix(".review.md").write_text(review_sheet(rows), encoding="utf-8")
    summary = summarise(rows, endpoint, args.cases, provenance(args.cases, health, args.note))
    args.output.with_suffix(".summary.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(summary["overall"], indent=1))
    print(f"\nwrote {args.output}.jsonl / .review.md / .summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
