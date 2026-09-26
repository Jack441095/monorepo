"""Named mix recipes: a clear mix intention becomes a small, exact, confirmable set of changes."""

from __future__ import annotations

import pytest

from kenn.core import volume_law
from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_action_service import LiveActionService
from kenn.core.live_command import handle_command


@pytest.fixture()
def ask(monkeypatch, tmp_path):
    from kenn.core import live_receipt_journal

    monkeypatch.setattr(live_receipt_journal, "JOURNAL_PATH", tmp_path / "receipts.jsonl")
    monkeypatch.setenv("KENN_ALLOW_DAW_CONTROL", "1")
    for name in ("KENN_LIVE_LLM_ENABLED", "KENN_LLM_ENABLED", "KENN_LLM_ENABLED_COMMAND"):
        monkeypatch.delenv(name, raising=False)
    return lambda text: handle_command(text, session_id=f"recipe-{tmp_path.name}", service=LiveActionService(FakeLiveBackend()))


def _steps(result):
    return result["proposal"]["steps"]


def _db_change(step):
    return volume_law.raw_to_db(step["after"]) - volume_law.raw_to_db(step["before"])


def test_room_for_the_kick_turns_the_bass_down_a_real_one_and_a_half_db(ask) -> None:
    for phrasing in ("make room for the kick", "the kick and bass are fighting"):
        (step,) = _steps(ask(phrasing))
        assert step["track_name"] == "Bass" and _db_change(step) == pytest.approx(-1.5, abs=0.05)


def test_vocal_space_sends_the_vocal_to_the_reverb_and_the_delay(ask) -> None:
    steps = _steps(ask("give the vocal some space"))
    assert {(s["return_track_name"], s["after"]) for s in steps} == {("A-Reverb", 0.15), ("B-Delay", 0.08)}


def test_drums_forward_lifts_the_drum_bus_and_never_past_zero(ask) -> None:
    (step,) = _steps(ask("bring the drums forward"))
    assert step["track_name"] == "Drum Bus" and _db_change(step) == pytest.approx(1.5, abs=0.05)
    assert volume_law.raw_to_db(step["after"]) <= 0.0


def test_an_already_centred_low_end_changes_nothing(ask) -> None:
    result = ask("make the low end mono")
    assert result["status"] == "clarification_required" and "already centred" in result["answer"]


def test_a_vague_volume_request_is_not_a_recipe(ask) -> None:
    # "too loud" names no amount: KENN asks, as the phrasing gate expects, rather than picking one.
    assert ask("the hats are too loud").get("proposal") is None
