from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[5] / "tooling" / "scripts" / "evaluate_session_grounded_advice.py"
module = importlib.util.module_from_spec(spec := importlib.util.spec_from_file_location("session_grounded_eval", SCRIPT))
assert spec.loader
spec.loader.exec_module(module)


def test_fixed_session_grounded_benchmark_qualifies() -> None:
    result = module.evaluate()
    assert result["qualified"] is True, result
    assert result["passed"] == result["case_count"] == 6


def test_benchmark_rejects_unlabelled_or_fabricated_session_evidence() -> None:
    def corrupted_answer(_question: str, _session_id: str) -> dict:
        return {
            "found": True,
            "answer": "General advice pretending to know the session.",
            "sources": [{"source": "vocal-deessing-and-sibilance.md"}],
            "session_evidence": [{"track_index": 99, "track_name": "Invented", "devices": []}],
        }
    result = module.evaluate(answerer=corrupted_answer)
    assert result["qualified"] is False
    assert all(row["passed"] is False for row in result["rows"])
