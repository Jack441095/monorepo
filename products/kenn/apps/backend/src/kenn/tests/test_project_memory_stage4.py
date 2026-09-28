"""Tests for Stage 4 Project Memory & Personalisation.

Guarantees:
- Testers can find and delete any memory via REST API and chat.
- Memory-using answers cite the memory in their prose and payload.
- No cross-project leaks: memory is strictly session-scoped.
- Nothing learned silently: only explicit opt-in preferences are stored.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from kenn.core.assistant_profile_memory import AssistantProfileStore
from kenn.core.chat_answer import answer_payload
from kenn.core.project_memory_advisory import (
    evaluate_memory_chat_intent,
    format_preference_citation,
    match_preferences_for_query,
    parse_explicit_preference,
)
from kenn.routes.fastapi_app import app


client = TestClient(app)


def test_parse_explicit_preferences():
    # North star explicit examples
    p1 = parse_explicit_preference("I like my vocals bright")
    assert p1 is not None
    assert p1[0] == "creative_direction"
    assert p1[1] == "vocals bright"

    p2 = parse_explicit_preference("I master to -9 LUFS")
    assert p2 is not None
    assert p2[0] == "workflow"
    assert "master to -9 LUFS" in p2[1]

    p3 = parse_explicit_preference("Remember that I mix on headphones")
    assert p3 is not None
    assert p3[0] == "monitoring"
    assert p3[1] == "headphones"

    p4 = parse_explicit_preference("Set preference mix_priority: vocals forward")
    assert p4 is not None
    assert p4[0] == "mix_priority"
    assert p4[1] == "vocals forward"

    # Non-preference query must NOT parse (nothing learned silently)
    assert parse_explicit_preference("How do I EQ a snare drum?") is None
    assert parse_explicit_preference("Can you mute track 2?") is None


def test_preference_matching_and_citation():
    preferences = [
        {"key": "creative_direction", "value": "vocals bright"},
        {"key": "workflow", "value": "master to -9 LUFS"},
        {"key": "monitoring", "value": "headphones"},
    ]

    # Query about vocal EQ matches vocal preference
    vocal_matches = match_preferences_for_query("How should I EQ my vocal track?", preferences)
    assert len(vocal_matches) == 1
    assert vocal_matches[0]["key"] == "creative_direction"
    citation = format_preference_citation(vocal_matches)
    assert "vocals bright" in citation
    assert "creative direction" in citation

    # Query about mastering loudness matches workflow preference
    master_matches = match_preferences_for_query("What limiter ceiling and target should I aim for when mastering?", preferences)
    assert len(master_matches) == 1
    assert master_matches[0]["key"] == "workflow"

    # Query about stereo width on headphones matches monitoring
    headphone_matches = match_preferences_for_query("How wide should my mix be on headphones?", preferences)
    assert len(headphone_matches) == 1
    assert headphone_matches[0]["key"] == "monitoring"

    # Unrelated query matches nothing
    snare_matches = match_preferences_for_query("How do I tune an 808?", preferences)
    assert len(snare_matches) == 0
    assert format_preference_citation([]) == ""


def test_chat_memory_commands(tmp_path):
    store = AssistantProfileStore(tmp_path / "test_memory.db")
    session_id = "test-session-chat"

    # 1. Initially empty
    view_empty = evaluate_memory_chat_intent("What do you remember about this project?", session_id=session_id, store=store)
    assert view_empty is not None
    assert "No project preferences or episodic memories" in view_empty["answer"]

    # 2. Explicitly tell KENN a preference
    set_res = evaluate_memory_chat_intent("I like my vocals bright", session_id=session_id, store=store)
    assert set_res is not None
    assert "Saved to project memory" in set_res["answer"]
    assert "vocals bright" in set_res["answer"]

    # 3. View memory shows active preference
    view_active = evaluate_memory_chat_intent("Show project memory", session_id=session_id, store=store)
    assert view_active is not None
    assert "Creative Direction" in view_active["answer"]
    assert "vocals bright" in view_active["answer"]

    # 4. Forget single preference
    forget_res = evaluate_memory_chat_intent("Forget preference creative_direction", session_id=session_id, store=store)
    assert forget_res is not None
    assert "Forgotten" in forget_res["answer"]

    # 5. Verify forgotten
    assert store.current_preferences(session_id) == []


def test_fastapi_memory_rest_api_lifecycle(tmp_path, monkeypatch):
    db_file = tmp_path / "api_test_memory.db"
    monkeypatch.setattr("kenn.core.session_memory.DB_PATH", db_file)

    session_a = "proj-alpha"
    session_b = "proj-beta"

    # Record preference in session A
    resp = client.post(
        "/api/memory/preference",
        json={
            "session_id": session_a,
            "key": "creative_direction",
            "value": "vocals bright",
            "user_statement": "I like my vocals bright",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["preference"]["value"] == "vocals bright"

    # Record second preference in session A
    resp2 = client.post(
        "/api/memory/preference",
        json={
            "session_id": session_a,
            "key": "workflow",
            "value": "master to -9 LUFS",
            "user_statement": "I master to -9 LUFS",
        },
    )
    assert resp2.status_code == 200

    # Get memory for session A
    get_a = client.get(f"/api/memory?session_id={session_a}")
    assert get_a.status_code == 200
    prefs_a = get_a.json()["producer_preferences"]
    assert len(prefs_a) == 2
    keys_a = {p["key"] for p in prefs_a}
    assert "creative_direction" in keys_a
    assert "workflow" in keys_a

    # Verify zero cross-project leaks: session B has zero preferences
    get_b = client.get(f"/api/memory?session_id={session_b}")
    assert get_b.status_code == 200
    assert len(get_b.json()["producer_preferences"]) == 0

    # Delete preference from session A
    del_resp = client.delete(f"/api/memory/preference?session_id={session_a}&key=creative_direction")
    assert del_resp.status_code == 200
    assert del_resp.json()["forgotten"] is True

    # Check session A now only has workflow
    get_a2 = client.get(f"/api/memory?session_id={session_a}")
    assert len(get_a2.json()["producer_preferences"]) == 1
    assert get_a2.json()["producer_preferences"][0]["key"] == "workflow"

    # Clear all memory for session A
    clear_resp = client.post("/api/memory/clear", json={"session_id": session_a})
    assert clear_resp.status_code == 200
    assert clear_resp.json()["cleared"]["preferences"] >= 1

    # Verify session A is empty
    get_a3 = client.get(f"/api/memory?session_id={session_a}")
    assert len(get_a3.json()["producer_preferences"]) == 0


def test_answer_payload_cites_memory_and_enforces_cross_project_isolation(tmp_path, monkeypatch):
    db_file = tmp_path / "answer_memory.db"
    monkeypatch.setattr("kenn.core.session_memory.DB_PATH", db_file)

    session_target = "song-cit-1"
    session_other = "song-cit-2"

    store = AssistantProfileStore(db_file)
    store.record_preference(
        session_id=session_target,
        key="creative_direction",
        value="vocals bright",
        source_turn_id="turn-init",
        user_statement="I like my vocals bright",
    )

    # Ask vocal question in session_target
    ans_target = answer_payload(
        "How should I EQ my vocal track?",
        session_id=session_target,
        allow_llm=False,
    )
    # Must cite preference in prose
    assert "Noting your preference for this project: vocals bright (creative direction)." in ans_target["answer"]
    # Must attach applied_preferences in payload
    assert len(ans_target.get("applied_preferences", [])) == 1
    assert ans_target["applied_preferences"][0]["key"] == "creative_direction"
    assert ans_target["applied_preferences"][0]["value"] == "vocals bright"

    # Ask identical vocal question in session_other (NO preferences saved)
    ans_other = answer_payload(
        "How should I EQ my vocal track?",
        session_id=session_other,
        allow_llm=False,
    )
    # Must NOT cite any preference in prose
    assert "Noting your preference" not in ans_other["answer"]
    assert ans_other.get("applied_preferences") == []
