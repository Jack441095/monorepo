"""Unit tests for MixDecisionEngine and MixRenderer.

Verifies that:
  1. Stem profiles + genreTargets -> valid MixPlan.
  2. MixRenderer successfully sums and applies master bus DSP (EQ, Compression, Limiting, AUX sends).
  3. Master output is limited below the ceiling.
"""

from __future__ import annotations

import numpy as np
import pytest

from audio_analysis.mixdown.stem_classifier import StemProfile
from audio_analysis.mixdown.mix_decision_engine import (
    ROUGH_INTENT_MAX_GAIN_DEVIATION_DB,
    MixPlan,
    generate_mix_plan,
)
from audio_analysis.mixdown.mix_renderer import mix_and_render_stems
from audio_analysis.mixdown import mix_renderer
from audio_analysis.mixdown.mix_rules import (
    GENRE_MODIFIERS,
    INSTRUMENT_RULES,
    get_rule_for_instrument,
)


def _profile(instrument: str) -> StemProfile:
    return StemProfile(
        name=f"{instrument}.wav",
        instrument=instrument,
        peak_dbfs=-6.0,
        rms_dbfs=-18.0,
        crest_factor_db=12.0,
    )


def test_every_instrument_genre_rule_has_safe_parameter_ranges():
    valid_eq_types = {"lowpass", "highpass", "lowshelf", "highshelf", "peaking", "notch", "allpass"}
    for genre in GENRE_MODIFIERS:
        for instrument in INSTRUMENT_RULES:
            rule = get_rule_for_instrument(instrument, genre)
            assert -60.0 <= float(rule.get("target_peak_dbfs", -6.0)) <= 0.0
            assert -60.0 <= float(rule.get("target_level_relative_to_anchor", 0.0)) <= 12.0
            assert 0.0 <= float(rule.get("highpass_hz", 0.0)) < 20_000.0
            assert -1.0 <= float(rule.get("pan", 0.0)) <= 1.0
            assert 0.0 <= float(rule.get("stereo_width", 1.0)) <= 2.0
            assert 0.0 <= float(rule.get("reverb_send", 0.0)) <= 1.0
            assert 0.0 <= float(rule.get("delay_send", 0.0)) <= 1.0
            assert rule.get("reverb_type", "room") in {"plate", "room", "hall"}
            assert 0.2 <= float(rule.get("reverb_decay_s", 1.2)) <= 8.0
            assert 0.0 <= float(rule.get("mono_below_hz", 120.0)) <= 500.0

            compression = rule.get("compression")
            if compression:
                assert 1.0 <= float(compression["ratio"]) <= 20.0
                assert 0.0 < float(compression["attack_ms"]) <= 500.0
                assert 0.0 < float(compression["release_ms"]) <= 2_000.0
                assert -80.0 <= float(compression["threshold_db"]) <= 0.0

            for band in rule.get("eq_character", []):
                assert band["type"] in valid_eq_types
                assert 10.0 <= float(band["freq"]) <= 24_000.0
                assert 0.01 <= float(band.get("q", 0.707)) <= 20.0


@pytest.mark.parametrize(
    ("genre", "expected_goal", "expected_lufs", "expected_ceiling"),
    [
        ("edm", "club", -14.0, -0.5),
        ("hip_hop", "rap_vocal", -14.0, -1.0),
        ("pop", "pop_vocal", -14.0, -1.0),
        ("podcast", "podcast", -16.0, -1.0),
        ("jazz", "premaster", -14.0, -1.0),
    ],
)
def test_genre_uses_canonical_target_profile(genre, expected_goal, expected_lufs, expected_ceiling):
    plan = generate_mix_plan([_profile("vocal")], genre=genre, target_lufs=None)

    assert plan.mix_goal == expected_goal
    assert plan.target_lufs == expected_lufs
    assert plan.bus.limiter_ceiling_db == expected_ceiling
    assert any(f"({expected_goal})" in entry for entry in plan.decisions_log)


def test_explicit_loudness_target_overrides_genre_default():
    plan = generate_mix_plan([_profile("vocal")], genre="podcast", target_lufs=-18.0)
    assert plan.target_lufs == -18.0


def test_decision_log_contains_readable_summary_for_every_stem():
    profiles = [_profile(instrument) for instrument in INSTRUMENT_RULES]
    plan = generate_mix_plan(profiles, genre="pop")

    summaries = [entry for entry in plan.decisions_log if entry.startswith("Stem plan '")]
    assert len(summaries) == len(profiles)
    for profile in profiles:
        summary = next(entry for entry in summaries if f"'{profile.name}'" in entry)
        assert all(label in summary for label in ("gain", "pan", "EQ band", "compression", "reverb", "delay", "width"))


def test_generate_mix_plan():
    # Setup mock stem profiles
    profiles = [
        StemProfile(
            name="kick.wav",
            instrument="kick",
            peak_dbfs=-2.0,
            rms_dbfs=-15.0,
            crest_factor_db=13.0,
        ),
        StemProfile(
            name="snare.wav",
            instrument="snare",
            peak_dbfs=-4.0,
            rms_dbfs=-18.0,
            crest_factor_db=14.0,
        ),
        StemProfile(
            name="bass.wav",
            instrument="bass",
            peak_dbfs=-6.0,
            rms_dbfs=-16.0,
            crest_factor_db=10.0,
        ),
        StemProfile(
            name="vocal.wav",
            instrument="vocal",
            peak_dbfs=-3.0,
            rms_dbfs=-14.0,
            crest_factor_db=11.0,
        ),
    ]

    # Generate plan
    plan = generate_mix_plan(profiles, masking_results=None, genre="pop", target_lufs=-14.0)

    assert isinstance(plan, MixPlan)
    assert plan.genre == "pop"
    assert len(plan.stems) == 4
    
    # Verify kick is anchor (target peak for pop is -5.5 dBFS)
    kick_config = next(c for c in plan.stems if c.stem_name == "kick.wav")
    assert kick_config.gain_db == pytest.approx(-5.5 - (-2.0))

    # Verify vocal presence boost was added as character EQ
    vocal_config = next(c for c in plan.stems if c.stem_name == "vocal.wav")
    assert any(b["type"] == "highshelf" and b["frequency"] == 10000.0 for b in vocal_config.eq_bands)
    
    assert plan.bus.limiter_ceiling_db == -1.0
    assert len(plan.decisions_log) > 0


@pytest.mark.parametrize(
    ("instrument", "peak_dbfs", "rms_dbfs", "expected_direction"),
    [
        ("vocal", -50.0, -80.0, 1),
        ("snare", -50.0, -65.0, 1),
        ("vocal", -0.1, -1.0, -1),
    ],
)
def test_gain_staging_preserves_rough_mix_intent(
    instrument, peak_dbfs, rms_dbfs, expected_direction
):
    profiles = [
        StemProfile(
            name="kick.wav",
            instrument="kick",
            peak_dbfs=-5.5,
            rms_dbfs=-16.0,
            crest_factor_db=10.5,
        ),
        StemProfile(
            name=f"{instrument}.wav",
            instrument=instrument,
            peak_dbfs=peak_dbfs,
            rms_dbfs=rms_dbfs,
            crest_factor_db=12.0,
        ),
    ]

    plan = generate_mix_plan(profiles, genre="pop")
    config = next(stem for stem in plan.stems if stem.stem_name == f"{instrument}.wav")

    assert config.gain_db == pytest.approx(
        expected_direction * ROUGH_INTENT_MAX_GAIN_DEVIATION_DB
    )
    assert any(
        f"'{instrument}.wav'" in entry and "rough-intent limit" in entry
        for entry in plan.decisions_log
    )


def test_gain_staging_retains_role_target_inside_rough_intent_bounds():
    profiles = [
        StemProfile("kick.wav", "kick", peak_dbfs=-5.5, rms_dbfs=-16.0),
        StemProfile("vocal.wav", "vocal", peak_dbfs=-8.0, rms_dbfs=-17.0),
    ]

    plan = generate_mix_plan(profiles, genre="pop")
    vocal = next(stem for stem in plan.stems if stem.stem_name == "vocal.wav")

    assert vocal.gain_db == pytest.approx(2.5)


def test_spatial_send_profiles_and_low_frequency_mono_policy():
    plan = generate_mix_plan(
        [_profile(name) for name in ("kick", "bass", "vocal", "snare", "synth_pad", "strings")],
        genre="pop",
    )
    configs = {config.instrument: config for config in plan.stems}

    assert configs["kick"].reverb_send == 0.0
    assert configs["bass"].reverb_send == 0.0
    assert (configs["vocal"].reverb_type, configs["vocal"].reverb_decay_s) == ("plate", 1.6)
    assert configs["vocal"].reverb_send <= 0.25
    assert (configs["snare"].reverb_type, configs["snare"].reverb_decay_s) == ("room", 1.2)
    assert configs["snare"].reverb_send >= 0.15
    assert (configs["synth_pad"].reverb_type, configs["synth_pad"].reverb_decay_s) == ("hall", 3.2)
    assert (configs["strings"].reverb_type, configs["strings"].reverb_decay_s) == ("hall", 3.0)
    assert all(config.mono_below_hz == 120.0 for config in plan.stems)
    assert any("plate reverb" in entry for entry in plan.decisions_log)


def test_renderer_applies_mono_policy_per_stem(monkeypatch):
    sample_rate = 44_100
    samples = np.sin(2.0 * np.pi * 80.0 * np.arange(2_000) / sample_rate)
    profiles = [_profile("vocal"), _profile("snare"), _profile("synth_pad")]
    prepared = [
        {"name": profile.name, "samples": samples, "sample_rate": sample_rate}
        for profile in profiles
    ]
    plan = generate_mix_plan(profiles, genre="pop")

    calls = []
    original = mix_renderer.mono_below_frequency

    def tracked(left, right, cutoff_hz, sr):
        calls.append((cutoff_hz, sr))
        return original(left, right, cutoff_hz, sr)

    monkeypatch.setattr(mix_renderer, "mono_below_frequency", tracked)
    mix_and_render_stems(prepared, plan)

    assert calls == [(120.0, sample_rate)] * len(prepared)


def test_mix_and_render(monkeypatch):
    sample_rate = 44100
    duration_samples = 22050  # 0.5 seconds
    
    # Generate simple test signals (sine wave + noise)
    t = np.linspace(0, 0.5, duration_samples, endpoint=False)
    kick_samples = np.sin(2.0 * np.pi * 60.0 * t) * 0.5
    snare_samples = np.random.randn(duration_samples) * 0.1
    bass_samples = np.sin(2.0 * np.pi * 80.0 * t) * 0.4
    vocal_samples = np.sin(2.0 * np.pi * 440.0 * t) * 0.3

    prepared_stems = [
        {"name": "kick.wav", "samples": kick_samples.tolist(), "sample_rate": sample_rate},
        {"name": "snare.wav", "samples": snare_samples.tolist(), "sample_rate": sample_rate},
        {"name": "bass.wav", "samples": bass_samples.tolist(), "sample_rate": sample_rate},
        {"name": "vocal.wav", "samples": vocal_samples.tolist(), "sample_rate": sample_rate},
    ]

    profiles = [
        StemProfile(name="kick.wav", instrument="kick", peak_dbfs=-6.0, rms_dbfs=-18.0, crest_factor_db=12.0),
        StemProfile(name="snare.wav", instrument="snare", peak_dbfs=-20.0, rms_dbfs=-30.0, crest_factor_db=10.0),
        StemProfile(name="bass.wav", instrument="bass", peak_dbfs=-8.0, rms_dbfs=-20.0, crest_factor_db=12.0),
        StemProfile(name="vocal.wav", instrument="vocal", peak_dbfs=-10.0, rms_dbfs=-22.0, crest_factor_db=12.0),
    ]

    plan = generate_mix_plan(profiles, masking_results=None, genre="pop", target_lufs=-14.0)
    kick_config = next(config for config in plan.stems if config.instrument == "kick")
    kick_config.saturation_drive_db = 7.0
    kick_config.saturation_mix = 0.35
    saturation_calls = []
    original_saturation = mix_renderer.apply_saturation

    def tracked_saturation(samples, **kwargs):
        saturation_calls.append(kwargs)
        return original_saturation(samples, **kwargs)

    monkeypatch.setattr(mix_renderer, "apply_saturation", tracked_saturation)

    # Render
    result = mix_and_render_stems(prepared_stems, plan)

    assert "mixdown_wav_bytes" in result
    assert isinstance(result["mixdown_wav_bytes"], bytes)
    assert len(result["mixdown_wav_bytes"]) > 44  # Should be larger than header
    assert len(result["left"]) == duration_samples
    assert len(result["right"]) == duration_samples
    assert result["sample_rate"] == sample_rate
    assert any(call["drive_db"] == 7.0 and call["mix"] == 0.35 for call in saturation_calls)

    # Check peaks are limited below ceiling (-1.0 dBFS approx 0.891)
    max_peak = np.max(np.abs(np.vstack([result["left"], result["right"]])))
    assert max_peak <= 10.0 ** (-1.0 / 20.0) + 1e-4


# ---------------------------------------------------------------------------
# Stage K: dynamics_flags wiring (skip compressor on a stem with an
# existing, detected sidechain treatment)
# ---------------------------------------------------------------------------


def test_dynamics_flags_none_is_fully_backward_compatible():
    """Omitting dynamics_flags (the default) must produce an identical plan
    to today's behavior -- no stem is ever backed off unless a caller
    explicitly opts in with real detection results."""
    profiles = [_profile("bass"), _profile("kick")]
    plan_without_param = generate_mix_plan(profiles, genre="pop", target_lufs=-9.0)
    plan_with_none = generate_mix_plan(profiles, genre="pop", target_lufs=-9.0, dynamics_flags=None)

    bass_without = next(c for c in plan_without_param.stems if c.instrument == "bass")
    bass_with_none = next(c for c in plan_with_none.stems if c.instrument == "bass")
    assert bass_without.compressor == bass_with_none.compressor


def test_sidechain_detected_stem_skips_its_own_compressor():
    profiles = [_profile("bass"), _profile("kick")]
    dynamics_flags = {
        "bass.wav": {
            "sidechain_detected": True,
            "sidechain_trigger": "kick.wav",
            "sidechain_correlation": 0.71,
            "sidechain_mean_dip_db": 18.4,
        },
    }

    plan = generate_mix_plan(profiles, genre="pop", target_lufs=-9.0, dynamics_flags=dynamics_flags)

    bass_config = next(c for c in plan.stems if c.instrument == "bass")
    kick_config = next(c for c in plan.stems if c.instrument == "kick")

    assert bass_config.compressor is None, "a flagged stem's own compressor must be skipped entirely"
    assert kick_config.compressor is not None, "an unflagged stem's compressor must be unaffected"
    assert any("Skipped compressor" in d and "bass.wav" in d for d in plan.decisions_log)


def test_unflagged_stem_compression_is_unchanged_by_dynamics_flags_param():
    """A dynamics_flags dict that doesn't mention a given stem (or flags it
    False) must leave that stem's compressor exactly as it would be without
    the parameter at all."""
    profiles = [_profile("bass")]
    dynamics_flags = {"bass.wav": {"sidechain_detected": False}}

    plan_flagged_false = generate_mix_plan(profiles, genre="pop", target_lufs=-9.0, dynamics_flags=dynamics_flags)
    plan_no_flags = generate_mix_plan(profiles, genre="pop", target_lufs=-9.0)

    bass_flagged_false = next(c for c in plan_flagged_false.stems if c.instrument == "bass")
    bass_no_flags = next(c for c in plan_no_flags.stems if c.instrument == "bass")
    assert bass_flagged_false.compressor == bass_no_flags.compressor
