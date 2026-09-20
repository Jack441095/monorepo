"""scripts/eval_chat_coverage.py evaluates the repository's 128-case chat
question corpus (apps/backend/src/kenn/evals/questions.json) but had no test enforcing
its overall pass/fail status in the regular regression suite -- the same gap
already found and closed for chat/eval_runner.py and scripts/eval_mix_review.py
this session. A future change could silently break real-question answering
or abstention behavior and the regression suite would never catch it.
"""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tooling" / "scripts"))

from eval_chat_coverage import _check_dimensions, evaluate


def test_evaluator_separates_behavior_retrieval_and_answer_failures() -> None:
    case = {
        "answer_must_include": ["sidechain"],
        "answer_must_include_any": ["release", "threshold"],
        "answer_must_not_include": ["always"],
        "min_confidence": "high",
        "source_kinds_any": ["note"],
        "source_must_include": ["approved-sidechain.md"],
        "topics_must_include": ["compression"],
        "routes_any": ["production"],
        "min_source_quality": "high",
        "weak_match": False,
    }
    response = {
        "answer": "Always boost the bass.",
        "confidence": "low",
        "sources": [{"kind": "web", "source": "unapproved.md"}],
        "topics": ["bass"],
        "route": "business",
        "source_quality": "low",
        "weak_match": True,
    }

    failures = _check_dimensions(case, response, expected_abstention=False)

    assert any(item.startswith("route:") for item in failures["behavior"])
    assert any(item.startswith("weak_match:") for item in failures["behavior"])
    assert any(item.startswith("missing_source:") for item in failures["retrieval"])
    assert any(item.startswith("missing_topic:") for item in failures["retrieval"])
    assert any(item.startswith("source_quality:") for item in failures["retrieval"])
    assert any(item.startswith("missing_answer:") for item in failures["answer"])
    assert any(item.startswith("missing_answer_any:") for item in failures["answer"])
    assert any(item.startswith("forbidden_answer:") for item in failures["answer"])
    assert any(item.startswith("confidence:") for item in failures["answer"])


def test_full_chat_coverage_receipt_passes() -> None:
    receipt = evaluate()
    assert receipt["failed"] == 0, [row for row in receipt["rows"] if not row["passed"]]
    assert receipt["passed"] == receipt["cases"]
