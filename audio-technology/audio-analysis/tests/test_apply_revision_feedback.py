"""apply_revision_feedback() had zero test coverage despite being an
actively-used feedback-correction path (automix_worker.py calls it).
Written alongside a P4 refactor (2026-07-13, docs/automix_deep_scan_2026-07-12.md
§4.5) that deduplicated the up/down trigger-word tuple retyped 8 times
inline in this function -- these tests lock in the exact original behavior,
including the two categories (brightness, warmth) whose word lists are
deliberately NOT identical to the shared constant."""

from __future__ import annotations

from audio_analysis.mixdown.stem_classifier import StemProfile
from audio_analysis.mixdown.mix_decision_engine import generate_mix_plan, apply_revision_feedback


def _plan():
    profiles = [
        StemProfile(name="vocal.wav", instrument="vocal", peak_dbfs=-6.0, rms_dbfs=-18.0, crest_factor_db=12.0),
        StemProfile(name="bass.wav", instrument="bass", peak_dbfs=-8.0, rms_dbfs=-20.0, crest_factor_db=10.0),
        StemProfile(name="snare.wav", instrument="snare", peak_dbfs=-10.0, rms_dbfs=-22.0, crest_factor_db=14.0),
    ]
    return generate_mix_plan(profiles, genre="pop", target_lufs=-14.0)


def _gain(plan, instrument: str) -> float:
    return next(s.gain_db for s in plan.stems if s.instrument == instrument)


def test_vocal_up_boosts_by_2db():
    plan = _plan()
    before = _gain(plan, "vocal")
    apply_revision_feedback(plan, "make the vocals louder")
    assert _gain(plan, "vocal") == before + 1.5
    assert any("Vocal gain boosted by +1.5 dB" in line for line in plan.decisions_log)


def test_vocal_down_cuts_by_2db():
    plan = _plan()
    before = _gain(plan, "vocal")
    apply_revision_feedback(plan, "vocal needs to be quieter")
    assert _gain(plan, "vocal") == before - 1.5


def test_bass_up_boosts_by_1_5db():
    plan = _plan()
    before = _gain(plan, "bass")
    apply_revision_feedback(plan, "more bass please")
    assert _gain(plan, "bass") == before + 1.5


def test_drums_down_cuts_by_1_5db():
    plan = _plan()
    before = _gain(plan, "snare")
    apply_revision_feedback(plan, "less snare")
    assert _gain(plan, "snare") == before - 1.5


def test_brightness_up_adds_highshelf_boost():
    plan = _plan()
    apply_revision_feedback(plan, "add some brightness")
    band = plan.bus.bus_eq_bands[-1]
    assert band["type"] == "highshelf" and band["gain_db"] == 1.5


def test_brightness_down_adds_highshelf_cut():
    plan = _plan()
    apply_revision_feedback(plan, "too bright, cut it down")
    band = plan.bus.bus_eq_bands[-1]
    assert band["type"] == "highshelf" and band["gain_db"] == -1.5


def test_warmth_up_adds_peaking_boost():
    plan = _plan()
    apply_revision_feedback(plan, "make it warmer")
    band = plan.bus.bus_eq_bands[-1]
    assert band["type"] == "peaking" and band["frequency"] == 300.0 and band["gain_db"] == 1.5


def test_warmth_down_adds_peaking_cut():
    plan = _plan()
    apply_revision_feedback(plan, "too muddy, needs to be clearer")
    band = plan.bus.bus_eq_bands[-1]
    assert band["type"] == "peaking" and band["frequency"] == 300.0 and band["gain_db"] == -1.5


def test_warmth_ignores_loud_and_quiet_deliberately_unlike_other_categories():
    """Section 5's word list deliberately omits 'loud'/'quiet' (ambiguous
    for a warmth judgment) -- 'warm' alone must not also fire off of a
    generic loudness word that happens to co-occur."""
    plan = _plan()
    apply_revision_feedback(plan, "warm but not loud")  # "loud" must not force the up-branch here
    band = plan.bus.bus_eq_bands[-1]
    assert band["gain_db"] == 1.5  # took the up branch via "warm", not confused by "loud"


def test_multiple_categories_apply_from_one_feedback_string():
    # 2026-08-06 (D1.5): a compound comment now applies EVERY distinct
    # change it names, not just the first -- previously this asserted the
    # opposite ("bass louder too" was silently dropped), locked in as
    # documented, deliberate behavior at the time. See mix_intent.py's
    # parse_mix_intents()/apply_revision_feedback()'s own docstrings for
    # why that limitation was real and has now been closed.
    plan = _plan()
    before_vocal = _gain(plan, "vocal")
    before_bass = _gain(plan, "bass")
    apply_revision_feedback(plan, "vocals louder, bass louder too")
    assert _gain(plan, "vocal") == before_vocal + 1.5
    assert _gain(plan, "bass") == before_bass + 1.5


def test_no_match_logs_unmatched_feedback():
    plan = _plan()
    apply_revision_feedback(plan, "make it sound like a hit record")
    assert any("no automatic heuristics matched" in line for line in plan.decisions_log)


def _reverb(plan, instrument: str) -> float:
    return next(s.reverb_send for s in plan.stems if s.instrument == instrument)


class TestMagnitudeWords:
    def test_subtle_word_halves_the_step(self):
        plan = _plan()
        before = _gain(plan, "vocal")
        apply_revision_feedback(plan, "a little more vocal please")
        assert _gain(plan, "vocal") == before + 0.5  # subtle scale

    def test_strong_word_doubles_the_step(self):
        plan = _plan()
        before = _gain(plan, "vocal")
        apply_revision_feedback(plan, "a lot more vocal please")
        assert _gain(plan, "vocal") == before + 3.0  # strong scale

    def test_no_magnitude_word_stays_at_the_original_moderate_step(self):
        plan = _plan()
        before = _gain(plan, "vocal")
        apply_revision_feedback(plan, "vocals louder")
        assert _gain(plan, "vocal") == before + 1.5

    def test_magnitude_word_scales_bus_eq_steps_too(self):
        plan = _plan()
        apply_revision_feedback(plan, "a little more brightness please")
        band = plan.bus.bus_eq_bands[-1]
        assert band["gain_db"] == 0.5  # subtle scale


class TestReverbFeedback:
    def test_more_reverb_raises_send_on_every_stem(self):
        plan = _plan()
        before_vocal = _reverb(plan, "vocal")
        before_bass = _reverb(plan, "bass")
        apply_revision_feedback(plan, "more reverb please")
        assert _reverb(plan, "vocal") == round(before_vocal + 0.15, 3)
        assert _reverb(plan, "bass") == round(before_bass + 0.15, 3)

    def test_wetter_is_recognized_as_more_reverb(self):
        plan = _plan()
        before = _reverb(plan, "vocal")
        apply_revision_feedback(plan, "make it wetter")
        assert _reverb(plan, "vocal") == round(before + 0.15, 3)

    def test_drier_lowers_reverb_send(self):
        plan = _plan()
        for stem in plan.stems:
            stem.reverb_send = 0.3
        apply_revision_feedback(plan, "make it drier")
        assert _reverb(plan, "vocal") == round(0.3 - 0.15, 3)

    def test_reverb_send_is_clamped_at_zero(self):
        plan = _plan()
        for stem in plan.stems:
            stem.reverb_send = 0.02
        apply_revision_feedback(plan, "much less reverb")  # strong -> 3.0 * 0.1 = 0.3
        assert _reverb(plan, "vocal") == 0.0  # clamped, not negative

    def test_reverb_send_is_clamped_at_one(self):
        plan = _plan()
        for stem in plan.stems:
            stem.reverb_send = 0.95
        apply_revision_feedback(plan, "a lot more reverb")  # strong -> 3.0 * 0.1 = 0.3
        assert _reverb(plan, "vocal") == 1.0  # clamped, not above unity

    def test_stronger_reverb_feedback_is_logged(self):
        plan = _plan()
        apply_revision_feedback(plan, "give it much more reverb")
        assert any("reverb send" in line.lower() for line in plan.decisions_log)


def test_returns_the_applied_changes_list():
    plan = _plan()
    applied = apply_revision_feedback(plan, "vocals louder, bass louder too")
    assert isinstance(applied, list)
    # 2026-08-06 (D1.5): both distinct changes are now applied and logged.
    assert len(applied) == 2
    assert applied == plan.decisions_log[-2:]


def test_returns_a_single_applied_change_for_a_single_topic_comment():
    plan = _plan()
    applied = apply_revision_feedback(plan, "make the vocals louder")
    assert isinstance(applied, list)
    assert len(applied) == 1
    assert applied == plan.decisions_log[-1:]
