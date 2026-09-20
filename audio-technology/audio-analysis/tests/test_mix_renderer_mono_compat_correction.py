"""Tests for the mono-compatibility correction stage in mix_and_render_stems().

Closes the "detected phase/fold-down risk but never corrected" gap, ear-confirmed
on real material (docs/audits/2026-07-17-stranger-v6-listening-findings.md —
DRUM_BREAK.wav, correlation ~0.05-0.10, source-material decorrelation, not a
pipeline bug). A bounded additional stereo-narrowing pass is applied to any stem
the mono-compatibility detector flagged warning/critical, gated by
MixPlan.apply_mono_compat_correction (default OFF).

Verifies the wiring only — apply_stereo_width's own math is tested elsewhere.
"""

from __future__ import annotations

import numpy as np

from audio_analysis.mixdown.stem_classifier import StemProfile
from audio_analysis.mixdown.mix_decision_engine import generate_mix_plan
from audio_analysis.mixdown.mix_renderer import (
    mix_and_render_stems,
    _MONO_COMPAT_CORRECTION_FACTOR,
)

SR = 44100
DURATION_S = 6.0
N = int(SR * DURATION_S)
_T = np.arange(N) / SR


def _profile(name: str, instrument: str) -> StemProfile:
    return StemProfile(
        name=name, instrument=instrument, peak_dbfs=-6.0, rms_dbfs=-18.0, crest_factor_db=12.0,
    )


def _decorrelated_stereo_tone(freq: float, seed: int = 1) -> tuple[np.ndarray, np.ndarray]:
    """Two independent noisy sine-based channels -- low correlation, like the
    real DRUM_BREAK case (a wide, naturally decorrelated stereo element)."""
    rng_l = np.random.default_rng(seed)
    rng_r = np.random.default_rng(seed + 100)
    base = np.sin(2 * np.pi * freq * _T)
    left = (base * 0.3 + rng_l.normal(0, 1, N) * 0.2).astype(np.float64)
    right = (base * 0.3 + rng_r.normal(0, 1, N) * 0.2).astype(np.float64)
    return left, right


def _mono_compat_dict(stem_name: str, severity: str) -> dict:
    """A minimal mono_compatibility dict shaped like analyze_mono_compatibility's
    to_dict(), flagging one stem."""
    return {
        "stems": [
            {"stem_name": stem_name, "severity": severity, "reasons": ["material_fold_down_loss"]},
        ],
    }


def _plan(stems_and_instruments, mono_compatibility, apply_correction):
    profiles = [_profile(name, instrument) for name, instrument, *_ in stems_and_instruments]
    plan = generate_mix_plan(profiles, genre="pop", target_lufs=-12.0)
    plan.genre = "pop"
    plan.bus.limiter_ceiling_db = -1.0
    plan.mono_compatibility = mono_compatibility
    plan.apply_mono_compat_correction = apply_correction
    return plan


def _render(stems_and_instruments, mono_compatibility, apply_correction):
    plan = _plan(stems_and_instruments, mono_compatibility, apply_correction)
    stem_dicts = []
    for name, _instrument, left, right in stems_and_instruments:
        stem_dicts.append({
            "name": name, "sample_rate": SR,
            "samples": (left + right) * 0.5,
            "left_samples": left, "right_samples": right,
            "stereo_preserved": True,
        })
    return mix_and_render_stems(stem_dicts, plan)


def _stems():
    l1, r1 = _decorrelated_stereo_tone(6000.0, seed=1)
    l2, r2 = _decorrelated_stereo_tone(300.0, seed=2)
    return [
        ("drum_break.wav", "percussion", l1, r1),
        ("bass.wav", "bass", l2, r2),
    ]


class TestMonoCompatCorrectionGate:
    def test_disabled_by_default_applies_nothing(self) -> None:
        mc = _mono_compat_dict("drum_break.wav", "warning")
        result = _render(_stems(), mc, apply_correction=False)
        assert result["mono_compat_corrections"] == {}

    def test_enabled_applies_correction_to_flagged_stem(self) -> None:
        mc = _mono_compat_dict("drum_break.wav", "warning")
        result = _render(_stems(), mc, apply_correction=True)
        assert "drum_break.wav" in result["mono_compat_corrections"]
        applied = result["mono_compat_corrections"]["drum_break.wav"]
        assert applied["severity"] == "warning"
        assert applied["correction_factor"] == _MONO_COMPAT_CORRECTION_FACTOR["warning"]

    def test_unflagged_stem_is_never_touched(self) -> None:
        mc = _mono_compat_dict("drum_break.wav", "warning")
        result = _render(_stems(), mc, apply_correction=True)
        assert "bass.wav" not in result["mono_compat_corrections"]

    def test_critical_gets_a_stronger_correction_than_warning(self) -> None:
        assert _MONO_COMPAT_CORRECTION_FACTOR["critical"] < _MONO_COMPAT_CORRECTION_FACTOR["warning"]

    def test_pass_severity_is_not_corrected(self) -> None:
        mc = _mono_compat_dict("drum_break.wav", "pass")
        result = _render(_stems(), mc, apply_correction=True)
        assert result["mono_compat_corrections"] == {}

    def test_enabled_changes_the_audio(self) -> None:
        mc = _mono_compat_dict("drum_break.wav", "critical")
        off = _render(_stems(), mc, apply_correction=False)
        on = _render(_stems(), mc, apply_correction=True)
        diff = float(np.max(np.abs(on["left"] - off["left"])))
        assert diff > 1e-6, "mono-compat correction should change the rendered audio"

    def test_correction_narrows_not_eliminates_the_side_signal(self) -> None:
        """Floor check: even at 'critical', the flagged stem must not be fully
        collapsed to mono in the captured per-stem audio -- narrowed, not erased."""
        mc = _mono_compat_dict("drum_break.wav", "critical")
        plan = _plan(_stems(), mc, apply_correction=True)
        stem_dicts = []
        for name, _instrument, left, right in _stems():
            stem_dicts.append({
                "name": name, "sample_rate": SR,
                "samples": (left + right) * 0.5,
                "left_samples": left, "right_samples": right,
                "stereo_preserved": True,
            })
        result = mix_and_render_stems(stem_dicts, plan, capture_stem_audio=True)
        s_l, s_r = result["stem_audio"]["drum_break.wav"]
        side = 0.5 * (s_l - s_r)
        assert float(np.max(np.abs(side))) > 1e-6, "side signal should survive, not be zeroed"

    def test_render_still_valid_with_correction_engaged(self) -> None:
        mc = _mono_compat_dict("drum_break.wav", "warning")
        result = _render(_stems(), mc, apply_correction=True)
        assert isinstance(result["mixdown_wav_bytes"], bytes)
        assert result["sample_rate"] == SR
        max_peak = float(np.max(np.abs(np.vstack([result["left"], result["right"]]))))
        assert max_peak <= 1.0 + 1e-6

    def test_no_mono_compatibility_data_is_a_safe_no_op(self) -> None:
        plan = _plan(_stems(), mono_compatibility={}, apply_correction=True)
        stem_dicts = []
        for name, _instrument, left, right in _stems():
            stem_dicts.append({
                "name": name, "sample_rate": SR,
                "samples": (left + right) * 0.5,
                "left_samples": left, "right_samples": right,
                "stereo_preserved": True,
            })
        result = mix_and_render_stems(stem_dicts, plan)
        assert result["mono_compat_corrections"] == {}
