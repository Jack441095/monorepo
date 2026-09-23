import pytest

from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_action_service import LiveActionService
from kenn.core.live_command import handle_command
from kenn.core.live_world_questions import answer_world_question


def _live() -> FakeLiveBackend:
    live = FakeLiveBackend()
    live.set_track_send(6, 0, 0.4)
    live.set_track_send(3, 0, 0.25)
    live.set_track_mute(2, True)
    return live


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("What's on the Lead Vocal track?", "'Lead Vocal' has: Compressor."),
        ("What's on the A-Reverb return?", "'A-Reverb' has: Reverb; Hybrid Reverb."),
        ("Which tracks send to the reverb?", "These tracks send to 'A-Reverb': Drum Bus (0.25), Lead Vocal (0.40)."),
        ("Which tracks send to the delay?", "No track sends to 'B-Delay' right now."),
        ("What's the threshold on the Drum Bus compressor?", "On 'Drum Bus' → Compressor: Threshold is 0.00 dB."),
        ("Is anything muted?", "Muted: Hi-Hats. Nothing is soloed."),
        ("What key is the song in?", "Live's scale setting is C Major."),
    ],
)
def test_world_questions_answer_from_the_model(question: str, expected: str) -> None:
    result = answer_world_question(question, _live())
    assert result["status"] == "inspected" and result["changed"] is False
    assert expected in result["answer"]
    assert result["backend"] == "fake" and len(result["world_model_fingerprint"]) == 64


def test_master_not_yet_readable_is_reported_not_guessed() -> None:
    result = answer_world_question("What's on the master?", _live())
    assert result["status"] == "unavailable" and "deploy_abletonosc.py" in result["answer"]


def test_ambiguous_name_asks_which_one() -> None:
    result = answer_world_question("What's on the drum track?", _live())
    assert result["status"] in {"inspected", "clarification_required"}
    assert "Drum Bus" in result["answer"]


@pytest.mark.parametrize("question", ["What is on track 4?", "Why does my mix sound muddy?", "Pan the Synth hard left."])
def test_other_messages_are_left_to_their_existing_routes(question: str) -> None:
    assert answer_world_question(question, _live()) is None


def test_world_questions_reach_the_command_path_read_only() -> None:
    live = _live()
    result = handle_command("Which tracks send to the reverb?", session_id="world-q", service=LiveActionService(live))
    assert result["changed"] is False and "Lead Vocal" in result["answer"]
    assert [w for w in live.writes if w[0] != "send" and w[0] != "mute"] == []
