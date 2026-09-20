"""thursday.feedback.get_helpfulness_summary()/get_service_helpfulness() had
no caller anywhere in thursday/ -- a complete, working scoring engine (D2.2
in docs/THURSDAY_IMPROVEMENT_PLAN.md) sitting unused. This wires it to
_handle_agent_reliability() (thursday/registry/handlers.py) and the
"agent_reliability" service (thursday/registry/system.py).
"""

from __future__ import annotations

import thursday.feedback as feedback
from thursday.registry.handlers import _handle_agent_reliability


def _seed(monkeypatch, tmp_path, records: list[dict]) -> None:
    log = tmp_path / "feedback.jsonl"
    monkeypatch.setattr(feedback, "FEEDBACK_LOG", log)
    monkeypatch.setattr(feedback, "HABITS_FILE", tmp_path / "habits.json")
    monkeypatch.setattr(feedback, "PATTERNS_FILE", tmp_path / "patterns.json")
    monkeypatch.setattr(feedback, "SUGGESTIONS_FILE", tmp_path / "suggestions.json")
    for i, r in enumerate(records):
        feedback.record_feedback(turn_id=f"t{i}", **r)


def test_no_feedback_reports_honestly(monkeypatch, tmp_path) -> None:
    _seed(monkeypatch, tmp_path, [])
    out = _handle_agent_reliability()
    assert "No feedback data collected yet" in out


def test_below_min_samples_reports_not_enough_data(monkeypatch, tmp_path) -> None:
    # get_service_helpfulness()'s min_samples default is 3; two ratings for
    # one service should not produce a per-service score line.
    _seed(monkeypatch, tmp_path, [
        {"service_id": "admin", "explicit_rating": 1},
        {"service_id": "admin", "explicit_rating": 1},
    ])
    out = _handle_agent_reliability()
    assert "2 feedback records" in out
    assert "Not enough samples per service" in out
    assert "admin:" not in out


def test_scored_service_appears_with_percentage(monkeypatch, tmp_path) -> None:
    _seed(monkeypatch, tmp_path, [
        {"service_id": "admin", "explicit_rating": 1},
        {"service_id": "admin", "explicit_rating": 1},
        {"service_id": "admin", "explicit_rating": 1},
        {"service_id": "marketing", "explicit_rating": -1},
        {"service_id": "marketing", "explicit_rating": -1},
        {"service_id": "marketing", "explicit_rating": -1},
    ])
    out = _handle_agent_reliability()
    assert "admin: 100%" in out
    assert "marketing: 0%" in out
    # Higher-scoring service listed first.
    assert out.index("admin:") < out.index("marketing:")


def test_thumbs_and_corrections_summarised(monkeypatch, tmp_path) -> None:
    _seed(monkeypatch, tmp_path, [
        {"service_id": "admin", "explicit_rating": 1},
        {"service_id": "admin", "explicit_rating": -1},
        {"service_id": "admin", "followup_type": "correction"},
    ])
    out = _handle_agent_reliability()
    assert "👍 1 · 👎 1" in out
    assert "1 corrections" in out
