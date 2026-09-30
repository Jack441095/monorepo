"""Round 6 of the blind check: hedged requests, tracks named by number or "called", chained requests, "X on"."""

from __future__ import annotations

import pytest

from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_action_service import LiveActionService
from kenn.core.live_command import handle_command


@pytest.fixture()
def say(monkeypatch, tmp_path, request):
    from kenn.core import live_receipt_journal

    monkeypatch.setattr(live_receipt_journal, "JOURNAL_PATH", tmp_path / "receipts.jsonl")
    monkeypatch.setenv("KENN_ALLOW_DAW_CONTROL", "1")
    for name in ("KENN_LIVE_LLM_ENABLED", "KENN_LLM_ENABLED", "KENN_LLM_ENABLED_COMMAND"):
        monkeypatch.delenv(name, raising=False)
    backend = FakeLiveBackend()
    service = LiveActionService(backend)
    say = lambda text: handle_command(text, session_id=f"round6-{request.node.name}", service=service, allow_llm=False)   # noqa: E731
    say.backend = backend
    return say


def steps(result):
    return [(step["action"], step["track_name"], step["after"]) for step in result["proposal"]["steps"]]


@pytest.mark.parametrize("text, action, track", [
    ("would you mind muting the hats", "set_mute", "Hi-Hats"),
    ("do you think you could bring the bass up 2 dB", "set_volume", "Bass"),
    ("any chance you could pull the kick down a couple dB", "set_volume", "Kick"),
    ("I was wondering if you could solo the bass", "set_solo", "Bass"),
    ("sorry to bother you, could you arm the vocal track", "set_arm", "Lead Vocal"),
    ("just a thought, maybe mute the clap", "set_mute", "Snare / Clap"),
    ("it'd be great if the synth were at -10", "set_volume", "Synth"),
])
def test_a_hedged_request_is_still_the_request(say, text, action, track) -> None:
    result = say(text)
    assert result["status"] == "confirmation_required" and result["proposal"]["action"] == action and result["proposal"]["track_name"] == track


@pytest.mark.parametrize("text", ["perhaps the vocal could be louder", "maybe the drums", "would you mind the hats"])
def test_a_hedge_with_no_request_in_it_still_asks(say, text) -> None:
    assert say(text)["status"] == "clarification_required"


@pytest.mark.parametrize("text, track", [("switch to track 2", "Snare / Clap"), ("go to track 2", "Snare / Clap"),
                                         ("focus the track called Snare", "Snare / Clap"), ("select the track called Bass", "Bass"),
                                         ("switch to the snare", "Snare / Clap")])
def test_moving_to_a_track_by_number_or_name(say, text, track) -> None:
    result = say(text)
    assert result["status"] == "confirmation_required" and result["proposal"]["action"] == "focus_track" and result["proposal"]["track_name"] == track


def test_the_name_after_called_is_not_swallowed_when_making_a_track(say) -> None:
    # "add a midi track called Keys" must keep "called": only focus/select/mute-style requests drop "track called".
    result = say("add a midi channel called Keys")
    assert result["proposal"]["action"] == "create_midi_track" and result["proposal"]["new_track_name"] == "Keys"
    assert say("create a new audio channel")["proposal"]["action"] == "create_audio_track"


def test_two_tracks_by_number_are_one_recipe(say) -> None:
    assert steps(say("mute tracks 1 and 2")) == [("set_mute", "Kick", True), ("set_mute", "Snare / Clap", True)]
    assert say("mute track 12")["status"] == "clarification_required"


def test_then_pan_it_means_the_track_just_named(say) -> None:
    result = say("solo the bass, then pan it 10% right")
    assert steps(result) == [("set_solo", "Bass", True), ("set_pan", "Bass", pytest.approx(0.1))]


def test_kick_n_bass_is_kick_and_bass(say) -> None:
    assert steps(say("solo kick n bass")) == [("set_solo", "Kick", True), ("set_solo", "Bass", True)]


@pytest.mark.parametrize("text", ["give me the bass by itself", "let me hear the bass by itself", "give me the bass on its own"])
def test_by_itself_means_solo(say, text) -> None:
    result = say(text)
    assert result["proposal"]["action"] == "set_solo" and result["proposal"]["track_name"] == "Bass" and result["proposal"]["after"] is True


def test_rec_ready_arms_the_track(say) -> None:
    result = say("vox rec ready")
    assert result["proposal"]["action"] == "set_arm" and result["proposal"]["track_name"] == "Lead Vocal"


@pytest.mark.parametrize("text", ["hats on", "turn the hats on", "turn hats on"])
def test_a_muted_track_can_be_turned_on(say, text) -> None:
    say.backend.set_track_mute(2, True)
    result = say(text)
    assert result["proposal"]["action"] == "set_mute" and result["proposal"]["track_name"] == "Hi-Hats" and result["proposal"]["after"] is False


@pytest.mark.parametrize("text", ["metronome on", "turn the reverb on", "click on", "turn it on"])
def test_on_for_something_that_is_not_a_track_changes_nothing(say, text) -> None:
    assert say(text)["status"] == "clarification_required"


@pytest.mark.parametrize("text", ["solo the sixth one", "call the bass Sub Bass", "solo the track with the EQ Eight"])
def test_forms_that_could_pick_the_wrong_track_still_ask(say, text) -> None:
    # "the sixth one" can mean the sixth option KENN just listed; the others have no clear boundary or name a device.
    assert say(text)["status"] == "clarification_required"
