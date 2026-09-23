import pytest

from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_action_service import LiveActionService
from kenn.core.midi_clip_service import MidiClipActionService
from kenn.core.midi_generation_chat import generation_kind, propose_generated_clip


def _with_midi_track() -> tuple[FakeLiveBackend, LiveActionService]:
    live = FakeLiveBackend()
    live.create_midi_track()
    live.set_track_name(8, "Pads")
    return live, LiveActionService(live)


@pytest.mark.parametrize(
    ("text", "kind"),
    [("Write a 4-bar chord progression in D minor", "chords"), ("make a drum pattern", "drums"),
     ("Generate a bassline", "bassline"), ("What chords are in this song?", None), ("Pan the Synth left", None)],
)
def test_generation_kind_needs_a_creative_verb_and_a_known_idea(text: str, kind) -> None:
    assert generation_kind(text) == kind


def test_no_midi_track_is_explained_not_worked_around() -> None:
    result = propose_generated_clip("Write chords in D minor", session_id="g", service=LiveActionService(FakeLiveBackend()))
    assert result["status"] == "clarification_required" and "Create a MIDI track" in result["answer"]


def test_chords_use_the_stated_key_and_apply_with_readback_then_undo() -> None:
    live, service = _with_midi_track()
    result = propose_generated_clip("Write a 4-bar chord progression in D minor on the Pads track",
                                    session_id="g", service=service)
    assert result["status"] == "confirmation_required" and result["changed"] is False
    assert "D minor" in result["answer"] and result["generation"]["key"] == "D minor"
    assert live.get_midi_clip_state(8, 0)["has_clip"] is False
    proposal = result["proposal"]
    midi = MidiClipActionService(live)
    applied = midi.execute_create(proposal, confirm_token=proposal["confirmation_token"], session_id="g",
                                  idempotency_key="g-apply")
    assert applied["ok"] and applied["receipt"]["verified"] is True
    assert {n["pitch"] % 12 for n in live.get_midi_clip_state(8, 0)["notes"]} <= {2, 4, 5, 7, 9, 10, 0}
    undo = midi.propose_undo(applied["receipt"], session_id="g")
    assert undo["ok"]
    removed = midi.execute_remove(undo["proposal"], confirm_token=undo["proposal"]["confirmation_token"],
                                  session_id="g", idempotency_key="g-undo")
    assert removed["ok"] and live.get_midi_clip_state(8, 0)["has_clip"] is False


def test_key_falls_back_to_lives_scale_setting_and_slots_advance() -> None:
    live, service = _with_midi_track()
    first = propose_generated_clip("Generate a bassline", session_id="g", service=service)
    assert first["generation"]["key"] == "C major"  # the fixture's Live scale setting
    p = first["proposal"]
    MidiClipActionService(live).execute_create(p, confirm_token=p["confirmation_token"], session_id="g",
                                               idempotency_key="g-bass")
    second = propose_generated_clip("make a drum pattern", session_id="g", service=service)
    assert second["generation"]["key"] is None and "slot 2" in second["answer"]


def test_same_request_previews_exactly_the_same_notes() -> None:
    _live, service = _with_midi_track()
    a = propose_generated_clip("Write chords in A minor", session_id="g", service=service)
    b = propose_generated_clip("Write chords in A minor", session_id="g", service=service)
    assert a["generation"]["seed"] == b["generation"]["seed"]
    assert a["proposal"]["notes"] == b["proposal"]["notes"]
