"""The retrieval holdout: a fixture nobody tunes a change against, and the guard that says so.

A holdout is only worth what nobody has tuned against it, so these tests cover the three ways
that can quietly go wrong: the marker is dropped, a tuning path reads the file anyway, and a
"split" of the corpus quietly duplicates or loses cases.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pytest

from scripts.sealed_fixtures import EVALS, SealedFixtureError, is_sealed, sealed_fixtures, tunable_cases


SCRIPTS = Path(__file__).resolve().parents[5] / "tooling" / "scripts"
INDEX_POINTER = Path(__file__).resolve().parents[2] / "kenn" / "data" / "index" / "CURRENT"

# The three fixtures tuned changes against, and the holdout that replaces the burned 228.
TUNED = ("questions.json", "device_purpose_retrieval_cases.json", "technique_purpose_retrieval_cases.json",
         "device_purpose_sealed_qwen8b.json")
HOLDOUT = "device_purpose_sealed_holdout.json"

# Reads a fixture to measure a candidate change. Each is named because a holdout in one of them
# destroys the holdout, and a convention is not enough to stop that happening by accident.
WORDING_TUNER = "measure_use_it_when_lines.py"
ROUTING_TUNER = "measure_chat_routing.py"


def _load(name: str) -> dict:
    return json.loads((EVALS / name).read_text(encoding="utf-8"))


def _eval_fixture_names(script: str) -> list[str]:
    """Which eval fixtures a tooling script names, so a new holdout cannot be added unnoticed."""
    source = (SCRIPTS / script).read_text(encoding="utf-8")
    return [name for name in re.findall(r'"([^"]+\.json)"', source) if (EVALS / name).exists()]


def test_the_holdout_declares_itself_sealed_and_says_what_sealed_means() -> None:
    data = _load(HOLDOUT)

    assert data["sealed"] is True
    assert data["schema"] == "kenn.retrieval_cases.v1"
    assert data["cases"], "a holdout with no cases protects nothing"
    assert any("never" in line for line in data["policy"]), data["policy"]
    assert sealed_fixtures() == [EVALS / HOLDOUT], "every holdout in evals/ should be listed, not just this one"


def test_the_guard_refuses_the_holdout_even_after_someone_renames_the_file(tmp_path: Path) -> None:
    renamed = tmp_path / "retrieval_cases.json"
    renamed.write_text((EVALS / HOLDOUT).read_text(encoding="utf-8"), encoding="utf-8")

    assert is_sealed(renamed) is True
    with pytest.raises(SealedFixtureError, match="sealed"):
        tunable_cases(renamed)


def test_a_holdout_that_lost_its_marker_would_be_tunable_again(tmp_path: Path) -> None:
    # The guard reads the file, not the filename, which is what stops a rename from unsealing a
    # holdout. The cost is that deleting the one marker line reopens the file, so this test fails
    # loudly the day that happens rather than leaving it to a code reviewer to notice.
    unmarked = tmp_path / "retrieval_cases.json"
    unmarked.write_text(json.dumps({"cases": _load(HOLDOUT)["cases"]}), encoding="utf-8")

    assert is_sealed(unmarked) is False
    assert len(tunable_cases(unmarked)) == len(_load(HOLDOUT)["cases"])


@pytest.mark.parametrize("script", [WORDING_TUNER, ROUTING_TUNER])
def test_a_tuning_script_that_reads_the_holdout_fails_instead_of_scoring_it(script: str) -> None:
    names = _eval_fixture_names(script)
    assert "questions.json" in names, f"{script}: no eval fixture found, so this test proves nothing"

    for name in names:
        tunable_cases(EVALS / name)  # raises on the holdout, which is the point

    assert HOLDOUT not in names
    assert "tunable_cases" in (SCRIPTS / script).read_text(encoding="utf-8")


def test_every_retrieval_case_belongs_to_exactly_one_fixture() -> None:
    # The 228-case set was never split; a new holdout was authored alongside it, so the corpus is
    # accounted for by addition. A copy-paste "half" would show up here as a duplicated id.
    seen: dict[str, list[str]] = {}
    for name in (*TUNED, HOLDOUT):
        for case in _load(name)["cases"]:
            seen.setdefault(str(case["id"]), []).append(name)

    duplicated = {case_id: owners for case_id, owners in seen.items() if len(owners) > 1}
    assert not duplicated, duplicated
    assert len(seen) == sum(len(_load(name)["cases"]) for name in (*TUNED, HOLDOUT))


def test_the_holdout_shares_no_question_or_id_with_a_tuned_fixture() -> None:
    holdout = _load(HOLDOUT)["cases"]
    tuned_ids = {str(case["id"]) for name in TUNED for case in _load(name)["cases"]}
    tuned_questions = {str(case["question"]).casefold() for name in TUNED for case in _load(name)["cases"]}

    assert {str(case["id"]) for case in holdout} & tuned_ids == set()
    assert {str(case["question"]).casefold() for case in holdout} & tuned_questions == set()


def test_each_holdout_note_has_exactly_two_questions() -> None:
    per_note = Counter(case["source_must_include"][0] for case in _load(HOLDOUT)["cases"])

    assert set(per_note.values()) == {2}, sorted(per_note)[:5]
    assert len(per_note) == 75


def test_no_holdout_question_names_the_note_it_was_written_from() -> None:
    giveaway = [
        case["id"] for case in _load(HOLDOUT)["cases"]
        if case["source_must_include"][0].casefold() in case["question"].casefold()
    ]

    assert giveaway == []


def test_every_holdout_case_names_a_note_that_is_actually_indexed() -> None:
    if not INDEX_POINTER.exists():
        pytest.skip("requires the local KENN corpus/index, excluded from public CI")
    chunks = Path(__file__).resolve().parents[2] / "kenn" / "data" / "index" / "versions"
    indexed = {
        json.loads(line)["source"].removesuffix(".md")
        for path in sorted(chunks.glob("*/chunks.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
        if json.loads(line).get("kind") == "note"
    }

    missing = sorted({target for case in _load(HOLDOUT)["cases"]
                      for target in case["source_any_include"]} - indexed)

    assert missing == []
