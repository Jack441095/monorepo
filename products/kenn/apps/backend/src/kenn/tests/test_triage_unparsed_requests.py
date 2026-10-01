"""B4 wording triage: the misses are clustered by the rule family that came closest, and each cluster
carries a proposal a human can act on. Nothing here may touch Live or edit live_intent.py."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.triage_unparsed_requests import (Cluster, Row, cluster, diagnose, is_miss, read_log_files, render,
                                               report)

KENN_ROOT = Path(__file__).resolve().parents[5]
SCRIPT = KENN_ROOT / "tooling" / "scripts" / "triage_unparsed_requests.py"
SYNTHETIC_SAMPLE = KENN_ROOT / "tooling" / "data" / "synthetic_asked_log_sample_2026-09-30.jsonl"
SCORER_RUN = KENN_ROOT / "tooling" / "data" / "natural_blind_drafted_2026-09-29_first_run.json"


@pytest.fixture(scope="module")
def snapshot_and_parse():
    from kenn.core.fake_live import FakeLiveBackend
    from kenn.core.live_intent import parse_request

    return FakeLiveBackend().query_session_state(), parse_request


def _child_env(**overrides) -> dict[str, str]:
    """Absolute PYTHONPATH: pytest may have been started with a relative one, which breaks once cwd moves."""
    return dict(os.environ, PYTHONPATH=f"{KENN_ROOT / 'apps' / 'backend' / 'src'}:{KENN_ROOT / 'tooling'}", **overrides)


def asked(query: str, **fields) -> Row:
    """One row in the shape asked_log.py writes, which is the only shape a tester produces."""
    return Row(source="asked_log.jsonl", line=1, query=query, reply=fields.pop("reply", ""),
               recorded=fields.pop("recorded", "clarification_required"), raw=fields)


def triage(queries: list[str], snapshot_and_parse) -> list[Cluster]:
    snapshot, parse = snapshot_and_parse
    return cluster([diagnose(asked(query), snapshot, parse) for query in queries])


def families(clusters: list[Cluster]) -> list[str]:
    return [group.family for group in clusters]


def test_a_vague_pan_lands_in_the_pan_cluster_and_not_with_the_fader_words(snapshot_and_parse) -> None:
    # Both are "KENN asked because a number was missing", and a grouping on that alone would merge them. The
    # fix is a different pattern for each, so they have to stay apart.
    clusters = triage(["pan the snare a bit", "lower the bass a bit"], snapshot_and_parse)
    assert families(clusters) == ["needs_amount/set_pan", "needs_amount/set_volume"]


def test_a_pronoun_only_request_is_called_a_track_gap_only_when_a_track_name_makes_it_parse(snapshot_and_parse) -> None:
    # "lower it a bit" parses the moment a track name replaces the pronoun, so a track rule would have caught it.
    snapshot, parse = snapshot_and_parse
    gap = diagnose(asked("lower it a bit"), snapshot, parse)
    assert (gap.signal, gap.action) == ("needs_track", "set_volume") and "Kick" in gap.probe

    # "make the drums slap" does not parse for any track in the set, so calling it a track gap would send a
    # human to the wrong rule table. It is a wording family with no measurable target.
    taste = diagnose(asked("make the drums slap"), snapshot, parse)
    assert taste.signal == "no_action/taste" and taste.probe == () and is_miss(taste)


def test_a_taste_request_and_a_missing_number_are_never_one_cluster(snapshot_and_parse) -> None:
    # The isolation this tool exists for: two phrasings a producer could both call "KENN didn't get it", and
    # two completely different fixes. Merged into one cluster, the report would propose one rule for both.
    clusters = triage(["lower the bass a bit", "pan the snare a bit", "make the drums slap", "make the hats sit "
                        "better", "widen the hats"], snapshot_and_parse)
    assert families(clusters) == ["no_action/taste", "needs_amount/set_pan", "needs_amount/set_volume"]
    taste = clusters[0]
    assert len(taste.rows) == 3 and all(row.disposition == "asked" for row in taste.rows)


def test_a_refusal_is_counted_and_labelled_as_the_boundary_not_a_wording_gap(snapshot_and_parse) -> None:
    snapshot, parse = snapshot_and_parse
    row = Row(source="asked_log.jsonl", line=1, query="delete the kick in the set", reply="",
              recorded="refused")
    [group] = cluster([diagnose(row, snapshot, parse)])
    assert (group.signal, group.rows[0].disposition) == ("refused", "refused")
    assert "boundary" in group.label and "should change here" in group.proposed["change"]


def test_a_row_the_rules_now_parse_is_clustered_away_from_the_parser_fixes(snapshot_and_parse) -> None:
    # The usual cause after a rule fix: the log says KENN asked, and the rules understand it today. Sending a
    # human to live_intent.py for that one wastes the day, so it gets its own cluster and says so.
    snapshot, parse = snapshot_and_parse
    stale = Row(source="asked_log.jsonl", line=1, query="turn the bass down 2 dB", reply="",
                recorded="clarification_required")
    diagnosed = diagnose(stale, snapshot, parse)
    [group] = cluster([diagnosed])
    assert group.signal == "asked_after_parsing" and group.family == "asked_after_parsing/set_volume"
    assert "not a live_intent.py problem" in group.proposed["change"]
    text = render([group], [diagnosed], 0, ["asked_log.jsonl"], 3)
    assert "the rules parsed it and the gateway still asked (set_volume)" in text


def test_a_correct_parse_is_counted_and_never_clustered(snapshot_and_parse) -> None:
    snapshot, parse = snapshot_and_parse
    right = Row(source="score.json", line=1, query="turn the bass down 2 dB", reply="", recorded="right")
    diagnosed = diagnose(right, snapshot, parse)
    assert diagnosed.disposition == "correct" and not is_miss(diagnosed)
    assert cluster([diagnosed]) == []

    # The same request recorded as an ask is a miss, of the kind no live_intent.py edit fixes.
    stale = diagnose(asked("turn the bass down 2 dB"), snapshot, parse)
    assert stale.signal == "asked_after_parsing" and is_miss(stale)
    assert "core/live_command.py" in cluster([stale])[0].proposed["change"]


def test_a_row_with_no_recorded_outcome_is_not_called_a_miss(snapshot_and_parse) -> None:
    # A phrasing fixture carries no verdict, so nothing said KENN failed on it. Reporting it as a miss would
    # invent a failure out of a fixture.
    snapshot, parse = snapshot_and_parse
    fixture = Row(source="fixture.jsonl", line=1, query="turn the bass down 2 dB", reply="", recorded="")
    diagnosed = diagnose(fixture, snapshot, parse)
    assert diagnosed.disposition == "understood" and not is_miss(diagnosed) and cluster([diagnosed]) == []


def test_a_fixture_row_that_the_rules_cannot_read_is_still_reported(snapshot_and_parse) -> None:
    snapshot, parse = snapshot_and_parse
    fixture = Row(source="fixture.jsonl", line=1, query="make the drums slap", reply="", recorded="")
    assert is_miss(diagnose(fixture, snapshot, parse))


def test_a_scorer_wrong_verdict_becomes_its_own_cluster_and_never_a_rule_proposal(snapshot_and_parse) -> None:
    snapshot, parse = snapshot_and_parse
    wrong = Row(source="score.json", line=1, query="set the kick to -12", reply="", recorded="wrong")
    diagnosed = diagnose(wrong, snapshot, parse)
    assert diagnosed.signal == "wrong_plan"
    [group] = cluster([diagnosed])
    assert "planned the wrong thing" in group.label
    assert "score_natural_phrasings.py" in group.proposed["change"]


def test_every_cluster_carries_the_rule_family_a_wording_and_a_test_to_add(snapshot_and_parse) -> None:
    clusters = triage(["lower the bass a bit", "turn the hats down a touch", "pan the snare a bit",
                       "turn the reverb send on the synth down 3 dB", "make the drums slap"], snapshot_and_parse)
    for group in clusters:
        proposal = group.proposed
        assert proposal["rules"] and proposal["change"] and proposal["test"]
        assert group.wordings, "a cluster with no wording gives a human nothing to copy into a test"
        # Every rule name is a real symbol in the parser, so the proposal points at code that exists.
        from kenn.core import live_intent
        for name in proposal["rules"].replace(",", " ").replace("(", " ").replace(")", " ").split():
            if name.startswith("_"):
                assert hasattr(live_intent, name), f"{name} is not in live_intent.py"


def test_the_rendered_report_names_the_patterns_examples_and_the_gate(snapshot_and_parse) -> None:
    queries = ["lower the bass a bit", "turn the hats down a touch"]
    snapshot, parse = snapshot_and_parse
    diagnoses = [diagnose(asked(query), snapshot, parse) for query in queries]
    text = render(cluster(diagnoses), diagnoses, 0, ["asked_log.jsonl"], 3, 8, 2)
    assert "_RELATIVE_VOLUME_AMOUNT" in text
    assert "lower the bass a bit" in text and "2 row(s), 2 wording(s)" in text
    assert "score_natural_phrasings.py" in text
    assert "never edits live_intent.py" in text


def test_a_cluster_shows_whether_kenn_asked_something_or_only_said_it_did_not_catch_it(snapshot_and_parse) -> None:
    # "Silent" is its own problem: the generic answer teaches the producer nothing and cannot be answered with a
    # number, while a named question can. The report has to show which one a cluster got.
    snapshot, parse = snapshot_and_parse
    silent = diagnose(asked("make the drums slap", reply="I didn't catch a change to make there. Try something "
                                                                 "like \"turn the bass down 2 dB\"..."), snapshot, parse)
    specific = diagnose(asked("lower the bass a bit", reply="By how much? For example \"turn Bass down 2 dB\"."),
                        snapshot, parse)
    by_family = {group.family: group for group in cluster([silent, specific])}
    assert by_family["no_action/taste"].replies == [silent.reply]
    assert by_family["needs_amount/set_volume"].replies == [specific.reply]
    assert silent.reply.startswith("I didn't catch") and specific.reply.startswith("By how much?")
    text = render([by_family["no_action/taste"]], [silent], 0, ["asked_log.jsonl"], 3)
    assert "KENN said: I didn't catch a change" in text


def test_clusters_are_ranked_by_size_so_the_biggest_win_is_first(snapshot_and_parse) -> None:
    clusters = triage(["make the drums slap", "lower the bass a bit", "turn the hats down a touch", "pan the snare "
                        "a bit", "kill playback"], snapshot_and_parse)
    assert [len(group.rows) for group in clusters] == [2, 1, 1, 1]


def test_the_report_says_so_when_the_log_has_no_rows(tmp_path, snapshot_and_parse) -> None:
    empty = tmp_path / "asked_log.jsonl"
    empty.write_text("", encoding="utf-8")
    rows, skipped = read_log_files([empty])
    text = render(cluster([]), rows, skipped, [str(empty)], 3)
    assert rows == [] and skipped == 0
    assert "No rows" in text and "understood everything this week" in text


def test_the_report_reconciles_with_the_scorers_own_counts(snapshot_and_parse) -> None:
    # The scorer owns the right/asked/wrong verdict (score_natural_phrasings.py). Reading one of its runs must
    # not change a single number, or the triage report would be contradicting the Stage 1 gate.
    rows, skipped = read_log_files([SCORER_RUN])
    payload = json.loads(SCORER_RUN.read_text(encoding="utf-8"))
    assert skipped == 0 and len(rows) == len(payload["rows"])
    snapshot, parse = snapshot_and_parse
    counts = report(cluster([diagnose(row, snapshot, parse) for row in rows]),
                    [diagnose(row, snapshot, parse) for row in rows], skipped, [str(SCORER_RUN)])["dispositions"]
    assert counts["correct"] == payload["counts"]["right"]
    assert counts["asked"] == payload["counts"]["asked"]
    assert counts["wrong_plan"] == payload["counts"]["wrong"]


def test_the_asked_log_the_app_writes_is_read_as_it_is(tmp_path) -> None:
    # The row shape asked_log.py.record writes, with the session key the diagnostics file drops.
    log = tmp_path / "asked_log.jsonl"
    log.write_text(json.dumps({"timestamp": 1.0, "session": "abc123", "said": "lower the bass a bit",
                               "kenn_said": "By how much?", "status": "clarification_required",
                               "next_said": "down 2", "next_status": "proposal_ready"}) + "\n", encoding="utf-8")
    [row] = read_log_files([log])[0]
    assert (row.query, row.reply, row.recorded) == ("lower the bass a bit", "By how much?", "clarification_required")


def test_a_diagnostics_file_or_scorer_run_wrapped_as_json_is_read_too(tmp_path) -> None:
    wrapper = tmp_path / "diagnostics.json"
    wrapper.write_text(json.dumps({"asked_log": [{"said": "make the drums slap", "status": "clarification_required"}]})
                       + "\n", encoding="utf-8")
    [row] = read_log_files([wrapper])[0]
    assert row.query == "make the drums slap"


def test_a_torn_last_line_is_skipped_rather_than_failing_the_run(tmp_path) -> None:
    # asked_log.record rewrites the file on every miss, so a technician copying it can catch a partial write.
    log = tmp_path / "asked_log.jsonl"
    log.write_text(json.dumps({"said": "lower the bass a bit", "status": "clarification_required"}) + "\n"
                   + '{"said": "turn the hats do', encoding="utf-8")
    rows, skipped = read_log_files([log])
    assert [row.query for row in rows] == ["lower the bass a bit"] and skipped == 1


def test_running_the_script_leaves_the_log_and_live_intent_untouched(tmp_path) -> None:
    log = tmp_path / "asked_log.jsonl"
    log.write_text("".join(json.dumps({"said": query, "kenn_said": "By how much?",
                                       "status": "clarification_required"}) + "\n"
                   for query in ("lower the bass a bit", "pan the snare a bit", "make the drums slap")),
                   encoding="utf-8")
    before_log = log.read_bytes()
    parser = KENN_ROOT / "apps" / "backend" / "src" / "kenn" / "core" / "live_intent.py"
    before_parser = (parser.stat().st_mtime_ns, parser.stat().st_size)

    result = subprocess.run([sys.executable, str(SCRIPT), str(log), "--out", str(tmp_path / "report.txt")],
                            capture_output=True, text=True, cwd=KENN_ROOT, env=_child_env())
    assert result.returncode == 0, result.stderr
    assert log.read_bytes() == before_log, "the triage run wrote to the log it was reading"
    assert (parser.stat().st_mtime_ns, parser.stat().st_size) == before_parser
    assert (tmp_path / "report.txt").is_file()
    assert not [path for path in tmp_path.iterdir() if path.suffix == ".json"]


def test_the_script_forces_the_fake_backend_even_when_the_environment_says_osc(tmp_path) -> None:
    # On the producer's Mac KENN_LIVE_BACKEND is often "osc". A triage run must never reach their Live set.
    log = tmp_path / "asked_log.jsonl"
    log.write_text(json.dumps({"said": "lower the bass a bit", "status": "clarification_required"}) + "\n",
                   encoding="utf-8")
    env = _child_env(KENN_LIVE_BACKEND="osc")
    result = subprocess.run([sys.executable, str(SCRIPT), str(log)], capture_output=True, text=True, cwd=KENN_ROOT,
                            env=env)
    assert result.returncode == 0, result.stderr
    assert "Parsed on FakeLiveBackend" in result.stdout and "8 track(s), 2 return track(s)" in result.stdout


def test_the_synthetic_sample_ships_in_the_asked_log_shape_and_is_marked_as_synthetic() -> None:
    # tooling/data/natural_holdout*.jsonl gates the Stage 1 numbers and must not gain rows; this file exists so
    # the triage script has something to read, and every row says so on its face.
    rows, skipped = read_log_files([SYNTHETIC_SAMPLE])
    payload = [json.loads(line) for line in SYNTHETIC_SAMPLE.read_text(encoding="utf-8").splitlines()]
    assert skipped == 0 and len(rows) == len(payload) and len(rows) >= 30
    assert all(row["synthetic"] is True and "synthetic" in row["source_kind"] for row in payload)
    assert all(row["status"] in {"clarification_required", "refused"} for row in payload)
    assert all(row["said"] and row["kenn_said"] for row in payload)
