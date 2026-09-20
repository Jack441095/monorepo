"""generate_mix_plan() silently falls back to "pop" for any genre string it
doesn't recognize, and there was previously no signal anywhere if the
rendered audio itself sounds nothing like the genre selected (P4/AutoMix
fix, 2026-07-13). validate_and_correct_mix() now cross-checks the first
iteration's spectral fingerprint against mix_style_classifier and logs an
informational (non-blocking) note on a confident mismatch."""

from __future__ import annotations

from audio_analysis.analysis_core.genre_profiles import GENRE_SEED_PROFILES
from audio_analysis.mixdown.stem_classifier import StemProfile
from audio_analysis.mixdown.mix_decision_engine import generate_mix_plan
from audio_analysis.mixdown.mix_validator import validate_and_correct_mix
from audio_analysis.mixdown import mix_validator


def _plan(genre: str) -> object:
    profiles = [
        StemProfile(name="vocal.wav", instrument="vocal", peak_dbfs=-6.0, rms_dbfs=-18.0, crest_factor_db=12.0)
    ]
    return generate_mix_plan(profiles, genre=genre, target_lufs=-14.0)


def _render_fn(stems, current_plan):
    return {"mixdown_wav_bytes": b"wav", "mix_plan": current_plan, "measured_lufs": -14.0}


def test_logs_informational_note_on_confident_genre_mismatch(monkeypatch):
    hip_hop_profile = GENRE_SEED_PROFILES["hip_hop"]["profile"]

    monkeypatch.setattr(
        mix_validator,
        "analyze_wav",
        lambda *a, **k: {
            "technical_score": 80,
            "flags": [],
            "metrics": {
                "integrated_lufs": -14.0,
                "true_peak_dbfs": -1.2,
                "log_bands_40": hip_hop_profile,
                "crest_factor_db": GENRE_SEED_PROFILES["hip_hop"]["crest_factor_db"],
            },
        },
    )
    plan = _plan("jazz")  # deliberately mismatched vs. the hip_hop fingerprint above

    validate_and_correct_mix(
        [{"name": "vocal.wav", "samples": [0.0], "sample_rate": 44_100}],
        plan,
        render_fn=_render_fn,
        max_iterations=1,
    )

    assert any("hip_hop" in line and "jazz" in line for line in plan.decisions_log)


def test_no_note_when_selected_genre_matches_detected_genre(monkeypatch):
    hip_hop_profile = GENRE_SEED_PROFILES["hip_hop"]["profile"]

    monkeypatch.setattr(
        mix_validator,
        "analyze_wav",
        lambda *a, **k: {
            "technical_score": 80,
            "flags": [],
            "metrics": {
                "integrated_lufs": -14.0,
                "true_peak_dbfs": -1.2,
                "log_bands_40": hip_hop_profile,
                "crest_factor_db": GENRE_SEED_PROFILES["hip_hop"]["crest_factor_db"],
            },
        },
    )
    plan = _plan("hip_hop")  # matches the fingerprint

    validate_and_correct_mix(
        [{"name": "vocal.wav", "samples": [0.0], "sample_rate": 44_100}],
        plan,
        render_fn=_render_fn,
        max_iterations=1,
    )

    assert not any("spectrally matches" in line for line in plan.decisions_log)


def test_no_note_when_metrics_lack_log_bands_40(monkeypatch):
    """Existing callers' fake reports (see test_mix_validator.py) never
    included log_bands_40 -- must degrade silently, not raise."""
    monkeypatch.setattr(
        mix_validator,
        "analyze_wav",
        lambda *a, **k: {
            "technical_score": 80,
            "flags": [],
            "metrics": {"integrated_lufs": -14.0, "true_peak_dbfs": -1.2},
        },
    )
    plan = _plan("jazz")

    validate_and_correct_mix(
        [{"name": "vocal.wav", "samples": [0.0], "sample_rate": 44_100}],
        plan,
        render_fn=_render_fn,
        max_iterations=1,
    )

    assert not any("spectrally matches" in line for line in plan.decisions_log)


def test_genre_mismatch_check_never_breaks_the_render_on_classifier_error(monkeypatch):
    monkeypatch.setattr(
        mix_validator,
        "analyze_wav",
        lambda *a, **k: {
            "technical_score": 80,
            "flags": [],
            "metrics": {"integrated_lufs": -14.0, "true_peak_dbfs": -1.2},
        },
    )

    def boom(*a, **k):
        raise RuntimeError("classifier exploded")

    monkeypatch.setattr(mix_validator, "classify_mix_style", boom)
    plan = _plan("jazz")

    result = validate_and_correct_mix(
        [{"name": "vocal.wav", "samples": [0.0], "sample_rate": 44_100}],
        plan,
        render_fn=_render_fn,
        max_iterations=1,
    )

    assert "mixdown_wav_bytes" in result  # render completed despite the classifier failing
