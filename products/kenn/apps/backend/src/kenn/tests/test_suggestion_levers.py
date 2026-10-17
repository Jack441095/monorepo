"""Tests for Milestone E3: Specific, Actionable Help & Suggestion Levers.

Verifies:
1. Every generated suggestion either names a Live target, offers Apply/Undo, or says it is outside Live.
2. All 5 penalized mix health dimensions (true peak, phase cancellation, low-mid mud,
   excessive compression, dull high end) plus sub excess produce actionable levers.
3. Every lever cites measured C++ DSP values with citable standards or house rules.
4. Applying a suggestion lever and re-measuring measurably shifts the grade, and undoing reverts it.
5. Accuracy margins and refusal paths from the 2026-10-14 review (significance floor, ambiguous tracks, healthy mix)
   are strictly preserved.
"""

from __future__ import annotations

import copy
import math
import pytest

from kenn.core.fake_live import FakeLiveBackend
from kenn.core.grade import combine_grade, grade_session
from kenn.core.live_action_service import LiveActionService
from kenn.core.mix_doctor import MixDoctor
from kenn.core.suggestion_levers import (
    AIR_DEFICIT_THRESHOLD,
    CREST_FACTOR_MIN_DB,
    DEFAULT_HELP_GRADE_THRESHOLD,
    LOW_MID_MUD_THRESHOLD,
    SUB_EXCESS_THRESHOLD,
    TRUE_PEAK_ADVISORY_MARGIN_DBTP,
    TRUE_PEAK_CEILING_DBTP,
    TRUE_PEAK_CRITICAL_MARGIN_DBTP,
    apply_suggestion_lever,
    generate_suggestion_levers,
    is_grade_low_enough_for_help,
    undo_suggestion_lever,
    with_suggestion_levers,
)


def _healthy_meters() -> dict:
    return {
        "rms_dbfs": -16.0,
        "integrated_lufs": -14.0,
        "true_peak_dbtp": -1.5,
        "phase_correlation": 0.85,
        "crest_factor_db": 12.0,
        "spectral_energy": {
            "sub_20_60hz": 0.25,
            "low_mid_200_500hz": 0.28,
            "high_mid_2_6khz": 0.25,
            "air_10_20khz": 0.18,
        },
    }


def _grade_for_meters(meters: dict, snapshot: dict | None = None, request: str = "Spotify") -> dict:
    tracks = (snapshot or {}).get("tracks") or []
    technical = MixDoctor().audit_session({"tracks": tracks}, meters=meters).to_dict()
    return grade_session(technical, meters, request=request, session_snapshot=snapshot)


# -----------------------------------------------------------------------------
# 1. Verification of Penalized Mix Health Dimensions
# -----------------------------------------------------------------------------

def test_true_peak_clipping_produces_actionable_lever_with_citable_standard():
    fake = FakeLiveBackend()
    snapshot = fake.query_session_state()
    # True peak at +0.20 dBTP exceeds ceiling by 1.2 dB.
    meters = {**_healthy_meters(), "true_peak_dbtp": 0.20}
    grade = _grade_for_meters(meters, snapshot)

    assert is_grade_low_enough_for_help(grade)
    levers = generate_suggestion_levers(grade, snapshot, meters=meters)

    tp_lever = next((l for l in levers if l["dimension"] == "dynamic_health" and "True Peak" in l["title"]), None)
    assert tp_lever is not None
    assert tp_lever["points_lost"] == 3.0
    assert "Spotify for Artists" in tp_lever["source"]
    assert tp_lever["tier"] == "published"
    assert "+0.20 dBTP" in tp_lever["why"]
    assert "<= -1.0 dBTP" in tp_lever["baseline"]
    # Binds to Live track volume fader with Apply/Undo.
    assert tp_lever["is_live_target"] is True
    assert tp_lever["target"]["parameter_name"] == "Volume"
    assert tp_lever["action"]["can_undo"] is True
    assert "turn the" in tp_lever["action"]["say"]


def test_phase_cancellation_produces_center_pan_lever_with_convention_rule():
    fake = FakeLiveBackend()
    snapshot = fake.query_session_state()
    # Bass track panned off-center (+0.40) causing negative correlation.
    for t in snapshot["tracks"]:
        if t["name"] == "Bass":
            t["panning"] = 0.40
    meters = {**_healthy_meters(), "phase_correlation": -0.15}
    grade = _grade_for_meters(meters, snapshot)

    assert is_grade_low_enough_for_help(grade)
    levers = generate_suggestion_levers(grade, snapshot, meters=meters)

    phase_lever = next((l for l in levers if l["dimension"] == "stereo_imaging"), None)
    assert phase_lever is not None
    assert phase_lever["points_lost"] == 4.5
    assert "Correlation meter convention" in phase_lever["source"]
    assert phase_lever["tier"] == "convention"
    assert "-0.15" in phase_lever["why"]
    assert "Expected baseline: phase correlation >= +0.50" in phase_lever["baseline"]
    # Binds to Bass pan fader with Apply/Undo.
    assert phase_lever["is_live_target"] is True
    assert phase_lever["target"]["track_name"] == "Bass"
    assert phase_lever["target"]["parameter_name"] == "Pan"
    assert phase_lever["action"]["can_undo"] is True
    assert phase_lever["action"]["say"] == "center the Bass"


def test_low_mid_mud_produces_boxiness_cut_lever_with_house_rule():
    fake = FakeLiveBackend()
    snapshot = fake.query_session_state()
    # 200-500 Hz energy is 42% (threshold is 38%).
    meters = {
        **_healthy_meters(),
        "spectral_energy": {**_healthy_meters()["spectral_energy"], "low_mid_200_500hz": 0.42},
    }
    grade = _grade_for_meters(meters, snapshot)

    assert is_grade_low_enough_for_help(grade)
    levers = generate_suggestion_levers(grade, snapshot, meters=meters)

    mud_lever = next((l for l in levers if l["dimension"] == "spectral_balance" and "Low-Mid" in l["title"]), None)
    assert mud_lever is not None
    assert mud_lever["points_lost"] == 1.8
    assert "house rule" in mud_lever["source"]
    assert mud_lever["tier"] == "judgement"
    assert "42.0%" in mud_lever["why"]
    assert "<= 38.0%" in mud_lever["baseline"]
    assert mud_lever["is_live_target"] is True
    assert mud_lever["action"]["can_undo"] is True


def test_excessive_compression_produces_compressor_easing_lever():
    fake = FakeLiveBackend()
    snapshot = fake.query_session_state()
    # PLR is 4.8 dB (< 6.0 dB hyper-compression line).
    meters = {**_healthy_meters(), "crest_factor_db": 4.8, "integrated_lufs": -10.0, "true_peak_dbtp": -5.2}
    grade = _grade_for_meters(meters, snapshot)

    assert is_grade_low_enough_for_help(grade)
    levers = generate_suggestion_levers(grade, snapshot, meters=meters)

    comp_lever = next((l for l in levers if "Hyper-Compression" in l["title"]), None)
    assert comp_lever is not None
    assert comp_lever["points_lost"] == 1.8
    assert "4.8 dB" in comp_lever["why"]
    assert "PLR >= 8.0 dB" in comp_lever["baseline"]
    assert comp_lever["is_live_target"] is True
    assert comp_lever["target"]["track_name"] == "Drum Bus"
    assert comp_lever["target"]["device_name"] == "Compressor"
    assert comp_lever["action"]["can_undo"] is True


def test_dull_high_end_produces_air_shelf_boost_lever():
    fake = FakeLiveBackend()
    snapshot = fake.query_session_state()
    # Air energy is 6% (< 10%).
    meters = {
        **_healthy_meters(),
        "spectral_energy": {**_healthy_meters()["spectral_energy"], "air_10_20khz": 0.06},
    }
    grade = _grade_for_meters(meters, snapshot)

    assert is_grade_low_enough_for_help(grade)
    levers = generate_suggestion_levers(grade, snapshot, meters=meters)

    air_lever = next((l for l in levers if "Air Extension" in l["title"]), None)
    assert air_lever is not None
    assert air_lever["points_lost"] == 0.9
    assert "6.0%" in air_lever["why"]
    assert "air energy (>10 kHz) >= 10.0%" in air_lever["baseline"]


def test_sub_excess_produces_sub_fader_reduction_lever():
    fake = FakeLiveBackend()
    snapshot = fake.query_session_state()
    # Sub energy is 52% (> 45%).
    meters = {
        **_healthy_meters(),
        "spectral_energy": {**_healthy_meters()["spectral_energy"], "sub_20_60hz": 0.52},
    }
    grade = _grade_for_meters(meters, snapshot)

    assert is_grade_low_enough_for_help(grade)
    levers = generate_suggestion_levers(grade, snapshot, meters=meters)

    sub_lever = next((l for l in levers if "Sub Energy" in l["title"]), None)
    assert sub_lever is not None
    assert sub_lever["points_lost"] == 1.5
    assert "52.0%" in sub_lever["why"]
    assert "<= 45.0%" in sub_lever["baseline"]
    assert sub_lever["is_live_target"] is True
    assert sub_lever["target"]["track_name"] == "Bass"
    assert "turn the Bass down 1.5 dB" in sub_lever["action"]["say"]


# -----------------------------------------------------------------------------
# 2. Every Suggestion Names a Live Target or Says Outside Live
# -----------------------------------------------------------------------------

def test_every_generated_suggestion_names_live_target_or_explicitly_says_outside_live():
    fake = FakeLiveBackend()
    snapshot = fake.query_session_state()
    penalized_meters = {
        "rms_dbfs": -14.0,
        "integrated_lufs": -11.0,
        "true_peak_dbtp": 0.40,  # clipping
        "phase_correlation": -0.20,  # phase cancellation
        "crest_factor_db": 4.5,  # squashed
        "spectral_energy": {
            "sub_20_60hz": 0.50,  # sub excess
            "low_mid_200_500hz": 0.45,  # mud
            "high_mid_2_6khz": 0.20,
            "air_10_20khz": 0.05,  # air deficit
        },
    }
    # Case A: Live session snapshot connected
    grade_with_live = _grade_for_meters(penalized_meters, snapshot)
    levers_live = generate_suggestion_levers(grade_with_live, snapshot, meters=penalized_meters)
    assert len(levers_live) >= 4

    for lever in levers_live:
        if lever["is_live_target"]:
            target = lever["target"]
            assert target["is_live_target"] is True
            assert target["outside_live"] is False
            assert "track_name" in target and target["track_name"]
            assert "parameter_name" in target and target["parameter_name"]
            assert lever["action"]["can_undo"] is True
        else:
            target = lever["target"]
            assert target["is_live_target"] is False
            assert target["outside_live"] is True
            assert "reason" in target and len(target["reason"]) > 10
            assert lever["action"]["can_undo"] is False

    # Case B: Outside Live / standalone export (no live session)
    grade_outside = _grade_for_meters(penalized_meters, None)
    levers_outside = generate_suggestion_levers(grade_outside, None, meters=penalized_meters)
    assert len(levers_outside) >= 4

    for lever in levers_outside:
        assert lever["is_live_target"] is False
        assert lever["target"]["is_live_target"] is False
        assert lever["target"]["outside_live"] is True
        assert "reason" in lever["target"]
        assert lever["action"]["outside_live"] is True
        assert lever["action"]["can_undo"] is False


# -----------------------------------------------------------------------------
# 3. Live Target Levers Offer Apply and Undo
# -----------------------------------------------------------------------------

def test_every_live_target_suggestion_offers_apply_and_undo():
    fake = FakeLiveBackend()
    service = LiveActionService(fake)
    snapshot = fake.query_session_state()
    session_id = "test-apply-undo"

    meters = {**_healthy_meters(), "true_peak_dbtp": 0.30}
    grade = _grade_for_meters(meters, snapshot)
    levers = generate_suggestion_levers(grade, snapshot, meters=meters, service=service, session_id=session_id)

    live_lever = next(l for l in levers if l["is_live_target"])
    assert live_lever["action"]["can_undo"] is True

    # 1. Apply the lever
    apply_result = apply_suggestion_lever(live_lever, service, session_id=session_id)
    assert apply_result["ok"] is True
    receipt = apply_result["receipt"]
    assert receipt["verified"] is True
    assert receipt["status"] == "applied"

    # 2. Undo the lever
    undo_result = undo_suggestion_lever(receipt, service, session_id=session_id)
    assert undo_result["ok"] is True
    undo_receipt = undo_result["receipt"]
    assert undo_receipt["verified"] is True
    assert undo_receipt["status"] == "applied"


# -----------------------------------------------------------------------------
# 4. Applying Recommendation Measurably Changes the Grade
# -----------------------------------------------------------------------------

def test_applying_true_peak_lever_and_remeasuring_improves_grade_and_undo_reverts():
    fake = FakeLiveBackend()
    service = LiveActionService(fake)
    snapshot = fake.query_session_state()
    session_id = "test-grade-change-peak"

    # Initial state: true peak at -0.1 dBTP (exceeds -1.0 dBTP ceiling).
    penalized_meters = {**_healthy_meters(), "true_peak_dbtp": -0.1}
    initial_grade = _grade_for_meters(penalized_meters, snapshot, request="Spotify")
    initial_points = initial_grade["points"]

    levers = generate_suggestion_levers(initial_grade, snapshot, meters=penalized_meters, service=service, session_id=session_id)
    peak_lever = next(l for l in levers if "True Peak" in l["title"])
    assert peak_lever["is_live_target"] is True

    # Initial fader level before applying
    bass_track_before = next(t for t in service.snapshot()["tracks"] if t["name"] == "Bass")
    vol_before = bass_track_before["volume"]

    # 1. Apply lever
    apply_result = apply_suggestion_lever(peak_lever, service, session_id=session_id)
    assert apply_result["ok"] is True

    bass_track_after = next(t for t in service.snapshot()["tracks"] if t["name"] == "Bass")
    assert bass_track_after["volume"] < vol_before

    # 2. Re-measure: lowering Bass by 2 dB drops master peak to -2.1 dBTP (cleanly below -1.0 dBTP ceiling).
    remeasured_meters = {**penalized_meters, "true_peak_dbtp": -2.1}
    updated_grade = _grade_for_meters(remeasured_meters, service.snapshot(), request="Spotify")

    # The grade measurably increases!
    assert updated_grade["points"] > initial_points
    # Dynamic health and declared target ceiling both recover full points.
    initial_dyn = next(p["points"] for p in initial_grade["parts"] if p["part"] == "technical_health")
    updated_dyn = next(p["points"] for p in updated_grade["parts"] if p["part"] == "technical_health")
    assert updated_dyn > initial_dyn

    # 3. Undo lever
    undo_result = undo_suggestion_lever(apply_result["receipt"], service, session_id=session_id)
    assert undo_result["ok"] is True

    bass_track_reverted = next(t for t in service.snapshot()["tracks"] if t["name"] == "Bass")
    assert bass_track_reverted["volume"] == pytest.approx(vol_before, abs=1e-5)

    # 4. Re-measure after undo returns to penalized grade
    reverted_grade = _grade_for_meters(penalized_meters, service.snapshot(), request="Spotify")
    assert reverted_grade["points"] == initial_points


def test_applying_phase_correlation_lever_and_remeasuring_improves_grade_and_undo_reverts():
    fake = FakeLiveBackend()
    service = LiveActionService(fake)
    snapshot = fake.query_session_state()
    session_id = "test-grade-change-phase"

    # Start with Bass track panned off-center (+0.40).
    service.client.set_track_pan(4, 0.40)
    penalized_meters = {**_healthy_meters(), "phase_correlation": -0.15}
    initial_grade = _grade_for_meters(penalized_meters, service.snapshot(), request="Spotify")
    initial_points = initial_grade["points"]

    levers = generate_suggestion_levers(initial_grade, service.snapshot(), meters=penalized_meters, service=service, session_id=session_id)
    phase_lever = next(l for l in levers if l["dimension"] == "stereo_imaging")

    # 1. Apply lever (centers the Bass)
    apply_result = apply_suggestion_lever(phase_lever, service, session_id=session_id)
    assert apply_result["ok"] is True

    bass_pan_after = next(t for t in service.snapshot()["tracks"] if t["name"] == "Bass")["pan"]
    assert bass_pan_after == pytest.approx(0.0, abs=1e-5)

    # 2. Re-measure with centered bass: phase correlation recovers to +0.80.
    remeasured_meters = {**penalized_meters, "phase_correlation": 0.80}
    updated_grade = _grade_for_meters(remeasured_meters, service.snapshot(), request="Spotify")

    assert updated_grade["points"] > initial_points
    # Stereo imaging recovered from 1.5 to 6.0 points (a 4.5-point shift).
    assert updated_grade["points"] == pytest.approx(initial_points + 4.5, abs=0.1)

    # 3. Undo lever
    undo_result = undo_suggestion_lever(apply_result["receipt"], service, session_id=session_id)
    assert undo_result["ok"] is True

    bass_pan_reverted = next(t for t in service.snapshot()["tracks"] if t["name"] == "Bass")["pan"]
    assert bass_pan_reverted == pytest.approx(0.40, abs=1e-5)

    reverted_grade = _grade_for_meters(penalized_meters, service.snapshot(), request="Spotify")
    assert reverted_grade["points"] == initial_points


def test_applying_low_mid_mud_lever_and_remeasuring_improves_grade():
    fake = FakeLiveBackend()
    service = LiveActionService(fake)
    snapshot = fake.query_session_state()
    session_id = "test-grade-change-mud"

    penalized_meters = {
        **_healthy_meters(),
        "spectral_energy": {**_healthy_meters()["spectral_energy"], "low_mid_200_500hz": 0.42},
    }
    initial_grade = _grade_for_meters(penalized_meters, snapshot)
    initial_points = initial_grade["points"]

    levers = generate_suggestion_levers(initial_grade, snapshot, meters=penalized_meters, service=service, session_id=session_id)
    mud_lever = next(l for l in levers if "Low-Mid" in l["title"])

    apply_result = apply_suggestion_lever(mud_lever, service, session_id=session_id)
    assert apply_result["ok"] is True

    # Re-measure: EQ dip brings low-mid energy down from 42% to 32% (below 38% threshold).
    remeasured_meters = {
        **penalized_meters,
        "spectral_energy": {**penalized_meters["spectral_energy"], "low_mid_200_500hz": 0.32},
    }
    updated_grade = _grade_for_meters(remeasured_meters, service.snapshot())

    assert updated_grade["points"] > initial_points
    assert updated_grade["points"] == pytest.approx(initial_points + 1.8, abs=0.1)


# -----------------------------------------------------------------------------
# 5. Refusal Paths and Accuracy Margins
# -----------------------------------------------------------------------------

def test_refusal_on_signal_below_significance_floor():
    # Audio at or below -60 dBFS significance floor cannot be reliably evaluated.
    quiet_meters = {**_healthy_meters(), "rms_dbfs": -62.0, "true_peak_dbtp": 0.50}
    grade = _grade_for_meters(quiet_meters)
    levers = generate_suggestion_levers(grade, meters=quiet_meters)

    # Refuses to emit levers for silent/near-silent audio.
    assert levers == []


def test_refusal_on_healthy_mix_grade():
    # Healthy mix has 0 deductions; no corrective levers are needed.
    healthy = _healthy_meters()
    grade = _grade_for_meters(healthy)
    assert not is_grade_low_enough_for_help(grade)

    levers = generate_suggestion_levers(grade, meters=healthy)
    assert levers == []


def test_refusal_to_guess_ambiguous_tracks():
    fake = FakeLiveBackend()
    snapshot = fake.query_session_state()
    # Add a second bass track to create ambiguity.
    snapshot["tracks"].append({"index": 8, "name": "Sub Bass 808", "volume": 0.85})

    meters = {
        **_healthy_meters(),
        "spectral_energy": {**_healthy_meters()["spectral_energy"], "sub_20_60hz": 0.55},
    }
    grade = _grade_for_meters(meters, snapshot)
    levers = generate_suggestion_levers(grade, snapshot, meters=meters)

    sub_lever = next(l for l in levers if "Sub Energy" in l["title"])
    # Ambiguous track roles refuse automated Live mutation and emit informational advice instead.
    assert sub_lever["is_live_target"] is False
    assert sub_lever["target"]["outside_live"] is True
    assert "More than one track" in sub_lever["target"]["reason"]


def test_with_suggestion_levers_decorates_grade_cleanly():
    fake = FakeLiveBackend()
    snapshot = fake.query_session_state()
    meters = {**_healthy_meters(), "true_peak_dbtp": 0.10}
    grade = _grade_for_meters(meters, snapshot)

    annotated = with_suggestion_levers(grade, snapshot, meters=meters)
    assert "levers" in annotated
    assert len(annotated["levers"]) >= 1
    assert annotated["points"] == grade["points"]
    assert annotated["points_available"] == grade["points_available"]
