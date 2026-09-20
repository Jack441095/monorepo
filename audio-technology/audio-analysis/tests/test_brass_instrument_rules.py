"""Brass got a dedicated instrument category 2026-07-13 (was mapped to
"strings" as a stopgap). Verifies brass gets its own distinct DSP treatment
end-to-end: classification, mix rules, priority, genre modifiers, sidechain
targeting, and natural-language mix-intent parsing."""

from __future__ import annotations

from audio_analysis.mixdown.stem_classifier import INSTRUMENT_TYPES, classify_from_filename
from audio_analysis.mixdown.mix_rules import (
    INSTRUMENT_PRIORITY,
    INSTRUMENT_RULES,
    get_rule_for_instrument,
)
from audio_analysis.analysis_core.sidechain_detection import _TARGET_INSTRUMENTS
from audio_analysis.integration.mix_intent import _parse_stem


def test_brass_is_a_real_instrument_type() -> None:
    assert "brass" in INSTRUMENT_TYPES


def test_brass_filenames_classify_as_brass_not_strings() -> None:
    for filename in ("horn_section.wav", "trumpet_01.wav", "trombone.wav", "sax.wav", "brass swell.wav"):
        instrument, confidence = classify_from_filename(filename)
        assert instrument == "brass", f"{filename} classified as {instrument!r}"
        assert confidence > 0.0


def test_brass_has_its_own_rule_distinct_from_strings() -> None:
    assert "brass" in INSTRUMENT_RULES
    brass_rule = INSTRUMENT_RULES["brass"]
    strings_rule = INSTRUMENT_RULES["strings"]

    # The whole point of the fix: brass must not silently inherit strings'
    # lush-pad treatment (no compression, very wide, long hall reverb).
    assert brass_rule["compression"] is not None
    assert brass_rule["stereo_width"] < strings_rule["stereo_width"]
    assert brass_rule["reverb_decay_s"] < strings_rule["reverb_decay_s"]


def test_get_rule_for_instrument_resolves_brass() -> None:
    rule = get_rule_for_instrument("brass")
    assert rule["compression"]["ratio"] == 2.5


def test_brass_has_a_masking_priority() -> None:
    assert "brass" in INSTRUMENT_PRIORITY
    # Brass should cut through like guitar/keys, not sit as far back as a pad.
    assert INSTRUMENT_PRIORITY["brass"] < INSTRUMENT_PRIORITY["synth_pad"]


def test_jazz_and_cinematic_genre_modifiers_cover_brass() -> None:
    from audio_analysis.mixdown.mix_rules import GENRE_MODIFIERS

    assert "brass" in GENRE_MODIFIERS["jazz"]
    assert "brass" in GENRE_MODIFIERS["cinematic"]


def test_brass_is_a_plausible_sidechain_target() -> None:
    assert "brass" in _TARGET_INSTRUMENTS


def test_mix_intent_recognizes_brass_keywords() -> None:
    assert _parse_stem("bring up the brass a little") == "brass"
    assert _parse_stem("the horns are too loud") == "brass"
    assert _parse_stem("mute the trumpet") == "brass"
