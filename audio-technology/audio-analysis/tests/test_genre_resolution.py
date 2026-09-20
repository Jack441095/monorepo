"""Tests for genre alias resolution (AUDIO_SOFTWARE_IMPROVEMENT_PLAN §3).

Unrecognized genres used to silently render as 'pop'. `resolve_genre` now (a)
maps unambiguous synonyms to the right supported profile and (b) returns a note
so any fallback/alias is recorded in the mix decision log rather than being
silent.
"""

from __future__ import annotations

from audio_analysis.mixdown.mix_decision_engine import (
    GENRE_MODIFIERS,
    resolve_genre,
)


def test_exact_supported_genre_passes_through_without_note():
    resolved, note = resolve_genre("edm")
    assert resolved == "edm"
    assert note == ""


def test_case_and_whitespace_insensitive():
    resolved, note = resolve_genre("  EDM ")
    assert resolved == "edm"
    assert note == ""


def test_known_aliases_map_to_supported_profiles():
    for alias, expected in (("electronic", "edm"), ("rap", "hip_hop"),
                            ("hip hop", "hip_hop"), ("classical", "cinematic"),
                            ("metal", "rock"), ("folk", "acoustic")):
        resolved, note = resolve_genre(alias)
        assert resolved == expected, f"{alias} -> {resolved}, expected {expected}"
        assert resolved in GENRE_MODIFIERS
        assert note, "an alias resolution must record a note"


def test_unknown_genre_falls_back_to_pop_with_note():
    resolved, note = resolve_genre("synthwave")
    assert resolved == "pop"
    assert "not recognized" in note
    assert "synthwave" in note


def test_empty_genre_falls_back_with_note():
    resolved, note = resolve_genre("")
    assert resolved == "pop"
    assert note  # non-silent


def test_all_alias_targets_are_valid_profiles():
    from audio_analysis.mixdown.mix_decision_engine import GENRE_ALIASES

    for target in set(GENRE_ALIASES.values()):
        assert target in GENRE_MODIFIERS, f"alias target {target} is not a supported genre"
