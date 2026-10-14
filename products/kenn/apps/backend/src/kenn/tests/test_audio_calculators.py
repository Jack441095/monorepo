"""Computed figures producers ask for, checked against hand arithmetic.

Each expected value below was worked out separately (13 Oct 2026): 240 000 / 128 / 8 x 1.5 = 351.5625 ms;
512 / 48 000 = 10.667 ms; 69 + 12 log2(100 / 440) = 43.35, so 100 Hz is G2 and 35 cents sharp; 10^(-6/20) = 0.501.
"""

from __future__ import annotations

import pytest

from kenn.core import audio_calculators as calc


@pytest.mark.parametrize("question, expected", [
    ("What delay time is a dotted 1/8 at 128 BPM?", "At 128 BPM a dotted 1/8 note lasts 351.6 ms (about 352 ms)"),
    ("quarter note delay at 120 bpm", "At 120 BPM a 1/4 note lasts 500 ms (about 500 ms), which is 2 Hz as an LFO rate"),
    ("1/16 triplet at 140 BPM in ms?", "At 140 BPM a 1/16 triplet note lasts 71.4 ms"),
    ("set the echo to 1/8t at 90 bpm", "At 90 BPM a 1/8 triplet note lasts 222.2 ms"),
    ("eighth note dotted at 100 BPM", "At 100 BPM a dotted 1/8 note lasts 450 ms"),
])
def test_note_values_at_a_tempo_come_out_in_milliseconds(question, expected):
    assert expected in calc.calculated_facts(question)


def test_a_timing_question_without_a_note_value_gets_the_common_settings():
    facts = calc.tempo_facts("What pre-delay should I use at 128 BPM?")
    assert [fact.split(" lasts ")[0] for fact in facts] == [
        "At 128 BPM a 1/4 note", "At 128 BPM a 1/8 note", "At 128 BPM a dotted 1/8 note",
        "At 128 BPM a 1/8 triplet note", "At 128 BPM a 1/16 note",
    ]


def test_a_tempo_mentioned_in_passing_is_not_a_timing_question():
    assert calc.calculated_facts("My track is 128 BPM, how do I make the kick punchier?") == ""


@pytest.mark.parametrize("question, expected", [
    ("How much latency is 512 samples at 48 kHz?", "512 samples at 48 kHz is 10.67 ms"),
    ("buffer of 256 samples at 44100 Hz", "256 samples at 44.1 kHz is 5.8 ms"),
])
def test_a_buffer_size_comes_out_in_milliseconds(question, expected):
    assert expected in calc.calculated_facts(question)


def test_a_frequency_is_named_in_both_octave_conventions():
    facts = calc.calculated_facts("What note is 220 Hz?")
    assert "220 Hz is exactly A3 in scientific pitch (MIDI note 57), which Live's piano roll labels A2" in facts


def test_an_off_pitch_frequency_says_how_far_off_it_is():
    assert "100 Hz is 35 cents sharp of G2 in scientific pitch (MIDI note 43)" in calc.calculated_facts(
        "Which note is 100 Hz?")


def test_a_note_name_comes_out_as_a_frequency():
    assert "C4 is 261.63 Hz: C4 in scientific pitch (MIDI note 60), which Live's piano roll labels C3" in \
        calc.calculated_facts("What frequency is C4?")


@pytest.mark.parametrize("question, expected", [
    ("What is -6 dB as a ratio?", "-6 dB is a gain factor of 0.501 on amplitude (50.1%) and 0.251 on power"),
    ("+3 dB as a multiplier", "+3 dB is a gain factor of 1.413 on amplitude (141.3%) and 1.995 on power"),
    ("what is −12 dB in percent", "-12 dB is a gain factor of 0.251 on amplitude (25.1%)"),
])
def test_a_db_change_comes_out_as_a_gain_factor(question, expected):
    assert expected in calc.calculated_facts(question)


def test_doubling_the_level_gives_both_amplitude_and_power_and_no_loudness_claim():
    facts = calc.calculated_facts("How many dB is double the volume?")
    assert "+6.02 dB" in facts and "+3.01 dB" in facts
    assert "perception, not this arithmetic" in facts


def test_a_level_reading_is_not_mistaken_for_a_change():
    # -6 dBFS is a level on a meter, not a gain change, so it gets no gain-factor arithmetic.
    assert calc.calculated_facts("Is -6 dBFS a good ratio of peak to headroom?") == ""


def test_an_ordinary_question_gets_no_calculation():
    assert calc.calculated_facts("How do I make my vocals sit in the mix?") == ""
    assert calc.calculated_facts("") == ""



# Regressions found in review on 14 Oct 2026. A calculation is injected as a tool reading and the gate then accepts
# its figures anywhere in the answer, so a wrong or unrequested fact lets an invented figure through.

@pytest.mark.parametrize("question, expected, wrong", [
    ("reduce by 6 dB, what percent is that?", "-6 dB is a gain factor of 0.501 on amplitude (50.1%)", "+6 dB"),
    ("cut 3 dB, what's the multiplier?", "-3 dB is a gain factor of 0.708 on amplitude (70.8%)", "+3 dB"),
])
def test_a_cut_is_worked_out_as_a_reduction(question, expected, wrong):
    # 14 Oct 2026: an unsigned dB after "reduce" or "cut" was read as a boost, giving 199.5% for a 6 dB cut.
    facts = calc.calculated_facts(question)
    assert expected in facts
    assert wrong not in facts


def test_a_pad_is_a_cut():
    # 14 Oct 2026: "a 3 dB pad" had no sign and no cut word, so it got the boost factor, 141.3%.
    facts = calc.calculated_facts("what multiplier is a 3 dB pad?")
    assert "-3 dB is a gain factor of 0.708 on amplitude (70.8%)" in facts
    assert "141.3%" not in facts


@pytest.mark.parametrize("question", [
    "the 3 dB point of the filter, what percent is that?",
    "what percent is 3 dB?",
])
def test_an_unsigned_db_with_no_direction_gets_no_factor(question):
    # 14 Oct 2026: an unsigned dB with no direction word was worked out as a boost; which way it goes is a guess.
    assert calc.calculated_facts(question) == ""


@pytest.mark.parametrize("question, expected", [
    ("convert -3 dB to gain", "-3 dB is a gain factor of 0.708"),
    ("-6 dB as gain", "-6 dB is a gain factor of 0.501"),
    ("what gain is -6 dB?", "-6 dB is a gain factor of 0.501"),
    ("-6 dB gain factor", "-6 dB is a gain factor of 0.501"),
])
def test_gain_is_a_conversion_target(question, expected):
    assert expected in calc.calculated_facts(question)


@pytest.mark.parametrize("question", [
    "what hz is A4 at 432 tuning",
    "A=442, what frequency is C4?",
    "I'm tuned to 432 Hz, what note is 220 Hz?",
])
def test_a_stated_tuning_other_than_440_gets_no_pitch_figure(question):
    # 14 Oct 2026: "A4 at 432 tuning" was answered with 440 Hz, the default the producer had just ruled out.
    assert calc.calculated_facts(question) == ""


def test_a_stated_440_tuning_still_gets_its_pitch_figure():
    assert "C4 is 261.63 Hz" in calc.calculated_facts("At A=440, what frequency is C4?")


def test_how_many_hz_is_a_note_is_a_conversion_question():
    assert "A4 is 440 Hz" in calc.calculated_facts("How many Hz is A4?")


@pytest.mark.parametrize("question", [
    "Should I cut 200 Hz on the vocal? what pitch is the vocal",
    "what frequency should I cut, my sampler is an E-mu E4",
    "what frequency should I cut on the C4 model",
    "set ratio 4:1 and threshold -18 dB",
    "time signature 7/8 at 140 bpm",
])
def test_a_figure_mentioned_beside_an_unrelated_question_gets_no_calculation(question):
    # 14 Oct 2026: a trigger word anywhere in the question (pitch, frequency, ratio, time) converted any number
    # nearby, so a cut frequency became a note name and a compressor threshold became a gain factor.
    assert calc.calculated_facts(question) == ""


def test_half_time_is_not_a_half_note():
    # 14 Oct 2026: "half time feel" was read as a 1/2 note and given a delay figure nobody asked for.
    assert "1/2 note" not in calc.calculated_facts("128bpm half time feel, what release time")


@pytest.mark.parametrize("question, expected", [
    ("dotted 1/8 delay at 144 BPM", "At 144 BPM a dotted 1/8 note lasts 312.5 ms (about 313 ms)"),
    ("1/8T delay at 128 bpm", "At 128 BPM a 1/8 triplet note lasts 156.3 ms"),
])
def test_an_exact_half_rounds_up(question, expected):
    # 14 Oct 2026: Python's round-half-to-even printed 312.5 ms as "about 312" and 156.25 ms as 156.2 ms.
    assert expected in calc.calculated_facts(question)


def test_a_frequency_above_the_midi_range_gets_no_note():
    # 14 Oct 2026: 20 000 Hz was named as MIDI note 135, which no MIDI note or Live clip can hold (0-127).
    assert calc.calculated_facts("what note is 20000 Hz") == ""


# The answer path: calculations reach the model and the gate as tool readings, from the typed question only.
from kenn.core import chat_answer  # noqa: E402
from kenn.tests.test_payload_transient_cache import _model, cache_writes  # noqa: E402,F401 (pytest fixture)
from kenn.tests.test_streamed_generation_prefix_guard import ACCEPTED_ANSWER, QUERY  # noqa: E402

TEMPO_QUESTION = QUERY + " And how long is a dotted 1/8 at 128 BPM?"
TEMPO_ANSWER = ACCEPTED_ANSWER.replace(
    "so the bass recovers before the next kick.",
    "so the bass recovers before the next kick. At 128 BPM a dotted 1/8 lasts 351.6 ms.")


def test_a_computed_figure_in_the_answer_passes_the_gate(monkeypatch, cache_writes):  # noqa: F811
    _model(monkeypatch, TEMPO_ANSWER)

    payload = chat_answer.answer_payload(TEMPO_QUESTION)

    assert payload["llm_enhanced"] is True
    assert "351.6 ms" in payload["answer"]


def test_without_the_calculation_the_same_figure_is_refused(monkeypatch, cache_writes):  # noqa: F811
    # The contrast that shows the calculator is what lets the figure through: no note prints 351.6 ms.
    monkeypatch.setattr(chat_answer, "calculated_facts", lambda question: "")
    _model(monkeypatch, TEMPO_ANSWER)

    payload = chat_answer.answer_payload(TEMPO_QUESTION)

    # The gate's figure cut removes the sentence and keeps the rest, so the figure is what goes missing.
    assert "351.6 ms" not in payload["answer"]


def test_only_the_question_typed_this_turn_is_calculated():
    # A follow-up's search string carries the earlier turn; a tempo from it would answer a question nobody asked.
    evidence = chat_answer._tool_evidence("dotted 1/8 at 128 BPM delay snare", None, "and the snare?")
    assert "KENN calculation" not in evidence
    assert "351.6 ms" in chat_answer._tool_evidence("snare", None, "dotted 1/8 at 128 BPM?")
