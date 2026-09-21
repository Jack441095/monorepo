from __future__ import annotations

from pathlib import Path
import sys

import pytest


SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

import eval_runner  # noqa: E402


def test_public_quality_suite_selection_excludes_non_mix_domains() -> None:
    for filename, allowed_categories in eval_runner.PUBLIC_KNOWLEDGE_CASES.items():
        cases = eval_runner._load_cases(filename)
        selected = [case for case in cases if case.get("category") in allowed_categories]
        assert selected
        assert all(case.get("category") not in eval_runner.PUBLIC_BOUNDARY_CATEGORIES for case in selected)


def test_public_corpus_boundary_check_requires_abstention(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        eval_runner.app,
        "answer_mix_question",
        lambda question: {
            "intent": "out_of_scope",
            "found": False,
            "sources": [],
        },
    )
    receipt = eval_runner._run_public_corpus_boundary_check()
    assert receipt["total"] == 13
    assert receipt["passed"] == 13
    assert receipt["failed"] == 0
