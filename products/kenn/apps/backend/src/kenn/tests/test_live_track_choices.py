from __future__ import annotations

import json

import pytest

from kenn.core import live_command
from kenn.core.live_intent import parse_request
from kenn.core.session_context import live_conversation_context
from kenn.tests.test_live_command import FakeLive, _service


def _vocal_pair():
    fake = FakeLive()
    fake.state["tracks"][1]["name"] = "Vocal"
    return fake, _service(fake)


def _ask(service, command, session):
    return live_command.handle_command(command, session_id=session, service=service, allow_llm=False)


def test_displayed_duplicate_tracks_support_other_one_after_selection_apply_and_undo():
    # Duplicate names lost their distinct identities between clarification and the next turn.
    fake, service = _vocal_pair()
    session = "track-choice-apply-undo"
    asked = _ask(service, "mute Vocal", session)
    assert asked["status"] == "clarification_required"
    assert asked["track_choices"] == [
        {"index": 1, "name": "Vocal", "number": 2},
        {"index": 2, "name": "Vocal", "number": 3},
    ]
    assert 'track 2 "Vocal"' in asked["answer"] and 'track 3 "Vocal"' in asked["answer"]

    first = _ask(service, "track 2", session)
    assert first["proposal"]["track_index"] == 1
    assert fake.writes == []
    applied = live_command.handle_command("apply", session_id=session, service=service,
        proposal=first["proposal"], confirm_token=first["proposal"]["confirmation_token"],
        idempotency_key=first["proposal"]["action_id"], allow_llm=False)
    assert applied["status"] == "applied" and applied["receipt"]["verified"] is True
    assert fake.state["tracks"][1]["muted"] is True

    other = _ask(service, "no, the other one", session)
    assert other["status"] == "confirmation_required"
    assert other["proposal"]["track_index"] == 2
    assert other["resolved_command"] == "mute Vocal on track 3"
    assert "still applied" in other["answer"]
    assert len(fake.writes) == 1
    assert "confirmation_token" not in json.dumps(live_conversation_context(session)["track_choice"])

    applied_other = live_command.handle_command("apply", session_id=session, service=service,
        proposal=other["proposal"], confirm_token=other["proposal"]["confirmation_token"],
        idempotency_key=other["proposal"]["action_id"], allow_llm=False)
    assert applied_other["status"] == "applied" and applied_other["receipt"]["verified"] is True
    undo = service.propose_undo(applied_other["receipt"], session_id=session)
    undone = live_command.handle_command("undo", session_id=session, service=service,
        proposal=undo["proposal"], confirm_token=undo["proposal"]["confirmation_token"],
        idempotency_key=undo["proposal"]["action_id"], allow_llm=False)
    assert undone["status"] == "applied" and undone["receipt"]["verified"] is True
    assert fake.state["tracks"][1]["muted"] is True
    assert fake.state["tracks"][2]["muted"] is False


def test_other_one_without_a_selected_choice_asks_and_keeps_the_original_request():
    fake, service = _vocal_pair()
    session = "track-choice-no-anchor"
    asked = _ask(service, "mute Vocal", session)
    other = _ask(service, "the other one", session)
    assert other["status"] == "clarification_required" and "proposal" not in other
    assert other["track_choices"] == asked["track_choices"]
    selected = _ask(service, "the second one", session)
    assert selected["status"] == "confirmation_required"
    assert selected["proposal"]["track_index"] == 2
    assert selected["proposal"]["action"] == "set_mute"
    assert fake.writes == []


@pytest.mark.parametrize("change", ["rename", "reorder", "remove", "expire", "unrelated", "different_session"])
@pytest.mark.parametrize("reply", ["no, the other one", "track 3"])
def test_track_choices_do_not_cross_session_or_current_identity_boundaries(change, reply, monkeypatch):
    fake, service = _vocal_pair()
    session = "track-choice-boundary-" + change + "-" + reply
    asked = _ask(service, "mute Vocal", session)
    assert len(asked["track_choices"]) == 2
    selected = _ask(service, "track 2", session)
    assert selected["proposal"]["track_index"] == 1
    assert live_conversation_context(session)["track_choice"]["selected"]["index"] == 1
    if change == "rename":
        fake.state["tracks"][2]["name"] = "New Vocal"
    elif change == "reorder":
        fake.state["tracks"][1], fake.state["tracks"][2] = fake.state["tracks"][2], fake.state["tracks"][1]
    elif change == "remove":
        fake.state["tracks"].pop(2)
    elif change == "expire":
        now = live_command.time.time()
        monkeypatch.setattr(live_command.time, "time", lambda: now + 301)
    elif change == "unrelated":
        _ask(service, "mute Kick", session)
    else:
        session += "-different"
    result = _ask(service, reply, session)
    assert result["status"] == "clarification_required" and "proposal" not in result
    assert fake.writes == []


def test_three_displayed_matches_require_an_explicit_track_instead_of_other_one():
    fake, service = _vocal_pair()
    fake.state["tracks"][3]["name"] = "Vocal"
    session = "track-choice-three"
    asked = _ask(service, "mute Vocal", session)
    assert len(asked["track_choices"]) == 3
    first = _ask(service, "track 2", session)
    assert first["proposal"]["track_index"] == 1
    result = _ask(service, "other one", session)
    assert result["status"] == "clarification_required" and "proposal" not in result
    selected = _ask(service, "track 3", session)
    assert selected["proposal"]["track_index"] == 2
    assert fake.writes == []


def test_shared_vocal_nickname_keeps_display_numbers_separate_from_track_indices():
    fake = FakeLive()
    fake.state["tracks"][1].update(name="Lead Vocal", index=11)
    fake.state["tracks"][2].update(name="Backing Vocal", index=22)
    parsed = parse_request("mute vox", fake.state)
    assert parsed["missing_fields"] == ["which_track"]
    assert parsed["track_candidates"] == [
        {"index": 11, "name": "Lead Vocal", "number": 2},
        {"index": 22, "name": "Backing Vocal", "number": 3},
    ]
    service = _service(fake)
    session = "track-choice-nickname"
    asked = _ask(service, "mute vox", session)
    assert asked["track_choices"] == parsed["track_candidates"]
    selected = _ask(service, "Backing Vocal", session)
    assert selected["proposal"]["track_index"] == 22
    other = _ask(service, "the other one", session)
    assert other["proposal"]["track_index"] == 11
    assert fake.writes == []


@pytest.mark.parametrize("typed_plan", [False, True])
def test_model_cannot_choose_a_track_while_the_producer_is_being_asked(typed_plan, monkeypatch):
    fake, service = _vocal_pair()
    monkeypatch.setenv("KENN_LIVE_LLM_ENABLED", "1")
    monkeypatch.setenv("KENN_LIVE_LLM_MODE", "propose")

    def unexpected_model(*args, **kwargs):
        raise AssertionError("an unresolved track choice must not spend a model call")

    monkeypatch.setattr(live_command, "_generate_llm_plan", unexpected_model)
    plan = {"schema": "kenn.ableton_llm_plan.v1", "action": "set_mute", "track_index": 1,
            "track_name": "Vocal", "value": True, "unit": "boolean"} if typed_plan else None
    result = live_command.handle_command("mute Vocal", session_id=f"track-choice-model-{typed_plan}",
                                       service=service, llm_plan=plan)
    assert result["status"] == "clarification_required" and "proposal" not in result
    assert len(result["track_choices"]) == 2
    assert result["llm"]["reason"] == "track_choice_requires_user"
    assert fake.writes == []


def test_diagnostic_copy_cannot_change_the_choices_or_confirmation_identity():
    fake, service = _vocal_pair()
    session = "track-choice-copy"
    _ask(service, "mute Vocal", session)
    first = _ask(service, "track 2", session)
    assert first["proposal"]["track_index"] == 1
    context = live_conversation_context(session)
    context["track_choice"]["tracks"][1]["index"] = 99
    context["track_choice"]["selected"]["index"] = 99
    other = _ask(service, "other one", session)
    assert other["proposal"]["track_index"] == 2
    assert "confirmation_token" not in json.dumps(live_conversation_context(session))
    assert fake.writes == []


def test_repeating_a_duplicate_name_keeps_the_action_and_amount_being_clarified():
    fake, service = _vocal_pair()
    session = "track-choice-relative"
    asked = _ask(service, "vocal down 2 dB", session)
    assert len(asked["track_choices"]) == 2
    repeated = _ask(service, "Vocal", session)
    assert repeated["status"] == "clarification_required"
    assert repeated["clarification_command"] == "vocal down 2 dB"
    selected = _ask(service, "track 2", session)
    assert selected["proposal"]["action"] == "set_volume"
    assert selected["proposal"]["track_index"] == 1
    other = _ask(service, "the other one", session)
    assert other["proposal"]["action"] == "set_volume"
    assert other["proposal"]["track_index"] == 2
    assert other["proposal"]["after"] < other["proposal"]["before"]
    assert other["resolved_command"] == "vocal down 2 dB on track 3"
    assert fake.writes == []
