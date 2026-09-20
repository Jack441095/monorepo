from __future__ import annotations

from kenn.core import chat_answer
from kenn.core.diagnostic_state import reported_findings, state_for_query, update
from kenn.core.chat_answer import build_template_answer
from kenn.core.session_memory import build_session_context, infer_preferences, update_session


def _results():
    return [(10.0, {"kind": "note", "title": "Muddy mix", "source": "muddy.md", "text": "Tags: mix muddy low mids\nShort answer:\nCheck overlap.\n\nTry this:\n1. Compare.\n\nWhy it matters:\nContext matters."})]


def test_state_records_user_reported_failed_technique() -> None:
    state = {"diagnostic_state": state_for_query("My mix sounds muddy.")}
    diagnosis = update(state, "I already tried EQ cuts and it is still muddy")
    assert diagnosis is not None
    assert diagnosis["key"] == "muddy_mix"
    assert diagnosis["failed_techniques"] == ["EQ"]
    assert diagnosis["outcomes"] == ["EQ did not resolve the symptom"]


def test_state_does_not_mark_a_technique_failed_without_negative_outcome() -> None:
    state = {"diagnostic_state": state_for_query("My mix sounds muddy.")}
    diagnosis = update(state, "I tried EQ cuts yesterday")
    assert diagnosis is not None
    assert diagnosis["failed_techniques"] == []


def test_state_can_start_a_translation_diagnosis() -> None:
    diagnosis = state_for_query("My mix does not translate in the car")
    assert diagnosis is not None
    assert diagnosis["key"] == "translation"


def test_state_can_start_a_flat_drum_diagnosis() -> None:
    diagnosis = state_for_query("My drums lack punch")
    assert diagnosis is not None
    assert diagnosis["key"] == "flat_drums"


def test_state_can_start_a_sibilance_diagnosis() -> None:
    diagnosis = state_for_query("My vocal has too much sibilance")
    assert diagnosis is not None
    assert diagnosis["key"] == "sibilant_vocal"


def test_state_can_start_a_harsh_mix_diagnosis() -> None:
    diagnosis = state_for_query("My mix is harsh and brittle")
    assert diagnosis is not None
    assert diagnosis["key"] == "harsh_mix"


def test_explicit_kick_mute_result_is_saved_as_limited_evidence() -> None:
    active = state_for_query("The kick disappears when the bass comes in")
    assert active is not None
    finding = reported_findings(active, "When I mute the bass, the kick returns")
    assert len(finding) == 1
    assert "does not by itself distinguish" in finding[0]
    updated = update({"diagnostic_state": active}, "When I mute the bass, the kick returns")
    assert updated is not None
    assert updated["confirmed_findings"] == finding


def test_bass_sidechain_bypass_is_saved_as_a_bounded_result() -> None:
    active = state_for_query("Why does my bass disappear when the kick plays?")
    assert active is not None
    finding = reported_findings(active, "When I bypass the sidechain, the bass returns.")
    assert len(finding) == 1
    assert "does not identify whether depth" in finding[0]


def test_level_matched_reference_result_does_not_overstate_the_cause() -> None:
    active = state_for_query("Why is my mix darker than my reference?")
    assert active is not None
    finding = reported_findings(active, "At matched loudness it is still darker.")
    assert len(finding) == 1
    assert "does not identify the contributing source" in finding[0]


def test_repeated_outcome_report_is_idempotent() -> None:
    state = {"diagnostic_state": state_for_query("My mix sounds muddy.")}
    first = update(state, "I already tried EQ cuts and it is still muddy")
    assert first is not None
    second = update({"diagnostic_state": first}, "I already tried EQ cuts and it is still muddy")
    assert second is not None
    assert second["outcomes"] == ["EQ did not resolve the symptom"]


def test_elliptical_followup_uses_active_symptom_and_avoids_repeating_failed_move(monkeypatch) -> None:
    diagnosis = state_for_query("My mix sounds muddy.")
    assert diagnosis is not None
    diagnosis["failed_techniques"] = ["EQ"]
    monkeypatch.setattr(chat_answer, "_load_session", lambda **_kwargs: {"diagnostic_state": diagnosis})
    answer = build_template_answer(
        "still muddy", _results(), route="production", answer_mode="mix_diagnosis", session_id="state-test"
    )
    assert "Diagnosis first:" in answer
    assert "Already tested:" in answer
    assert "EQ did not resolve this symptom" in answer


def test_reported_test_result_immediately_uses_active_plan_and_explains_its_limit(monkeypatch) -> None:
    diagnosis = state_for_query("The kick disappears when the bass comes in")
    assert diagnosis is not None
    monkeypatch.setattr(chat_answer, "_load_session", lambda **_kwargs: {"diagnostic_state": diagnosis})
    answer = build_template_answer(
        "When I mute the bass, the kick returns", _results(), route="production", answer_mode="mix_diagnosis", session_id="state-test"
    )
    assert "What your test result supports:" in answer
    assert "does not by itself distinguish" in answer


def test_outer_chat_route_does_not_clarify_an_active_result_report(monkeypatch) -> None:
    diagnosis = state_for_query("The kick disappears when the bass comes in")
    assert diagnosis is not None
    monkeypatch.setattr(chat_answer, "_load_session", lambda **_kwargs: {"diagnostic_state": diagnosis})
    result = chat_answer._answer_payload_raw(
        "When I mute the bass, the kick returns", allow_llm=False, session_id="state-test"
    )
    assert "What your test result supports:" in result["answer"]


def test_explicit_creative_direction_is_user_context_not_a_technical_claim(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("kenn.core.session_memory.DB_PATH", tmp_path / "kenn.db")
    assert infer_preferences("I am aiming for dark and intimate") ["creative_direction"] == "dark and intimate"
    state = update_session("I want warm and wide", "A generic answer mentions rock and headphones.", session_id="creative-context")
    assert state["preferences"]["creative_direction"] == "warm and wide"
    assert state["preferences"].get("genre") is None
    assert state["preferences"].get("monitoring") is None
    state["turn_count"] = 2
    assert "preference, not a technical fault" in build_session_context(state)


def test_session_turn_bypasses_semantic_cache_so_diagnostic_memory_can_update(monkeypatch) -> None:
    monkeypatch.setattr(
        "kenn.core.session_memory.get_semantic_cache_hit",
        lambda _query: [{"event": "metadata", "data": {"answer": "stale cached answer"}}],
    )
    monkeypatch.setattr(
        chat_answer,
        "_answer_payload_raw",
        lambda *_args, **_kwargs: {"answer": "fresh session-aware answer", "confidence": "medium"},
    )
    result = chat_answer._answer_payload("My mix sounds muddy", allow_llm=True, session_id="state-test")
    assert result["answer"] == "fresh session-aware answer"
    assert "semantic_cache_hit" not in result
