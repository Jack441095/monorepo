"""Song tempo as a Live change: proposal, verified write, exact undo (27 Sept 2026)."""

from __future__ import annotations

import pytest

from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_action_service import LiveActionService
from kenn.core.live_command import handle_command
from kenn.core.live_intent import parse_request


@pytest.fixture
def fake():
    return FakeLiveBackend()


@pytest.mark.parametrize("request_text, bpm", [
    ("set the tempo to 124", 124.0),
    ("tempo 128", 128.0),
    ("128 bpm", 128.0),
    ("change the bpm to 90.5", 90.5),
    ("can you set the tempo to 124 please", 124.0),
    ("tempo up 2 bpm", 122.0),
    ("bump the tempo by 3", 123.0),
    ("slow the tempo down 4 bpm", 116.0),
    ("drop the tempo to 118", 118.0),
])
def test_tempo_requests_become_a_tempo_change(fake, request_text, bpm) -> None:
    parsed = parse_request(request_text, fake.query_session_state())
    assert parsed["action"] == "set_tempo" and parsed["desired_value"] == bpm and not parsed["missing_fields"]


@pytest.mark.parametrize("request_text", [
    "is 128 bpm too fast for techno?",
    "warp the clip to 120 bpm",
    "sync the delay to 120 bpm",
    "stretch my samples to fit the track's tempo",
    "make me a techno loop at 128 bpm",
    "set the kick to 124",
])
def test_other_bpm_talk_is_not_a_tempo_change(fake, request_text) -> None:
    assert parse_request(request_text, fake.query_session_state())["action"] != "set_tempo"


@pytest.mark.parametrize("request_text, words", [
    ("speed it up a bit", "To what tempo? It's 120 BPM now."),
    ("set the tempo to 1200", "20 to 999 BPM"),
])
def test_a_tempo_request_missing_a_usable_number_asks(fake, request_text, words) -> None:
    parsed = parse_request(request_text, fake.query_session_state())
    assert parsed["missing_fields"] == ["amount"] and words in parsed["ambiguity"][0]


def test_tempo_change_is_confirmed_verified_and_undone_exactly(fake) -> None:
    service = LiveActionService(fake)
    planned = handle_command("set the tempo to 124", session_id="tempo", service=service, allow_llm=False)
    assert planned["status"] == "confirmation_required"
    assert "from 120 BPM to 124 BPM" in planned["answer"] and fake.writes == []

    proposal = planned["proposal"]
    applied = handle_command("", session_id="tempo", service=service, proposal=proposal,
                             confirm_token=proposal["confirmation_token"], allow_llm=False)
    assert applied["receipt"]["verified"] and applied["receipt"]["readback"] == 124.0

    undo = service.propose_undo(applied["receipt"], session_id="tempo")
    assert undo["ok"] and undo["proposal"]["after"] == 120.0
    assert service.execute(undo["proposal"], confirm_token=undo["proposal"]["confirmation_token"], session_id="tempo")["ok"]
    assert fake.query_session_state()["tempo"] == 120.0


def test_a_tempo_changed_in_live_after_the_proposal_is_not_overwritten(fake) -> None:
    service = LiveActionService(fake)
    proposal = service.propose_tempo_action(124.0, session_id="tempo")["proposal"]
    fake.set_tempo(100.0)  # someone moves the tempo in Live before Apply
    result = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="tempo")
    assert not result["ok"] and "changed since the proposal" in result["error"]
    assert fake.query_session_state()["tempo"] == 100.0


def test_undo_is_stale_once_the_tempo_moves_again(fake) -> None:
    service = LiveActionService(fake)
    proposal = service.propose_tempo_action(124.0, session_id="tempo")["proposal"]
    receipt = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="tempo")["receipt"]
    fake.set_tempo(130.0)
    undo = service.propose_undo(receipt, session_id="tempo")
    assert not undo["ok"] and "stale" in undo["error"]


def test_the_same_tempo_changes_nothing(fake) -> None:
    reply = handle_command("tempo 120", session_id="tempo", service=LiveActionService(fake), allow_llm=False)
    assert reply["answer"].startswith("The tempo is already 120 BPM") and not reply.get("proposal")




@pytest.mark.parametrize("request_text, signature", [
    ("set the time signature to 3/4", (3, 4)),
    ("time signature 6/8", (6, 8)),
    ("switch to 7/8 time", (7, 8)),
    ("change the meter to 5/4", (5, 4)),
])
def test_time_signature_requests_become_a_signature_change(fake, request_text, signature) -> None:
    parsed = parse_request(request_text, fake.query_session_state())
    assert parsed["action"] == "set_time_signature" and not parsed["missing_fields"]
    assert (parsed["desired_value"]["numerator"], parsed["desired_value"]["denominator"]) == signature


def test_a_signature_live_cannot_take_is_refused(fake) -> None:
    parsed = parse_request("set the time signature to 4/3", fake.query_session_state())
    assert parsed["missing_fields"] == ["amount"] and "1, 2, 4, 8 or 16" in parsed["ambiguity"][0]


def test_time_signature_change_is_verified_and_undone_exactly(fake) -> None:
    service = LiveActionService(fake)
    planned = handle_command("set the time signature to 3/4", session_id="sig", service=service, allow_llm=False)
    assert "from 4/4 to 3/4" in planned["answer"] and fake.writes == []
    proposal = planned["proposal"]
    applied = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="sig")
    assert applied["receipt"]["verified"] and applied["receipt"]["readback"] == {"numerator": 3, "denominator": 4}
    undo = service.propose_undo(applied["receipt"], session_id="sig")
    assert service.execute(undo["proposal"], confirm_token=undo["proposal"]["confirmation_token"], session_id="sig")["ok"]
    state = fake.query_session_state()
    assert (state["signature_numerator"], state["signature_denominator"]) == (4, 4)


@pytest.mark.parametrize("request_text", ["the hats play 1/16 notes", "the hats play eighth notes", "3/4"])
def test_note_values_and_bare_fractions_change_nothing(fake, request_text) -> None:
    assert parse_request(request_text, fake.query_session_state())["action"] not in {"transport_play", "set_time_signature"}


@pytest.mark.parametrize("request_text, signature", [
    ("can we go to 3/4?", (3, 4)),
    ("the bass is still too loud, maybe we need to lower it more, but the time signature is 4/4. can we try 6/8?", (6, 8)),
])
def test_a_signature_said_without_the_word(fake, request_text, signature) -> None:
    parsed = parse_request(request_text, fake.query_session_state())
    assert parsed["action"] == "set_time_signature"
    assert (parsed["desired_value"]["numerator"], parsed["desired_value"]["denominator"]) == signature
