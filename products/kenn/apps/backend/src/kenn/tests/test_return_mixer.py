"""Return-track level, pan and mute as Live changes: proposal, stale check, readback, exact undo (27 Sept 2026)."""

from __future__ import annotations

import pytest

from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_action_service import LiveActionService
from kenn.core.live_command import handle_command
from kenn.core.live_intent import parse_request


@pytest.fixture
def fake():
    return FakeLiveBackend()


@pytest.mark.parametrize("request_text, action, name, value, relative", [
    ("lower the A-Reverb by 1db", "set_return_volume", "A-Reverb", None, -1.0),
    ("turn the A-Reverb up 3 dB", "set_return_volume", "A-Reverb", None, 3.0),
    ("set the reverb return to -10 dB", "set_return_volume", "A-Reverb", -10.0, None),
    ("mute the B-Delay", "set_return_mute", "B-Delay", True, None),
    ("unmute return B", "set_return_mute", "B-Delay", False, None),
    ("pan the delay return 30% left", "set_return_pan", "B-Delay", -0.3, None),
])
def test_return_track_requests(fake, request_text, action, name, value, relative) -> None:
    parsed = parse_request(request_text, fake.query_session_state())
    assert parsed["action"] == action and parsed["return_track_name"] == name and not parsed["missing_fields"]
    assert parsed["desired_value"] == value and parsed.get("relative_db") == relative


def test_a_send_to_a_return_is_still_a_send(fake) -> None:
    assert parse_request("send the vocal to the A-Reverb at 20%", fake.query_session_state())["action"] == "set_send"


def test_return_level_is_confirmed_read_back_and_undone_exactly(fake) -> None:
    service = LiveActionService(fake)
    planned = handle_command("lower the A-Reverb by 1db", session_id="ret", service=service, allow_llm=False)
    assert "from -14.0 dB" in planned["answer"] and "to -15.0 dB" in planned["answer"] and fake.writes == []
    proposal = planned["proposal"]
    applied = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="ret")
    assert applied["receipt"]["verified"]
    undo = service.propose_undo(applied["receipt"], session_id="ret")
    assert service.execute(undo["proposal"], confirm_token=undo["proposal"]["confirmation_token"], session_id="ret")["ok"]
    assert fake.get_bus_mixer("return", 0)["volume"] == pytest.approx(0.5)


def test_a_return_changed_in_live_before_apply_is_not_overwritten(fake) -> None:
    service = LiveActionService(fake)
    proposal = service.propose_return_mixer_action("set_return_mute", return_index=1, return_name="B-Delay", value=True,
                                                   session_id="ret")["proposal"]
    fake.set_return_mixer(1, "mute", True)
    result = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="ret")
    assert not result["ok"] and "changed since the proposal" in result["error"]


def test_a_return_above_0_db_is_refused(fake) -> None:
    reply = handle_command("turn the A-Reverb up 20 dB", session_id="ret", service=LiveActionService(fake), allow_llm=False)
    assert "above 0 dB" in reply["answer"] and not reply.get("proposal")


def test_what_returns_cannot_do_yet_is_said_plainly(fake) -> None:
    parsed = parse_request("solo the B-Delay", fake.query_session_state())
    assert parsed["missing_fields"] == ["return_track_action"] and "not its name or solo" in parsed["ambiguity"][0]


@pytest.mark.parametrize("request_text, name", [
    ("can you lower the reverb by 1db?", "A-Reverb"),
    ("turn the delay down", "B-Delay"),
    ("The snare is fine. Maybe the delay time is too short. Oh, can you lower the reverb by 1db?", "A-Reverb"),
])
def test_a_bare_effect_level_asks_return_or_send(fake, request_text, name) -> None:
    # These got mix notes (round 8, 27 Sept 2026): it's the return's level or one track's send, so KENN asks which.
    parsed = parse_request(request_text, fake.query_session_state())
    assert parsed["missing_fields"] == ["which_change"] and f"The {name} return's level" in parsed["ambiguity"][0]
    assert not parsed["confirmation_required"]


def test_turning_down_the_reverb_on_a_track_asks_for_its_send_level(fake) -> None:
    parsed = parse_request("turn down the reverb on the snare", fake.query_session_state())
    assert parsed["action"] == "set_send" and parsed["missing_fields"] == ["amount"]
    assert "Snare / Clap's reverb send" in parsed["ambiguity"][0]
