"""Follow-ups repeat the last whole-track change on another track ("do that on the snare too")."""

from __future__ import annotations

import pytest

from kenn.core import volume_law
from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_action_service import LiveActionService
from kenn.core.live_command import handle_command


@pytest.fixture()
def say(monkeypatch, tmp_path):
    from kenn.core import live_receipt_journal

    monkeypatch.setattr(live_receipt_journal, "JOURNAL_PATH", tmp_path / "receipts.jsonl")
    monkeypatch.setenv("KENN_ALLOW_DAW_CONTROL", "1")
    for name in ("KENN_LIVE_LLM_ENABLED", "KENN_LLM_ENABLED", "KENN_LLM_ENABLED_COMMAND"):
        monkeypatch.delenv(name, raising=False)
    service = LiveActionService(FakeLiveBackend())
    session = f"follow-up-{tmp_path.name}"
    return lambda command: handle_command(command, session_id=session, service=service)


def _after_db(result) -> float:
    return volume_law.raw_to_db(result["proposal"]["after"])


def test_a_relative_change_repeats_from_the_new_tracks_own_level(say) -> None:
    say("Bring the bass down 2 dB")
    for follow_up, track in [("do that on the snare too", "Snare / Clap"), ("same for the hats", "Hi-Hats"),
                             ("and the synth", "Synth"), ("now the vocal", "Lead Vocal")]:
        result = say(follow_up)
        assert result["status"] == "confirmation_required" and result["proposal"]["track_name"] == track
        before = volume_law.raw_to_db(result["proposal"]["before"])
        assert _after_db(result) == pytest.approx(before - 2.0, abs=0.05)


def test_that_is_not_rewritten_into_the_previous_track(say) -> None:
    # Regression: "do that on the snare too" once became "do Bass on the snare too" and lowered the Bass again.
    say("Bring the bass down 2 dB")
    assert say("do that on the snare too")["proposal"]["track_name"] == "Snare / Clap"


def test_the_opposite_flips_the_change(say) -> None:
    say("pan the synth 20% left")
    result = say("do the opposite on the vocal")
    assert result["proposal"]["track_name"] == "Lead Vocal" and result["proposal"]["after"] == pytest.approx(0.2)
    say("mute the hats")
    assert say("and the kick too")["proposal"]["after"] is True


@pytest.mark.parametrize("follow_up", ["do that on the bass too", "do that on the snare and the kick"])
def test_the_same_track_or_two_tracks_ask_instead(say, follow_up) -> None:
    say("Bring the bass down 2 dB")
    assert say(follow_up)["status"] == "clarification_required"


def test_a_follow_up_with_nothing_before_it_asks(say) -> None:
    assert say("same for the hats")["status"] == "clarification_required"


@pytest.mark.parametrize("question, reply, track, after", [
    ("make the bass louder", "3 dB", "Bass", volume_law.db_to_raw(volume_law.raw_to_db(0.5) + 3)),
    ("make the bass louder", "by 3", "Bass", volume_law.db_to_raw(volume_law.raw_to_db(0.5) + 3)),
    ("pan the synth left", "30%", "Synth", -0.3),       # regression: this once panned 30% right
    ("pan the synth left", "hard", "Synth", -1.0),
    ("pan the synth 20%", "left", "Synth", -0.2),
    ("kick -3 dB", "at -3", "Kick", volume_law.db_to_raw(-3.0)),
    ("kick -3 dB", "3 dB quieter", "Kick", volume_law.db_to_raw(volume_law.raw_to_db(0.5) - 3)),
    ("mute", "the hats", "Hi-Hats", True),
])
def test_a_short_reply_finishes_the_request_kenn_asked_about(say, question, reply, track, after) -> None:
    assert say(question)["status"] == "clarification_required"
    result = say(reply)
    assert result["status"] == "confirmation_required" and result["proposal"]["track_name"] == track
    assert result["proposal"]["after"] == pytest.approx(after, abs=1e-3)


def test_a_reply_is_not_joined_to_a_generic_not_sure(say) -> None:
    assert say("fix the mix")["status"] == "clarification_required"
    assert say("3 dB")["status"] == "clarification_required"
