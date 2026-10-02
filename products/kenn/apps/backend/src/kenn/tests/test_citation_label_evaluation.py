"""Independent citation labels must never inherit a passing production verdict."""

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[5] / "tooling/scripts/evaluate_citation_labels.py"
spec = importlib.util.spec_from_file_location("citation_label_evaluation", SCRIPT)
tool = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(tool)


def capture(answer="The release is 150 ms [#a].", *, accepted=True):
    return {"question": "What is the release?", "answer": answer, "accepted": accepted,
            "candidate_text_available": True,
            "evidence_sources": [{"id": "a", "text": "The release is 150 ms."},
                                 {"id": "b", "text": "The ratio is 4:1."}]}


def reviewed(answer="The release is 150 ms [#a].", *, shown=True, cited=True,
             citations=None, acceptable=True):
    row = tool.prepare_rows([capture(answer)])[0]
    row["review"] = {"complete": True, "reviewer": "fixture", "origin": "model",
                     "answer_acceptable": acceptable}
    row["claims"] = [{"start": 0, "end": len(answer), "factual": True,
                      "shown_support": shown, "cited_support": cited,
                      "citations": citations if citations is not None else [{"id": "a", "supports": cited}]}]
    return row


def test_gate_acceptance_cannot_make_an_unsupported_claim_pass():
    row = reviewed(shown=False, cited=False, acceptable=False)
    result = tool.score_rows([row])
    assert result["metrics"] == {"citation_precision": 0, "citation_recall": 0,
                                 "faithfulness": 0, "answer_acceptability": 0,
                                 "accepted_unsupported_risk": 1}
    assert result["counts"]["gate_accepted_unsupported"] == 1
    assert result["labels_are_human_only"] is False
    assert result["minimum_sample_met"] is False


def test_joint_support_counts_each_contributing_source():
    row = reviewed("The release is 150 ms and ratio 4:1 [#a] [#b].",
                   citations=[{"id": "a", "supports": True}, {"id": "b", "supports": True}])
    report = tool.score_rows([row])
    assert report["metrics"]["citation_precision"] == 1
    assert report["metrics"]["citation_recall"] == 1
    assert report["counts"]["useful_citations"] == 2


def test_unknown_and_irrelevant_citations_stay_in_precision_denominator():
    row = reviewed("The release is 150 ms [#a] [#b] [#invented].",
                   citations=[{"id": "a", "supports": True}, {"id": "b", "supports": False},
                              {"id": "invented", "supports": False}])
    report = tool.score_rows([row])
    assert report["metrics"]["citation_precision"] == pytest.approx(1 / 3)
    assert report["metrics"]["citation_recall"] == 1
    assert report["counts"]["unknown_citations"] == 1


def test_supported_but_uncited_claim_reduces_recall_without_reducing_faithfulness():
    row = reviewed("The release is 150 ms.", cited=False, citations=[])
    report = tool.score_rows([row])
    assert report["metrics"]["citation_precision"] is None
    assert report["metrics"]["citation_recall"] == 0
    assert report["metrics"]["faithfulness"] == 1


def test_pending_and_lost_candidates_cannot_become_zero_error_observations():
    lost = capture()
    lost["candidate_text_available"] = False
    pending, unavailable = tool.prepare_rows([capture(), lost])
    report = tool.score_rows([pending, unavailable])
    assert report["counts"]["reviewed"] == 0
    assert report["counts"]["pending"] == report["counts"]["unavailable"] == 1
    assert all(value is None for value in report["metrics"].values())
    assert report["coverage_complete"] is False
    unavailable["review"]["complete"] = True
    with pytest.raises(ValueError, match="unavailable row"):
        tool.score_rows([unavailable])


def test_legacy_flattened_evidence_is_not_reconstructed_from_a_new_index():
    legacy = capture()
    del legacy["evidence_sources"]
    row = tool.prepare_rows([legacy])[0]
    assert row["unavailable_reason"] == "per-source evidence not recorded"


@pytest.mark.parametrize("edit,reason", [
    (lambda r: r["capture"].update(answer="changed"), "capture changed"),
    (lambda r: r["claims"][0].update(start=-1), "claim offsets"),
    (lambda r: r["claims"][0].update(citations=[]), "every mention"),
    (lambda r: r["claims"][0].update(shown_support=None), "boolean"),
    (lambda r: r["claims"][0].update(shown_support=False), "shown-supported"),
    (lambda r: r["review"].update(origin="gate"), "named reviewer"),
    (lambda r: r.update(split="wrong"), "question split"),
    (lambda r: r["claims"].append(copy.deepcopy(r["claims"][0])), "nonoverlapping"),
])
def test_inconsistent_or_incomplete_labels_fail_instead_of_producing_a_score(edit, reason):
    row = reviewed()
    edit(row)
    with pytest.raises(ValueError, match=reason):
        tool.score_rows([row])


def test_citation_outside_claim_spans_is_not_silently_ignored():
    row = reviewed()
    row["claims"][0].update(end=21, citations=[], cited_support=False)
    with pytest.raises(ValueError, match="every citation"):
        tool.score_rows([row])


def test_an_unshown_source_cannot_be_labelled_as_useful():
    row = reviewed("The release is 150 ms [#invented].",
                   citations=[{"id": "invented", "supports": True}])
    with pytest.raises(ValueError, match="shown source"):
        tool.score_rows([row])


def test_an_honest_abstention_has_no_factual_claim_denominator():
    row = reviewed("I don't have enough evidence.", cited=False, citations=[])
    row["claims"] = []
    report = tool.score_rows([row])
    assert report["metrics"]["faithfulness"] is None
    assert report["metrics"]["citation_recall"] is None
    assert report["metrics"]["answer_acceptability"] == 1


def test_repeated_questions_do_not_inflate_sample_size_or_get_independent_intervals():
    first = reviewed()
    second = reviewed("Use a release of 150 ms [#a].")
    report = tool.score_rows([first, second])
    assert report["counts"]["unique_reviewed_questions"] == 1
    assert report["answer_acceptability_wilson95"] is None
    assert first["split"] == second["split"]
    with pytest.raises(ValueError, match="duplicate"):
        tool.score_rows([first, first])
    with pytest.raises(ValueError, match="duplicate"):
        tool.prepare_rows([capture(), capture()])


def test_minimum_sample_counts_distinct_reviewed_questions():
    rows = []
    for index in range(150):
        row = reviewed()
        row["capture"]["question"] = f"Release question {index}?"
        frozen = tool.prepare_rows([row["capture"]])[0]
        frozen.update(review=row["review"], claims=row["claims"])
        rows.append(frozen)
    assert tool.score_rows(rows)["minimum_sample_met"] is True
    rows[-1]["review"]["complete"] = False
    assert tool.score_rows(rows)["minimum_sample_met"] is False


def test_cli_prepares_scores_and_preserves_existing_review_work(tmp_path):
    raw, labels, receipt = [tmp_path / name for name in ("raw.jsonl", "labels.jsonl", "receipt.json")]
    raw.write_text(json.dumps(capture()) + "\n")
    command = [sys.executable, str(SCRIPT)]
    prepared = subprocess.run(command + ["prepare", str(raw), "--output", str(labels)], capture_output=True, text=True)
    assert prepared.returncode == 0, prepared.stderr
    assert json.loads(labels.read_text())["review"]["complete"] is False
    row = reviewed()
    labels.write_text(json.dumps(row) + "\n")
    scored = subprocess.run(command + ["score", str(labels), "--output", str(receipt)], capture_output=True, text=True)
    assert scored.returncode == 0, scored.stderr
    result = json.loads(receipt.read_text())
    assert result["metrics"]["citation_precision"] == 1
    assert row["capture"]["answer"] not in receipt.read_text()
    refused = subprocess.run(command + ["prepare", str(raw), "--output", str(labels)], capture_output=True, text=True)
    assert refused.returncode == 1
    assert json.loads(labels.read_text()) == row
