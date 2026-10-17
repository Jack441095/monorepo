"""Tests for formal mixing curriculum and ad-hoc question isolation (Milestone E8).

Verifies:
1. Curriculum catalog authoring across 5 fundamental mix topics with verifiable objectives.
2. Starting a curriculum lesson with objective, starting grade, and suggested path.
3. Objective evaluation: success path (completes objective, calculates grade delta).
4. Failure path: identifies exact metric gap and logs into failed_suggestions_log.
5. Session lifecycle: pause, resume, abandon.
6. Absolute isolation: ad-hoc Q&A does not corrupt or advance curriculum state,
   and active curriculum state never blocks or interferes with ad-hoc questions.
7. Clean per-session reset: purging one session does not touch another.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict
import pytest

from kenn.core.mix_curriculum import (
    CURRICULUM_CATALOG,
    CURRICULUM_SCHEMA,
    OBJECTIVE_SCHEMA,
    CurriculumObjective,
    CurriculumSession,
    MixCurriculumManager,
)
from kenn.core.session_memory import reset_session_data
from kenn.routes.chat_routes import handle_ask


@pytest.fixture
def temp_db(monkeypatch, tmp_path):
    """Provide a temporary, isolated SQLite database for curriculum tests."""
    db_file = tmp_path / "test_curriculum.sqlite3"
    monkeypatch.setattr("kenn.core.session_memory.DB_PATH", db_file)
    monkeypatch.setattr("kenn.core.mix_curriculum.DB_PATH", db_file)
    manager = MixCurriculumManager(db_path=db_file)
    return manager


def test_curriculum_catalog_completeness():
    """Verify in-house authored curriculum catalog covers the core penalized mix dimensions."""
    expected_topics = {
        "spectral_clarity",
        "low_end_control",
        "loudness_and_peaks",
        "stereo_imaging",
        "dynamic_control",
    }
    assert set(CURRICULUM_CATALOG.keys()) == expected_topics

    for topic_id, obj in CURRICULUM_CATALOG.items():
        assert isinstance(obj, CurriculumObjective)
        assert obj.topic_id == topic_id
        assert len(obj.title) > 5
        assert len(obj.suggested_steps) >= 3
        assert obj.target_operator in ("<=", ">=", "<", ">")
        assert len(obj.cited_standards) >= 1
        assert len(obj.lesson_notes) > 50

        # Check serialization round-trip
        data = obj.to_dict()
        assert data["schema"] == OBJECTIVE_SCHEMA
        restored = CurriculumObjective.from_dict(data)
        assert restored.topic_id == obj.topic_id
        assert restored.target_value == obj.target_value


def test_start_curriculum_lesson(temp_db):
    """Verify starting a lesson establishes objective, starting grade, and in_progress status."""
    manager = temp_db
    session_id = "session-prod-alpha"

    initial_meters = {
        "true_peak_dbtp": -0.4,
        "integrated_lufs": -11.2,
        "correlation": 0.82,
        "spectral_energy": {
            "sub": 0.32,
            "low_mid": 0.44,  # 44.0% - muddy low-mid excess above 38.0% threshold
            "air": 0.08,
        },
    }
    initial_grade = {
        "points": 45.0,
        "points_available": 100.0,
        "score_pct": 45.0,
        "letter": "C-",
    }

    session = manager.start_lesson(
        session_id=session_id,
        topic_id="spectral_clarity",
        current_meters=initial_meters,
        current_grade=initial_grade,
    )

    assert session["schema"] == CURRICULUM_SCHEMA
    assert session["session_id"] == session_id
    assert session["topic_id"] == "spectral_clarity"
    assert session["status"] == "in_progress"
    assert session["starting_grade"]["points"] == 45.0
    assert session["objective"]["target_metric"] == "low_mid_energy_pct"
    assert session["objective"]["target_value"] == 38.0
    assert len(session["failed_suggestions_log"]) == 0

    # Retrieve from DB
    retrieved = manager.get_session_status(session_id)
    assert retrieved is not None
    assert retrieved["session_id"] == session_id
    assert retrieved["title"] == session["title"]


def test_evaluate_progress_objective_achieved(temp_db):
    """Verify evaluating improved telemetry completes the objective and computes grade delta."""
    manager = temp_db
    session_id = "session-prod-beta"

    initial_meters = {
        "spectral_energy": {"low_mid": 0.45},
    }
    initial_grade = {"points": 40.0}

    manager.start_lesson(
        session_id=session_id,
        topic_id="spectral_clarity",
        current_meters=initial_meters,
        current_grade=initial_grade,
    )

    # Telemetry after applying a 3.0 dB cut at 300 Hz on pads
    improved_meters = {
        "spectral_energy": {"low_mid": 0.35},  # 35.0% <= 38.0% target
    }
    improved_grade = {"points": 64.0}

    result = manager.evaluate_progress(
        session_id=session_id,
        current_meters=improved_meters,
        current_grade=improved_grade,
    )

    assert result["ok"] is True
    assert result["objective_met"] is True
    assert result["status"] == "completed"
    assert result["measured_value"] == 35.0
    assert result["target_value"] == 38.0
    assert result["grade_delta"] == 24.0  # +24.0 points improvement
    assert "Objective achieved" in result["feedback"]

    status = manager.get_session_status(session_id)
    assert status["status"] == "completed"
    assert status["completed_at"] is not None


def test_evaluate_progress_objective_failed_logs_gap(temp_db):
    """Verify an insufficient acoustic adjustment logs the exact numerical gap into failed suggestions."""
    manager = temp_db
    session_id = "session-prod-gamma"

    initial_meters = {
        "spectral_energy": {"low_mid": 0.46},
    }
    initial_grade = {"points": 38.0}

    manager.start_lesson(
        session_id=session_id,
        topic_id="spectral_clarity",
        current_meters=initial_meters,
        current_grade=initial_grade,
    )

    # Producer attempted a minor cut, but low-mids are still 42.0% (> 38.0%)
    attempted_meters = {
        "spectral_energy": {"low_mid": 0.42},
    }
    attempted_grade = {"points": 41.0}
    failed_lever = {
        "dimension": "low_mid_mud",
        "action_type": "parametric_eq_cut",
        "cut_db": -1.0,
    }

    result = manager.evaluate_progress(
        session_id=session_id,
        current_meters=attempted_meters,
        current_grade=attempted_grade,
        last_applied_lever=failed_lever,
    )

    assert result["ok"] is True
    assert result["objective_met"] is False
    assert result["status"] == "in_progress"
    assert result["measured_value"] == 42.0
    assert result["failed_suggestions_count"] == 1
    assert "excess" in result["gap_identified"]

    session_state = manager.get_session_status(session_id)
    assert len(session_state["failed_suggestions_log"]) == 1
    logged_gap = session_state["failed_suggestions_log"][0]
    assert logged_gap["measured_value"] == 42.0
    assert logged_gap["lever_applied"] == failed_lever


def test_curriculum_lifecycle_pause_resume_abandon(temp_db):
    """Verify pausing, resuming, and abandoning curriculum sessions."""
    manager = temp_db
    session_id = "session-lifecycle"

    manager.start_lesson(
        session_id=session_id,
        topic_id="low_end_control",
        current_meters={"spectral_energy": {"sub": 0.52}},
        current_grade={"points": 50.0},
    )

    # Pause
    assert manager.pause_lesson(session_id) is True
    assert manager.get_session_status(session_id)["status"] == "paused"

    # Resume
    assert manager.resume_lesson(session_id) is True
    assert manager.get_session_status(session_id)["status"] == "in_progress"

    # Abandon
    assert manager.abandon_lesson(session_id) is True
    assert manager.get_session_status(session_id)["status"] == "abandoned"


def test_ad_hoc_questions_do_not_corrupt_curriculum(temp_db):
    """Verify that asking general ad-hoc questions does not mutate or corrupt curriculum state."""
    manager = temp_db
    session_id = "session-isolated"

    # Start an active curriculum session
    manager.start_lesson(
        session_id=session_id,
        topic_id="stereo_imaging",
        current_meters={"correlation": 0.25},
        current_grade={"points": 48.0},
    )

    state_before = manager.get_session_status(session_id)

    # Producer asks an ad-hoc question about drum compression
    status_code, response = handle_ask(
        {
            "question": "What attack time should I use for a punchy snare compressor?",
            "session_id": session_id,
        },
        request_id="req-adhoc-1",
    )

    assert status_code == 200
    assert "answer" in response or "content" in response or "text" in response or len(response) > 0

    # Ensure curriculum state is completely untouched
    state_after = manager.get_session_status(session_id)
    assert state_after["status"] == state_before["status"]
    assert state_after["topic_id"] == state_before["topic_id"]
    assert state_after["starting_grade"] == state_before["starting_grade"]
    assert state_after["failed_suggestions_log"] == state_before["failed_suggestions_log"]
    assert state_after["updated_at"] == state_before["updated_at"]


def test_session_reset_purges_curriculum_isolated(temp_db):
    """Verify that reset_session_data cleanly wipes curriculum for that session without touching others."""
    manager = temp_db
    session_a = "session-alice"
    session_b = "session-bob"

    manager.start_lesson(
        session_id=session_a,
        topic_id="spectral_clarity",
        current_meters={"spectral_energy": {"low_mid": 0.44}},
        current_grade={"points": 50.0},
    )
    manager.start_lesson(
        session_id=session_b,
        topic_id="dynamic_control",
        current_meters={"crest_factor_db": 4.5},
        current_grade={"points": 52.0},
    )

    # Reset session A
    counts = reset_session_data(session_a)
    assert counts.get("curriculum", 0) == 1

    # Session A is wiped
    assert manager.get_session_status(session_a) is None

    # Session B is completely intact
    bob_status = manager.get_session_status(session_b)
    assert bob_status is not None
    assert bob_status["topic_id"] == "dynamic_control"
    assert bob_status["status"] == "in_progress"


def test_curriculum_rest_endpoints(temp_db):
    """Verify FastAPI endpoints for curriculum catalog, lifecycle, and progress evaluation."""
    from fastapi.testclient import TestClient
    from kenn.routes.fastapi_app import app

    client = TestClient(app)
    session_id = "session-rest-test"

    # 1. Catalog
    res = client.get("/api/curriculum/catalog")
    assert res.status_code == 200
    catalog = res.json()["catalog"]
    assert len(catalog) == 5

    # 2. Start
    start_payload = {
        "session_id": session_id,
        "topic_id": "loudness_and_peaks",
        "current_meters": {"true_peak_dbtp": 0.5},
        "current_grade": {"points": 42.0},
    }
    res = client.post("/api/curriculum/start", json=start_payload)
    assert res.status_code == 200
    assert res.json()["session"]["topic_id"] == "loudness_and_peaks"

    # 3. Status
    res = client.get(f"/api/curriculum/status?session_id={session_id}")
    assert res.status_code == 200
    assert res.json()["session"]["status"] == "in_progress"

    # 4. Evaluate - incomplete attempt
    eval_fail = {
        "session_id": session_id,
        "current_meters": {"true_peak_dbtp": -0.2},  # Still above -1.0 dBTP
        "current_grade": {"points": 48.0},
        "last_applied_lever": {"dimension": "true_peak", "gain_db": -0.7},
    }
    res = client.post("/api/curriculum/evaluate", json=eval_fail)
    assert res.status_code == 200
    assert res.json()["objective_met"] is False
    assert res.json()["failed_suggestions_count"] == 1

    # 5. Evaluate - complete
    eval_pass = {
        "session_id": session_id,
        "current_meters": {"true_peak_dbtp": -1.2},  # Meets <= -1.0 dBTP
        "current_grade": {"points": 65.0},
    }
    res = client.post("/api/curriculum/evaluate", json=eval_pass)
    assert res.status_code == 200
    assert res.json()["objective_met"] is True
    assert res.json()["status"] == "completed"

    # 6. Lifecycle controls
    client.post("/api/curriculum/pause", json={"session_id": session_id})
    res = client.get(f"/api/curriculum/status?session_id={session_id}")
    assert res.json()["session"]["status"] == "paused"

    client.post("/api/curriculum/resume", json={"session_id": session_id})
    res = client.get(f"/api/curriculum/status?session_id={session_id}")
    assert res.json()["session"]["status"] == "in_progress"

    client.post("/api/curriculum/abandon", json={"session_id": session_id})
    res = client.get(f"/api/curriculum/status?session_id={session_id}")
    assert res.json()["session"]["status"] == "abandoned"

