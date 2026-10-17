"""Tests for Remembering the Session (Milestone E7).

Guarantees:
- Keeps corrections across turns within the same session.
- Keeps advice the producer followed with before/after grade progression.
- Session isolation: corrections and advice stored in Session A are invisible to Session B.
- Clean export and reset: one session's data can be exported and completely purged without touching other sessions or producers.
- REST API validation for all session learning endpoints.
"""

from __future__ import annotations

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from kenn.core.session_memory import (
    export_session_data,
    get_session_corrections,
    get_session_followed_advice,
    load_session,
    parse_session_learning,
    record_session_correction,
    record_session_followed_advice,
    reset_session_data,
    save_session,
)
from kenn.routes.fastapi_app import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_parse_session_learning_corrections() -> None:
    """Verifies that natural language corrections are accurately parsed with topics."""
    # North star E7 example
    p1 = parse_session_learning("I told you to reduce the low-mids; what's the grade now?")
    assert p1["is_correction"] is True
    assert p1["correction_data"]["topic"] == "low_mids"
    assert "reduce the low-mids" in p1["correction_data"]["correction_text"]

    p2 = parse_session_learning("Correction: target loudness is -14 LUFS, not -9")
    assert p2["is_correction"] is True
    assert p2["correction_data"]["topic"] == "target_loudness"

    p3 = parse_session_learning("Actually, don't touch the lead vocal, adjust the reverb instead")
    assert p3["is_correction"] is True
    assert p3["correction_data"]["topic"] in ("vocal", "reverb")

    # Regular question must not misfire as a correction
    p4 = parse_session_learning("How do I reduce low-mid boxiness in my mix?")
    assert p4["is_correction"] is False
    assert p4["is_followed_advice"] is False


def test_parse_session_learning_followed_advice() -> None:
    """Verifies that followed advice statements extract action and grade before/after."""
    # North star E7 example
    p1 = parse_session_learning("I lowered the low-mids and the grade went from 42 to 61")
    assert p1["is_followed_advice"] is True
    data1 = p1["followed_advice_data"]
    assert "low-mids" in data1["action"]
    assert data1["grade_before"] == 42.0
    assert data1["grade_after"] == 61.0
    assert data1["grade_delta"] == 19.0
    assert data1["topic"] == "low_mids"

    p2 = parse_session_learning("I applied the ceiling limiter and the score improved from 52.5 to 58.0")
    assert p2["is_followed_advice"] is True
    data2 = p2["followed_advice_data"]
    assert data2["grade_before"] == 52.5
    assert data2["grade_after"] == 58.0
    assert data2["grade_delta"] == 5.5


def test_record_and_retrieve_session_correction() -> None:
    """Verifies storing a correction in a session and reading it in a later turn."""
    session_id = "session_e7_alpha"

    # Initial session turn
    res = record_session_correction(
        session_id=session_id,
        user_statement="I told you to reduce the low-mids; what's the grade now?",
        topic="low_mids",
        correction_text="reduce the low-mids",
        source_turn_id="turn-1",
    )
    assert res["ok"] is True
    corr_id = res["correction"]["correction_id"]
    assert corr_id.startswith("corr-")

    # Later turn reads session corrections
    corrections = get_session_corrections(session_id)
    assert len(corrections) >= 1
    matched = next((c for c in corrections if c["correction_id"] == corr_id), None)
    assert matched is not None
    assert matched["topic"] == "low_mids"
    assert matched["correction_text"] == "reduce the low-mids"
    assert matched["source_turn_id"] == "turn-1"

    # In-memory session object also carries it
    state = load_session(session_id)
    assert any(c["correction_id"] == corr_id for c in state.get("corrections", []))


def test_record_and_retrieve_followed_advice() -> None:
    """Verifies storing followed advice with grade delta."""
    session_id = "session_e7_alpha"

    res = record_session_followed_advice(
        session_id=session_id,
        user_statement="I lowered the low-mids and the grade went from 42 to 61",
        action="lowered low-mids",
        grade_before=42.0,
        grade_after=61.0,
        source_turn_id="turn-2",
    )
    assert res["ok"] is True
    adv = res["followed_advice"]
    assert adv["grade_delta"] == 19.0

    advice_list = get_session_followed_advice(session_id)
    assert len(advice_list) >= 1
    assert advice_list[0]["grade_before"] == 42.0
    assert advice_list[0]["grade_after"] == 61.0
    assert advice_list[0]["grade_delta"] == 19.0


def test_session_isolation_corrections_and_advice() -> None:
    """Guarantees session A's corrections and advice are completely invisible to session B."""
    session_a = "session_isolation_A"
    session_b = "session_isolation_B"

    # Clean both before test
    reset_session_data(session_a)
    reset_session_data(session_b)

    # Record in Session A
    record_session_correction(
        session_id=session_a,
        user_statement="I told you to cut 400 Hz on snare",
        topic="low_mids",
        correction_text="cut 400 Hz on snare",
    )
    record_session_followed_advice(
        session_id=session_a,
        user_statement="Lowered snare level and grade rose from 50 to 55",
        action="lowered snare level",
        grade_before=50.0,
        grade_after=55.0,
    )

    # Session B queries: must be completely empty!
    b_corrections = get_session_corrections(session_b)
    b_advice = get_session_followed_advice(session_b)
    assert b_corrections == []
    assert b_advice == []

    # Session A queries: contains recorded items
    a_corrections = get_session_corrections(session_a)
    a_advice = get_session_followed_advice(session_a)
    assert len(a_corrections) == 1
    assert a_corrections[0]["correction_text"] == "cut 400 Hz on snare"
    assert len(a_advice) == 1
    assert a_advice[0]["grade_delta"] == 5.0


def test_export_and_reset_session_data() -> None:
    """Verifies that export bundles full session context, and reset wipes that session while keeping others intact."""
    session_x = "session_to_wipe"
    session_y = "session_to_keep"

    # Populate session X
    record_session_correction(session_x, "Correction on X", "dynamics", "tame master compressor")
    record_session_followed_advice(session_x, "Advice followed on X", "backed off threshold", 40.0, 52.0)

    # Populate session Y
    record_session_correction(session_y, "Correction on Y", "air", "boost 12 kHz on acoustic guitar")

    # Export session X
    exported = export_session_data(session_x)
    assert exported["schema"] == "kenn.session_export.v1"
    assert exported["session_id"] == session_x
    assert len(exported["corrections"]) >= 1
    assert len(exported["followed_advice"]) >= 1

    # Reset session X
    counts = reset_session_data(session_x)
    assert counts.get("corrections", 0) >= 1
    assert counts.get("followed_advice", 0) >= 1

    # Verify session X is completely wiped
    assert get_session_corrections(session_x) == []
    assert get_session_followed_advice(session_x) == []

    # CRITICAL: Session Y is completely intact!
    y_corrections = get_session_corrections(session_y)
    assert len(y_corrections) >= 1
    assert y_corrections[0]["correction_text"] == "boost 12 kHz on acoustic guitar"


def test_session_rest_endpoints(client: TestClient) -> None:
    """Verifies HTTP endpoints for session corrections, advice, export, and reset."""
    session_id = "session_rest_test"

    # 1. Record correction via REST
    resp = client.post(
        "/api/session/correction",
        json={
            "session_id": session_id,
            "user_statement": "I told you to reduce the low-mids; what's the grade now?",
            "topic": "low_mids",
            "correction_text": "reduce the low-mids",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["correction"]["topic"] == "low_mids"

    # 2. Get corrections via REST
    resp = client.get("/api/session/corrections", params={"session_id": session_id})
    assert resp.status_code == 200
    assert len(resp.json()["corrections"]) >= 1

    # 3. Record followed advice via REST
    resp = client.post(
        "/api/session/followed-advice",
        json={
            "session_id": session_id,
            "user_statement": "I lowered the low-mids and the grade went from 42 to 61",
            "action": "lowered low-mids",
            "grade_before": 42.0,
            "grade_after": 61.0,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["followed_advice"]["grade_delta"] == 19.0

    # 4. Get followed advice via REST
    resp = client.get("/api/session/followed-advice", params={"session_id": session_id})
    assert resp.status_code == 200
    assert len(resp.json()["followed_advice"]) >= 1

    # 5. Export session via REST
    resp = client.get("/api/session/export", params={"session_id": session_id})
    assert resp.status_code == 200
    assert resp.json()["session_id"] == session_id

    # 6. Reset session via REST
    resp = client.post("/api/session/reset", json={"session_id": session_id})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # 7. Confirm wiped
    resp = client.get("/api/session/corrections", params={"session_id": session_id})
    assert resp.status_code == 200
    assert resp.json()["corrections"] == []
