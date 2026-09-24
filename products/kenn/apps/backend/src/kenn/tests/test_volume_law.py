"""Live's mixer fader law: measured table, provisional fallback, display parsing."""

from __future__ import annotations

import json
import math

import pytest

from kenn.core import volume_law


@pytest.fixture
def table(tmp_path, monkeypatch):
    """Point volume_law at a temporary table file and reload it per test."""
    path = tmp_path / "live_volume_law.json"
    monkeypatch.setattr(volume_law, "TABLE_PATH", path)
    volume_law.law.cache_clear()
    yield path
    volume_law.law.cache_clear()


def test_without_a_measured_table_the_provisional_law_is_flagged(table) -> None:
    law = volume_law.law()
    assert law.measured is False and "provisional" in law.source
    assert volume_law.db_to_raw(0.0) == pytest.approx(0.85)
    assert volume_law.db_to_raw(6.0) == pytest.approx(1.0)
    assert volume_law.db_to_raw(-6.0) == pytest.approx(0.7)
    assert volume_law.db_to_raw(-5.0) == pytest.approx(0.725)  # between measured points


def test_a_measured_table_replaces_the_provisional_law(table) -> None:
    table.write_text(json.dumps({"live_version": "12.4.6", "measured_at": "2026-09-24",
                                 "points": [[0.1, -40.0], [0.5, -10.0], [0.8, 0.0], [1.0, 6.0]]}))
    law = volume_law.law()
    assert law.measured is True and "12.4.6" in law.source
    assert volume_law.db_to_raw(0.0) == pytest.approx(0.8)
    assert volume_law.db_to_raw(-5.0) == pytest.approx(0.65)
    assert volume_law.raw_to_db(0.65) == pytest.approx(-5.0)


def test_an_unusable_table_falls_back_to_the_provisional_law(table) -> None:
    table.write_text(json.dumps({"points": [[0.5, -10.0], [0.4, -12.0]]}))  # not ascending
    assert volume_law.law().measured is False


def test_levels_outside_the_table_are_refused_not_clamped(table) -> None:
    assert volume_law.db_to_raw(7.0) is None
    assert volume_law.db_to_raw(-80.0) is None
    assert volume_law.db_to_raw(math.nan) is None
    assert volume_law.raw_to_db(0.0) == -math.inf
    assert volume_law.raw_to_db(0.01) is None


def test_round_trip_through_the_law(table) -> None:
    for db in (-40.0, -18.0, -6.5, -1.0, 0.0, 3.0):
        assert volume_law.raw_to_db(volume_law.db_to_raw(db)) == pytest.approx(db, abs=1e-4)


@pytest.mark.parametrize("text, value", [
    ("-6.0 dB", -6.0), ("0.0 dB", 0.0), ("6.0 dB", 6.0), ("+2.5 dB", 2.5), ("-inf dB", -math.inf), ("50 %", None),
])
def test_parse_live_display(text, value) -> None:
    assert volume_law.parse_db(text) == value


def test_clean_points_takes_the_middle_of_each_display_run() -> None:
    samples = [(0.0, "-inf dB"), (0.10, "-40.0 dB"), (0.11, "-40.0 dB"), (0.12, "-39.9 dB"),
               (0.84, "-0.1 dB"), (0.85, "0.0 dB"), (0.86, "0.0 dB"), (1.0, "6.0 dB")]
    assert volume_law.clean_points(samples) == [(0.105, -40.0), (0.12, -39.9), (0.84, -0.1), (0.855, 0.0), (1.0, 6.0)]
