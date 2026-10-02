"""A re-score has to judge answers against the evidence the gate reads, not against the capture's own field.

The capture's evidence_text was rendered from display_results(query, results, 3) and raw chunk["text"] while the gate
had been reading model_evidence()'s cleaned, budgeted excerpts since the 2 Oct 2026 rework, so 14 of the 22 rows in
that day's capture disagreed with it. A leak check built on the field reported 8 of 18 accepted answers citing a
measurement the gate held on screen; the same check against the gate's evidence reported 0 of 18. That was a
harness artifact and it nearly went out as a gate regression.

These tests pin the two guards that stop it recurring: recompute the evidence, and say so when the capture cannot be
placed against today's configuration.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def disable_llm_for_evidence_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    # Scope the offline policy to each test so collection cannot disable the planner.
    monkeypatch.setenv("KENN_LLM_ENABLED", "0")


SCRIPT = Path(__file__).resolve().parents[5] / "tooling" / "scripts" / "rescore_captured_answers.py"
module = importlib.util.module_from_spec(
    spec := importlib.util.spec_from_file_location("rescore_captured_answers", SCRIPT)
)
assert spec.loader
spec.loader.exec_module(module)


@pytest.mark.parametrize("enabled", [None, "1"])
@pytest.mark.parametrize("has_index", [False, True])
def test_replay_cli_disables_models_and_restores_the_callers_switch(
    tmp_path, monkeypatch, enabled, has_index,
) -> None:
    # Importing the replay helper once disabled unrelated planners for the entire suite.
    if enabled is None:
        monkeypatch.delenv("KENN_LLM_ENABLED", raising=False)
    else:
        monkeypatch.setenv("KENN_LLM_ENABLED", enabled)
    capture = tmp_path / "answers.jsonl"
    capture.write_text("", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["rescore_captured_answers.py", str(capture)])

    def load_index():
        assert os.environ.get("KENN_LLM_ENABLED") == "0"
        return ([{}] if has_index else []), {}

    monkeypatch.setattr(module, "_load_index", load_index)
    monkeypatch.setattr(module, "_index_version", lambda: "test-index")
    monkeypatch.setattr(module, "_gate_budget_chars", lambda: 1200)

    assert module.main() == (0 if has_index else 1)
    assert os.environ.get("KENN_LLM_ENABLED") == enabled


QUERY = "What release time should I use for sidechain compression on bass?"
# 150 ms and 6 dB, both of which _measurements recognises: the gate's unit list is hz, khz, dB/FS/TP, ms, %, lufs,
# bpm and bits. A compression ratio like 4:1 is not a measurement to the gate and would prove nothing here.
ANSWER = (
    "Short answer:\nStart the release at 150 ms and the threshold at 6 dB.\n\n"
    "Try this:\n1. Set the compressor release to 150 ms.\n2. Match the threshold to 6 dB.\n\n"
    "Check:\nListen for the bass staying audible under the kick.\n\n"
    "Sources:\n- Sidechain Bass To Kick (sidechain-bass-to-kick.md)\n"
)
GOLD_CHUNK_ID = "a"

# The field the capture wrote while it still rendered display_results() over raw chunk text: a note title, a
# filename and a Related-questions line, with none of the numbers the gate held. This is the 8-of-18 phantom in
# one string.
STALE_EVIDENCE_TEXT = (
    "Sidechain Bass To Kick sidechain-bass-to-kick.md "
    "- What release time for sidechain compression?"
)

RESULTS = [
    (12.0, {
        "id": GOLD_CHUNK_ID,
        "kind": "note",
        "title": "Sidechain Bass To Kick",
        "source": "sidechain-bass-to-kick.md",
        "page": 0,
        "section": "Try this",
        "text": "Start the release at 150 ms and set the threshold to 6 dB.",
    }),
]


def _row(**overrides) -> dict:
    """A capture row shaped like what measure_chat_latency.py --capture-answers writes today."""
    row = {
        "question": QUERY,
        "answer": ANSWER,
        "accepted": True,
        "warnings": [],
        "unsupported_measurements": [],
        "fabricated_sources": [],
        "evidence_text": STALE_EVIDENCE_TEXT,
        "evidence_chunks_shown": 1,
        "evidence_budget_chars": 1200,
        "prompt_context_chars": 1200,
        "index_version": "v-test",
        "gold_chunk_id": GOLD_CHUNK_ID,
        "additional_evidence_text": "",
        "timeline_context": "",
    }
    row.update(overrides)
    return row


def _replay_to(monkeypatch, results: list[tuple[float, dict]]) -> None:
    """Stand in for retrieval so the test exercises evidence selection, not the index on this machine.

    The index under apps/backend/src/kenn/data/ is git-ignored and takes minutes to build, and rebuilding it here
    would stall a shared machine.
    """
    monkeypatch.setattr(module, "_replay_results", lambda query, chunks, terms: results)


def test_a_stale_capture_field_does_not_make_a_grounded_answer_look_like_a_leak(monkeypatch) -> None:
    """The phantom itself: the answer's 150 ms and 4:1 are in the gate's evidence, so nothing leaks.

    Trusting the captured field here reported 8 of 18 accepted answers as citing an absent measurement. Recomputing
    through model_evidence() reports none, which is what made the 2 Oct figures wrong in the first place.
    """
    _replay_to(monkeypatch, RESULTS)
    row = _row()

    # The fixture only proves anything if the stale field really would call this answer a leak.
    phantom = sorted(module._measurement_keys(ANSWER) - module._measurement_keys(STALE_EVIDENCE_TEXT))
    assert phantom == ["150ms", "6db"], "the stale field must look like it is missing both measurements"

    item = module.score_item(row, [], {})

    assert item["evidence_source"] == "recomputed"
    assert item["answer_measurements"] == ["150ms", "6db"]
    assert item["unsupported_measurements"] == []
    assert item["gold_chunk_scored"] is True
    assert item["measurements_not_in_gold_chunk"] == []
    assert item["numeric_claims_traceable"] is True


def test_the_evidence_scored_is_the_gate_s_not_the_capture_s_field(monkeypatch) -> None:
    """Pin which evidence the traceability column actually used, so a regression shows up in the numbers.

    Guards the guard: if evidence selection reverted to the captured field, evidence_measurements would be empty,
    measurements_not_in_gold_chunk would go non-empty, and the phantom would be back behind a correct-looking
    source column.
    """
    _replay_to(monkeypatch, RESULTS)

    item = module.score_item(_row(), [], {})

    assert item["evidence_measurements"] == ["150ms", "6db"]
    assert item["evidence_measurements"] != sorted(module._measurement_keys(STALE_EVIDENCE_TEXT))
    assert item["evidence_chunks_shown"] == 1


def test_row_that_cannot_be_replayed_falls_back_to_the_captured_field_and_says_so(monkeypatch, capsys) -> None:
    """Retrieval returning nothing must not read as "the model invented every number".

    An empty replay leaves the gate with no evidence, so the fallback keeps the capture's own field, marks the row
    unverified, and is counted in the printed report rather than passed off as a clean re-score.
    """
    _replay_to(monkeypatch, [])
    item = module.score_item(_row(), [], {})

    assert item["evidence_source"] == "captured_field"
    assert item["gold_chunk_scored"] is False
    assert item["numeric_claims_traceable"] is None
    assert item["measurements_not_in_gold_chunk"] == []

    summary = module.report([item], source=Path("answers.jsonl"), current_index="v-test", current_budget=1200)
    out = capsys.readouterr().out

    assert "captured_field 1" in out
    assert "WARNING" in out and "fell back to the capture" in out
    assert summary["evidence_sources"]["captured_field"] == 1
    assert summary["numeric_answers"] == 0
    assert summary["numeric_answers_unscorable"] == 1


def test_capture_written_at_a_different_budget_warns_instead_of_reporting_a_clean_result(monkeypatch, capsys) -> None:
    """650 chars against today's 1200 changes which excerpts survive, so the rates are not comparable.

    This is the condition that made the 2 Oct numbers untrustworthy: nothing recorded the budget, so a later
    change to it could not be detected from the capture.
    """
    _replay_to(monkeypatch, RESULTS)
    item = module.score_item(_row(evidence_budget_chars=650), [], {})

    summary = module.report([item], source=Path("answers.jsonl"), current_index="v-test", current_budget=1200)
    out = capsys.readouterr().out

    assert summary["provenance_warnings"], "a budget mismatch must not report cleanly"
    assert any("650" in w and "1200" in w for w in summary["provenance_warnings"])
    assert "budget 650" in out
    assert out.index("budget 650") < out.index("acceptance:")


def test_capture_from_a_different_index_warns(monkeypatch, capsys) -> None:
    """Retrieval results differ between indexes, so a replay cannot stand in for the index the answers saw."""
    _replay_to(monkeypatch, RESULTS)
    item = module.score_item(_row(index_version="v-db8c6334cf63"), [], {})

    summary = module.report([item], source=Path("answers.jsonl"), current_index="v-test", current_budget=1200)

    assert any("v-db8c6334cf63" in w for w in summary["provenance_warnings"])
    assert "v-test" in capsys.readouterr().out


def test_capture_with_no_recorded_provenance_is_labelled_provisional(monkeypatch, capsys) -> None:
    """The 22-row capture of 2 Oct 2026 recorded neither field. Such a capture cannot be cleared, only flagged.

    It must not be reported as provisional only when something else also went wrong, because nothing does.
    """
    _replay_to(monkeypatch, RESULTS)
    item = module.score_item(_row(index_version="", evidence_budget_chars=None, prompt_context_chars=None), [], {})

    summary = module.report([item], source=Path("answers.jsonl"), current_index="v-test", current_budget=1200)
    out = capsys.readouterr().out

    assert len(summary["provenance_warnings"]) == 1, summary["provenance_warnings"]
    assert "predates" in summary["provenance_warnings"][0]
    assert "provisional" in out


def test_matching_budget_and_index_report_no_provenance_warning(monkeypatch, capsys) -> None:
    """A capture that agrees with today's configuration says nothing, or the guard is noise nobody reads."""
    _replay_to(monkeypatch, RESULTS)
    item = module.score_item(_row(), [], {})

    summary = module.report([item], source=Path("answers.jsonl"), current_index="v-test", current_budget=1200)
    out = capsys.readouterr().out

    assert summary["provenance_warnings"] == []
    assert "budget" not in out


def test_row_whose_prompt_budget_differs_from_the_gate_budget_is_flagged(monkeypatch) -> None:
    """KENN_LLM_CONTEXT_CHARS moved the prompt and not the gate, so the model saw less than the gate vouches for."""
    _replay_to(monkeypatch, RESULTS)
    item = module.score_item(_row(prompt_context_chars=650), [], {})

    warnings = module.provenance_warnings([item], current_index="v-test", current_budget=1200)

    assert any("prompt budget" in w for w in warnings)


def test_a_missing_gold_chunk_excludes_the_row_from_the_rate_instead_of_calling_every_number_a_leak(monkeypatch, capsys) -> None:
    """An unlabelled row cannot be gold-checked. Counting it as untraceable is the phantom in a second column."""
    _replay_to(monkeypatch, RESULTS)
    item = module.score_item(_row(gold_chunk_id=""), [], {})

    assert item["gold_chunk_scored"] is False
    assert item["measurements_not_in_gold_chunk"] == []

    summary = module.report([item], source=Path("answers.jsonl"), current_index="v-test", current_budget=1200)

    assert summary["numeric_answers"] == 0
    assert summary["numeric_answers_unscorable"] == 1
    assert "excluded from the rate" in capsys.readouterr().out
