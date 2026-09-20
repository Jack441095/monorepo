"""Tests for kenn.core.track_relevance (item 1,
docs/KENN_WEEKLY_OPTIMIZATION_PLAN_2026-08-08.md)."""

from __future__ import annotations

from kenn.core.track_relevance import relevant_tracks

TRACKS = [
    {"name": "Vocals", "volume": 0.8},
    {"name": "Drums", "volume": 0.7},
    {"name": "Bass", "volume": 0.75},
]


def test_matches_a_named_track():
    result = relevant_tracks("what's the volume on my vocals track", TRACKS)
    assert result == [TRACKS[0]]


def test_matches_a_track_name_substring():
    # "vocal" (query word) is a substring of "Vocals" (track name).
    result = relevant_tracks("why does the vocal sound buried", TRACKS)
    assert result == [TRACKS[0]]


def test_matches_multiple_named_tracks():
    result = relevant_tracks("compare vocals and bass levels", TRACKS)
    assert result == [TRACKS[0], TRACKS[2]]


def test_falls_back_to_none_when_nothing_matches():
    assert relevant_tracks("show my whole session", TRACKS) is None


def test_falls_back_to_none_when_every_track_matches():
    # No actual narrowing benefit if the filter would just return everything.
    result = relevant_tracks("vocals drums bass all sound off", TRACKS)
    assert result is None


def test_falls_back_to_none_with_no_tracks():
    assert relevant_tracks("show my vocals", []) is None


def test_falls_back_to_none_with_short_query_words_only():
    # Words under 3 chars are ignored to avoid noisy matches (e.g. "on",
    # "my") accidentally substring-matching a track name.
    assert relevant_tracks("is it ok", TRACKS) is None


def test_never_returns_an_empty_list():
    # Under-filtering (show everything) is the safe failure mode, not
    # over-filtering (hide a track by returning an empty match list).
    result = relevant_tracks("xyz nonexistent track name", TRACKS)
    assert result is None
