"""The combined E2 grade: parts add up, and what was not graded is named instead of rescaled."""

from kenn.core.declared_target import score_declared_target
from kenn.core.grade import combine_grade, grade_session, stated_target_from_text
from kenn.core.mix_doctor import MixDoctor


def _technical():
    meters = {"integrated_lufs": -14.0, "true_peak_dbtp": -1.5, "phase_correlation": 0.8,
              "spectral_energy": {"sub_20_60hz": 0.2, "low_mid_200_500hz": 0.2, "high_mid_2_6khz": 0.2, "air_10_20khz": 0.2}}
    return MixDoctor().audit_session({"tracks": []}, meters=meters).to_dict()


def test_without_a_reference_the_grade_is_out_of_sixty_and_says_so():
    declared = score_declared_target(-14.0, -1.5, target="spotify")
    grade = combine_grade(technical=_technical(), declared_target=declared)

    assert grade["points_available"] == 60.0 and grade["full_marks"] == 100.0
    assert grade["points"] <= 60.0  # never rescaled up toward 100
    assert [u["part"] for u in grade["ungraded"]] == ["reference_match"]
    assert "not graded: reference match (no reference track supplied)" in grade["meaning"]


def test_a_part_with_nothing_scorable_counts_as_not_graded():
    # An empty meter frame scores no technical-health dimensions that need a reading.
    empty = MixDoctor().audit_session({"tracks": []}, meters={}).to_dict()
    nothing_to_score = {"mqm_score": 0.0, "points_available": 0.0, "meaning": empty["meaning"]}
    grade = combine_grade(technical=nothing_to_score)

    assert grade["points_available"] == 0 and grade["points"] == 0
    assert {u["part"] for u in grade["ungraded"]} == {"technical_health", "declared_target", "reference_match"}


def test_the_parts_add_up_and_the_same_inputs_give_the_same_grade():
    reference = {"points": 31.5, "points_available": 35.0, "unscored": ["stereo_width"]}
    declared = score_declared_target(-9.0, -0.2, target="spotify")  # 5 LU loud and 0.8 dB over the ceiling
    first = combine_grade(technical=_technical(), declared_target=declared, reference_match=reference)
    second = combine_grade(technical=_technical(), declared_target=declared, reference_match=reference)

    assert first["points"] == round(sum(p["points"] for p in first["parts"]), 1)
    assert first["points_available"] == 30.0 + 30.0 + 35.0  # the reference part had 5 of its 40 left out
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
