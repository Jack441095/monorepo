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
