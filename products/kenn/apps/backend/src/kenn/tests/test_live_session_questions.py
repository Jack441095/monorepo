"""Tests for grounded, read-only questions about the current Live Set."""

from __future__ import annotations

from copy import deepcopy

import pytest

from kenn.core import live_receipt_journal
from kenn.core.live_action_service import LiveActionService
from kenn.core.live_command import handle_command
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
def test_common_session_questions_use_command_path_with_fresh_read_only_snapshot(question: str, expected: str) -> None:
    client = SessionLive()
    result = handle_command(question, session_id="session-qa", service=Service(client))

    assert result is not None
    assert result["status"] == "inspected"
    assert result["changed"] is False
    assert result["route"] == "ableton_command"
    assert result["answer_mode"] == "session_question"
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


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("What's selected?", "Track 4, '4-Audio'"),
        ("Any duplicate track names?", "no duplicate track names"),
    ],
)
def test_investor_demo_session_phrases_are_grounded(question: str, expected: str) -> None:
    result = handle_command(question, session_id="demo-session-qa", service=Service(SessionLive()))

    assert result["status"] == "inspected"
    assert result["answer_mode"] == "session_question"
    assert expected.casefold() in result["answer"].casefold()


def test_unrelated_chat_is_not_hijacked() -> None:
    client = SessionLive()
    result = answer_live_session_question(
        "Why does my mix collapse in mono?",
        service=Service(client),
    )

    assert result is None
    assert client.reads == 0


def test_track_count_uses_fresh_song_probe_without_full_snapshot() -> None:
    class CountProbeLive(SessionLive):
        def probe_connection(self):
            return {"status": "connected", "track_count": 4, "track_names": ["1-MIDI", "2-MIDI", "3-Audio", "4-Audio"]}

        def query_session_state(self, **_kwargs):
            raise AssertionError("track count should not request devices or mixer state")

    result = answer_live_session_question(
        "How many tracks are there?",
        service=Service(CountProbeLive()),
    )

    assert result["status"] == "inspected"
    assert result["track_count"] == 4
    assert result["answer"] == "The current Live Set has 4 tracks."


def _seed_change_journal(tmp_path, monkeypatch: pytest.MonkeyPatch) -> LiveActionService:
    monkeypatch.setattr(live_receipt_journal, "JOURNAL_PATH", tmp_path / "receipts.jsonl")
    service = LiveActionService(SessionLive())
    for index in range(12):
        live_receipt_journal.record_receipt(
            {
                "schema": "kenn.ableton_action_receipt.v1",
                "receipt_id": f"receipt-{index}",
                "action": "set_volume",
                "status": "applied",
                "verified": True,
                "target": {"track_name": f"Track {index}", "parameter": "volume"},
                "before": round(index / 20, 2),
                "readback": round((index + 1) / 20, 2),
                "undo_payload": {"action": "set_volume"},
                "undo_available": index != 11,
                "timestamp": 1_700_000_000 + index,
            },
            session_id="history-test",
        )
    return service


def test_describe_recent_changes_is_newest_first_bounded_and_shows_undo_status(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = _seed_change_journal(tmp_path, monkeypatch)

    result = service.describe_recent_changes(limit=3)

    assert [item["receipt_id"] for item in result["changes"]] == ["receipt-11", "receipt-10", "receipt-9"]
    assert "Track 11" in result["answer"]
    assert "not undoable" in result["answer"]
    assert "undoable" in result["answer"]


def test_describe_recent_changes_handles_empty_journal(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(live_receipt_journal, "JOURNAL_PATH", tmp_path / "missing.jsonl")

    result = LiveActionService(SessionLive()).describe_recent_changes()

    assert result["status"] == "no_changes"
    assert result["changes"] == []
    assert "haven't made any changes" in result["answer"]


@pytest.mark.parametrize("question", ["What did you change?", "Show me the history", "Undo everything"])
def test_change_history_uses_command_path_without_reading_live(question: str, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = _seed_change_journal(tmp_path, monkeypatch)

    result = handle_command(question, session_id="history-test", service=service)

    assert result["status"] == "inspected"
    assert result["intent"] == {"action": "inspect_change_history"}
    assert result["answer_mode"] == "session_question"
    assert len(result["changes"]) == 10
    assert service.client.reads == 0
