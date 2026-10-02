"""The eval substrate reports a rate with its n, and never hides a stratum that failed.

Acceptance was judged on n=29 for weeks and 9-row partials inside one session were read as verdicts twice. These tests
pin the reporting rules that make that impossible to repeat, rather than the numbers themselves, which move with the
index.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

KENN_ROOT = Path(__file__).resolve().parents[5]
TOOLING_SCRIPTS = KENN_ROOT / "tooling" / "scripts"
sys.path.insert(0, str(TOOLING_SCRIPTS))

import rescore_captured_answers as harness  # noqa: E402


def _item(**overrides) -> dict:
    base = {
        "question": "q",
        "stratum": "production.numeric",
        "gold_chunk_id": "c1",
        "must_abstain": False,
        "route": "production",
        "confidence": "high",
        "answer_mode": "studio_dialogue",
        "recorded_accepted": True,
        "accepted": True,
        "verdict_changed": False,
        "warnings": [],
        "unsupported_measurements": [],
        "fabricated_sources": [],
        "evidence_chunks_shown": 3,
        "evidence_source": "recomputed",
        # Stated rather than left to the harness default: report() reads a row with no gold match as unscored, so a
        # fixture that omits it would be excluded from the traceability rate these tests are asserting on.
        "gold_chunk_scored": True,
        "answer_measurements": [],
        "measurements_not_in_gold_chunk": [],
        "numeric_claims_traceable": True,
    }
    base.update(overrides)
    return base


def _report(items, capsys) -> str:
    harness.report(items, source=Path("capture.jsonl"))
    return capsys.readouterr().out


def test_a_rate_below_fifty_rows_is_announced_as_uninterpretable(capsys) -> None:
    # 29 rows is the standing case: the rate moved 41% to 66% and the interval still spans about 17 points, so the
    # number must never be printable without that caveat attached to it.
    out = _report([_item() for _ in range(29)], capsys)
    assert "not statistically interpretable" in out
    assert "n=29" in out


def test_fifty_rows_clears_the_interpretability_warning(capsys) -> None:
    out = _report([_item() for _ in range(50)], capsys)
    assert "not statistically interpretable" not in out


def test_every_stratum_rate_prints_its_own_n(capsys) -> None:
    out = _report(
        [
            _item(stratum="production.numeric"),
            _item(stratum="production.numeric"),
            _item(stratum="production.numeric", accepted=False, recorded_accepted=False,
                  verdict_changed=True, warnings=["generated answer punts to the sources instead of synthesizing them"]),
            _item(stratum="ableton.no_numeric", accepted=False, recorded_accepted=False, verdict_changed=True),
        ],
        capsys,
    )
    # The failing tail stratum is named with its own denominator, so 1-of-1 cannot be read as a 100% failure rate or
    # averaged away into the dominant stratum.
    assert "production.numeric" in out
    assert "2/3" in out
    assert "ableton.no_numeric" in out
    assert "0/1" in out
    assert "macro" in out


def test_a_must_abstain_answer_counts_as_the_failure_not_a_pass(capsys) -> None:
    out = _report(
        [_item(stratum="related_question_echo", must_abstain=True, accepted=True)], capsys
    )
    assert "answered anyway" in out
    assert "not 'passed'" in out


def test_measurements_absent_from_the_gold_chunk_are_reported_separately_from_the_gate(capsys) -> None:
    out = _report(
        [
            _item(
                answer_measurements=["2db", "4:1"],
                measurements_not_in_gold_chunk=["2db"],
                numeric_claims_traceable=False,
                accepted=True,
            )
        ],
        capsys,
    )
    # The gate cleared this (2 db is somewhere in the shown evidence). The stricter question the eval set exists to
    # ask is whether it is in the gold chunk, and that has to be visible as its own number.
    assert "0/1 = 0.0% of answers carrying any measurement" in out
    assert "1 measurement(s) absent from the gold chunk" in out


def test_a_changed_verdict_reports_the_reason_it_changed(capsys) -> None:
    out = _report(
        [
            _item(
                recorded_accepted=True,
                accepted=False,
                verdict_changed=True,
                warnings=["generated answer cites sources not in the retrieved evidence"],
            )
        ],
        capsys,
    )
    assert "accepted -> rejected" in out
    assert "cites sources not in the retrieved evidence" in out


def test_an_unlabelled_capture_still_gets_strata_so_a_run_is_never_silently_flat(capsys) -> None:
    out = _report([_item(stratum="", route="ableton")], capsys)
    assert "ableton(unlabelled)" in out


def test_the_harness_verdict_is_the_gate_verdict_and_nothing_else(monkeypatch) -> None:
    # The one invariant that keeps this harness honest: score_item's accepted flag is whatever the production gate
    # returned, computed independently here from the same inputs. If a second copy of the thresholds ever creeps into
    # score_item, these two drift and the test fails.
    from kenn.core.chat_grounding import generated_answer_validation

    chunk = {
        "id": "bass-processing-basics-note-2", "source": "bass-processing-basics.md", "kind": "note",
        "title": "Bass Processing Basics", "page": 0, "evidence_class": "curated_kenn_note",
        "section": "Try this", "topics": ["bass"],
        "text": "Try this:\n1. High-pass non-bass elements that do not need sub information.\n"
                "2. Cut muddy low-mids around 200-350 Hz only if the bass sounds boxy.",
    }
    chunks = [chunk]
    results = [(243.0, chunk)]
    row = {
        "question": "how do I process bass",
        "answer": "High-pass the non-bass elements, then cut muddy low-mids around 200-350 Hz with "
                  "EQ Eight on the bass track only when it sounds boxy. Add a saturator so the low end "
                  "is audible on laptop speakers. Sources:\n- Bass Processing Basics "
                  "(bass-processing-basics.md)",
        "accepted": False,
        "warnings": [],
    }

    # score_item re-runs retrieval, which would consult the real index; the point here is the gate call, not retrieval.
    monkeypatch.setattr(harness, "_replay_results", lambda q, c, t: results)
    monkeypatch.setattr(harness, "_gate_inputs", lambda q, r, tc: ("production", "high", "studio_dialogue"))

    item = harness.score_item(row, chunks, _stub_terms())
    direct = generated_answer_validation(
        "how do I process bass",
        results,
        row["answer"],
        route="production",
        confidence="high",
        answer_mode="studio_dialogue",
        timeline_context=None,
        additional_evidence_text=None,
    )
    assert item["accepted"] == direct["accepted"]
    assert item["warnings"] == list(direct["warnings"])
    assert item["route"] == "production"
    # 200-350 Hz came out of the evidence, so neither the gate nor the harness should call it invented.
    assert item["unsupported_measurements"] == []


def _stub_terms() -> dict:
    return {"version": 3, "total_docs": 1, "avg_len": 1.0, "lengths": [1], "term_counts": [{}], "idf": {},
            "inverted_index": {}}


def test_a_range_in_the_answer_is_read_as_two_measurements_not_a_negative() -> None:
    # 2 Oct 2026: "200-400 Hz" parsed as "-400 Hz", so quoting a range's own lower bound was rejected as invented and
    # "-18 dBFS" could be restated "+18 dBFS" and pass. The harness must read measurements with the production parser,
    # which expands ranges to their endpoints first.
    from kenn.core.chat_grounding import _measurements

    assert _measurements("cut 200-400 Hz") == {"200hz", "400hz"}
    assert harness._measurement_keys("cut 200-400 Hz") == {"200hz", "400hz"}
    # The minus is captured and the plus is not, so the two spellings land on different keys and restating the sign
    # cannot slip through as the same value.
    assert _measurements("keep -18 dBFS headroom") == {"-18dbfs"}
    assert _measurements("keep +18 dBFS headroom") == {"18dbfs"}
    assert _measurements("keep -18 dBFS headroom") & _measurements("keep +18 dBFS headroom") == set()


def test_the_harness_does_not_duplicate_the_gate_decision_logic() -> None:
    source = (TOOLING_SCRIPTS / "rescore_captured_answers.py").read_text(encoding="utf-8")
    for forbidden in ("ANSWER_QUALITY_MIN_SCORE", "0.16"):
        assert forbidden not in source, f"harness re-implements a gate threshold: {forbidden}"
    # Warning text is fine to display, because it is only ever read back out of the gate's own return value, never
    # matched locally. What must not appear is a locally written copy of the message the gate constructs.
    for line in source.splitlines():
        stripped = line.strip()
        if "generated answer introduced unsupported measurements" in stripped:
            assert "warnings" in stripped or "stratum" in stripped, (
                f"harness hardcodes a gate warning string: {stripped}"
            )


def test_the_built_eval_sets_carry_the_label_schema_the_harness_joins_on() -> None:
    data = KENN_ROOT / "tooling" / "data"
    required = {"query", "expected_route", "expected_intent", "gold_chunk_id", "must_abstain", "stratum"}
    for name in ("eval_stratified_v1.jsonl", "eval_must_abstain_v1.jsonl"):
        rows = [json.loads(line) for line in (data / name).read_text(encoding="utf-8").splitlines() if line.strip()]
        assert rows, f"{name} is empty"
        for row in rows:
            assert required <= set(row), f"{name} row missing {required - set(row)}"
            assert row["must_abstain"] is False or row.get("abstain_reason"), (
                f"{name}: a must_abstain row with no stated reason is not checkable"
            )
