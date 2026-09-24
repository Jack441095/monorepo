"""Refusals survive keyboard slips (owner rehearsal 2026-09-24: "et the master volume to maximum." got
mastering advice instead of the refusal), without refusing ordinary words or questions."""

from __future__ import annotations

import pytest

from kenn import server
from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_intent import parse_request

SNAPSHOT = FakeLiveBackend().query_session_state()


@pytest.mark.parametrize("query", [
    "et the master volume to maximum.", "set the mastr volume to maximum", "delte track 3", "dleete track 3",
    "crank the master", "master to max", "turn the master up to max", "push the master fader all the way up",
])
def test_slipped_or_reworded_unsafe_requests_are_refused(query) -> None:
    assert parse_request(query, SNAPSHOT)["mode"] == "refuse"


@pytest.mark.parametrize("query", [
    "the remote", "removed", "set up the master bus compression", "set the master bus compressor ratio to 4",
    "what is a master bus?", "the mater of taste",
])
def test_real_words_and_ordinary_requests_are_not_refused(query) -> None:
    assert parse_request(query, SNAPSHOT)["mode"] != "refuse"


@pytest.mark.parametrize("question, routed", [
    ("et the master volume to maximum.", True), ("delte track 3", True), ("crank the master", True),
    ("Set the master volume to maximum.", True), ("How do I delete a track?", False), ("Am I clipping?", False),
    ("An EQ question", False), ("Show the finding cards in the chat.", False),
])
def test_chat_route_sends_slipped_commands_to_the_gateway(question, routed) -> None:
    assert server._is_live_imperative(question) is routed
