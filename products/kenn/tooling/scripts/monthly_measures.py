#!/usr/bin/env python3
"""Print the North Star's monthly measures by running the scripts that already measure them.

Every number here is quoted out of an existing evaluation script that this report runs as a subprocess. Nothing is
re-scored, re-weighted or re-derived here, because a measure that quietly changes definition is the failure the
North Star's risk table names: "a gate quietly stops gating". Where a script prints a number the North Star quotes
differently, both appear and the report says which is stale.

A measure whose script is slow, needs a fixture, or needs a runtime log that only exists after the product has been
used is printed as "not run: ..." or "not measured: ..." with the reason. It is never printed as a blank, a zero or a
guess, because a wrong zero on a gate is worse than an absent one.

Two of the measures are gates rather than printouts: unauthorised writes must be zero, and answers with no citable
source must be zero. The exit code says how each went -- 0 both measured and both met, 1 one violated, 2 one could
not be measured at all. "Not measured" is deliberately not exit 0: an unmeasured zero requirement that reads as a
pass is the same quiet gate as any other, and on a checkout with no retrieval index the uncited-answer count is
exactly that.

    monthly_measures.py                     # print the report; writes nothing
    monthly_measures.py --receipt           # also write tooling/evaluation/results/KENN_MONTHLY_MEASURES_<date>.json
    monthly_measures.py --full-output       # print each script's whole stdout, not just the lines quoted
    monthly_measures.py --pilot-log <log>   # fold real-Live supervised sessions in (repeatable)
    monthly_measures.py --reviewer-a a.json --reviewer-b b.json   # quote two reviewer score sets

Run it from products/kenn. The retrieval, chat and coverage measures need the local index, and the route measures
need a route log, so on a checkout without either those sections say so instead of guessing.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

KENN_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KENN_ROOT / "apps" / "backend" / "src"))

from kenn.core import route_log  # noqa: E402
from kenn.retrieval import index_store  # noqa: E402

RESULTS_DIR = KENN_ROOT / "tooling" / "evaluation" / "results"
SCHEMA = "kenn.monthly_measures.v1"
NORTH_STAR = "KENN_PLAN.md (Acceptance targets and measurement rules)"

# The index is gitignored (apps/backend/src/kenn/data/), so a clean checkout has none. That is the difference between
# "recall fell" and "there is no index to recall from", and eval_chat_coverage.py answers 0 on every case without one.
INDEX_POINTER = index_store.INDEX_DIR / index_store.CURRENT_FILENAME

HOLDOUT_FILES = ["tooling/data/natural_holdout.jsonl", "tooling/data/natural_holdout_candidates.jsonl"]
# The North Star's 28 Sept figures for each fixture, kept beside the script's own so a reader can see which moved.
RETRIEVAL_FIXTURES = [
    ("original (128 cases in file)", "apps/backend/src/kenn/evals/questions.json", "0.983"),
    ("describe-it (125 in file)", "apps/backend/src/kenn/evals/device_purpose_retrieval_cases.json", "0.784"),
    ("technique-purpose (50 in file)", "apps/backend/src/kenn/evals/technique_purpose_retrieval_cases.json", "0.84"),
    ("sealed Qwen3 8B (228 in file)", "apps/backend/src/kenn/evals/device_purpose_sealed_qwen8b.json", "0.425"),
]

PHRASINGS_LINE = re.compile(
    r"^(?P<total>\d+) phrasings \(rule path\): right (?P<right>\d+) \((?P<pct>[\d.]+)%\), "
    r"asked (?P<asked>\d+), wrong (?P<wrong>\d+)$", re.MULTILINE)
E2E_SUMMARY = re.compile(r"^(?P<executed>\d+) executed: (?P<passed>\d+) passed apply", re.MULTILINE)
REQUESTS_LINE = re.compile(r"^(?P<requests>\d+) requests; (?P<over>routes over the 4 s p95 target: .*)$", re.MULTILINE)
UPGRADES_PREFIX = "model answers (upgrades): "
REJECTED_COUNT = re.compile(r"(?P<n>\d+) rejected")
# The two safety verdicts e2e_demo_commands.py prints once per command it actually applied. We count what it said, we
# do not re-decide it; the cross-check against its own summary count is there so a change in the script's output shows
# up as "not measured" instead of as a wrong gate.
UNTOUCHED_BEFORE_APPLY = re.compile(r"nothing written before Apply: (?P<verdict>True|False)")
RESTORED_EXACTLY = re.compile(r"set restored exactly: (?P<verdict>True|False)")


@dataclass
class Run:
    """One existing script, run as a subprocess, with its output kept exactly as it printed it."""

    command: str
    returncode: int
    stdout: str
    stderr: str
    seconds: float

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@dataclass
class Measure:
    title: str
    status: str = ""
    number: str = ""
    denominator: str = ""
    command: str = ""
    measured_at: str = ""
    requirement: str = ""
    verdict: str = ""
    # Only the North Star's two required-zero measures gate the exit code. Undo success carries a requirement too,
    # but a report that failed the build on it would cry wolf over commands KENN has no safe inverse for.
    gated: bool = False
    quotes: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _python() -> str:
    return sys.executable or "python3"


def default_runner(argv: Sequence[str]) -> Run:
    """Run one script from products/kenn with the same PYTHONPATH ci_verification.sh sets."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(KENN_ROOT / "apps" / "backend" / "src"), str(KENN_ROOT / "tooling"), env.get("PYTHONPATH", "")]).strip(
        os.pathsep)
    started = time.perf_counter()
    try:
        done = subprocess.run([_python(), *argv], cwd=KENN_ROOT, env=env, capture_output=True, text=True, timeout=1800)
    except subprocess.TimeoutExpired as exc:
        return Run(f"python3 {' '.join(argv)}", 124, exc.stdout or "", f"timed out after 1800 s: {exc}", 1800.0)
    return Run(f"python3 {' '.join(argv)}", done.returncode, done.stdout, done.stderr, time.perf_counter() - started)


def _route_log() -> Path:
    """KENN's own route-log path, so a KENN_ROUTE_LOG override is honoured here for the same reason it is there."""
    return route_log.LOG


def _display_path(path: Path) -> str:
    """A path as the reader would type it, not the absolute one this machine happens to have."""
    try:
        return str(path.relative_to(KENN_ROOT))
    except ValueError:
        return str(path)


def _route_command() -> str:
    return f"python3 tooling/scripts/route_latency_report.py --log {_display_path(_route_log())}"


def _iso_or_run(iso: str | None, fallback: str | None = None) -> str:
    if iso:
        return str(iso)[:19].replace("T", " ") + " UTC (the timestamp the script wrote)"
    if fallback:
        return f"receipt carries no timestamp; source_git_commit {fallback[:12]}"
    return f"run {date.today().isoformat()} (the script prints no timestamp of its own)"


def _route_lines(run: Run) -> tuple[str, str]:
    """The two human lines route_latency_report.py prints after its JSON: the request total, and the upgrade line."""
    requests = REQUESTS_LINE.search(run.stdout)
    upgrades = [line for line in run.stdout.splitlines() if line.startswith(UPGRADES_PREFIX)]
    return (requests.group(0) if requests else ""), (upgrades[0] if upgrades else "")


def _route_measured_at() -> str:
    log = _route_log()
    return f"route log last written {datetime.fromtimestamp(log.stat().st_mtime, timezone.utc).date().isoformat()}"


def measure_understanding(runner) -> Measure:
    """Natural phrasings through the whole command gateway (Stage 1 gate: >= 95% on >= 500)."""
    run = runner(["tooling/scripts/score_natural_phrasings.py", "--show", "none"])
    if not run.ok:
        return Measure(title="Understanding (natural phrasings)", status=f"not run: exited {run.returncode}",
                       command=run.command, notes=[run.stderr.strip()[-400:]])
    found = PHRASINGS_LINE.search(run.stdout)
    if not found:
        return Measure(title="Understanding (natural phrasings)",
                       status="not run: the script printed no summary line to quote", command=run.command)
    groups = {name: int(found.group(name)) for name in ("total", "right", "asked", "wrong")}
    return Measure(
        title="Understanding (natural phrasings)",
        status="measured",
        number=f"right {groups['right']} of {groups['total']} ({found.group('pct')}%), asked {groups['asked']}, "
               f"wrong {groups['wrong']}",
        denominator=f"{groups['total']} phrasings, rule path",
        command=run.command,
        measured_at=f"run {date.today().isoformat()} (this script prints no timestamp of its own)",
        quotes=[found.group(0)],
        notes=[f"wrong {groups['wrong']} is the number that matters: a producer who presses Apply on a wrong plan gets "
               f"a change they did not ask for.",
               "The North Star (28 Sept) quotes 494 / 505 (97.8%) with 11 asked. Today's run of the same script over the "
               "same two holdout files asks about two more phrasings, so 494 is the stale figure and 492 is what the "
               "code does now. Neither is wrong about the code; the North Star records a past run."],
    )


def measure_answer_quality(runner, coverage: dict | None, reviewers: tuple[Path, Path] | None) -> Measure:
    """Reviewer scores are the measure; the chat-coverage receipt is quoted beside them and does not stand in."""
    title = "Answer quality (independent reviewer scores)"
    adjudication = ("python3 tooling/scripts/adjudicate_human_review.py --reviewer-a <reviewer-a.json> "
                    "--reviewer-b <reviewer-b.json>")
    if reviewers is not None:
        reviewer_a, reviewer_b = reviewers
        with tempfile.TemporaryDirectory(prefix="kenn-measures-review-") as temp:
            run = runner(["tooling/scripts/adjudicate_human_review.py", "--reviewer-a", str(reviewer_a),
                          "--reviewer-b", str(reviewer_b), "--output", str(Path(temp) / "adjudication.json")])
        try:
            receipt = json.loads(run.stdout)
        except json.JSONDecodeError:
            return Measure(title=title, status=f"not run: exited {run.returncode} with no receipt to quote",
                           command=run.command, notes=[run.stdout.strip()[:400] or run.stderr.strip()[:400]])
        criteria = receipt.get("by_criterion") or {}
        return Measure(
            title=title, status="measured (two reviewers, adjudication still outstanding)",
            number=f"overall combined mean {receipt.get('thresholds', {}).get('overall_combined_mean')}; "
                   + ", ".join(f"{name} {bucket.get('combined_mean')}" for name, bucket in sorted(criteria.items())),
            denominator=f"{receipt.get('case_count')} packet cases scored by each of two independent reviewers",
            command=run.command, measured_at=_iso_or_run(receipt.get("generated_at")),
            quotes=[f'"status": "{receipt.get("status")}"',
                    f'"exact_agreement_rate": {(receipt.get("agreement") or {}).get("exact_agreement_rate")}"'],
            notes=["adjudicate_human_review.py validates the two score sets and reports agreement; it deliberately "
                   "does not produce the release decision, which an authorised adjudicator signs."],
        )
    measure = Measure(
        title=title, status="not measured", command=adjudication,
        notes=["not measured: two independent reviewer score files are needed and none are tracked. "
               "adjudicate_human_review.py requires both and has no default for either on purpose -- it will not "
               "invent a score. Pass --reviewer-a and --reviewer-b to close this measure.",
               "build_human_review_packet.py builds the packet those reviewers score and deliberately does not score "
               "the answers itself."],
    )
    if coverage is None:
        measure.notes.append(f"not measured: the automated chat-coverage receipt is also unavailable, because there is "
                             f"no retrieval index at {_display_path(INDEX_POINTER)}.")
        return measure
    measure.command = "python3 tooling/scripts/eval_chat_coverage.py"
    measure.measured_at = _iso_or_run(coverage.get("generated_at"))
    measure.notes.append(
        f"Automated fixture evidence only, quoted for context: coverage {coverage.get('passed')}/{coverage.get('cases')} "
        f"cases, {coverage.get('applicable_passed')}/{coverage.get('applicable_cases')} applicable, abstention "
        f"{coverage.get('abstention_passed')}/{coverage.get('abstention_cases')}. That is a different measure from "
        f"reviewer scores and it does not close this one. The North Star (28 Sept) quotes 124/128 with abstention "
        f"43/44, after a correction recording 124/128 rather than an earlier 125/128.")
    return measure


def measure_retrieval_recall(runner) -> Measure:
    """recall@4 per fixture, from the retrieval-mode comparison that already scores the index."""
    command = "python3 tooling/scripts/evaluate_retrieval_modes.py --cases <fixture>"
    if not INDEX_POINTER.exists():
        return Measure(title="Retrieval recall (recall@4)", status="not run", command=command,
                       notes=[f"not run: no retrieval index at {_display_path(INDEX_POINTER)}. Without one the script "
                              f"still prints a receipt, but every rank is null, recall@4 reads 0.0 for a reason that "
                              f"has nothing to do with retrieval quality, and it exits 0. A missing index must never be "
                              f"reported as recall of zero."])
    per_fixture: list[str] = []
    generated_at = ""
    for label, fixture, north_star in RETRIEVAL_FIXTURES:
        run = runner(["tooling/scripts/evaluate_retrieval_modes.py", "--cases", fixture])
        try:
            receipt = json.loads(run.stdout)
        except json.JSONDecodeError as exc:
            per_fixture.append(f"{label}: not run: unreadable receipt ({exc})")
            continue
        generated_at = generated_at or str(receipt.get("generated_at") or "")
        hybrid = (receipt.get("modes") or {}).get("hybrid", {}).get("summary") or {}
        bm25 = (receipt.get("modes") or {}).get("bm25", {}).get("summary") or {}
        per_fixture.append(
            f"{label}: hybrid recall@4 {hybrid.get('recall_at_4')} over {receipt.get('fixture_count')} scored cases "
            f"(BM25 {bm25.get('recall_at_4')}, MRR {hybrid.get('mrr')}); North Star quotes {north_star}")
    return Measure(
        title="Retrieval recall (recall@4)",
        status="measured",
        number="; ".join(per_fixture),
        denominator="cases naming an expected source; the script drops abstention cases, so this is smaller than the "
                    "file's case count",
        command=command,
        measured_at=_iso_or_run(generated_at or None),
        notes=["Both numbers are shown per fixture. The script's is the one with a date on it, and the North Star's is "
               "the 28 Sept record; where they differ the difference is the index and notes having moved since, not a "
               "change of definition."],
    )


def measure_latency(run: Run | None) -> Measure:
    """Per-route p50/p95 from the route log. The four stages the North Star names do not reach disk; see the note."""
    title = "Latency by stage"
    if run is None:
        return Measure(title=title, status="not measured", command=_route_command(),
                       notes=[f"not measured: no route log at {_display_path(_route_log())}. The log is written as the "
                              f"product answers, so it only exists after KENN has been used on a Mac; it is gitignored "
                              f"and this report will not create one.",
                              "The North Star asks for planning, OSC round trip, readback and analysis separately. Only "
                              "the per-route total is written down: timing_stats holds per-stage samples in memory "
                              "(MAX_SAMPLES 200, no file) and no script dumps it, so the stage split cannot be read off "
                              "any file and this report will not reconstruct it from the route total."])
    requests, _ = _route_lines(run)
    return Measure(
        title=title, status="measured (per route, not per stage)", number=requests,
        denominator="requests in the route log (the script's own total)", command=run.command,
        measured_at=_route_measured_at(), quotes=[requests] if requests else [],
        notes=["Per-route p50 and p95 are in the script's own JSON receipt, which --full-output prints.",
               "The stage split the North Star wants is not on disk. Adding it means recording the four stages in "
               "route_log.record, which is a change to the product and not this report's to make."],
    )


def measure_unauthorised_writes_and_undo(runner) -> tuple[Measure, Measure]:
    """Both safety measures come from one e2e run over the tracked holdout, on the demo backend."""
    undo_title = "Undo success"
    with tempfile.TemporaryDirectory(prefix="kenn-measures-") as temp:
        combined = Path(temp) / "holdout.jsonl"
        fed = 0
        with combined.open("w", encoding="utf-8") as handle:
            for relative in HOLDOUT_FILES:
                for line in (KENN_ROOT / relative).read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        handle.write(line + "\n")
                        fed += 1
        command = (f"cat {' '.join(HOLDOUT_FILES)} > \"$TMP/holdout.jsonl\"; "
                   f"python3 tooling/scripts/e2e_demo_commands.py \"$TMP/holdout.jsonl\"")
        run = runner(["tooling/scripts/e2e_demo_commands.py", str(combined)])
    measured_at = f"run {date.today().isoformat()} on the demo backend (FakeLiveBackend; real Live was never touched)"
    note = ["e2e_demo_commands.py prints one verdict per command it applied and does not total the two safety "
            "verdicts itself, so the counts below are the number of its printed lines that read False. The verdict is "
            "its own; nothing here re-decides whether a write was authorised.",
            "This is the demo backend, the Live-free path to that number. The real-Live number is the supervised "
            "pilot's, which needs logs only a tester session can produce; pass --pilot-log for it."]

    def writes(status: str, *, extra_notes: list[str] | None = None, **extra) -> Measure:
        # Every state of this measure is the required-zero gate, so the gate travels with the measure. Building it
        # here is what stops a script failure from quietly removing the gate from the report.
        return Measure(title="Unauthorised writes (writes to the set with no Apply)", status=status, command=command,
                       requirement="must be 0", gated=True, notes=note + (extra_notes or []), **extra)

    def both_unmeasured(reason: str) -> tuple[Measure, Measure]:
        return (writes(f"not measured: {reason}"),
                Measure(title=undo_title, status=f"not measured: {reason}", command=command, notes=note))

    if not run.ok and not run.stdout.strip():
        status = f"not run: exited {run.returncode}"
        return writes(status), Measure(title=undo_title, status=status, command=command, notes=note)
    summary = E2E_SUMMARY.search(run.stdout)
    if summary is None:
        return both_unmeasured("the script printed no summary line to quote")
    executed = int(summary.group("executed"))
    before_apply = UNTOUCHED_BEFORE_APPLY.findall(run.stdout)
    restored = RESTORED_EXACTLY.findall(run.stdout)
    if len(before_apply) != executed or len(restored) != executed:
        # If the script's own applied count and its per-command lines disagree, we are reading output we no longer
        # understand. Say so instead of gating on a number we guessed at.
        return both_unmeasured(
            f"the script's summary counts {executed} applied commands but it printed {len(before_apply)} "
            f"before-Apply verdicts and {len(restored)} undo verdicts, so these lines cannot be counted")
    unauthorised = sum(1 for verdict in before_apply if verdict == "False")
    lost_undo = sum(1 for verdict in restored if verdict == "False")
    write_measure = writes(
        "measured", number=f"{unauthorised}", measured_at=measured_at,
        denominator=f"{executed} commands applied through the gateway, out of {fed} phrasings fed in",
        verdict="met" if unauthorised == 0 else "violated",
        quotes=[line.strip() for line in run.stdout.splitlines() if "nothing written before Apply: False" in line],
        extra_notes=[f"The other {fed - executed} phrasings asked or answered without writing anything, which is the "
                     f"script's own summary count and not a safety problem."],
    )
    undo = Measure(
        title=undo_title, status="measured",
        number=f"{executed - lost_undo} of {executed} restored exactly ({lost_undo} not restored)",
        denominator=f"{executed} applied commands, each followed by an undo and a full set comparison",
        command=command, measured_at=measured_at, requirement="must be 100%",
        verdict="met" if lost_undo == 0 else "violated",
        quotes=[line.strip() for line in run.stdout.splitlines() if "set restored exactly: False" in line],
        notes=note + ["The script's own summary also reports how many passed apply -> verify -> undo, but that passes on "
                      "the right action too, so it is not the undo-success rate and is not used as one.",
                      "This measure is reported, not gated: the North Star names only unauthorised writes and uncited "
                      "answers as the two required-zero gates. Read the quoted lines before treating a shortfall as a "
                      "lost undo -- a command KENN has no safe inverse for asks to undo rather than losing one, and "
                      "reclassifying that here would be this report quietly changing a measure's definition."],
    )
    return write_measure, undo


def measure_model_answer_lands(run: Run | None) -> Measure:
    """How often the local model's answer lands, and how long it took, on a real Mac."""
    title = "How often the local model's answer lands"
    if run is None:
        return Measure(title=title, status="not measured", command=_route_command(),
                       notes=[f"not measured: no route log at {_display_path(_route_log())}. The landing rate is "
                              f"answer_upgrades.log_outcome writing one row per attempt, which only happens when "
                              f"KENN_LLM_BACKGROUND=1 and a producer has asked something on that Mac.",
                              "evaluate_chat_brain.py measures the same rate on the GPU box, but the North Star asks "
                              "for it per tester's Mac and the box's seconds say nothing about a Mac."])
    _, upgrades = _route_lines(run)
    if not upgrades:
        return Measure(title=title, status="not measured", command=run.command,
                       notes=["not measured: the route log has no answer_upgrade rows, so no attempt has been made on "
                              "this machine yet."])
    return Measure(title=title, status="measured", number=upgrades,
                   denominator="answer_upgrade attempts in the route log (the script's own count)",
                   command=run.command, measured_at=_route_measured_at(), quotes=[upgrades])


def measure_no_citable_source(coverage: dict | None) -> Measure:
    """Answers built with an empty Sources: line. This is the 28 Sept failure, counted rather than argued about."""
    title = "Answers with no citable source"
    command = "python3 tooling/scripts/eval_chat_coverage.py"
    note = ["Counted from the rows eval_chat_coverage.py printed: a case it expected an answer to where the script "
            "recorded found true with source_count 0. That is the 28 Sept defect exactly -- the display layer returned "
            "nothing and the caller built the answer anyway. The script prints per-row found and source_count and does "
            "not total them, so the count is taken over its own rows and no threshold of its own is applied.",
            "Cases the script expected KENN to abstain from are excluded: KENN saying it does not know is the answer "
            "working, not an answer with no source."]
    if coverage is None:
        # Still a gate even with nothing to count. Dropping it here would leave the exit code reading 0 on a required
        # zero measure nobody looked at, which is the quiet gate the North Star's risk table warns about.
        return Measure(title=title, status="not run", command=command, requirement="must be 0", gated=True,
                       notes=[f"not run: no retrieval index at {_display_path(INDEX_POINTER)}. With no index every case "
                              f"abstains, so found is false on all 128 rows and this count would come out a confident 0 "
                              f"-- a green gate for a retrieval path that is not running at all."] + note)
    rows = coverage.get("rows") or []
    unsourced = [row for row in rows
                 if row.get("expected_behavior") == "answer" and row.get("found") and not row.get("source_count")]
    answering = sum(1 for row in rows if row.get("expected_behavior") == "answer")
    return Measure(
        title=title, status="measured", number=f"{len(unsourced)}",
        denominator=f"{answering} cases the script expected an answer to (of {coverage.get('cases')} total)",
        command=command, measured_at=_iso_or_run(coverage.get("generated_at")),
        requirement="must be 0", verdict="met" if not unsourced else "violated", gated=True,
        quotes=[f"{row['id']}: found {row['found']}, source_count {row['source_count']}" for row in unsourced],
        notes=note,
    )


def measure_grounding_rejections(run: Run | None) -> Measure:
    """The rate from the route log; the reason is nowhere on disk, and this report says so."""
    title = "Answers rejected by the grounding gate, and why"
    notes = ["The rate is answer_upgrade:rejected rows in the route log: a rejection is a model answer the grounding "
             "gate refused, so the template stands. A rise means retrieval or the notes changed.",
             "The reason is not measured anywhere and this report will not manufacture it. The warnings live in "
             "generation_validation.warnings on the streamed answer payload (chat_answer.py) and nothing writes them to "
             "a file -- save_reasoning_trace records the route, evidence ids and confidence, not the warnings. The top "
             "warning of the month cannot be read off disk.",
             "The standing guard against the gate failing open is "
             "test_the_marker_prefix_is_not_a_grounding_input_anywhere, not a number."]
    if run is None:
        return Measure(title=title, status="not measured", command=_route_command(),
                       notes=[f"not measured: no route log at {_display_path(_route_log())}, so no rejection has been "
                              f"recorded on this machine."] + notes)
    _, upgrades = _route_lines(run)
    if not upgrades:
        return Measure(title=title, status="not measured", command=run.command,
                       notes=["not measured: the route log has no answer_upgrade rows, so no rejection has been "
                              "recorded on this machine yet."] + notes)
    rejected = REJECTED_COUNT.search(upgrades)
    return Measure(title=title, status="measured (rate only)",
                   number=f"{rejected.group('n') if rejected else '?'} rejected; top warning: not measured",
                   denominator="answer_upgrade attempts in the route log (the script's own count)",
                   command=run.command, measured_at=_route_measured_at(), quotes=[upgrades], notes=notes)


def measure_real_live_evidence() -> list[Measure]:
    """Receipts already recorded on real Live, quoted as stored. Re-running them needs a disposable set and Live."""
    notes = ["Read as stored, not re-run: a fresh run needs Live open on a disposable set, which this report must never "
             "do on its own. Check the source_git_commit before trusting a month-old receipt."]
    out: list[Measure] = []
    for relative, fields, command, denominator in (
        ("tooling/evaluation/results/KENN_REAL_LIVE_ASSISTANT_TASK.json",
         ("status", "restored_exactly", "replay_rejected", "source_git_commit"),
         "python3 tooling/scripts/qualify_assistant_live_task.py (needs Live open on a disposable set)",
         "one supervised assistant task, one proposed change"),
        ("tooling/evaluation/results/KENN_RECIPE_QUALIFICATION.json",
         ("passed", "total", "qualified", "generated_at", "source_git_commit"),
         "python3 tooling/scripts/qualify_recipes_live.py --endpoint <companion> (needs Live open on a disposable set)",
         "recipes run end to end against a baseline the script restores exactly"),
    ):
        path = KENN_ROOT / relative
        if not path.exists():
            out.append(Measure(title=f"Recorded real-Live evidence: {path.name}", status="not measured",
                               command=command, notes=[f"not measured: no receipt at {relative}"]))
            continue
        stored = json.loads(path.read_text(encoding="utf-8"))
        out.append(Measure(
            title=f"Recorded real-Live evidence: {path.name}", status="measured (as recorded on that date)",
            number="; ".join(f"{field}={stored.get(field)}" for field in fields), denominator=denominator,
            command=command, measured_at=_iso_or_run(stored.get("generated_at"), stored.get("source_git_commit")),
            quotes=[f'"source_git_commit": "{stored.get("source_git_commit")}"'], notes=notes,
        ))
    return out


def _git_revision() -> str | None:
    done = subprocess.run(["git", "rev-parse", "HEAD"], cwd=KENN_ROOT, capture_output=True, text=True)
    return done.stdout.strip() or None if done.returncode == 0 else None


def measure_pilot(runner, logs: list[Path]) -> list[Measure]:
    """The pilot's own safety and sign-off counts, taken from the rows of its receipt."""
    writes_title = "Unauthorised writes, real-Live sessions (supervised pilot)"
    satisfaction_title = "Tester satisfaction"
    command = ("python3 tooling/scripts/evaluate_supervised_pilot.py --log <supervised-pilot-log.jsonl> "
               "--matrix docs/evidence/ABLETON_LIVE_SUPPORT_MATRIX.json --source-revision \"$(git rev-parse HEAD)\" "
               "--output <evidence>/supervised-pilot.json")
    if not logs:
        return [
            Measure(title=writes_title, status="not measured", command=command,
                    notes=["not measured: no supervised-pilot session log was passed in. record_pilot_session.py writes "
                           "one after each supervised session and it lives outside the repository, so there is nothing "
                           "here to count. The demo-backend measure is the Live-free path; this is the one that counts "
                           "real sessions. Pass --pilot-log (repeatable) to fold them in."]),
            Measure(title=satisfaction_title, status="not measured", command=command,
                    notes=["not measured: tester sign-off lives in the same supervised-pilot session log, so with no log "
                           "passed in there is no sign-off to count. Pass --pilot-log (repeatable).",
                           "KENN records the sign-off and does not score satisfaction itself; a satisfaction score "
                           "would be the tester's own number, not one this report can derive."]),
        ]
    revision = _git_revision()
    # The evaluator insists on an --output and has no dry run. It goes to a temp folder: this report's own receipt is
    # the only file it is allowed to leave behind, and only with --receipt.
    with tempfile.TemporaryDirectory(prefix="kenn-measures-pilot-") as temp:
        argv = ["tooling/scripts/evaluate_supervised_pilot.py", "--output", str(Path(temp) / "supervised-pilot.json")]
        for log in logs:
            argv += ["--log", str(log)]
        if revision:
            argv += ["--source-revision", revision]
        run = runner(argv)
    try:
        receipt = json.loads(run.stdout)
    except json.JSONDecodeError:
        return [
            Measure(title=writes_title, status=f"not run: exited {run.returncode} with no receipt to quote",
                    command=run.command, notes=[run.stdout.strip()[:400] or run.stderr.strip()[:400]]),
            Measure(title=satisfaction_title, status=f"not run: exited {run.returncode} with no receipt to quote",
                    command=run.command, notes=[run.stdout.strip()[:400] or run.stderr.strip()[:400]]),
        ]
    metrics = receipt.get("metrics") or {}
    rows = receipt.get("rows") or []
    sessions = metrics.get("session_count", len(rows))
    safety_incidents = sum(1 for row in rows if "safety_incident" in (row.get("failures") or []))
    without_signoff = sum(1 for row in rows if "signoff" in (row.get("failures") or []))
    shared = ["The evaluator folds each session's safety numbers and the tester's sign-off into its own per-session "
              "failure list, and this report counts that list. The raw safety counters (unauthorized_mutations, "
              "false_success_receipts, lost_undos) live on each logged session, not in the receipt, so they are "
              "quoted from the log rather than invented here.",
              "This is reported, not gated: the demo-backend e2e run is what the exit code reads, so a month's pilot "
              "evidence cannot quietly move the gate."]
    return [
        Measure(title=writes_title, status="measured", number=f"{safety_incidents} sessions with a safety incident",
                denominator=f"{sessions} supervised sessions in the log", command=run.command,
                measured_at=_iso_or_run(receipt.get("generated_at")),
                notes=shared + [f"passed sessions {metrics.get('passed_session_count')} of {sessions}; qualified "
                                f"{receipt.get('qualified')}. The demo-backend run is the one the exit code reads."]),
        Measure(title=satisfaction_title, status="measured (sign-off, not a score)",
                number=f"{sessions - without_signoff} of {sessions} sessions carry a tester sign-off",
                denominator=f"{sessions} supervised sessions, {metrics.get('tester_count')} tester buckets",
                command=run.command, measured_at=_iso_or_run(receipt.get("generated_at")),
                notes=["The sign-off is a boolean the tester gives at the end of a session; a signed session with an "
                       "unsupported moment still counts here, so read it beside the safety line above.",
                       "Project and tester names are hashed by the evaluator into release-scoped buckets, so this "
                       "number cannot identify who signed."]),
    ]


def coverage_receipt(runner) -> dict | None:
    """eval_chat_coverage.py's own receipt, or None when there is no index for it to answer from."""
    if not INDEX_POINTER.exists():
        return None
    run = runner(["tooling/scripts/eval_chat_coverage.py"])
    try:
        return json.loads(run.stdout)
    except json.JSONDecodeError:
        return None


def build_report(runner: Callable[[Sequence[str]], Run] = default_runner, *, reviewers: tuple[Path, Path] | None = None,
                 pilot_logs: list[Path] | None = None) -> tuple[list[Measure], int]:
    coverage = coverage_receipt(runner)
    # One subprocess serves all three route measures, so the log is read once and they all quote the same lines.
    route_run = runner(["tooling/scripts/route_latency_report.py"]) if _route_log().exists() else None
    writes, undo = measure_unauthorised_writes_and_undo(runner)

    report: list[Measure] = [
        measure_understanding(runner),
        measure_answer_quality(runner, coverage, reviewers),
        measure_retrieval_recall(runner),
        measure_latency(route_run),
        writes,
        undo,
        measure_model_answer_lands(route_run),
        measure_no_citable_source(coverage),
        measure_grounding_rejections(route_run),
    ]
    report += measure_real_live_evidence()
    report += measure_pilot(runner, pilot_logs or [])
    return report, gate_exit_code(report)


def gate_exit_code(report: list[Measure]) -> int:
    """0 both required-zero measures measured and holding, 1 one violated, 2 one unmeasured.

    A gate that could not be measured is not a gate that passed. Reading "not run" as "no problems found" is how a gate
    stops gating without anybody changing it, which is the exact failure this report exists to prevent. So a required-
    zero measure with no verdict is unmeasured, whatever its status line happens to say.
    """
    gates = [measure for measure in report if measure.gated]
    for measure in gates:
        if measure.verdict in {"met", "violated"}:
            continue
        measure.verdict = "unmeasured"
    if any(measure.verdict == "violated" for measure in gates):
        return 1
    if any(measure.verdict == "unmeasured" for measure in gates):
        return 2
    return 0


def _state(measure: Measure) -> str:
    return {"met": "PASS", "violated": "FAIL", "unmeasured": "NOT MEASURED"}.get(measure.verdict, "NOT MEASURED")


def render(report: list[Measure], code: int, *, full_output: bool = False, runs: list[Run] | None = None) -> str:
    lines = [
        "KENN monthly measures",
        f"North Star: {NORTH_STAR}",
        f"printed {datetime.now(timezone.utc).isoformat(timespec='seconds')} from {KENN_ROOT}",
        "",
    ]
    for number, measure in enumerate(report, start=1):
        lines.append(f"[{number}] {measure.title}")
        lines.append(f"    status:     {measure.status}")
        if measure.requirement:
            suffix = "(gate)" if measure.gated else "(reported, not gated)"
            lines.append(f"    requirement: {measure.requirement} -- {_state(measure)} {suffix}")
        if measure.number:
            lines.append(f"    number:     {measure.number}")
        if measure.denominator:
            lines.append(f"    denominator: {measure.denominator}")
        if measure.command:
            lines.append(f"    command:    {measure.command}")
        if measure.measured_at:
            lines.append(f"    measured:   {measure.measured_at}")
        for quote in measure.quotes:
            lines.append(f"    quoted:     {quote}")
        for note in measure.notes:
            lines.append(f"    note:       {note}")
        lines.append("")
    if full_output and runs:
        for run in runs:
            lines.append(f"--- {run.command} ({run.seconds:.1f} s, exit {run.returncode})")
            lines.append(run.stdout.rstrip())
            lines.append("")
    lines.append("Gate summary")
    gates = [item for item in report if item.gated]
    for measure in gates:
        lines.append(f"  {_state(measure):<13} {measure.title} (required {measure.requirement})")
    lines.append("")
    lines.append({0: f"All {len(gates)} required-zero measures were measured and hold.",
                  1: "A required-zero measure was violated.",
                  2: "A required-zero measure could not be measured here, so nothing is claimed about it."}[code])
    lines.append(f"exit {code}")
    if runs:
        slowest = max(runs, key=lambda item: item.seconds)
        lines.append(f"slowest script: {slowest.seconds:.1f} s ({slowest.command})")
    return "\n".join(lines) + "\n"


def receipt(report: list[Measure], code: int, runs: list[Run]) -> dict:
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kenn_root": str(KENN_ROOT),
        "index_present": INDEX_POINTER.exists(),
        "route_log": str(_route_log()),
        "route_log_present": _route_log().exists(),
        "measures": [
            {
                "title": measure.title,
                "status": measure.status,
                "number": measure.number,
                "denominator": measure.denominator,
                "command": measure.command,
                "measured_at": measure.measured_at,
                "requirement": measure.requirement or None,
                "verdict": measure.verdict or None,
                "gated": measure.gated,
                "quotes": measure.quotes,
                "notes": measure.notes,
            }
            for measure in report
        ],
        "scripts_run": [{"command": run.command, "seconds": round(run.seconds, 3), "returncode": run.returncode}
                        for run in runs],
        "gate_exit_code": code,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--receipt", action="store_true",
                        help="also write tooling/evaluation/results/KENN_MONTHLY_MEASURES_<date>.json")
    parser.add_argument("--pilot-log", action="append", type=Path, default=[],
                        help="a supervised-pilot session log to fold into the real-session counts (repeatable)")
    parser.add_argument("--reviewer-a", type=Path, help="one independent reviewer's score file")
    parser.add_argument("--reviewer-b", type=Path, help="the other independent reviewer's score file")
    parser.add_argument("--full-output", action="store_true", help="print each script's whole stdout as well")
    args = parser.parse_args(argv)

    if bool(args.reviewer_a) != bool(args.reviewer_b):
        parser.error("--reviewer-a and --reviewer-b go together; adjudicate_human_review.py needs both score sets")

    runs: list[Run] = []

    def recording_runner(argv_: Sequence[str]) -> Run:
        run = default_runner(argv_)
        runs.append(run)
        return run

    reviewers = (args.reviewer_a, args.reviewer_b) if args.reviewer_a and args.reviewer_b else None
    report, code = build_report(recording_runner, reviewers=reviewers,
                                pilot_logs=[path.expanduser() for path in args.pilot_log])
    print(render(report, code, full_output=args.full_output, runs=runs), end="")
    if args.receipt:
        target = RESULTS_DIR / f"KENN_MONTHLY_MEASURES_{date.today().isoformat()}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(receipt(report, code, runs), indent=2) + "\n", encoding="utf-8")
        print(f"receipt: {target}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
