"""Unit tests for kenn.core.arrangement_planner (D3.4,
docs/KENN_FUTURE_PLAN.md Phase 3)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "studio" / "kenn"))

from kenn.core.arrangement_planner import (  # noqa: E402
    describe_structure,
    parse_arrangement_request,
    suggest_song_structure,
)


def test_parse_arrangement_request_extracts_bars_and_build_up():
    result = parse_arrangement_request("build a 32-bar verse/chorus structure with a build-up at bar 17")
    assert result == {"total_bars": 32, "build_up_bar": 17}


def test_parse_arrangement_request_without_build_up():
    result = parse_arrangement_request("build a 16 bar arrangement")
    assert result == {"total_bars": 16, "build_up_bar": None}


def test_parse_arrangement_request_none_for_unrelated_text():
    assert parse_arrangement_request("how do I saturate sub bass?") is None


def test_parse_arrangement_request_none_for_bar_count_without_structure_word():
    # A bar count alone, with no structure/arrangement word, must not fire.
    assert parse_arrangement_request("this loop is 8 bars long") is None


def test_parse_arrangement_request_none_for_out_of_range_bar_counts():
    assert parse_arrangement_request("build a 2 bar structure") is None
    assert parse_arrangement_request("build a 9999 bar structure") is None


def test_parse_arrangement_request_ignores_out_of_range_build_up_bar():
    result = parse_arrangement_request("build a 16 bar structure with a build-up at bar 99")
    assert result == {"total_bars": 16, "build_up_bar": None}


def test_parse_arrangement_request_empty_text():
    assert parse_arrangement_request("") is None
    assert parse_arrangement_request(None) is None


def test_suggest_song_structure_with_build_up_uses_the_given_bar():
    sections = suggest_song_structure(32, build_up_bar=17)
    names = [s["name"] for s in sections]
    assert names == ["Groove", "Build-up", "Drop"]
    assert sections[0]["start_bar"] == 1
    assert sections[0]["length_bars"] == 16  # bars 1-16, build-up starts at 17
    assert sections[1]["start_bar"] == 17
    total_covered = sum(s["length_bars"] for s in sections)
    assert total_covered == 32


def test_suggest_song_structure_build_up_at_bar_one_has_no_groove():
    sections = suggest_song_structure(16, build_up_bar=1)
    assert sections[0]["name"] == "Build-up"
    assert sum(s["length_bars"] for s in sections) == 16


def test_suggest_song_structure_default_verse_chorus_split():
    sections = suggest_song_structure(32)
    names = [s["name"] for s in sections]
    assert names == ["Intro", "Verse", "Chorus", "Outro"]
    assert sum(s["length_bars"] for s in sections) == 32
    # Sections are contiguous with no gaps or overlaps.
    bar = 1
    for section in sections:
        assert section["start_bar"] == bar
        bar += section["length_bars"]


def test_suggest_song_structure_never_emits_a_nonpositive_length_section():
    for total_bars in (4, 5, 6, 7, 8, 10, 12, 16, 20, 32, 64, 128):
        sections = suggest_song_structure(total_bars)
        assert all(s["length_bars"] > 0 for s in sections)
        assert sum(s["length_bars"] for s in sections) == total_bars


def test_suggest_song_structure_very_short_request_degrades_gracefully():
    sections = suggest_song_structure(4)
    assert sum(s["length_bars"] for s in sections) == 4
    assert all(s["length_bars"] > 0 for s in sections)


def test_describe_structure_formats_bar_ranges():
    sections = [{"name": "Intro", "start_bar": 1, "length_bars": 4}, {"name": "Verse", "start_bar": 5, "length_bars": 12}]
    text = describe_structure(sections)
    assert "Intro: bars 1-4" in text
    assert "Verse: bars 5-16" in text
