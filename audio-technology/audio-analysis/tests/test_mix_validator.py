"""Unit tests for the mix validator and auto-correction loop.

Verifies that the validator loop runs multiple iterations, adjusts the limiter threshold
to correct LUFS deviations, and returns a validated mix down result.
"""

from __future__ import annotations

import numpy as np
import pytest

from audio_analysis.mixdown.stem_classifier import StemProfile
from audio_analysis.mixdown.mix_decision_engine import generate_mix_plan
from audio_analysis.mixdown.mix_renderer import mix_and_render_stems
from audio_analysis.mixdown.stem_prep import write_wav
from audio_analysis.mixdown.mix_validator import validate_and_correct_mix
from audio_analysis.mixdown import mix_validator


def test_validation_loop():
    sample_rate = 44100
    duration_samples = 22050  # 0.5 seconds
    
    t = np.linspace(0, 0.5, duration_samples, endpoint=False)
    # Generate simple test signals
    kick_samples = np.sin(2.0 * np.pi * 60.0 * t) * 0.5
    vocal_samples = np.sin(2.0 * np.pi * 440.0 * t) * 0.3

    prepared_stems = [
        {"name": "kick.wav", "samples": kick_samples.tolist(), "sample_rate": sample_rate},
        {"name": "vocal.wav", "samples": vocal_samples.tolist(), "sample_rate": sample_rate},
    ]

    profiles = [
        StemProfile(name="kick.wav", instrument="kick", peak_dbfs=-6.0, rms_dbfs=-18.0, crest_factor_db=12.0),
        StemProfile(name="vocal.wav", instrument="vocal", peak_dbfs=-10.0, rms_dbfs=-22.0, crest_factor_db=12.0),
    ]

    # Generate initial plan targeting -14.0 LUFS
    plan = generate_mix_plan(profiles, masking_results=None, genre="pop", target_lufs=-14.0)

    # Let's run the validation loop
    result = validate_and_correct_mix(
        prepared_stems,
        plan,
        render_fn=mix_and_render_stems,
        max_iterations=3,
    )

    assert "mixdown_wav_bytes" in result
    assert "history" in result
    assert "report" in result
    
    history = result["history"]
    assert len(history) >= 1
    
    # Final integrated LUFS should be close to -14.0 LUFS (within 0.5 LU)
    final_lufs = result["measured_lufs"]
    assert abs(final_lufs - (-14.0)) <= 0.5
    assert result["quality_gate"]["minimum_score"] == 65
    assert "before" in result["comparison_report"]
    assert "after" in result["comparison_report"]


def _test_plan():
    profiles = [
        StemProfile(
            name="vocal.wav",
            instrument="vocal",
            peak_dbfs=-6.0,
            rms_dbfs=-18.0,
            crest_factor_db=12.0,
        )
    ]
    return generate_mix_plan(profiles, genre="pop", target_lufs=-14.0)


def test_validator_corrects_clipping_and_leaves_phase_for_manual_review(monkeypatch):
    reports = iter(
        [
            {
                "technical_score": 70,
                "flags": [{"id": "phase_correlation_low", "band": "bass"}],
                "metrics": {"integrated_lufs": -14.0, "true_peak_dbfs": 0.2},
            },
            {
                "technical_score": 75,
                "flags": [],
                "metrics": {"integrated_lufs": -14.0, "true_peak_dbfs": -1.2},
            },
        ]
    )
    monkeypatch.setattr(mix_validator, "analyze_wav", lambda *args, **kwargs: next(reports))
    plan = _test_plan()

    result = validate_and_correct_mix(
        [{"name": "vocal.wav", "samples": [0.0], "sample_rate": 44_100}],
        plan,
        render_fn=lambda stems, current_plan: {
            "mixdown_wav_bytes": b"wav",
            "mix_plan": current_plan,
            "measured_lufs": -14.0,
        },
        max_iterations=3,
    )

    assert len(result["history"]) == 2
    assert plan.bus.limiter_threshold_db == pytest.approx(1.0)
    assert result["comparison_report"]["delta"]["technical_score"] == 5
    assert any("Clipping correction" in line for line in plan.decisions_log)
    assert any("no automatic phase correction" in line for line in plan.decisions_log)


def test_validator_reports_low_advisory_score_without_failing_safe_delivery(monkeypatch):
    monkeypatch.setattr(
        mix_validator,
        "analyze_wav",
        lambda *args, **kwargs: {
            "technical_score": 54,
            "flags": [],
            "metrics": {"integrated_lufs": -14.0, "true_peak_dbfs": -1.2},
        },
    )
    plan = _test_plan()

    silence = [0.0] * 1000
    result = validate_and_correct_mix(
        [{"name": "vocal.wav", "samples": [0.0], "sample_rate": 44_100}],
        plan,
        render_fn=lambda stems, current_plan: {
            "mixdown_wav_bytes": write_wav(silence, silence, 44_100, bit_depth=24),
            "left": np.asarray(silence),
            "right": np.asarray(silence),
            "sample_rate": 44_100,
            "mix_plan": current_plan,
            "measured_lufs": -14.0,
        },
        max_iterations=1,
        min_technical_score=60,
    )

    assert result["quality_gate"]["passed"] is True
    assert result["quality_gate"]["safety_passed"] is True
    assert result["quality_gate"]["advisory_score_passed"] is False
    assert result["quality_gate"]["technical_score"] == 54
    assert result["quality_gate"]["minimum_score"] == 60
    assert any("Advisory quality target not reached" in line for line in plan.decisions_log)


def test_validator_stops_when_advisory_flags_produce_no_plan_change(monkeypatch):
    monkeypatch.setattr(
        mix_validator,
        "analyze_wav",
        lambda *args, **kwargs: {
            "technical_score": 20,
            "flags": [{"id": "manual_balance_review", "band": ""}],
            "metrics": {"integrated_lufs": -14.0, "true_peak_dbfs": -1.2},
        },
    )
    plan = _test_plan()
    silence = [0.0] * 1_000
    renders = 0

    def render(stems, current_plan):
        nonlocal renders
        renders += 1
        return {
            "mixdown_wav_bytes": write_wav(silence, silence, 44_100, bit_depth=24),
            "left": np.asarray(silence),
            "right": np.asarray(silence),
            "sample_rate": 44_100,
            "mix_plan": current_plan,
            "measured_lufs": -14.0,
        }

    result = validate_and_correct_mix(
        [{"name": "vocal.wav", "samples": silence, "sample_rate": 44_100}],
        plan,
        render_fn=render,
        max_iterations=3,
        min_technical_score=65,
    )

    assert renders == 1
    assert len(result["history"]) == 1
    assert result["quality_gate"]["advisory_score_passed"] is False
    assert any("no_effect" in line for line in plan.decisions_log)


def test_verify_render_output_fails_closed_on_nonfinite_or_misaligned_audio() -> None:
    from audio_analysis.mixdown.mix_validator import verify_render_output

    nonfinite = verify_render_output(
        np.asarray([0.0, np.nan]), np.asarray([0.0, 0.0]), 44_100, b"invalid"
    )
    misaligned = verify_render_output(
        np.asarray([0.0]), np.asarray([]), 44_100, b"invalid"
    )

    assert nonfinite["ok"] is False
    assert any("NaN" in reason for reason in nonfinite["hard_failures"])
    assert misaligned["ok"] is False
    assert any("different lengths" in reason for reason in misaligned["hard_failures"])


def test_verify_render_output_rejects_truncated_session_duration() -> None:
    from audio_analysis.mixdown.mix_validator import verify_render_output

    result = verify_render_output(
        np.zeros(1_000),
        np.zeros(1_000),
        44_100,
        write_wav([0.0] * 1_000, [0.0] * 1_000, 44_100, 24),
        expected_num_samples=44_100,
    )

    assert result["ok"] is False
    assert any("does not match the prepared session" in reason for reason in result["hard_failures"])


def test_validator_uses_canonical_mix_goal_not_automix_genre(monkeypatch):
    received_goals = []

    def fake_analyze(*args, **kwargs):
        received_goals.append(kwargs["mix_goal"])
        return {
            "technical_score": 80,
            "flags": [],
            "metrics": {"integrated_lufs": -14.0, "true_peak_dbfs": -1.2},
        }

    monkeypatch.setattr(mix_validator, "analyze_wav", fake_analyze)
    plan = generate_mix_plan(
        [
            StemProfile(
                name="vocal.wav",
                instrument="vocal",
                peak_dbfs=-6.0,
                rms_dbfs=-18.0,
                crest_factor_db=12.0,
            )
        ],
        genre="edm",
        target_lufs=-14.0,
    )

    validate_and_correct_mix(
        [{"name": "vocal.wav", "samples": [0.0], "sample_rate": 44_100}],
        plan,
        render_fn=lambda stems, current_plan: {
            "mixdown_wav_bytes": b"wav",
            "mix_plan": current_plan,
            "measured_lufs": -14.0,
        },
        max_iterations=1,
    )

    assert received_goals == ["club"]
