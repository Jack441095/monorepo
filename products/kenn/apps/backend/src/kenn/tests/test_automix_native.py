"""Unit, parity, and boundary qualification tests for the native AutoMix C++ DSP kernels.

Covers the six recovered C++ kernels exposed via ``kenn.core.automix_native``:
- limiter (sliding lookahead maximum + release one-pole)
- biquad (Direct Form II Transposed cascaded SOS)
- correlation (lag-windowed Pearson cross-correlation)
- smooth (asymmetric attack/release one-pole envelope)
- gate (hysteresis hold and attack/release gain envelope)
- threshold (per-frame rolling median + MAD adaptive threshold)

Tests verify numerical contracts against analytical expectations and ensure
fail-fast rejection on malformed inputs (NaN/Inf samples, empty buffers, negative
coefficients, unstable filter poles, and extreme lookahead/lag parameters).
"""

from __future__ import annotations

import math
import numpy as np
import pytest

from kenn.core import automix_native


@pytest.fixture(autouse=True)
def _ensure_native_enabled(monkeypatch):
    """Enable native AutoMix dispatch for the test suite, resetting cached module load."""
    monkeypatch.setenv("KENN_DSP_NATIVE", "1")
    monkeypatch.setattr(automix_native, "_native", None)
    monkeypatch.setattr(automix_native, "_load_attempted", False)


def test_automix_native_available_reports_true_when_extension_built():
    """Contract: available() returns True when the native extension is loaded and enabled."""
    assert automix_native.available() is True


def test_automix_native_abstains_when_disabled_via_flag(monkeypatch):
    """Contract: KENN_DSP_NATIVE=0 disables dispatch and returns None across all kernels."""
    monkeypatch.setenv("KENN_DSP_NATIVE", "0")
    monkeypatch.setattr(automix_native, "_native", None)
    monkeypatch.setattr(automix_native, "_load_attempted", False)

    assert automix_native.available() is False
    assert automix_native.limiter([0.5], input_gain=1.0, ceiling_lin=1.0, alpha_rel=0.9, lookahead=1) is None
    assert automix_native.biquad([[1.0, 0.0, 0.0, 1.0, 0.0, 0.0]], [0.5]) is None
    assert automix_native.correlation([0.5], [0.5], max_lag=1) is None
    assert automix_native.smooth([0.5], alpha_att=0.1, alpha_rel=0.9, init=0.0, attack_when_less=False) is None
    assert automix_native.gate([0.5], threshold=0.1, alpha_att=0.1, alpha_rel=0.9, hold_samples=1, target_gain_open=1.0, target_gain_closed=0.0) is None
    assert automix_native.threshold([0.5], radius=2, min_floor=0.01, mad_multiplier=3.0) is None


# ---------------------------------------------------------------------------
# 1. Limiter Kernel Tests
# ---------------------------------------------------------------------------

def test_limiter_gain_envelope_restricts_output_to_linear_ceiling():
    """Verify that input overshoots are clamped to ceiling_lin with instant attack."""
    # 256 samples with an overshoot burst of 2.0 linear (approx +6.02 dBFS)
    # between sample 64 and 128.
    samples = np.zeros(256, dtype=np.float64)
    samples[64:128] = 2.0
    ceiling = 1.0  # 0.0 dBFS ceiling
    alpha_rel = 0.95  # moderate release decay per sample

    result = automix_native.limiter(
        samples, input_gain=1.0, ceiling_lin=ceiling, alpha_rel=alpha_rel, lookahead=8
    )
    assert result is not None
    audio = np.asarray(result["audio"], dtype=np.float64)
    gain = np.asarray(result["gain"], dtype=np.float64)

    # Maximum output magnitude must never exceed the linear ceiling + numerical epsilon
    assert float(np.max(np.abs(audio))) <= ceiling + 1e-12

    # During the 2.0 burst, target gain is ceiling / peak = 1.0 / 2.0 = 0.5
    assert float(np.min(gain[64:128])) <= 0.5 + 1e-12

    # After sample 128, release one-pole recovers smoothly back toward 1.0
    assert float(gain[200]) > float(gain[130])


def test_limiter_handles_extreme_lookahead_without_oom_or_hang():
    """Lookahead exceeding sample count must clamp to buffer length without hanging."""
    # 64 samples with lookahead = 500,000 samples (far exceeds length)
    samples = np.ones(64, dtype=np.float64) * 0.8
    result = automix_native.limiter(
        samples, input_gain=1.0, ceiling_lin=0.5, alpha_rel=0.9, lookahead=500_000
    )
    assert result is not None
    audio = np.asarray(result["audio"])
    assert len(audio) == 64
    assert float(np.max(audio)) <= 0.5 + 1e-12


@pytest.mark.parametrize(
    ("bad_input", "error_match"),
    [
        (np.array([], dtype=np.float64), "non-empty"),
        (np.array([1.0, np.nan, 0.5]), "NaN or infinite"),
        (np.array([1.0, np.inf, 0.5]), "NaN or infinite"),
    ],
)
def test_limiter_rejects_malformed_input_buffers(bad_input, error_match):
    """Ensure invalid buffers raise clean ValueError before DSP execution."""
    with pytest.raises(ValueError, match=error_match):
        automix_native.limiter(bad_input, input_gain=1.0, ceiling_lin=1.0, alpha_rel=0.9, lookahead=4)


@pytest.mark.parametrize(
    ("kwargs", "error_match"),
    [
        ({"input_gain": -1.0, "ceiling_lin": 1.0, "alpha_rel": 0.9, "lookahead": 4}, "input_gain"),
        ({"input_gain": 0.0, "ceiling_lin": 1.0, "alpha_rel": 0.9, "lookahead": 4}, "input_gain"),
        ({"input_gain": 1.0, "ceiling_lin": -0.5, "alpha_rel": 0.9, "lookahead": 4}, "ceiling_lin"),
        ({"input_gain": 1.0, "ceiling_lin": 1.0, "alpha_rel": 1.0, "lookahead": 4}, "alpha_rel"),
        ({"input_gain": 1.0, "ceiling_lin": 1.0, "alpha_rel": -0.1, "lookahead": 4}, "alpha_rel"),
        ({"input_gain": 1.0, "ceiling_lin": 1.0, "alpha_rel": 0.9, "lookahead": 0}, "lookahead"),
    ],
)
def test_limiter_rejects_out_of_bounds_parameters(kwargs, error_match):
    """Ensure invalid gain, ceiling, alpha, or lookahead raise ValueError."""
    samples = np.ones(64, dtype=np.float64)
    with pytest.raises(ValueError, match=error_match):
        automix_native.limiter(samples, **kwargs)


# ---------------------------------------------------------------------------
# 2. Biquad Cascaded SOS Filter Tests
# ---------------------------------------------------------------------------

def test_biquad_identity_section_preserves_signal():
    """Identity section [1, 0, 0, 1, 0, 0] must pass input bit-identically."""
    # 128 samples of deterministic sine wave
    t = np.linspace(0, 1.0, 128, endpoint=False)
    signal = np.sin(2.0 * np.pi * 5.0 * t)
    identity_sos = np.array([[1.0, 0.0, 0.0, 1.0, 0.0, 0.0]], dtype=np.float64)

    filtered = automix_native.biquad(identity_sos, signal)
    assert filtered is not None
    np.testing.assert_allclose(filtered, signal, rtol=1e-12, atol=1e-12)


def test_biquad_normalizes_unnormalized_sos_section():
    """A section where a0 != 1.0 is normalized by a0 prior to filtering."""
    # Section with overall gain of 2.0 scaled by a0 = 2.0:
    # b = [2.0, 0.0, 0.0], a = [2.0, 0.0, 0.0] -> transfer function H(z) = 1.0
    signal = np.array([1.0, -0.5, 0.25, -0.125], dtype=np.float64)
    scaled_sos = np.array([[2.0, 0.0, 0.0, 2.0, 0.0, 0.0]], dtype=np.float64)

    filtered = automix_native.biquad(scaled_sos, signal)
    assert filtered is not None
    np.testing.assert_allclose(filtered, signal, rtol=1e-12, atol=1e-12)


def test_biquad_rejects_unstable_poles_blowing_up_to_infinity():
    """Unstable filter producing non-finite output must raise ValueError rather than propagate infs."""
    # Strongly unstable pole at z = 3.0 (a1 = -3.0): over 2000 samples, 3^2000 blows past 1e308 IEEE-754 double limit
    unstable_sos = np.array([[1.0, 0.0, 0.0, 1.0, -3.0, 0.0]], dtype=np.float64)
    signal = np.ones(2000, dtype=np.float64)
    with pytest.raises(ValueError, match="non-finite"):
        automix_native.biquad(unstable_sos, signal)


@pytest.mark.parametrize(
    ("bad_sos", "error_match"),
    [
        (np.array([], dtype=np.float64), "shape"),
        (np.zeros((1, 5), dtype=np.float64), "shape"),
        (np.array([[1.0, 0.0, 0.0, 0.0, 0.0, 0.0]]), "a0 coefficient must be non-zero"),
        (np.array([[1.0, np.nan, 0.0, 1.0, 0.0, 0.0]]), "NaN or infinite"),
    ],
)
def test_biquad_rejects_malformed_sos_matrix(bad_sos, error_match):
    """Ensure malformed SOS matrices raise ValueError."""
    signal = np.ones(32, dtype=np.float64)
    with pytest.raises(ValueError, match=error_match):
        automix_native.biquad(bad_sos, signal)


# ---------------------------------------------------------------------------
# 3. Correlation Kernel Tests
# ---------------------------------------------------------------------------

def test_correlation_finds_exact_phase_delay_and_unit_peak():
    """Cross-correlation of delayed signal matches known integer sample shift."""
    # Deterministic noise burst of 128 samples
    rng = np.random.default_rng(0x4B454E4E)
    signal = rng.standard_normal(128)

    # Shift right by 4 samples (lag = +4)
    shift = 4
    delayed = np.zeros_like(signal)
    delayed[shift:] = signal[:-shift]

    result = automix_native.correlation(signal, delayed, max_lag=16)
    assert result is not None
    # Best lag should recover the exact relative offset
    assert abs(int(result["lag"])) == shift
    assert float(result["correlation"]) > 0.85


def test_correlation_bounds_huge_max_lag_without_spinning():
    """max_lag far exceeding buffer length is clamped cleanly to valid lag window."""
    signal = np.sin(np.linspace(0, 10.0, 64))
    result = automix_native.correlation(signal, signal, max_lag=500_000)
    assert result is not None
    assert int(result["lag"]) == 0
    assert math.isclose(float(result["correlation"]), 1.0, abs_tol=1e-12)


def test_correlation_returns_zero_on_pure_dc():
    """Zero variance signal returns zero correlation without division by zero."""
    dc = np.ones(64, dtype=np.float64) * 0.42
    result = automix_native.correlation(dc, dc, max_lag=8)
    assert result is not None
    assert float(result["correlation"]) == 0.0
    assert int(result["lag"]) == 0


def test_correlation_rejects_mismatched_lengths():
    """Mismatched left and right channels raise ValueError."""
    left = np.zeros(64, dtype=np.float64)
    right = np.zeros(65, dtype=np.float64)
    with pytest.raises(ValueError, match="equal lengths"):
        automix_native.correlation(left, right, max_lag=8)


# ---------------------------------------------------------------------------
# 4. Smooth Attack/Release Envelope Tests
# ---------------------------------------------------------------------------

def test_smooth_tracks_step_transition_with_specified_coefficients():
    """Smooth one-pole follows instant attack and exponential release for gain reductions."""
    # In dynamics (attack_when_less=False), ducking gain (target <= current) is attack,
    # and releasing back up toward 1.0 is release.
    gain_target = np.ones(128, dtype=np.float64)
    gain_target[10:60] = 0.2  # Gain reduction event

    smoothed = automix_native.smooth(
        gain_target, alpha_att=0.0, alpha_rel=0.9, init=1.0, attack_when_less=False
    )
    assert smoothed is not None
    values = np.asarray(smoothed)

    # Instant attack: index 10 immediately ducks from 1.0 to 0.2
    assert math.isclose(float(values[10]), 0.2, abs_tol=1e-12)

    # Exponential release: index 60 starts recovering from 0.2 toward 1.0
    # 0.9 * 0.2 + 0.1 * 1.0 = 0.28
    assert math.isclose(float(values[60]), 0.28, abs_tol=1e-12)


@pytest.mark.parametrize(
    ("bad_alpha", "error_match"),
    [
        (-0.1, "alpha_att"),
        (1.1, "alpha_att"),
        (np.nan, "alpha_att"),
    ],
)
def test_smooth_rejects_invalid_alpha(bad_alpha, error_match):
    """Coefficients outside [0.0, 1.0] raise ValueError."""
    with pytest.raises(ValueError, match=error_match):
        automix_native.smooth(np.ones(10), alpha_att=bad_alpha, alpha_rel=0.5, init=0.0, attack_when_less=False)


# ---------------------------------------------------------------------------
# 5. Gate Envelope Tests
# ---------------------------------------------------------------------------

def test_gate_opens_on_threshold_and_holds_before_releasing():
    """Gate opens when level exceeds threshold, remains open for hold_samples, then releases."""
    # Levels in dBFS: silent (-90 dBFS), loud burst (-10 dBFS for 10 samples), then silent (-90 dBFS)
    levels = np.full(64, -90.0, dtype=np.float64)
    levels[10:20] = -10.0
    threshold_db = -30.0
    hold = 5

    gated = automix_native.gate(
        levels,
        threshold=threshold_db,
        alpha_att=0.0,
        alpha_rel=0.5,
        hold_samples=hold,
        target_gain_open=1.0,
        target_gain_closed=0.0,
    )
    assert gated is not None
    gain = np.asarray(gated)

    # Before sample 10: closed
    assert float(gain[5]) == 0.0

    # During burst (10..19): instant open to 1.0
    assert float(gain[15]) == 1.0

    # Hold period: samples 20..24 remain fully open (1.0) because hold_samples = 5
    for i in range(20, 20 + hold):
        assert float(gain[i]) == 1.0

    # Sample 25: hold expires, release starts decaying toward 0.0
    assert float(gain[25]) < 1.0


# ---------------------------------------------------------------------------
# 6. Threshold Rolling Median / MAD Tests
# ---------------------------------------------------------------------------

def test_threshold_computes_rolling_median_and_mad_envelope():
    """Adaptive threshold matches median + max(min_floor, mad_multiplier * mad)."""
    # Deterministic step: 20 samples of 1.0, 20 samples of 3.0
    flux = np.concatenate([np.ones(20), np.full(20, 3.0)]).astype(np.float64)
    result = automix_native.threshold(flux, radius=4, min_floor=0.05, mad_multiplier=2.0)
    assert result is not None
    th = np.asarray(result)
    assert len(th) == 40
    # Over the uniform 1.0 region, median=1.0, mad=0.0 -> threshold = 1.0 + min_floor (1.05)
    assert math.isclose(float(th[5]), 1.05, abs_tol=1e-12)
    # Over the uniform 3.0 region, median=3.0, mad=0.0 -> threshold = 3.0 + min_floor (3.05)
    assert math.isclose(float(th[35]), 3.05, abs_tol=1e-12)


def test_threshold_bounds_huge_radius_scratchpad():
    """radius exceeding flux length is bounded cleanly without massive buffer allocations."""
    flux = np.ones(32, dtype=np.float64) * 0.5
    result = automix_native.threshold(flux, radius=500_000, min_floor=0.02, mad_multiplier=3.0)
    assert result is not None
    assert len(result) == 32
    assert math.isclose(float(result[0]), 0.52, abs_tol=1e-12)
