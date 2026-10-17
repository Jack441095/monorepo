"""Tests for Milestone E5: End-to-End Closed-Loop Mix Analysis, Grading, Levers, and Apply-Undo Workflow.

Verifies the full end-to-end closed loop:
1. Real-Time Analysis Window (100 ms C++ telemetry)
2. Grounded Grade out of 100 (technical health, declared target, reference match)
3. Actionable Suggestion Levers (Live target binding or outside Live)
4. Grounded Pedagogical Explanation (MixAssist phrasing, cited standards, auditory cues)
5. Apply Lever to FakeLive (LiveActionService execution and receipt verification)
6. Re-measuring & Grade Delta Verification (acoustic delta strictly improves grade score)
7. Undo Action & Verification (exact parameter and grade restoration to initial state)
8. Audio calculator grounding check (tempo, latency, pitch with middle C labelled C3 in Live, dB factors)
"""

from __future__ import annotations

import math
import pytest

from kenn.core.audio_calculators import (
    calculated_facts,
    latency_facts,
    level_facts,
    pitch_facts,
    tempo_facts,
)
from kenn.core.fake_live import FakeLiveBackend
from kenn.core.grade import combine_grade, grade_session
from kenn.core.live_action_service import LiveActionService
from kenn.core.mix_doctor import MixDoctor
from kenn.core.plugin_grade import selected_insert_grade, selected_insert_grade_answer
from kenn.core.suggestion_levers import (
    apply_suggestion_lever,
    explain_grade,
    explain_suggestion_lever,
    generate_suggestion_levers,
    undo_suggestion_lever,
    with_suggestion_levers,
)
from kenn.core.volume_law import db_to_raw, raw_to_db


def _baseline_healthy_meters() -> dict:
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


def _grade_session_helper(meters: dict, snapshot: dict | None = None, request: str = "Spotify") -> dict:
    tracks = (snapshot or {}).get("tracks") or []
    technical = MixDoctor().audit_session({"tracks": tracks}, meters=meters).to_dict()
    return grade_session(
        technical, meters, request=request, session_snapshot=snapshot,
        include_levers=True, include_explanation=True,
    )


# -----------------------------------------------------------------------------
# 1. Closed-Loop True Peak Remediation Workflow
# -----------------------------------------------------------------------------

def test_closed_loop_true_peak_remediation_workflow():
    """Verify closed loop for true peak: Analysis -> Grade -> Lever -> Explain -> Apply -> Re-measure -> Undo."""
    fake = FakeLiveBackend()
    service = LiveActionService(fake)
    snapshot = fake.query_session_state()
    session_id = "closed-loop-true-peak"

    # Step 1: 100 ms C++ analysis window telemetry indicates inter-sample clipping (+0.30 dBTP)
    initial_meters = {**_baseline_healthy_meters(), "true_peak_dbtp": 0.30}

    # Step 2: Grounded Grade out of 100
    initial_grade = _grade_session_helper(initial_meters, snapshot, request="Spotify")
    initial_score = initial_grade["points"]
    assert initial_score < initial_grade["points_available"], "Expected deductions for true peak clipping"

    # Step 3 & 4: Actionable Suggestion Levers with Grounded Pedagogical Explanation
    levers = initial_grade.get("levers") or []
    assert len(levers) >= 1
    tp_lever = next(l for l in levers if "True Peak" in l["title"])
    assert tp_lever["is_live_target"] is True
    assert tp_lever["target"]["parameter_name"] == "Volume"

    expl = tp_lever["explanation"]
    assert expl is not None
    assert expl["metric_name"] == "True Peak"
    assert expl["measured_value"] == 0.30
    assert any("EBU Tech 3343" in s for s in expl["cited_standards"])
    assert "crunchy" in expl["auditory_cues"]["before"].lower()
    assert "clean" in expl["auditory_cues"]["after"].lower()

    # Step 5: Apply Lever to FakeLive
    bass_track_before = next(t for t in service.snapshot()["tracks"] if t["name"] == "Bass")
    initial_raw_volume = bass_track_before["volume"]

    apply_result = apply_suggestion_lever(tp_lever, service, session_id=session_id)
    assert apply_result["ok"] is True
    receipt = apply_result["receipt"]
    assert receipt["verified"] is True
    assert receipt["status"] == "applied"

    # Verify FakeLive state changed: fader pulled down 2 dB
    bass_track_applied = next(t for t in service.snapshot()["tracks"] if t["name"] == "Bass")
    assert bass_track_applied["volume"] < initial_raw_volume

    # Step 6: Re-measuring & Grade Delta Verification
    # Re-measuring after volume attenuation shows true peak dropped safely below -1.0 dBTP ceiling
    remeasured_meters = {**initial_meters, "true_peak_dbtp": -1.70}
    remeasured_grade = _grade_session_helper(remeasured_meters, service.snapshot(), request="Spotify")
    remeasured_score = remeasured_grade["points"]

    assert remeasured_score > initial_score, "Grade must measurably improve after applying remediation"
    score_delta = remeasured_score - initial_score
    assert score_delta >= 2.0, f"Expected at least +2.0 point gain, got +{score_delta:.1f}"

    # Step 7: Undo Action & Verification
    undo_result = undo_suggestion_lever(receipt, service, session_id=session_id)
    assert undo_result["ok"] is True
    assert undo_result["receipt"]["status"] == "applied"

    # Verify FakeLive state cleanly reverted back to initial volume
    bass_track_reverted = next(t for t in service.snapshot()["tracks"] if t["name"] == "Bass")
    assert abs(bass_track_reverted["volume"] - initial_raw_volume) < 1e-4

    # Re-measuring in reverted state restores initial grade
    reverted_grade = _grade_session_helper(initial_meters, service.snapshot(), request="Spotify")
    assert reverted_grade["points"] == initial_score


# -----------------------------------------------------------------------------
# 2. Closed-Loop Stereo Phase Cancellation Remediation Workflow
# -----------------------------------------------------------------------------

def test_closed_loop_phase_cancellation_remediation_workflow():
    """Verify closed loop for phase cancellation: Analysis -> Grade -> Center Pan Lever -> Apply -> Re-measure -> Undo."""
    fake = FakeLiveBackend()
    service = LiveActionService(fake)
    snapshot = fake.query_session_state()
    session_id = "closed-loop-phase"

    # Introduce phase cancellation: pan Bass off-center to +0.40
    bass_idx = next(t["index"] for t in snapshot["tracks"] if t["name"] == "Bass")
    fake.set_track_pan(bass_idx, 0.40)
    snapshot = fake.query_session_state()

    # Step 1: 100 ms C++ analysis window reports negative phase correlation (-0.18)
    initial_meters = {**_baseline_healthy_meters(), "phase_correlation": -0.18}

    # Step 2: Compute Grounded Grade
    initial_grade = _grade_session_helper(initial_meters, snapshot, request="Spotify")
    initial_score = initial_grade["points"]

    # Step 3 & 4: Suggestion Lever & Grounded Pedagogical Explanation
    levers = initial_grade["levers"]
    phase_lever = next(l for l in levers if l["dimension"] == "stereo_imaging")
    assert phase_lever["is_live_target"] is True
    assert phase_lever["target"]["parameter_name"] == "Pan"

    expl = phase_lever["explanation"]
    assert expl["measured_value"] == -0.18
    assert any("Correlation" in s for s in expl["cited_standards"])
    assert "mono" in expl["auditory_cues"]["before"].lower()
    assert "focused" in expl["auditory_cues"]["after"].lower() or "punch" in expl["auditory_cues"]["after"].lower()

    # Step 5: Apply Center Pan Lever
    apply_result = apply_suggestion_lever(phase_lever, service, session_id=session_id)
    assert apply_result["ok"] is True
    receipt = apply_result["receipt"]

    bass_track_applied = next(t for t in service.snapshot()["tracks"] if t["name"] == "Bass")
    assert abs(bass_track_applied.get("pan", 0.0) - 0.0) < 1e-4

    # Step 6: Re-measure & Grade Delta Verification
    # Re-measuring with centered bass restores positive correlation (+0.82)
    remeasured_meters = {**initial_meters, "phase_correlation": 0.82}
    remeasured_grade = _grade_session_helper(remeasured_meters, service.snapshot(), request="Spotify")

    assert remeasured_grade["points"] > initial_score
    delta = remeasured_grade["points"] - initial_score
    assert delta >= 4.0, f"Expected +4.5 point recovery on stereo dimension, got +{delta:.1f}"

    # Step 7: Undo Action & Verification
    undo_result = undo_suggestion_lever(receipt, service, session_id=session_id)
    assert undo_result["ok"] is True

    bass_track_reverted = next(t for t in service.snapshot()["tracks"] if t["name"] == "Bass")
    assert abs(bass_track_reverted.get("pan", 0.0) - 0.40) < 1e-4

    reverted_grade = _grade_session_helper(initial_meters, service.snapshot(), request="Spotify")
    assert reverted_grade["points"] == initial_score


# -----------------------------------------------------------------------------
# 3. Closed-Loop Low-Mid Mud EQ Remediation Workflow
# -----------------------------------------------------------------------------

def test_closed_loop_low_mid_mud_eq_remediation_workflow():
    """Verify closed loop for low-mid boxiness: Analysis -> Grade -> EQ Eight Dip Lever -> Apply -> Re-measure."""
    fake = FakeLiveBackend()
    service = LiveActionService(fake)
    snapshot = fake.query_session_state()
    session_id = "closed-loop-mud"

    # Step 1: 100 ms analysis window indicates 42.0% energy in 200-500 Hz (threshold 38%)
    initial_meters = {
        **_baseline_healthy_meters(),
        "spectral_energy": {**_baseline_healthy_meters()["spectral_energy"], "low_mid_200_500hz": 0.42},
    }

    # Step 2: Compute Grade
    initial_grade = _grade_session_helper(initial_meters, snapshot)
    initial_score = initial_grade["points"]

    # Step 3 & 4: Suggestion Lever & Explanation
    levers = initial_grade["levers"]
    mud_lever = next(l for l in levers if "Low-Mid" in l["title"])
    assert mud_lever["is_live_target"] is True

    expl = mud_lever["explanation"]
    assert expl["measured_value"] == 42.0
    assert any("Wilson & Fazenda (2016)" in s for s in expl["cited_standards"])
    assert "vocal" in expl["auditory_cues"]["after"].lower()

    # Step 5: Apply EQ Eight parameter write
    apply_result = apply_suggestion_lever(mud_lever, service, session_id=session_id)
    assert apply_result["ok"] is True
    receipt = apply_result["receipt"]
    assert receipt["action"] in ("set_device_parameter", "set_volume")

    # Step 6: Re-measure & Verify Score Improvement
    # Re-measuring after EQ dip brings low-mid energy down to 30.0%
    remeasured_meters = {
        **initial_meters,
        "spectral_energy": {**initial_meters["spectral_energy"], "low_mid_200_500hz": 0.30},
    }
    remeasured_grade = _grade_session_helper(remeasured_meters, service.snapshot())
    assert remeasured_grade["points"] > initial_score


# -----------------------------------------------------------------------------
# 4. Audio Calculator Grounding Checks & Live C3 Label Mapping
# -----------------------------------------------------------------------------

def test_audio_calculators_grounding_and_middle_c_labels():
    """Verify audio calculators stay grounded and label middle C as C3 in Live piano roll."""
    # 1. Tempo / Delay facts
    tempo_res = tempo_facts("dotted eighth delay at 128 bpm")
    assert len(tempo_res) == 1
    # 240,000 / 128 * (1/8) * 1.5 = 1875 * 0.1875 = 351.56 -> 351.6 ms
    assert "351.6 ms" in tempo_res[0]
    assert "128 BPM" in tempo_res[0]

    # 2. Buffer latency facts
    latency_res = latency_facts("512 samples at 48 khz")
    assert len(latency_res) == 1
    # 512 / 48000 * 1000 = 10.666... -> 10.67 ms (about 10.7 ms)
    assert "10.67 ms" in latency_res[0]
    assert "48 kHz" in latency_res[0]

    # 3. Pitch facts: Scientific C4 vs Live C3 verification
    pitch_res = pitch_facts("what note is 261.63 Hz")
    assert len(pitch_res) == 1
    text = pitch_res[0]
    # Verify scientific pitch C4 (MIDI 60) is explicitly labelled C3 in Live
    assert "C4 in scientific pitch" in text
    assert "MIDI note 60" in text
    assert "Live's piano roll labels C3" in text

    # Reverse lookup: C4 to Hz
    c4_res = pitch_facts("what frequency is C4")
    assert len(c4_res) == 1
    assert "261.63 Hz" in c4_res[0]
    assert "Live's piano roll labels C3" in c4_res[0]

    # 4. Level facts: dB to linear gain factors
    level_res = level_facts("-6 dB as a factor")
    assert len(level_res) >= 1
    # -6 dB = 10^(-6/20) = 0.501 amplitude factor (50.1%)
    assert "-6 dB" in level_res[0]
    assert "0.501" in level_res[0]
    assert "50.1%" in level_res[0]

    # 5. Full calculated_facts string output check
    all_facts = calculated_facts("what note is 261.63 Hz and what is a dotted eighth delay at 120 bpm")
    assert "KENN calculation:" in all_facts
    assert "C4 in scientific pitch" in all_facts
    assert "Live's piano roll labels C3" in all_facts
    assert "375 ms" in all_facts  # 240,000 / 120 * 0.1875 = 375 ms


# -----------------------------------------------------------------------------
# 5. Selected Insert Grade with 100 ms Window & Explanation Answer
# -----------------------------------------------------------------------------

def test_selected_insert_grade_with_100ms_window():
    """Verify 100 ms insert window projection into plugin grade and human answer."""
    window = {
        "valid": True,
        "window_duration_ms": 100.0,
        "sample_rate": 48000,
        "input_channels": 2,
        "correlation_valid": True,
        "start_sample": 0,
        "end_sample": 4800,
        "sequence": 1,
        "source_generation": 1,
    }
    item = {
        "conversation_id": "test-conv-1",
        "host_track_name": "Mix Master",
        "measurement_window": window,
        "metrics": {
            "sample_rate": 48000,
            "input_channels": 2,
            "rms_dbfs": -16.0,
            "stereo_correlation": 0.45,
            "correlation_valid": True,
        },
    }
    result = selected_insert_grade(
        conversation_id="test-conv-1",
        insert_id="ins-1",
        item=item,
        age_seconds=0.05,
        current=True,
        max_age_seconds=2.0,
    )

    assert result["status"] == "graded"
    assert result["grade"]["points"] == 5.1  # 6.0 - 0.9 points for correlation in [0.25, 0.5)
    assert result["grade"]["points_available"] == 6.0

    # Answer text must specify 100 ms window
    answer = selected_insert_grade_answer(result, "Mix Master")
    assert "100 ms stereo window earns 5.1 of 6 available points" in answer

