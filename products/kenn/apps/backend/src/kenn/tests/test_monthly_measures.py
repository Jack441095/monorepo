"""F2 monthly measures report: the report quotes other scripts' output, and gates what it cannot measure."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from scripts import monthly_measures
from scripts.monthly_measures import Measure, Run, build_report, gate_exit_code, main, render

KENN_ROOT = Path(__file__).resolve().parents[5]


def e2e_output(applied: int = 2, *, writes_before_apply: int = 0, not_restored: int = 0) -> str:
    """The lines e2e_demo_commands.py prints: one before-Apply and one undo verdict per applied command."""
    lines: list[str] = []
    for index in range(applied):
        wrote = "False" if index < writes_before_apply else "True"
        lines.append("“turn the bass down two dB”  (expected: set_volume)")
        lines.append(f"  proposed set_volume (nothing written before Apply: {wrote})")
        lines.append("  applied: applied, Live readback verified: True; changed: Bass volume: 0.500 -> 0.450")
        restored = "False" if index < not_restored else "True"
        lines.append(f"  undo: {'clarification_required' if restored == 'False' else 'applied'}; "
                     f"set restored exactly: {restored} (Track creation has no safe automatic inverse.)"
                     if restored == "False" else
                     f"  undo: applied; set restored exactly: {restored}")
    lines.append(f"\n{applied} executed: {applied} passed apply → verify → undo; 3 asked or answered without "
                 f"writing. State kept in /tmp/kenn-e2e-test")
    return "\n".join(lines)


def coverage_output(unsourced: int = 0, *, total: int = 4) -> str:
    """The rows eval_chat_coverage.py prints, reduced to the fields the uncited-answer count reads."""
    rows = []
    for index in range(total):
        answering = index < total - 1
        rows.append({
            "id": f"case-{index}", "category": "howto", "expected_behavior": "answer" if answering else "abstain",
            "passed": True, "failures": [], "found": answering,
            "confidence": "medium" if answering else "none",
            "source_count": 0 if (answering and index < unsourced) else (2 if answering else 0),
            "error": None,
        })
    return json.dumps({
        "schema": "kenn_chat_coverage_receipt.v1", "generated_at": "2026-09-30T10:00:00+00:00",
        "cases": total, "passed": total, "failed": 0,
        "applicable_cases": total - 1, "applicable_passed": total - 1,
        "abstention_cases": 1, "abstention_passed": 1, "rows": rows,
    })


PHRASINGS = "\n505 phrasings (rule path): right 492 (97.4%), asked 13, wrong 0"
ROUTE_EMPTY = "{}\n0 requests; routes over the 4 s p95 target: none"
ROUTE_WITH_UPGRADES = json.dumps({"chat": {"requests": 4, "p50_ms": 210.0, "p95_ms": 900.0, "brain": 1}}, indent=1) + (
    "\n4 requests; routes over the 4 s p95 target: none\n"
    "model answers (upgrades): 3 started, 2 accepted (67%), 1 rejected, 0 failed, 0 skipped because the model was "
    "busy; accepted ones took a median 4.1 s, p95 5.0 s")


def runner_for(outputs: dict[str, str]):
    """A stand-in for the subprocess runner: each script returns the output it printed in real life."""
    def runner(argv):
        script = Path(argv[0]).name
        return Run(f"python3 {script}", 0, outputs.get(script, ""), "", 0.01)
    return runner


@pytest.fixture
def no_index(monkeypatch, tmp_path):
    """This checkout has no gitignored index, which is the state every month-to-month comparison starts from."""
    monkeypatch.setattr(monthly_measures, "INDEX_POINTER", tmp_path / "data" / "index" / "CURRENT")
    return tmp_path


def find(report: list[Measure], needle: str) -> Measure:
    return next(measure for measure in report if needle in measure.title)


def test_missing_route_log_reports_not_measured_rather_than_a_latency_number(no_index):
    report, _ = build_report(runner_for({"e2e_demo_commands.py": e2e_output()}), pilot_logs=[])
    for title in ("Latency by stage", "How often the local model's answer lands",
                  "Answers rejected by the grounding gate"):
        measure = find(report, title)
        assert measure.status == "not measured"
        assert measure.number == "", f"{title} printed {measure.number!r} where nothing was measured"
        assert "no route log at" in " ".join(measure.notes)


def test_missing_index_leaves_recall_unrun_rather_than_recall_of_zero(no_index):
    report, _ = build_report(runner_for({"e2e_demo_commands.py": e2e_output()}), pilot_logs=[])
    recall = find(report, "Retrieval recall")
    assert recall.status == "not run" and recall.number == ""
    # evaluate_retrieval_modes.py would have printed recall@4 0.0 and exited 0 with no index at all.
    assert "no retrieval index at" in " ".join(recall.notes)


def test_a_required_zero_measure_that_could_not_be_measured_exits_two_and_stays_in_the_gate_summary(no_index):
    # The 28 Sept lesson: a gate nobody measured must not read as a pass. This is the regression that keeps the
    # uncited-answer measure in the gate list even when there is no index to count it over.
    report, code = build_report(runner_for({"e2e_demo_commands.py": e2e_output()}), pilot_logs=[])
    assert code == 2
    summary = render(report, code)
    assert re.search(r"NOT MEASURED\s+Answers with no citable source \(required must be 0\)", summary)
    assert "All 2 required-zero measures were measured and hold." not in summary
    assert next(measure for measure in report if measure.gated and "citable" in measure.title).verdict == "unmeasured"


def test_a_violated_zero_requirement_exits_non_zero(no_index):
    report, code = build_report(
        runner_for({"e2e_demo_commands.py": e2e_output(writes_before_apply=1)}), pilot_logs=[])
    assert code == 1
    writes = find(report, "Unauthorised writes (writes to the set")
    assert writes.number == "1" and writes.verdict == "violated" and writes.gated
    assert re.search(r"FAIL\s+Unauthorised writes", render(report, code))
    # The offending line is quoted so a reader can see which command wrote before Apply.
    assert any("nothing written before Apply: False" in quote for quote in writes.quotes)


def test_a_passing_run_with_both_required_zero_measures_met_exits_zero(monkeypatch, tmp_path):
    monkeypatch.setattr(monthly_measures, "INDEX_POINTER", tmp_path / "CURRENT")
    (tmp_path / "CURRENT").write_text("v1\n", encoding="utf-8")
    report, code = build_report(
        runner_for({"e2e_demo_commands.py": e2e_output(), "eval_chat_coverage.py": coverage_output()}), pilot_logs=[])
    assert code == 0
    assert find(report, "Answers with no citable source").number == "0"
    assert find(report, "Unauthorised writes (writes to the set").number == "0"
    assert "All 2 required-zero measures were measured and hold." in render(report, code)


def test_an_uncited_answer_fails_the_gate_it_was_added_for(monkeypatch, tmp_path):
    monkeypatch.setattr(monthly_measures, "INDEX_POINTER", tmp_path / "CURRENT")
    (tmp_path / "CURRENT").write_text("v1\n", encoding="utf-8")
    report, code = build_report(
        runner_for({"e2e_demo_commands.py": e2e_output(), "eval_chat_coverage.py": coverage_output(unsourced=1)}),
        pilot_logs=[])
    uncited = find(report, "Answers with no citable source")
    assert code == 1 and uncited.number == "1" and uncited.verdict == "violated"
    assert uncited.quotes == ["case-0: found True, source_count 0"]


def test_a_route_log_with_no_upgrade_rows_reports_no_landing_rate_instead_of_zero_percent(monkeypatch, tmp_path):
    monkeypatch.setattr(monthly_measures.route_log, "LOG", tmp_path / "routes.jsonl")
    (tmp_path / "routes.jsonl").write_text('{"route": "chat", "ms": 210.0, "brain": false}\n', encoding="utf-8")
    outputs = {"e2e_demo_commands.py": e2e_output(), "route_latency_report.py": ROUTE_EMPTY}
    report, _ = build_report(runner_for(outputs), pilot_logs=[])
    lands = find(report, "How often the local model's answer lands")
    assert lands.status == "not measured" and lands.number == ""
    assert "no answer_upgrade rows" in " ".join(lands.notes)


def test_latency_quotes_the_script_s_request_line_not_the_end_of_its_json(monkeypatch, tmp_path):
    monkeypatch.setattr(monthly_measures.route_log, "LOG", tmp_path / "routes.jsonl")
    (tmp_path / "routes.jsonl").write_text('{"route": "chat", "ms": 210.0, "brain": false}\n', encoding="utf-8")
    outputs = {"e2e_demo_commands.py": e2e_output(), "route_latency_report.py": ROUTE_WITH_UPGRADES}
    report, _ = build_report(runner_for(outputs), pilot_logs=[])
    latency = find(report, "Latency by stage")
    assert latency.number == "4 requests; routes over the 4 s p95 target: none"
    assert "}" not in latency.number
    lands = find(report, "How often the local model's answer lands")
    assert lands.status == "measured" and "2 accepted (67%)" in lands.number
    rejections = find(report, "Answers rejected by the grounding gate")
    assert rejections.number == "1 rejected; top warning: not measured"


def test_understanding_is_quoted_from_the_script_rather_than_recomputed(no_index):
    report, _ = build_report(
        runner_for({"e2e_demo_commands.py": e2e_output(), "score_natural_phrasings.py": PHRASINGS}), pilot_logs=[])
    measure = find(report, "Understanding")
    assert measure.number == "right 492 of 505 (97.4%), asked 13, wrong 0"
    assert measure.quotes == [PHRASINGS.strip()]
    # The North Star's older 494 stays visible beside the script's 492, and the report says which is stale.
    assert "494" in " ".join(measure.notes) and "stale" in " ".join(measure.notes)


def test_a_summary_the_report_cannot_reconcile_reports_not_measured_instead_of_gating(no_index):
    # The e2e script claims 4 applied commands but only prints 2 verdicts: our parser is reading output it no longer
    # understands, so neither safety measure may be quoted from it.
    broken = e2e_output(applied=2).replace("2 executed: 2 passed", "4 executed: 4 passed")
    report, code = build_report(runner_for({"e2e_demo_commands.py": broken}), pilot_logs=[])
    writes = find(report, "Unauthorised writes (writes to the set")
    assert writes.status.startswith("not measured: ") and writes.number == "" and writes.verdict == "unmeasured"
    assert find(report, "Undo success").status.startswith("not measured: ")
    assert code == 2


def test_a_broken_safety_script_cannot_let_the_other_gate_carry_the_exit_code(monkeypatch, tmp_path):
    # With the index present the uncited-answer gate holds, so a broken e2e run is the only thing unmeasured. If the
    # gate dropped out of the list on that path the report would exit 0 on a run that never counted a write.
    monkeypatch.setattr(monthly_measures, "INDEX_POINTER", tmp_path / "CURRENT")
    (tmp_path / "CURRENT").write_text("v1\n", encoding="utf-8")
    broken = e2e_output(applied=2).replace("2 executed: 2 passed", "4 executed: 4 passed")
    report, code = build_report(
        runner_for({"e2e_demo_commands.py": broken, "eval_chat_coverage.py": coverage_output()}), pilot_logs=[])
    assert find(report, "Answers with no citable source").verdict == "met"
    assert find(report, "Unauthorised writes (writes to the set").verdict == "unmeasured"
    assert code == 2


def test_an_undo_shortfall_is_reported_but_does_not_fail_the_gate(monkeypatch, tmp_path):
    # KENN has no safe inverse for track creation, so an undo shortfall there is a known bound, not a lost undo.
    # Reclassifying it would be this report quietly changing a measure's definition.
    monkeypatch.setattr(monthly_measures, "INDEX_POINTER", tmp_path / "CURRENT")
    (tmp_path / "CURRENT").write_text("v1\n", encoding="utf-8")
    report, code = build_report(
        runner_for({"e2e_demo_commands.py": e2e_output(not_restored=1), "eval_chat_coverage.py": coverage_output()}),
        pilot_logs=[])
    undo = find(report, "Undo success")
    assert undo.verdict == "violated" and not undo.gated
    assert undo.number == "1 of 2 restored exactly (1 not restored)"
    assert code == 0


def test_pilot_measures_stay_unmeasured_without_a_session_log(no_index):
    report, _ = build_report(runner_for({"e2e_demo_commands.py": e2e_output()}), pilot_logs=[])
    writes = find(report, "real-Live sessions (supervised pilot)")
    satisfaction = find(report, "Tester satisfaction")
    assert writes.status == "not measured" and writes.number == ""
    assert "not measured: no supervised-pilot session log" in " ".join(writes.notes)
    assert satisfaction.status == "not measured" and satisfaction.number == ""
    assert "not measured: tester sign-off" in " ".join(satisfaction.notes)


def test_a_default_run_writes_nothing_tracked_and_leaves_no_receipt(monkeypatch, capsys):
    monkeypatch.setattr(monthly_measures, "INDEX_POINTER", KENN_ROOT / "apps/backend/src/kenn/data/index/CURRENT")
    monkeypatch.setattr(monthly_measures, "default_runner", runner_for({"e2e_demo_commands.py": e2e_output()}))
    before = tracked_changes()
    receipts = sorted((KENN_ROOT / "tooling/evaluation/results").glob("KENN_MONTHLY_MEASURES_*.json"))
    main([])
    capsys.readouterr()
    assert tracked_changes() == before
    assert sorted((KENN_ROOT / "tooling/evaluation/results").glob("KENN_MONTHLY_MEASURES_*.json")) == receipts


def test_receipt_is_written_only_on_request_with_a_dated_schema_consistent_name(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(monthly_measures, "default_runner", runner_for({"e2e_demo_commands.py": e2e_output()}))
    monkeypatch.setattr(monthly_measures, "RESULTS_DIR", tmp_path / "results")
    main(["--receipt"])
    capsys.readouterr()
    written = list((tmp_path / "results").glob("*.json"))
    assert len(written) == 1 and written[0].name.startswith("KENN_MONTHLY_MEASURES_")
    payload = json.loads(written[0].read_text(encoding="utf-8"))
    assert payload["schema"] == "kenn.monthly_measures.v1"
    assert payload["gate_exit_code"] in {0, 1, 2}
    assert payload["measures"] and payload["index_present"] is False


def test_reviewer_scores_are_only_measured_when_both_score_files_are_given(monkeypatch, no_index, tmp_path, capsys):
    monkeypatch.setattr(monthly_measures, "default_runner", runner_for({"e2e_demo_commands.py": e2e_output()}))
    # adjudicate_human_review.py needs both score sets; one alone must be refused rather than half-answered.
    for argv in (["--reviewer-a", str(tmp_path / "a.json")], ["--reviewer-b", str(tmp_path / "b.json")]):
        with pytest.raises(SystemExit):
            main(argv)
    capsys.readouterr()


def test_every_measure_carries_a_command_and_a_status_so_no_line_is_blank(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(monthly_measures.route_log, "LOG", tmp_path / "routes.jsonl")
    (tmp_path / "routes.jsonl").write_text('{"route": "chat", "ms": 210.0, "brain": false}\n', encoding="utf-8")
    monkeypatch.setattr(monthly_measures, "default_runner", runner_for({
        "e2e_demo_commands.py": e2e_output(), "route_latency_report.py": ROUTE_WITH_UPGRADES,
        "score_natural_phrasings.py": PHRASINGS}))
    main([])
    printed = capsys.readouterr().out
    for measure in build_report(runner_for({
            "e2e_demo_commands.py": e2e_output(), "route_latency_report.py": ROUTE_WITH_UPGRADES,
            "score_natural_phrasings.py": PHRASINGS}), pilot_logs=[])[0]:
        assert measure.status, f"{measure.title} has no status"
        assert measure.command, f"{measure.title} has no command to reproduce it"
        assert measure.number or measure.status.startswith("not "), f"{measure.title} printed neither a number nor a reason"
    assert "not measured" in printed and "PASS" in printed


def tracked_changes() -> str:
    done = subprocess.run(["git", "status", "--porcelain"], cwd=KENN_ROOT, capture_output=True, text=True)
    return done.stdout


def test_gate_exit_code_reads_a_bare_gate_with_no_verdict_as_unmeasured():
    # A required-zero measure with no verdict and no measured status is unmeasured, whatever its status line says.
    bare = Measure(title="Answers with no citable source", status="not run", gated=True)
    assert gate_exit_code([bare]) == 2
    assert bare.verdict == "unmeasured"
