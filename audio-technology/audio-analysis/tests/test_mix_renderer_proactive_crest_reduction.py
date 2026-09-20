"""Wiring tests for the proactive crest-factor reduction stage in
mix_and_render_stems() (§10.4, gated by
MixPlan.apply_proactive_crest_reduction, default OFF).

_apply_proactive_crest_reduction's own math/behavior is tested directly in
test_proactive_crest_reduction.py; this file only verifies the render
pipeline actually wires the flag through, and — critically — that engaging
this stage never changes the final measured integrated LUFS, since the whole
point is to change density/shape at a *fixed* loudness, not the loudness
itself.
"""

from __future__ import annotations

import numpy as np

from audio_analysis.mixdown.stem_classifier import StemProfile
from audio_analysis.mixdown.mix_decision_engine import generate_mix_plan
from audio_analysis.mixdown.mix_renderer import mix_and_render_stems
from audio_analysis.analysis_core.loudness import calculate_loudness_profile

SR = 44100
DURATION_S = 5.0
N = int(SR * DURATION_S)


def _profile(name: str, instrument: str) -> StemProfile:
    return StemProfile(
        name=name, instrument=instrument, peak_dbfs=-3.0, rms_dbfs=-24.0, crest_factor_db=20.0,
    )


def _peaky_stem(seed: int = 1) -> tuple[np.ndarray, np.ndarray]:
    """Low sustained level with sparse sharp transient spikes -- a wide,
    easily measurable crest factor at the master bus, the situation this
    stage exists to correct."""
    rng = np.random.default_rng(seed)
    sustain = rng.normal(0, 0.04, N)
    signal = sustain.copy()
    for pos in rng.integers(0, N - 200, size=10):
        signal[pos:pos + 50] = 0.9
    return signal.astype(np.float64), signal.astype(np.float64)


def _plan(apply_correction: bool, target_lufs: float = -14.0):
    profile = _profile("lead.wav", "vocal")
    plan = generate_mix_plan([profile], genre="pop", target_lufs=target_lufs)
    plan.genre = "pop"
    plan.bus.limiter_ceiling_db = -1.0
    plan.apply_proactive_crest_reduction = apply_correction
    return plan


def _render(apply_correction: bool, target_lufs: float = -14.0):
    plan = _plan(apply_correction, target_lufs)
    left, right = _peaky_stem()
    stem_dicts = [{
        "name": "lead.wav", "sample_rate": SR,
        "samples": (left + right) * 0.5,
        "left_samples": left, "right_samples": right,
        "stereo_preserved": True,
    }]
    return mix_and_render_stems(stem_dicts, plan)


class TestProactiveCrestReductionGate:
    def test_disabled_by_default_does_not_engage(self) -> None:
        result = _render(apply_correction=False)
        diag = result["loudness_solver"]["proactive_crest_reduction"]
        assert diag == {"engaged": False}

    def test_enabled_on_peaky_material_engages(self) -> None:
        result = _render(apply_correction=True)
        diag = result["loudness_solver"]["proactive_crest_reduction"]
        assert diag["engaged"] is True
        assert diag["final_crest_db"] < diag["baseline_crest_db"]

    def test_enabled_changes_the_rendered_audio(self) -> None:
        off = _render(apply_correction=False)
        on = _render(apply_correction=True)
        diff = float(np.max(np.abs(on["left"] - off["left"])))
        assert diff > 1e-6, "proactive crest reduction should change the rendered audio"

    def test_final_integrated_lufs_is_unaffected_by_the_flag(self) -> None:
        """The whole point is density at a *fixed* loudness -- both renders
        must land on (very close to) the same target LUFS regardless of
        whether this stage engaged."""
        off = _render(apply_correction=False)
        on = _render(apply_correction=True)

        off_profile = calculate_loudness_profile(off["left"].tolist(), off["right"].tolist(), SR)
        on_profile = calculate_loudness_profile(on["left"].tolist(), on["right"].tolist(), SR)

        off_lufs = float(off_profile.get("integrated_lufs", -60.0))
        on_lufs = float(on_profile.get("integrated_lufs", -60.0))
        assert abs(off_lufs - on_lufs) < 0.3, (
            f"expected near-identical final LUFS regardless of the flag, "
            f"got off={off_lufs:.2f} on={on_lufs:.2f}"
        )

    def test_disabled_result_has_no_engagement_regardless_of_target(self) -> None:
        result = _render(apply_correction=False, target_lufs=-9.0)
        assert result["loudness_solver"]["proactive_crest_reduction"] == {"engaged": False}
