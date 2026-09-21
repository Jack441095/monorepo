"""Tests for grounded, read-only questions about the current Live Set."""

from __future__ import annotations

from copy import deepcopy

import pytest

from kenn.core.live_session_questions import answer_live_session_question


class SessionLive:
    backend_name = "ableton-control-deck-mcp"

    def __init__(self) -> None:
        self.state = {
            "status": "connected",
            "backend": self.backend_name,
            "tempo": 120.0,
            "signature_numerator": 4,
            "signature_denominator": 4,
            "is_playing": False,
            "selected_track_index": 3,
            "tracks": [
                {"index": 0, "name": "1-MIDI", "devices": []},
                {"index": 1, "name": "2-MIDI", "devices": []},
                {"index": 2, "name": "3-Audio", "devices": []},
                {"index": 3, "name": "4-Audio", "devices": []},
            ],
        }
        self.reads = 0

    def query_session_state(self, **_kwargs):
        self.reads += 1
        return deepcopy(self.state)


class Service:
    def __init__(self, client: SessionLive) -> None:
        self.client = client

    def snapshot(self, *, include_mixer: bool = True):
        assert include_mixer is True
        return self.client.query_session_state(include_mixer=include_mixer)


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Are you connected to Ableton?", "fresh read-only connection"),
        ("How many tracks are there?", "4 tracks"),
        ("What is track 3?", "Track 3 is '3-Audio'"),
        ("What is the current tempo and time signature?", "120 BPM"),
        ("Which track is selected?", "Track 4, '4-Audio'"),
        ("Which tracks have duplicate names?", "no duplicate track names"),
        ("Describe this Live Set.", "4 tracks"),
    ],
)
def test_common_session_questions_use_fresh_read_only_snapshot(question: str, expected: str) -> None:
    client = SessionLive()
    result = answer_live_session_question(question, service=Service(client))

    assert result is not None
    assert result["status"] == "inspected"
    assert result["changed"] is False
    assert expected.casefold() in result["answer"].casefold()
    assert client.reads == 1


def test_duplicate_names_are_reported_exactly() -> None:
    client = SessionLive()
    client.state["tracks"][3]["name"] = "3-Audio"
    result = answer_live_session_question(
        "Which tracks have duplicate names?",
        service=Service(client),
    )

    assert result["duplicate_track_names"] == ["3-Audio"]


def test_unrelated_chat_is_not_hijacked() -> None:
    client = SessionLive()
    result = answer_live_session_question(
        "Why does my mix collapse in mono?",
        service=Service(client),
    )

    assert result is None
    assert client.reads == 0
