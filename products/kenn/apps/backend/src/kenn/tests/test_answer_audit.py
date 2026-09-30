"""The answer audit must be able to fail, and must not pass vacuously.

Two ways this could have been a gate that always says PASS, both of which happened while building it: running with
no retrieval index (every answer abstains, so "no citable source" reads 0), and counting a recipe as an uncited
factual answer. Both are pinned here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import answer_audit


def _payload(**overrides):
    base = {"answer": "text", "found": True, "sources": [{"kind": "note"}],
            "grounding": {"score": 90, "warnings": []}, "route": "knowledge"}
    base.update(overrides)
    return base


def test_an_answer_that_cites_nothing_is_a_failure(monkeypatch) -> None:
    monkeypatch.setattr("kenn.core.chat_answer.answer_payload", lambda query, **kw: _payload(sources=[]))
    report = answer_audit.audit([{"id": "q1", "question": "how do I EQ a vocal?"}], allow_llm=False)
    assert report["counts"]["no_citable_source"] == 1
    assert report["uncited"][0]["id"] == "q1"


def test_a_recipe_that_makes_no_claim_is_not_an_uncited_answer(monkeypatch) -> None:
    """"fix muddy low mids" returns a six-step mixer recipe with grounding None; nothing factual to cite."""
    monkeypatch.setattr("kenn.core.chat_answer.answer_payload",
                        lambda query, **kw: _payload(sources=[], grounding=None, route="autonomous_producer"))
    report = answer_audit.audit([{"id": "muddy-low-mids", "question": "fix muddy low mids in a mix"}], allow_llm=False)
    assert report["counts"]["no_citable_source"] == 0
    assert report["counts"]["uncited_recipes"] == 1


def test_abstaining_is_not_being_uncited(monkeypatch) -> None:
    """Saying "I don't know" is the display layer working, which is why the measure is about answers being built."""
    monkeypatch.setattr("kenn.core.chat_answer.answer_payload",
                        lambda query, **kw: {"answer": "", "found": False, "sources": [], "grounding": None})
    report = answer_audit.audit([{"id": "q1", "question": "?"}], allow_llm=False)
    assert report["counts"]["abstained"] == 1 and report["counts"]["no_citable_source"] == 0


def test_grounding_warnings_are_counted_with_the_top_one_named(monkeypatch) -> None:
    monkeypatch.setattr("kenn.core.chat_answer.answer_payload",
                        lambda query, **kw: _payload(grounding={"score": 40, "warnings": ["source topic mismatch"]}))
    report = answer_audit.audit([{"id": "q1", "question": "?"}, {"id": "q2", "question": "?"}], allow_llm=False)
    assert report["counts"]["grounding_warned"] == 2
    assert report["top_grounding_warning"]["warning"] == "source topic mismatch"
    assert report["top_grounding_warning"]["answers"] == 2


def test_an_exception_is_never_reported_as_a_clean_audit(monkeypatch) -> None:
    def boom(query, **kwargs):
        raise RuntimeError("index exploded")
    monkeypatch.setattr("kenn.core.chat_answer.answer_payload", boom)
    report = answer_audit.audit([{"id": "q1", "question": "?"}], allow_llm=False)
    assert report["counts"]["errors"] == 1 and report["rows"][0]["error"].startswith("RuntimeError")


def test_a_missing_retrieval_index_is_reported_as_unmeasured_not_pass(tmp_path, monkeypatch) -> None:
    """The vacuous-PASS trap: with no index every answer abstains and the required-zero measure reads 0."""
    fake_root = tmp_path / "kenn"
    monkeypatch.setattr(answer_audit, "KENN_ROOT", fake_root)
    missing = answer_audit.index_missing()
    assert missing is not None and "index" in str(missing)


def test_an_index_present_is_not_reported_missing(tmp_path, monkeypatch) -> None:
    fake_root = tmp_path / "kenn"
    version = fake_root / "apps" / "backend" / "src" / "kenn" / "data" / "index" / "versions" / "v-test"
    version.mkdir(parents=True)
    (version / "chunks.jsonl").write_text("{}\n", encoding="utf-8")
    (version / "terms.json").write_text("{}", encoding="utf-8")
    index = fake_root / "apps" / "backend" / "src" / "kenn" / "data" / "index"
    (index / "CURRENT").write_text("v-test\n", encoding="utf-8")
    monkeypatch.setattr(answer_audit, "KENN_ROOT", fake_root)
    assert answer_audit.index_missing() is None


def test_a_blank_question_is_skipped_rather_than_answered(monkeypatch) -> None:
    monkeypatch.setattr("kenn.core.chat_answer.answer_payload", lambda query, **kw: _payload())
    report = answer_audit.audit([{"id": "blank", "question": "   "}], allow_llm=False)
    assert report["counts"]["answers"] == 0
