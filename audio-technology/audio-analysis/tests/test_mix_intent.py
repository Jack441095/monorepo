"""Tests for integration/mix_intent.py's apply_intent_to_plan.

Had zero coverage before this. Written alongside a real bug fix: the
"width" parameter used to write its delta into reverb_send ("proxy for
width" per the old comment) instead of the actual stereo_width field --
meaning any caller that ever wired this up would have silently turned a
width request into a reverb change. Fixed to touch stereo_width directly;
these tests lock that in.
"""

from __future__ import annotations

from audio_analysis.integration.mix_intent import (
    apply_intent_to_plan,
    apply_intents_to_plan,
    describe_mix_intent,
    describe_mix_intents,
    parse_mix_intent,
    parse_mix_intents,
)
from audio_analysis.mixdown.stem_classifier import StemProfile
from audio_analysis.mixdown.mix_decision_engine import generate_mix_plan


def _plan():
    profiles = [
        StemProfile(name="vocal.wav", instrument="vocal", peak_dbfs=-6.0, rms_dbfs=-18.0, crest_factor_db=12.0),
        StemProfile(name="bass.wav", instrument="bass", peak_dbfs=-8.0, rms_dbfs=-20.0, crest_factor_db=10.0),
    ]
    return generate_mix_plan(profiles, genre="pop", target_lufs=-14.0)


def _stem(plan, instrument: str):
    return next(s for s in plan.stems if s.instrument == instrument)


def test_width_up_widens_stereo_width_not_reverb_send():
    plan = _plan()
    before_width = _stem(plan, "vocal").stereo_width
    before_reverb = _stem(plan, "vocal").reverb_send
    intent = {"target_stem": "vocal", "parameter": "width", "direction": "up", "magnitude": "moderate"}
    new_plan = apply_intent_to_plan(intent, plan)
    after = _stem(new_plan, "vocal")
    assert after.stereo_width > before_width
    assert after.reverb_send == before_reverb


def test_width_down_narrows_stereo_width():
    plan = _plan()
    # Force a known, mid-range starting width -- real per-instrument role
    # defaults (e.g. bass often starts near-mono) can already sit at/below
    # the floor clamp, which would make "narrower" clamp upward instead of
    # actually narrowing. This test is about the direction of the change,
    # not about any particular instrument's default.
    for stem in plan.stems:
        stem.stereo_width = 1.0
    intent = {"target_stem": "bass", "parameter": "width", "direction": "down", "magnitude": "moderate"}
    new_plan = apply_intent_to_plan(intent, plan)
    assert _stem(new_plan, "bass").stereo_width < 1.0


def test_width_is_clamped_between_0_3_and_2_0():
    plan = _plan()
    intent = {"target_stem": "vocal", "parameter": "width", "direction": "up", "magnitude": "strong"}
    for _ in range(20):
        plan = apply_intent_to_plan(intent, plan)
    assert _stem(plan, "vocal").stereo_width <= 2.0

    intent_down = {"target_stem": "vocal", "parameter": "width", "direction": "down", "magnitude": "strong"}
    for _ in range(20):
        plan = apply_intent_to_plan(intent_down, plan)
    assert _stem(plan, "vocal").stereo_width >= 0.3


def test_reverb_level_up_raises_reverb_send_only():
    plan = _plan()
    before_width = _stem(plan, "vocal").stereo_width
    before_reverb = _stem(plan, "vocal").reverb_send
    intent = {"target_stem": "vocal", "parameter": "reverb_level", "direction": "up", "magnitude": "moderate"}
    new_plan = apply_intent_to_plan(intent, plan)
    after = _stem(new_plan, "vocal")
    assert after.reverb_send > before_reverb
    assert after.stereo_width == before_width


def test_only_the_targeted_stem_changes():
    plan = _plan()
    before_bass_gain = _stem(plan, "bass").gain_db
    intent = {"target_stem": "vocal", "parameter": "gain_db", "direction": "up", "magnitude": "moderate"}
    new_plan = apply_intent_to_plan(intent, plan)
    assert _stem(new_plan, "vocal").gain_db > _stem(plan, "vocal").gain_db
    assert _stem(new_plan, "bass").gain_db == before_bass_gain


def test_parse_mix_intent_recognizes_wider_as_width_up():
    intent = parse_mix_intent("make the vocal wider", {})
    assert intent["parameter"] == "width"
    assert intent["direction"] == "up"


# --- describe_mix_intent -----------------------------------------------------
# Written for the KENN chat conversational-revision-explanation feature
# (business/app/ableton_bridge.py's _handle_mix_revision()) -- the plan's own
# example: "I'll boost the brightness highshelf EQ on the master bus by a
# moderate +1.5 dB adjustment." Each assertion below is checked against
# apply_intent_to_plan()'s real mapping (same file, just above), not
# independently invented numbers.


def test_describe_brightness_matches_the_plan_example():
    intent = {"target_stem": "all", "parameter": "brightness", "direction": "up", "magnitude": "moderate"}
    assert describe_mix_intent(intent) == (
        "boost the brightness highshelf EQ on the master bus by a moderate +1.5 dB adjustment"
    )


def test_describe_warmth_down():
    intent = {"target_stem": "all", "parameter": "warmth", "direction": "down", "magnitude": "subtle"}
    assert describe_mix_intent(intent) == (
        "cut the low-mid warmth EQ on the master bus by a subtle -0.5 dB adjustment"
    )


def test_describe_gain_db_names_the_target_stem():
    intent = {"target_stem": "vocal", "parameter": "gain_db", "direction": "up", "magnitude": "strong"}
    assert describe_mix_intent(intent) == "boost the overall level of vocal by a strong +3.0 dB adjustment"


def test_describe_gain_db_all_stems():
    intent = {"target_stem": "all", "parameter": "gain_db", "direction": "down", "magnitude": "moderate"}
    assert describe_mix_intent(intent) == "cut the overall level of all by a moderate -1.5 dB adjustment"


def test_describe_sub_gain_and_bass_gain_and_air_gain_use_their_real_frequencies():
    assert "60 Hz" in describe_mix_intent(
        {"target_stem": "bass", "parameter": "sub_gain", "direction": "up", "magnitude": "moderate"}
    )
    assert "120 Hz" in describe_mix_intent(
        {"target_stem": "bass", "parameter": "bass_gain", "direction": "up", "magnitude": "moderate"}
    )
    assert "10 kHz" in describe_mix_intent(
        {"target_stem": "vocal", "parameter": "air_gain", "direction": "up", "magnitude": "moderate"}
    )
    assert "3.5 kHz" in describe_mix_intent(
        {"target_stem": "vocal", "parameter": "presence_gain", "direction": "up", "magnitude": "moderate"}
    )


def test_describe_width_up_and_down():
    up = describe_mix_intent({"target_stem": "vocal", "parameter": "width", "direction": "up", "magnitude": "moderate"})
    down = describe_mix_intent({"target_stem": "vocal", "parameter": "width", "direction": "down", "magnitude": "moderate"})
    assert "widen" in up
    assert "narrow" in down


def test_describe_reverb_up_and_down():
    up = describe_mix_intent({"target_stem": "vocal", "parameter": "reverb_level", "direction": "up", "magnitude": "moderate"})
    down = describe_mix_intent({"target_stem": "vocal", "parameter": "reverb_level", "direction": "down", "magnitude": "moderate"})
    assert "add more" in up
    assert "pull back" in down


def test_describe_unrecognized_gives_an_honest_explanation_not_a_false_promise():
    """apply_intent_to_plan() treats "unrecognized" as a no-op -- the
    explanation must not claim a specific DSP change will happen when
    nothing will actually change."""
    intent = {"target_stem": "all", "parameter": "unrecognized", "direction": "up", "magnitude": "moderate"}
    description = describe_mix_intent(intent)
    assert "dB adjustment" not in description
    assert "couldn't pin down" in description.lower()


class TestMultiIntentParsing:
    """D1.5 (docs/KENN_FUTURE_PLAN.md Phase 1): a compound instruction
    ("make the vocal louder, add more reverb, and brighten it up") should
    produce one intent per distinct change, not just the first."""

    def test_two_distinct_stems_produce_two_intents(self):
        intents = parse_mix_intents("vocals louder, bass louder too", {})
        assert len(intents) == 2
        stems = {i["target_stem"] for i in intents}
        assert stems == {"vocal", "bass"}

    def test_three_distinct_topics_produce_three_intents(self):
        intents = parse_mix_intents("make the vocal louder, add more reverb, and brighten it up", {})
        parameters = [i["parameter"] for i in intents]
        assert "gain_db" in parameters
        assert "reverb_level" in parameters
        assert "brightness" in parameters
        assert len(intents) == 3

    def test_single_topic_instruction_produces_one_intent(self):
        intents = parse_mix_intents("make the vocals louder", {})
        assert len(intents) == 1
        assert intents[0]["target_stem"] == "vocal"

    def test_bare_direction_word_does_not_fragment_a_single_thought(self):
        # Real regression found building this: "too bright, cut it down" is
        # ONE instruction (reduce brightness), not two -- "cut it down" has
        # no topic word of its own, just an ambiguous bare direction word.
        intents = parse_mix_intents("too bright, cut it down", {})
        assert len(intents) == 1
        assert intents[0]["parameter"] == "brightness"
        assert intents[0]["direction"] == "down"

    def test_nothing_recognized_returns_empty_list(self):
        assert parse_mix_intents("make it sound like a hit record", {}) == []

    def test_empty_utterance_returns_empty_list(self):
        assert parse_mix_intents("", {}) == []
        assert parse_mix_intents("   ", {}) == []

    def test_duplicate_topic_mentions_are_deduplicated(self):
        intents = parse_mix_intents("boost the vocal, and boost the vocal more", {})
        assert len(intents) == 1

    def test_apply_intents_to_plan_applies_every_intent(self):
        plan = _plan()
        vocal_before = _stem(plan, "vocal").gain_db
        bass_before = _stem(plan, "bass").gain_db
        intents = [
            {"target_stem": "vocal", "parameter": "gain_db", "direction": "up", "magnitude": "moderate"},
            {"target_stem": "bass", "parameter": "gain_db", "direction": "down", "magnitude": "subtle"},
        ]
        new_plan = apply_intents_to_plan(intents, plan)
        assert _stem(new_plan, "vocal").gain_db == round(vocal_before + 1.5, 2)
        assert _stem(new_plan, "bass").gain_db == round(bass_before - 0.5, 2)

    def test_describe_mix_intents_joins_multiple_with_and(self):
        intents = [
            {"target_stem": "vocal", "parameter": "gain_db", "direction": "up", "magnitude": "moderate"},
            {"target_stem": "vocal", "parameter": "reverb_level", "direction": "up", "magnitude": "moderate"},
        ]
        description = describe_mix_intents(intents)
        assert ", and " in description

    def test_describe_mix_intents_single_matches_singular_form(self):
        intents = [{"target_stem": "vocal", "parameter": "gain_db", "direction": "up", "magnitude": "moderate"}]
        assert describe_mix_intents(intents) == describe_mix_intent(intents[0])

    def test_describe_mix_intents_empty_gives_honest_explanation(self):
        description = describe_mix_intents([])
        assert "couldn't pin down" in description.lower()
