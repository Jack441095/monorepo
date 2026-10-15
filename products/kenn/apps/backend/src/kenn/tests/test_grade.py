"""The combined E2 grade: parts add up, and what was not graded is named instead of rescaled."""

from copy import deepcopy

import pytest

from kenn.core.declared_target import score_declared_target
from kenn.core.grade import combine_grade, grade_session, stated_target_from_text
from kenn.core.local_mix_review_service import _grade_from_report
from kenn.core.mix_doctor import MixDoctor


def _technical():
    meters = {"integrated_lufs": -14.0, "true_peak_dbtp": -1.5, "phase_correlation": 0.8,
              "spectral_energy": {"sub_20_60hz": 0.2, "low_mid_200_500hz": 0.2, "high_mid_2_6khz": 0.2, "air_10_20khz": 0.2}}
    return MixDoctor().audit_session({"tracks": []}, meters=meters).to_dict()


def test_without_a_reference_the_grade_is_out_of_sixty_and_says_so():
    declared = score_declared_target(-14.0, -1.5, target="spotify")
    grade = combine_grade(technical=_technical(), declared_target=declared)

    assert grade["points_available"] == 54.0 and grade["full_marks"] == 100.0  # 24 technical (no stem score) + 30 target
    assert grade["points"] <= 54.0  # never rescaled up toward 100
    assert [u["part"] for u in grade["ungraded"]] == ["reference_match"]
    assert "not graded: reference match (no reference track supplied)" in grade["meaning"]


def test_a_part_with_nothing_scorable_counts_as_not_graded():
    # An empty meter frame scores no technical-health dimensions that need a reading.
    empty = MixDoctor().audit_session({"tracks": []}, meters={}).to_dict()
    nothing_to_score = {"mqm_score": 0.0, "points_available": 0.0, "meaning": empty["meaning"]}
    grade = combine_grade(technical=nothing_to_score)

    assert grade["points_available"] == 0 and grade["points"] == 0
    assert {u["part"] for u in grade["ungraded"]} == {"technical_health", "declared_target", "reference_match"}


def test_a_supplied_but_unavailable_reference_keeps_its_failure_reason():
    # "No reference supplied" hid analysis failures even though the producer had attached one.
    grade = combine_grade(reference_match={
        "points": 0.0, "points_available": 0.0, "note": "reference RMS at/below -60 dBFS",
    })

    reference = next(u for u in grade["ungraded"] if u["part"] == "reference_match")
    assert reference["reason"] == "reference RMS at/below -60 dBFS"
    assert "no reference track supplied" not in grade["meaning"]


def test_the_parts_add_up_and_the_same_inputs_give_the_same_grade():
    reference = {"points": 31.5, "points_available": 35.0, "unscored": ["stereo_width"]}
    declared = score_declared_target(-9.0, -0.2, target="spotify")  # 5 LU loud and 0.8 dB over the ceiling
    first = combine_grade(technical=_technical(), declared_target=declared, reference_match=reference)
    second = combine_grade(technical=_technical(), declared_target=declared, reference_match=reference)

    assert first["points"] == round(sum(p["points"] for p in first["parts"]), 1)
    assert first["points_available"] == 24.0 + 30.0 + 35.0  # stem separation is unscored; the reference part had 5 of 40 left out
    assert first == second
    assert first["parts"][2]["left_out"] == ["stereo_width"]
    assert first["ungraded"] == []


def test_a_target_the_producer_names_or_states_is_read_from_their_words():
    assert stated_target_from_text("audit this for Spotify") == {"target": "spotify"}
    assert stated_target_from_text("I'm aiming for -9.5 LUFS with a -0.5 dBTP ceiling") == {
        "stated_lufs": -9.5, "stated_ceiling_dbtp": -0.5,
    }
    assert stated_target_from_text("check the mix") == {}


def test_an_unsigned_figure_is_not_taken_as_a_stated_target():
    # "2 dBTP of headroom" and "a 3 LUFS boost" are not targets; both are negative in a real target.
    assert stated_target_from_text("leave 2 dBTP of headroom and give it a 3 LUFS boost") == {}


def test_a_session_grade_scores_the_default_ceiling_when_no_target_was_given():
    meters = {"integrated_lufs": -9.0, "true_peak_dbtp": -2.0}
    grade = grade_session(_technical(), meters, "check session")
    declared = next(p for p in grade["parts"] if p["part"] == "declared_target")

    assert declared["points_available"] == 10.0  # the ceiling part only; loudness had no target to score against
    assert declared["points"] == 10.0
    assert [u["part"] for u in grade["ungraded"]] == ["reference_match"]


def _file_report(layout):
    return {
        "metrics": {"rms_dbfs": -18.0, "integrated_lufs": -18.7, "true_peak_dbtp": -0.64, "crest_factor_db": 14.0,
                    "correlation_timeline": {"correlation": [1.0]}},
        "input_context": {"channel_layout": layout},
    }


def test_an_uploaded_file_is_graded_only_on_what_the_analyser_measured():
    grade = _grade_from_report(_file_report("stereo"))
    technical = next(p for p in grade["parts"] if p["part"] == "technical_health")

    # Dynamics and stereo image had readings (6 each). Low end, spectral balance and stem separation did not.
    assert technical["points_available"] == 12.0
    assert [u["part"] for u in grade["ungraded"]] == ["reference_match"]


def test_a_mono_files_placeholder_correlation_is_not_read_as_a_perfect_stereo_image():
    # The engine fills a mono file's timeline with 1.0; scoring it would give the stereo dimension free points.
    technical = next(p for p in _grade_from_report(_file_report("mono"))["parts"] if p["part"] == "technical_health")

    assert technical["points_available"] == 6.0


@pytest.mark.parametrize("rms", ["missing", None, True, float("nan"), float("inf"), -float("inf"), 10 ** 1000, -60.0, -60.01])
def test_an_unqualified_uploaded_source_has_no_grade_points(rms):
    report = _file_report("stereo")
    if rms == "missing":
        report["metrics"].pop("rms_dbfs")
    else:
        report["metrics"]["rms_dbfs"] = rms

    grade = _grade_from_report(report, reference_match={"points": 20.0, "points_available": 30.0})

    assert grade["points"] == 0.0
    assert grade["points_available"] == 0.0
    assert grade["parts"] == []
    assert {part["part"] for part in grade["ungraded"]} == {
        "technical_health", "declared_target", "reference_match",
    }


def test_an_uploaded_source_just_above_significance_floor_retains_its_grade():
    report = _file_report("stereo")
    report["metrics"]["rms_dbfs"] = -59.99

    grade = _grade_from_report(report)

    assert next(part for part in grade["parts"] if part["part"] == "technical_health")["points_available"] == 12.0


@pytest.mark.parametrize("part_name", ["technical_health", "declared_target", "reference_match"])
@pytest.mark.parametrize("points,available", [
    (float("nan"), 20.0), (20.0, float("inf")), (True, 20.0),
    (20.0, True), (-1.0, 20.0), (21.0, 20.0), (0.0, -1.0),
    (0.0, 41.0), (10 ** 1000, 20.0), (None, 20.0), ("20", 20.0),
])
def test_invalid_combined_part_is_withheld_without_clamping_or_erasing_other_parts(part_name, points, available):
    reference = {"points": 20.0, "points_available": 30.0}
    declared = score_declared_target(-14.0, -1.5, target="spotify")
    technical = _technical()
    parts = {"technical_health": technical, "declared_target": declared, "reference_match": reference}
    bad = parts[part_name]
    bad["mqm_score" if part_name == "technical_health" else "points"] = points
    bad["points_available"] = available
    before = deepcopy(parts)
    result = combine_grade(technical=technical, declared_target=declared, reference_match=reference)
    assert [part["part"] for part in result["ungraded"]] == [part_name]
    assert "invalid" in result["ungraded"][0]["reason"]
    assert {part["part"] for part in result["parts"]} == set(parts) - {part_name}
    assert result["points"] == round(sum(part["points"] for part in result["parts"]), 1)
    assert result["points_available"] == sum(part["points_available"] for part in result["parts"])
    assert parts == before


def _composed_session_grade(meters, request="aim for -14 LUFS and -1 dBTP", reference=None):
    technical = MixDoctor().audit_session({"tracks": []}, meters=meters).to_dict()
    return grade_session(technical, meters, request, reference)


def _parts_by_name(grade):
    return {part["part"]: part for part in grade["parts"]}


def test_composed_grade_moves_with_measured_peak_and_repeats_after_intervening_analysis():
    meters = {"integrated_lufs": -14.0, "true_peak_dbtp": -1.5, "phase_correlation": 0.8}
    reference = {"points": 25.0, "points_available": 35.0}
    original = deepcopy((meters, reference))
    first = _composed_session_grade(meters, reference=reference)
    changed = _composed_session_grade({**meters, "true_peak_dbtp": -0.1}, reference=reference)
    repeated = _composed_session_grade(meters, reference=reference)
    assert first == repeated
    assert changed["points"] < first["points"]
    assert changed["points_available"] == first["points_available"]
    before, after = _parts_by_name(first), _parts_by_name(changed)
    assert after["technical_health"]["points"] < before["technical_health"]["points"]
    assert after["declared_target"]["points"] < before["declared_target"]["points"]
    assert after["reference_match"] == before["reference_match"]
    assert (meters, reference) == original


def test_composed_target_change_moves_only_declared_part_and_does_not_stick():
    meters = {"integrated_lufs": -14.0, "true_peak_dbtp": -1.5, "phase_correlation": 0.8}
    first = _composed_session_grade(meters)
    changed = _composed_session_grade(meters, "aim for -20 LUFS and -1 dBTP")
    repeated = _composed_session_grade(meters)
    before, after = _parts_by_name(first), _parts_by_name(changed)
    assert repeated == first
    assert changed["points"] < first["points"]
    assert changed["points_available"] == first["points_available"]
    assert after["technical_health"] == before["technical_health"]
    assert after["declared_target"]["points"] == 10.0
    assert changed["ungraded"] == first["ungraded"]


def test_composed_missing_peak_removes_available_points_instead_of_rescaling():
    meters = {"integrated_lufs": -14.0, "true_peak_dbtp": -1.5, "phase_correlation": 0.8}
    full = _composed_session_grade(meters)
    missing = _composed_session_grade({**meters, "true_peak_dbtp": None})
    declared = _parts_by_name(missing)["declared_target"]
    assert declared["points"] == declared["points_available"] == 20.0
    assert declared["left_out"] == ["true_peak_ceiling"]
    assert missing["points_available"] < full["points_available"]
    assert missing["full_marks"] == full["full_marks"] == 100.0


@pytest.mark.parametrize("peak", [True, float("nan"), float("inf"), "-1.5"])
def test_session_grade_does_not_turn_invalid_peak_into_declared_ceiling_points(peak):
    grade = grade_session(_technical(), {"integrated_lufs": -14.0, "true_peak_dbtp": peak}, "Spotify")
    declared = _parts_by_name(grade)["declared_target"]
    assert declared["points"] == declared["points_available"] == 20.0
    assert declared["left_out"] == ["true_peak_ceiling"]
