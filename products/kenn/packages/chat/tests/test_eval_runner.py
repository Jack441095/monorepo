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


def test_full_evaluation_receipt_passes() -> None:
    """The held-out chat evaluation pack (diagnostic/conversation/public-
    knowledge cases, abstention probes, and the public-corpus boundary check)
    had no test enforcing its overall pass/fail status in the regular
    regression suite -- unlike apps/backend/src/kenn/tests/test_ableton_assistant_eval.py,
    which does exactly this for the Ableton holdout. A future change could
    silently break real-question answering or citation/abstention behavior
    and the 500+-test suite would never catch it. This runs the real
    evaluation (no mocks) and asserts every suite is green."""
    receipt = eval_runner.run_evaluation()
    assert receipt["passed"] is True, receipt["failures"]
    assert receipt["diagnostic"]["failed"] == 0
    assert receipt["conversation"]["failed"] == 0
    assert receipt["abstention_check"]["failed"] == 0
    assert receipt["public_corpus_boundary"]["failed"] == 0
    for suite in receipt["public_knowledge"].values():
        assert suite["failed"] == 0
