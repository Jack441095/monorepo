"""Chat decides between changing Live and answering from the notes the way the rule parser reads the message."""

from __future__ import annotations

import pytest

from kenn.core.chat_live_router import asks_how_to, wants_live_change
from kenn.core.fake_live import FakeLiveBackend


@pytest.fixture()
def demo() -> dict:
    return FakeLiveBackend().query_session_state()


# 26 Sept 2026: these reached the notes, because they didn't open with one of the chat's command verbs.
@pytest.mark.parametrize("request_text", [
    "can you solo the hats",
    "bump the synth up 1 dB",
    "Send the synth to A-Reverb 30 percent",
    "I want to send 50% of the snare and clap to the B-Delay to add some depth, could you handle that?",
    "drumbus down 2 dB",
    "go to the kick",
])
def test_requests_worded_any_way_reach_live(demo, request_text) -> None:
    assert wants_live_change(request_text, demo)


# 26 Sept 2026: these came back as Live proposals (the Synth turned down, a Glue Compressor, a mute).
@pytest.mark.parametrize("question", [
    "I'm mixing vocals and they sound a bit muddy. How can I make them clearer without losing their warmth?",
    "My drum tracks have a lot of low-end rumble. What's a quick way to clean them up without affecting the punch?",
    "I need a way to quickly mute the bass during a breakdown without affecting the rest of the track.",
    "I want to add more depth to my synth sounds, but I don't want it to sound muddy or too processed.",
    "how do I mute a track",
])
def test_asking_how_stays_with_the_notes(demo, question) -> None:
    assert asks_how_to(question)
    assert not wants_live_change(question, demo)


def test_nothing_goes_to_live_without_a_connected_set() -> None:
    assert not wants_live_change("mute the kick", {"status": "offline", "tracks": []})
    assert not wants_live_change("mute the kick", None)


# 26 Sept 2026, a sealed set of chat messages written by Qwen3 8B on the box: 76% of requests reached Live on first
# score. These are the general shapes it found; none of them changed anything before.
@pytest.mark.parametrize("request_text, action, track", [
    ("Can you lower the bass a bit?", "set_volume", "Bass"),                      # asks by how much
    ("The kick is too loud, can you bring it down to -16?", "set_volume", "Kick"),
    ("bring the kick down to -16, it's too loud", "set_volume", "Kick"),
    ("I need the lead vocal back to center, please.", "set_pan", "Lead Vocal"),
    ("Just make sure the snare is centered.", "set_pan", "Snare / Clap"),
    ("I need the drum bus muted for now.", "set_mute", "Drum Bus"),
    ("Focus on the hi-hats for a moment.", "focus_track", "Hi-Hats"),
    ("Let's focus on the lead vocal track.", "focus_track", "Lead Vocal"),
])
def test_everyday_chat_wording_reads_as_the_request(demo, request_text, action, track) -> None:
    from kenn.core.live_intent import parse_request

    intent = parse_request(request_text, demo)
    assert intent["action"] == action and intent["track"]["name"] == track


@pytest.mark.parametrize("not_a_request", [
    "the drum bus is muted",                      # describing the set
    "the kick is too loud",                       # a complaint, no request
    "just the kick",                              # still means solo the kick, not a stripped "just"
    "send a track out to my hardware compressor and back into Live",
])
def test_the_new_wording_rules_leave_these_alone(demo, not_a_request) -> None:
    from kenn.core.live_intent import parse_request

    intent = parse_request(not_a_request, demo)
    assert intent.get("action") in {None, "set_solo"} and "send_amount" not in (intent.get("missing_fields") or [])


def test_a_send_without_an_amount_asks_how_much(demo) -> None:
    from kenn.core.live_intent import parse_request

    assert "send_amount" in parse_request("Could you send the synth to the A-Reverb?", demo)["missing_fields"]
    assert wants_live_change("Could you send the synth to the A-Reverb?", demo)
