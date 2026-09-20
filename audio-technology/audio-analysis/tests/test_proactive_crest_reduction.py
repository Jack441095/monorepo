"""Tests for _apply_proactive_crest_reduction (§10.4, opt-in via
MixPlan.apply_proactive_crest_reduction, default OFF).

Closes a density gap fixed-LUFS normalization can't fix on its own: a mix can
already be far *louder* than its target pre-normalization (so the existing
reachability-gated _reduce_crest_factor_if_needed correctly never engages)
and still measure a real crest-factor/density gap against a commercial
reference at matched integrated loudness (docs/PROJECT_ACTION_PLAN_2026-07-14.md
§10.16 — stranger measured -18.2dB median RMS vs a reference's -11.6dB at the
same -14 LUFS integrated). This stage engages on measured crest factor alone,
independent of reachability.

Tests the pure function directly (real signal, real measurement) rather than
mocking the limiter primitive it reuses (_apply_peak_catching_prelimiter),
matching how the sibling reachability-gated function has no direct unit test
of its own but this one benefits from having one since it's a new trigger
condition, not just new wiring.
"""

from __future__ import annotations

import numpy as np

from audio_analysis.mixdown.mix_renderer import (
    _apply_proactive_crest_reduction,
    _measure_crest_factor_db,
    _PROACTIVE_CREST_TRIGGER_DB,
)

SR = 44100
DURATION_S = 4.0
N = int(SR * DURATION_S)


def _peaky_signal(seed: int = 1) -> tuple[np.ndarray, np.ndarray]:
    """Low sustained level with occasional sharp, brief transient spikes --
    a wide, easily-measurable crest factor, like a lightly-arranged mix with
    a few loud transient hits and otherwise low RMS (the "peaky, thin at
    matched loudness" problem this stage targets)."""
    rng = np.random.default_rng(seed)
    sustain = rng.normal(0, 0.05, N)
    signal = sustain.copy()
    spike_positions = rng.integers(0, N - 200, size=8)
    for pos in spike_positions:
        signal[pos:pos + 50] = 0.95
    return signal.astype(np.float64), signal.astype(np.float64)


def _dense_signal(seed: int = 2) -> tuple[np.ndarray, np.ndarray]:
    """Already-dense, narrow-crest-factor signal (loud, sustained noise near
    its own peak) -- should not trigger any reduction."""
    rng = np.random.default_rng(seed)
    signal = rng.normal(0, 0.3, N)
    signal = np.clip(signal, -0.9, 0.9).astype(np.float64)
    return signal, signal.copy()


def test_peaky_signal_measures_above_trigger_threshold():
    left, right = _peaky_signal()
    crest_db = _measure_crest_factor_db(left, right)
    assert crest_db > _PROACTIVE_CREST_TRIGGER_DB, (
        f"fixture crest factor {crest_db:.2f}dB should exceed the "
        f"{_PROACTIVE_CREST_TRIGGER_DB}dB trigger for this test to be meaningful"
    )


def test_engages_and_reduces_crest_factor_on_peaky_material():
    left, right = _peaky_signal()
    baseline_crest_db = _measure_crest_factor_db(left, right)

    out_l, out_r, diag = _apply_proactive_crest_reduction(left, right, SR)

    assert diag["engaged"] is True
    assert diag["baseline_crest_db"] == baseline_crest_db
    assert diag["final_crest_db"] < baseline_crest_db
    assert diag["attempts"], "expected at least one candidate attempt logged"

    final_crest_db = _measure_crest_factor_db(out_l, out_r)
    assert final_crest_db < baseline_crest_db
    assert abs(final_crest_db - diag["final_crest_db"]) < 0.5


def test_never_returns_a_worse_crest_factor_than_input():
    left, right = _peaky_signal()
    out_l, out_r, diag = _apply_proactive_crest_reduction(left, right, SR)
    assert _measure_crest_factor_db(out_l, out_r) <= diag["baseline_crest_db"]


def test_noop_on_already_dense_material():
    left, right = _dense_signal()
    baseline_crest_db = _measure_crest_factor_db(left, right)
    assert baseline_crest_db <= _PROACTIVE_CREST_TRIGGER_DB, (
        f"fixture crest factor {baseline_crest_db:.2f}dB should already be at/under "
        f"the {_PROACTIVE_CREST_TRIGGER_DB}dB trigger for this test to be meaningful"
    )

    out_l, out_r, diag = _apply_proactive_crest_reduction(left, right, SR)

    assert diag["engaged"] is False
    assert diag["final_crest_db"] == diag["baseline_crest_db"]
    assert diag["attempts"] == []
    # No-op means the identical arrays come back, not just numerically equal.
    assert out_l is left
    assert out_r is right


def test_diagnostics_shape_always_present():
    left, right = _dense_signal()
    _, _, diag = _apply_proactive_crest_reduction(left, right, SR)
    assert set(diag.keys()) == {"engaged", "baseline_crest_db", "final_crest_db", "attempts"}
