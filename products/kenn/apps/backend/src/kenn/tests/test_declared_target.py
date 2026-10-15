"""The declared-target part of the grade: 30 points, every deduction tied to a figure and where it came from."""

from __future__ import annotations

import pytest

from kenn.core.declared_target import DECLARED_TARGET_POINTS, STREAMING_TARGETS, score_declared_target


def _part(result, name):
    return next(p for p in result["parts"] if p["part"] == name)


def test_a_master_on_the_spotify_target_gets_full_marks():
    result = score_declared_target(-14.0, -1.5, target="spotify")

    assert result["points"] == result["points_available"] == result["full_marks"] == 30.0
    assert result["unscored"] == []


def test_loudness_inside_one_lu_is_free_and_six_lu_off_loses_the_part():
    assert _part(score_declared_target(-14.9, -3.0, target="spotify"), "loudness")["points"] == 20.0
    assert _part(score_declared_target(-20.0, -3.0, target="spotify"), "loudness")["points"] == 0.0
    # Halfway between the 1 LU tolerance and the 6 LU full loss: 3.5 LU off loses half of the 20 points.
    assert _part(score_declared_target(-17.5, -3.0, target="spotify"), "loudness")["points"] == 10.0


def test_louder_than_the_spotify_target_gets_the_stricter_ceiling():
    # Spotify's page says a master above -14 LUFS should stay under -2 dBTP, so -1.5 dBTP passes at -14 but not at -12.
    quiet = _part(score_declared_target(-14.0, -1.5, target="spotify"), "true_peak_ceiling")
    loud = _part(score_declared_target(-12.0, -1.5, target="spotify"), "true_peak_ceiling")

    assert quiet["points"] == 10.0
    assert loud["points"] == 5.0 and loud["gap"] == 0.5


def test_a_peak_with_headroom_is_not_charged():
    part = _part(score_declared_target(-14.0, -9.0, target="spotify"), "true_peak_ceiling")

    assert part["points"] == 10.0 and part["gap"] < 0


def test_the_producers_stated_figures_override_the_named_target():
    result = score_declared_target(-9.0, -0.4, target="spotify", stated_lufs=-9.0, stated_ceiling_dbtp=-0.3)

    assert result["points"] == 30.0
    assert _part(result, "loudness")["source"] == "the loudness you stated"
    assert _part(result, "true_peak_ceiling")["source"] == "the ceiling you stated"


def test_no_target_still_checks_the_default_ceiling_but_not_loudness():
    result = score_declared_target(-14.0, -0.2)

    assert result["unscored"] == ["loudness"]
    assert result["points_available"] == 10.0
    assert _part(result, "true_peak_ceiling")["points"] == 2.0  # 0.8 dB over the -1 dBTP default loses 0.8 of the 10 points


def test_a_missing_reading_is_unscored_not_a_zero_or_a_pass():
    # 14 Oct 2026: the same rule as the mix audit; a meter that did not report cannot earn or lose points.
    result = score_declared_target(None, None, target="spotify")

    assert result["parts"] == [] and result["points"] == 0.0 and result["points_available"] == 0.0
    assert result["unscored"] == ["loudness", "true_peak_ceiling"]


def test_every_part_names_where_its_figure_came_from():
    for part in score_declared_target(-14.0, -1.5, target="aes_streaming_music")["parts"]:
        assert part["source"]


def test_an_unknown_target_name_is_an_error_not_a_silent_pass():
    with pytest.raises(KeyError):
        score_declared_target(-14.0, -1.0, target="spotfiy")


def test_the_parts_add_up_to_thirty():
    assert sum(DECLARED_TARGET_POINTS.values()) == 30.0
    assert set(STREAMING_TARGETS) == {"spotify", "aes_streaming_music"}


@pytest.mark.parametrize("invalid", [True, False, "-14", float("nan"), float("inf"), -float("inf"), 10 ** 1000])
@pytest.mark.parametrize("field", ["integrated_lufs", "true_peak_dbtp"])
def test_invalid_measured_levels_remove_only_their_target_points(field, invalid):
    # NaN passed through min/max as zero loss and previously earned full marks.
    readings = {"integrated_lufs": -14.0, "true_peak_dbtp": -1.5}
    readings[field] = invalid
    result = score_declared_target(**readings, target="spotify")
    missing = "loudness" if field == "integrated_lufs" else "true_peak_ceiling"
    remaining = 10.0 if field == "integrated_lufs" else 20.0
    assert result["unscored"] == [missing]
    assert result["points"] == result["points_available"] == remaining


@pytest.mark.parametrize("field", ["stated_lufs", "stated_ceiling_dbtp"])
@pytest.mark.parametrize("invalid", [True, "-14", float("nan"), float("inf"), 10 ** 1000])
def test_invalid_explicit_target_is_unscored_instead_of_replaced_with_named_default(field, invalid):
    result = score_declared_target(-14.0, -1.5, target="spotify", **{field: invalid})
    missing = "loudness" if field == "stated_lufs" else "true_peak_ceiling"
    assert result["unscored"] == [missing]
    assert result["points_available"] == (10.0 if field == "stated_lufs" else 20.0)
