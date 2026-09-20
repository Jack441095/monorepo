"""Tests for business/app/automix_worker.py's opt-in engine-correction logic
and its per-stem before/after comparison.

_process_job() itself is a large, DB/job-queue-integrated function with no
existing unit-test seam (see test_automix_local.py's own docstring on why
the underlying DSP pipeline is tested elsewhere). apply_opt_in_engine_corrections
and build_per_stem_before_after were both pulled out as small, pure(-ish)
functions specifically so this logic has real test coverage rather than
being untestable inline code.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np

import automix_worker
from audio_analysis.mixdown.mix_decision_engine import generate_mix_plan
from audio_analysis.mixdown.mix_renderer import render_unprocessed_stem_sum
from audio_analysis.mixdown.stem_classifier import StemProfile

SR = 44100
DURATION_S = 6.0
_N = int(SR * DURATION_S)
_T = np.arange(_N) / SR


def _fake_plan() -> SimpleNamespace:
    return SimpleNamespace(
        apply_masking_corrections=False,
        apply_mono_compat_correction=False,
        apply_proactive_crest_reduction=False,
        apply_deesser=False,
        decisions_log=[],
    )


def test_all_flags_off_by_default_with_empty_style_prefs() -> None:
    plan = _fake_plan()
    automix_worker.apply_opt_in_engine_corrections(plan, {})
    assert plan.apply_masking_corrections is False
    assert plan.apply_mono_compat_correction is False
    assert plan.apply_proactive_crest_reduction is False
    assert plan.apply_deesser is False
    assert plan.decisions_log == []


def test_masking_corrections_opt_in() -> None:
    plan = _fake_plan()
    automix_worker.apply_opt_in_engine_corrections(plan, {"masking_corrections": True})
    assert plan.apply_masking_corrections is True
    assert plan.apply_mono_compat_correction is False
    assert plan.apply_proactive_crest_reduction is False
    assert any("Masking corrections enabled" in entry for entry in plan.decisions_log)


def test_mono_compat_correction_opt_in() -> None:
    plan = _fake_plan()
    automix_worker.apply_opt_in_engine_corrections(plan, {"mono_compat_correction": True})
    assert plan.apply_mono_compat_correction is True
    assert plan.apply_masking_corrections is False
    assert any("Mono-compatibility correction enabled" in entry for entry in plan.decisions_log)


def test_proactive_crest_reduction_opt_in() -> None:
    plan = _fake_plan()
    automix_worker.apply_opt_in_engine_corrections(plan, {"proactive_crest_reduction": True})
    assert plan.apply_proactive_crest_reduction is True
    assert any("Proactive crest-factor reduction enabled" in entry for entry in plan.decisions_log)


def test_deesser_opt_in() -> None:
    plan = _fake_plan()
    automix_worker.apply_opt_in_engine_corrections(plan, {"deesser": True})
    assert plan.apply_deesser is True
    assert any("De-esser sibilance control enabled" in entry for entry in plan.decisions_log)


def test_all_three_opt_in_together() -> None:
    plan = _fake_plan()
    automix_worker.apply_opt_in_engine_corrections(
        plan,
        {
            "masking_corrections": True,
            "mono_compat_correction": True,
            "proactive_crest_reduction": True,
        },
    )
    assert plan.apply_masking_corrections is True
    assert plan.apply_mono_compat_correction is True
    assert plan.apply_proactive_crest_reduction is True
    assert len(plan.decisions_log) == 3


def test_explicit_false_does_not_enable() -> None:
    plan = _fake_plan()
    automix_worker.apply_opt_in_engine_corrections(
        plan, {"masking_corrections": False, "mono_compat_correction": False, "proactive_crest_reduction": False},
    )
    assert plan.apply_masking_corrections is False
    assert plan.apply_mono_compat_correction is False
    assert plan.apply_proactive_crest_reduction is False
    assert plan.decisions_log == []


def test_unrelated_style_prefs_keys_are_ignored() -> None:
    """The rest of style_prefs (sliders, feedback text, etc.) must not
    accidentally trip these flags -- only the exact opt-in keys matter."""
    plan = _fake_plan()
    automix_worker.apply_opt_in_engine_corrections(
        plan,
        {"bright_warm": 0.9, "dry_wet": 1.0, "feedback": "make it louder", "narrow_wide": 1.0},
    )
    assert plan.apply_masking_corrections is False
    assert plan.apply_mono_compat_correction is False
    assert plan.apply_proactive_crest_reduction is False


def test_truthy_non_bool_values_are_accepted() -> None:
    """style_prefs arrives as parsed JSON from the client -- a client could
    plausibly send "true"/1 instead of a JSON boolean. bool() coercion means
    any truthy value opts in, matching how the rest of this codebase treats
    loosely-typed client input."""
    plan = _fake_plan()
    automix_worker.apply_opt_in_engine_corrections(plan, {"masking_corrections": 1})
    assert plan.apply_masking_corrections is True


def test_resource_snapshot_is_safe_and_uses_bytes_for_memory() -> None:
    """The offline telemetry helper must never make a render fail."""
    snapshot = automix_worker._resource_snapshot(started_at=0.0)

    assert snapshot["elapsed_ms"] >= 0
    assert snapshot["peak_rss_bytes"] is None or snapshot["peak_rss_bytes"] > 0


def test_take_probe_wav_releases_unneeded_render_buffers() -> None:
    render_result = {
        "mixdown_wav_bytes": b"RIFF-probe",
        "left": np.zeros(16),
        "right": np.zeros(16),
        "stem_audio": {"kick": (np.zeros(16), np.zeros(16))},
    }

    assert automix_worker._take_probe_wav(render_result) == b"RIFF-probe"
    assert render_result == {}


def test_take_probe_wav_rejects_invalid_renderer_output() -> None:
    with np.testing.assert_raises_regex(RuntimeError, "did not produce WAV"):
        automix_worker._take_probe_wav({"mixdown_wav_bytes": bytearray(b"not-immutable")})


def test_reference_width_policy_skips_third_render_after_tonal_matching() -> None:
    plan = SimpleNamespace(bus=SimpleNamespace(reference_width_factor=1.0), decisions_log=[])
    called = False

    def should_not_be_called(*_args):
        nonlocal called
        called = True
        return 1.1

    result = automix_worker.apply_reference_width_policy(
        plan,
        match_bands=[{"frequency": 100.0}],
        probe_wav_bytes=b"probe",
        reference_path=Path("reference.wav"),
        compute_width_factor=should_not_be_called,
    )

    assert result == {"applied": False, "reason": "third_render_budget"}
    assert called is False
    assert plan.bus.reference_width_factor == 1.0
    assert "third whole-project probe" in plan.decisions_log[0]


def test_reference_width_policy_uses_existing_probe_without_tonal_bands() -> None:
    plan = SimpleNamespace(bus=SimpleNamespace(reference_width_factor=1.0), decisions_log=[])
    result = automix_worker.apply_reference_width_policy(
        plan,
        match_bands=[],
        probe_wav_bytes=b"probe",
        reference_path=Path("reference.wav"),
        compute_width_factor=lambda wav, ref: 1.08 if wav == b"probe" and ref.name == "reference.wav" else None,
    )

    assert result == {"applied": True, "factor": 1.08}
    assert plan.bus.reference_width_factor == 1.08


def test_reference_match_budget_skips_long_project_without_explicit_opt_in(monkeypatch) -> None:
    monkeypatch.setattr(automix_worker, "REFERENCE_MATCH_MAX_DURATION_SECONDS", 10.0)
    stems = [{"samples": np.zeros(441_100), "sample_rate": 44_100}]

    decision = automix_worker.reference_match_budget_decision(stems, {})

    assert decision["allowed"] is False
    assert decision["duration_seconds"] > 10.0
    assert decision["reason"] == "duration_budget_exceeded"


def test_reference_match_budget_allows_explicit_long_render_opt_in(monkeypatch) -> None:
    monkeypatch.setattr(automix_worker, "REFERENCE_MATCH_MAX_DURATION_SECONDS", 10.0)
    stems = [{"samples": np.zeros(441_001), "sample_rate": 44_100}]

    decision = automix_worker.reference_match_budget_decision(stems, {"allow_long_reference_match": True})

    assert decision["allowed"] is True
    assert decision["explicit_opt_in"] is True


def _tone_stem(name: str, instrument: str, freq: float) -> tuple[StemProfile, dict]:
    samples = (0.2 * np.sin(2 * np.pi * freq * _T)).astype(np.float64)
    profile = StemProfile(name=name, instrument=instrument, peak_dbfs=-6.0, rms_dbfs=-18.0, crest_factor_db=12.0)
    prepared = {"name": name, "sample_rate": SR, "samples": samples}
    return profile, prepared


def _real_plan_and_prepared_stems():
    kick_profile, kick_stem = _tone_stem("kick.wav", "kick", 60.0)
    bass_profile, bass_stem = _tone_stem("bass.wav", "bass", 110.0)
    plan = generate_mix_plan([kick_profile, bass_profile], genre="pop", target_lufs=-14.0)
    plan.genre = "pop"
    plan.mix_goal = "premaster"
    plan.bus.limiter_ceiling_db = -1.0
    return plan, [kick_stem, bass_stem]


def test_build_per_stem_before_after_returns_a_comparison_per_stem() -> None:
    plan, prepared_stems = _real_plan_and_prepared_stems()
    source_stem_audio = render_unprocessed_stem_sum(prepared_stems)["stem_audio"]

    result = automix_worker.build_per_stem_before_after(
        prepared_stems, plan, source_stem_audio, SR, mix_goal="premaster",
    )

    assert result["stems_total"] == 2
    assert result["stems_truncated"] is False
    assert set(result["stems"]) == {"kick.wav", "bass.wav"}
    for stem_comparison in result["stems"].values():
        assert set(stem_comparison) == {"before", "after", "deltas"}
        assert set(stem_comparison["before"]["bands"]) == {
            "sub", "bass", "low_mids", "mids", "presence", "sibilance", "air",
        }


def test_build_per_stem_before_after_truncates_beyond_the_cap(monkeypatch) -> None:
    monkeypatch.setattr(automix_worker, "MAX_PER_STEM_COMPARISON", 1)
    plan, prepared_stems = _real_plan_and_prepared_stems()
    source_stem_audio = render_unprocessed_stem_sum(prepared_stems)["stem_audio"]

    result = automix_worker.build_per_stem_before_after(
        prepared_stems, plan, source_stem_audio, SR, mix_goal="premaster",
    )

    assert result["stems_total"] == 2
    assert result["stems_truncated"] is True
    assert len(result["stems"]) == 1


def test_build_per_stem_before_after_only_includes_stems_with_a_plan_config() -> None:
    plan, prepared_stems = _real_plan_and_prepared_stems()
    source_stem_audio = render_unprocessed_stem_sum(prepared_stems)["stem_audio"]
    # A stem with no matching plan config (and no "other" fallback) never
    # reaches the mixer's stem_audio capture -- must be excluded, not raise.
    source_stem_audio["ghost.wav"] = source_stem_audio["kick.wav"]

    result = automix_worker.build_per_stem_before_after(
        prepared_stems, plan, source_stem_audio, SR, mix_goal="premaster",
    )

    assert "ghost.wav" not in result["stems"]
    assert result["stems_total"] == 2
