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


@pytest.mark.parametrize(
    "question",
    [
        "What's your advice on drum bus compression?",
        "What's your take on the release on the Drum Bus?",
        "Any tips for the Lead Vocal track?",
    ],
)
def test_advice_that_names_a_track_goes_to_the_notes_not_the_inventory(question: str) -> None:
    # 5 Oct 2026 probe: the first of these got "'Drum Bus' has: Compressor." and the model was never asked.
    assert answer_world_question(question, _live()) is None


@pytest.mark.parametrize(
    "question",
    [
        # The exact probe row. Routed to the model since 3018af79; pinned through the session entry the chat uses.
        "What's your advice on drum bus compression?",
        "What's a good attack for the Drum Bus compressor?",
        "What's the best release for the drum bus compressor?",
        "What's the ideal ratio on the Drum Bus?",
        "What's the threshold I should use on the drum bus compressor?",
        # Re-review of 97de3829: other ways of asking for a good value that still read back the current one.
        "what's a good starting point for the drum bus compressor attack",
        "what's a decent ratio for the drum bus compressor",
        "what's the right threshold for the drum bus compressor",
        "what's a sensible ratio on the drum bus",
        "what's the optimal release for the drum bus compressor",
        "what's the threshold, and should I set it lower on the drum bus compressor?",
    ],
)
def test_asking_for_a_good_value_is_advice_not_the_current_value(question: str) -> None:
    # Probe row `followup-drums`, 5 Oct 2026: advice naming the Drum Bus was answered from the inventory. 3018af79
    # fixed "advice on"; "what's a good attack for the drum bus compressor?" still got "Attack is 1.00 ms." back.
    from kenn.core.live_session_questions import answer_live_session_question

    assert answer_live_session_question(question, service=LiveActionService(_live())) is None


@pytest.mark.parametrize(
    "question",
    [
        "Is anything muted that should not be?",
        "What's on the drum bus that should not be there?",
        "What's the threshold on the Drum Bus compressor? It should be around -20.",
        "What is the gain on the drum bus compressor, it sounds good",
        "Is the key right? What key is the song in, it should be C",
        # A trailing "I should ..." is the user's aside after the question, not a request for advice.
        "What's on the drum bus? I should set it up",
        "What key is the song in? I should put it in C",
        "What's the attack on the drum bus compressor, I should set it faster?",
        "What's the gain on the right side of the drum bus compressor?",
    ],
)
def test_a_should_or_good_inside_an_inspection_question_does_not_make_it_advice(question: str) -> None:
    # Review of 30782ed8: a bare "should"/"good" anywhere vetoed every question kind, so these stopped reading Live.
    from kenn.core.live_session_questions import answer_live_session_question

    result = answer_live_session_question(question, service=LiveActionService(_live()))
    assert result is not None and result["status"] == "inspected"


@pytest.mark.parametrize("track", ["Best Take", "Good Vocal", "Usual Suspects"])
def test_a_track_named_with_an_advice_word_still_reads_live(track: str) -> None:
    # Same review: the new advice words are only advice next to a parameter, not inside a track's name.
    from kenn.core.live_session_questions import answer_live_session_question

    live = _live()
    live.set_track_name(3, track)  # index 3 is the Drum Bus, the track with the Compressor
    result = answer_live_session_question(f"What's on the {track} track?", service=LiveActionService(live))
    assert result is not None and f"'{track}' has: Compressor." in result["answer"]


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("What's on the Drum Bus?", "'Drum Bus' has: Compressor."),
        ("What devices are on Drum Bus", "'Drum Bus' has: Compressor."),
        ("what is on the drum bus", "'Drum Bus' has: Compressor."),
        ("What's the attack on the drum bus compressor?", "Attack is 1.00 ms."),
        ("What's the current release on the Drum Bus compressor?", "Release is 30.0 ms"),
    ],
)
def test_inspection_questions_about_the_bus_still_read_live(question: str, expected: str) -> None:
    from kenn.core.live_session_questions import answer_live_session_question

    result = answer_live_session_question(question, service=LiveActionService(_live()))
    assert result["status"] == "inspected" and expected in result["answer"]


def test_world_questions_reach_the_command_path_read_only() -> None:
    live = _live()
    result = handle_command("Which tracks send to the reverb?", session_id="world-q", service=LiveActionService(live))
    assert result["changed"] is False and "Lead Vocal" in result["answer"]
    assert [w for w in live.writes if w[0] != "send" and w[0] != "mute"] == []


def test_a_parameter_question_on_a_track_named_with_an_advice_word_still_reads_live() -> None:
    # The wider word gap for "good starting point" must not reach across to a track name: "Best Vocal" sits after
    # the parameter here, so this is a value read, not advice.
    from kenn.core.live_session_questions import answer_live_session_question

    live = _live()
    live.set_track_name(3, "Best Vocal")
    result = answer_live_session_question("What's the output on the Best Vocal track?", service=LiveActionService(live))
    assert result is not None and result["intent"]["action"] == "inspect_parameter_value"
