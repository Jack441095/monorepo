from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[3] / "tooling" / "scripts" / "evaluate_chat_hard_cases.py"
SPEC = importlib.util.spec_from_file_location("evaluate_chat_hard_cases", SCRIPT)
benchmark = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(benchmark)


def test_engine_assertions_reject_weak_grounding_and_answer_quality() -> None:
    failures = benchmark._check_engine_assertions(
        {"grounding_mode": "strong", "min_grounding_score": 75, "min_answer_quality": 80},
        {
            "grounding_mode": "weak",
            "grounding": {"score": 45},
            "answer_quality": {"score": 60},
            "answer_self_check": {"passed": False},
        },
    )
    assert any(item.startswith("grounding_mode:") for item in failures)
    assert any(item.startswith("grounding_score:") for item in failures)
    assert any(item.startswith("answer_quality:") for item in failures)
    assert "answer_self_check_failed" in failures


def test_real_engine_hard_case_benchmark_passes_without_storing_content() -> None:
    receipt = benchmark.evaluate()
    assert receipt["case_count"] > 0
    assert receipt["failed"] == 0, [row for row in receipt["rows"] if not row["passed"]]
    assert receipt["qualified"] is True
    assert receipt["privacy"] == {
        "stores_questions": False,
        "stores_answers": False,
        "stores_source_text": False,
    }
    assert all("question" not in row and "answer" not in row and "sources" not in row for row in receipt["rows"])
