"""Audio advice ends with one next step: a clean, reversible track command or a question, never a master change."""

from __future__ import annotations

from kenn.core.advice_next_step import next_step, next_step_line
from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_intent import parse_request

SET = FakeLiveBackend().query_session_state()
LOW_END = {"type": "possible_low_end_excess"}
CLIPPING = {"type": "clipping", "severity": "high"}
TRUE_PEAK = {"type": "true_peak_over_ceiling"}


def test_low_end_offers_a_small_fader_test_on_the_one_bass_track() -> None:
    step = next_step([CLIPPING, LOW_END], SET, scope="low_end")
    assert step == {"kind": "command", "say": "turn the Bass down 1 dB", "why": step["why"]}
    parsed = parse_request(step["say"], SET)  # what the tester says becomes an ordinary proposal
    assert parsed["action"] == "set_volume" and parsed["confirmation_required"] and not parsed["ambiguity"]
    assert "Undo" in step["why"]


def test_vocal_clipping_offers_the_vocal_fader_with_the_recording_caveat() -> None:
    step = next_step([CLIPPING, TRUE_PEAK], SET, scope="vocal")
    assert step["kind"] == "command" and step["say"] == "turn the Lead Vocal down 3 dB"
    assert "not in the recording" in step["why"]


def test_whole_mix_problems_are_questions_because_kenn_never_changes_the_master() -> None:
    assert next_step([CLIPPING], SET, scope="mix")["kind"] == "question"
    assert next_step([TRUE_PEAK], SET, scope="mix") == {
        "kind": "question", "say": "how do I keep my master under -1 dBTP?",
        "why": "True peak is set on the master limiter, which KENN doesn't change."}


def test_no_single_bass_track_means_a_question_not_a_guess() -> None:
    two_basses = {**SET, "tracks": [*SET["tracks"], {"index": 8, "name": "Sub Bass", "volume": 0.5}]}
    assert next_step([LOW_END], two_basses, scope="low_end")["kind"] == "question"
    assert next_step([LOW_END], {"tracks": []}, scope="low_end")["kind"] == "question"


def test_nothing_concrete_means_no_step() -> None:
    assert next_step([{"type": "possible_resonance"}], SET, scope="mix") is None
    assert next_step_line(None) == ""
    assert next_step_line(next_step([LOW_END], SET, scope="low_end")).startswith('Next step you can say: "turn the Bass')


def test_mix_review_gets_one_question_for_its_most_severe_mapped_flag() -> None:
    from kenn.core.advice_next_step import mix_review_next_step, with_mix_review_next_step

    review = {"flags": [
        {"fault_family": "loudness_estimate", "severity": "low", "label": "Loudness Estimate"},
        {"fault_family": "headroom", "severity": "medium", "label": "Headroom"},
        {"fault_family": "dc_offset", "severity": "high", "label": "DC Offset"},  # no checked question: skipped
    ]}
    assert mix_review_next_step(review)["say"] == "how do I keep my master under -1 dBTP?"
    annotated = with_mix_review_next_step(review)
    assert annotated["advice"][-1].startswith('Next, you could ask KENN: "how do I keep my master under -1 dBTP?"')
    assert "load the new file in Inputs" in annotated["advice"][-1]
    assert "advice" not in review  # the stored review is not changed
    assert with_mix_review_next_step({"flags": [{"fault_family": "dc_offset", "severity": "high"}]}) == {
        "flags": [{"fault_family": "dc_offset", "severity": "high"}]}
