"""Unit tests for the DSP engine module.

Verifies correct operation of eq, dynamics, gain_pan, spatial, and saturation processors.
"""

from __future__ import annotations

import math
import numpy as np
import pytest
from scipy.signal import sosfreqz

from audio_analysis.dsp_engine import (
    EQBand,
    ParametricEQ,
    Compressor,
    Limiter,
    Gate,
    apply_gain,
    apply_pan,
    apply_stereo_width,
    mono_below_frequency,
    Reverb,
    Delay,
    apply_saturation,
    __version__,
)


def _response_db(filter_type: str, probe_hz: float, *, gain_db: float = 0.0) -> float:
    eq = ParametricEQ(sample_rate=48_000)
    eq.add_band(filter_type, frequency=1_000.0, gain_db=gain_db, q=1.0)
    frequencies, response = sosfreqz(eq.get_sos(), worN=32_768, fs=48_000)
    index = int(np.argmin(np.abs(frequencies - probe_hz)))
    return float(20.0 * np.log10(max(abs(response[index]), 1e-12)))


def test_package_version_and_eq_band_serialisation():
    assert __version__ == "1.0.0"
    assert EQBand("peaking", 1_000.0, 3.0, 1.2).to_dict() == {
        "type": "peaking",
        "frequency": 1_000.0,
        "gain_db": 3.0,
        "q": 1.2,
    }


def test_frequency_response_for_every_eq_filter_type():
    assert _response_db("lowpass", 8_000.0) < -30.0
    assert _response_db("highpass", 100.0) < -30.0
    assert _response_db("lowshelf", 100.0, gain_db=6.0) == pytest.approx(6.0, abs=0.25)
    assert _response_db("highshelf", 8_000.0, gain_db=6.0) == pytest.approx(6.0, abs=0.25)
    assert _response_db("peaking", 1_000.0, gain_db=6.0) == pytest.approx(6.0, abs=0.1)
    assert _response_db("notch", 1_000.0) < -45.0
    assert _response_db("allpass", 4_000.0) == pytest.approx(0.0, abs=1e-8)


def test_peaking_eq_matches_reference_gain_in_minimum_and_zero_phase_modes():
    sample_rate = 48_000
    samples = np.sin(2.0 * np.pi * 1_000.0 * np.arange(sample_rate) / sample_rate)
    eq = ParametricEQ(sample_rate=sample_rate).add_band("peaking", 1_000.0, gain_db=6.0, q=2.0)

    minimum_phase = eq.apply(samples)
    zero_phase = eq.apply(samples, linear_phase=True)
    middle = slice(sample_rate // 4, 3 * sample_rate // 4)
    input_rms = np.sqrt(np.mean(samples[middle] ** 2))

    assert 20.0 * np.log10(np.sqrt(np.mean(minimum_phase[middle] ** 2)) / input_rms) == pytest.approx(6.0, abs=0.1)
    assert 20.0 * np.log10(np.sqrt(np.mean(zero_phase[middle] ** 2)) / input_rms) == pytest.approx(6.0, abs=0.1)


def test_eq():
    sample_rate = 44100
    # Generate 1 second of white noise
    np.random.seed(42)
    x = np.random.randn(sample_rate) * 0.1

    eq = ParametricEQ(sample_rate=sample_rate)
    eq.add_band("highpass", frequency=100.0, q=0.707)
    eq.add_band("peaking", frequency=1000.0, gain_db=6.0, q=1.0)
    eq.add_band("lowshelf", frequency=200.0, gain_db=-3.0, q=0.707)

    # Minimum phase
    y_min = eq.apply(x, linear_phase=False)
    assert len(y_min) == len(x)
    assert not np.isnan(y_min).any()

    # Linear phase (zero phase)
    y_lin = eq.apply(x, linear_phase=True)
    assert len(y_lin) == len(x)
    assert not np.isnan(y_lin).any()


def test_compressor():
    sample_rate = 44100
    np.random.seed(42)
    # Generate an envelope that goes from soft to loud to verify compressor activates
    envelope = np.ones(sample_rate)
    envelope[sample_rate // 2:] = 10.0  # abrupt volume jump
    x = np.random.randn(sample_rate) * 0.05 * envelope

    comp = Compressor(
        sample_rate=sample_rate,
        threshold_db=-20.0,
        ratio=4.0,
        attack_ms=5.0,
        release_ms=50.0,
        knee_db=2.0,
        makeup_gain_db=0.0,
    )

    y = comp.apply(x)
    assert len(y) == len(x)
    assert not np.isnan(y).any()
    
    # In the loud section, compression should reduce the gain relative to the original
    ratio_x = np.max(np.abs(x[sample_rate // 2:]))
    ratio_y = np.max(np.abs(y[sample_rate // 2:]))
    assert ratio_y < ratio_x


def test_limiter():
    sample_rate = 44100
    # Signal with a single massive peak exceeding 0 dBFS
    x = np.zeros(1000)
    x[100] = 5.0
    x[200] = -4.0

    lim = Limiter(
        sample_rate=sample_rate,
        ceiling_db=-1.0,
        release_ms=10.0,
        lookahead_ms=2.0,
        true_peak=False,
    )

    y = lim.apply(x)
    assert len(y) == len(x)
    assert not np.isnan(y).any()
    
    # Peak should be capped at -1.0 dBFS (approx 0.891 linear)
    max_peak = np.max(np.abs(y))
    assert max_peak <= 10.0 ** (-1.0 / 20.0) + 1e-4


def test_gate():
    sample_rate = 44100
    # Quiet noise followed by loud burst
    x = np.zeros(2000)
    x[:1000] = np.random.randn(1000) * 0.0001  # below -40 dB
    x[1000:] = np.random.randn(1000) * 0.5     # above -40 dB

    gate = Gate(
        sample_rate=sample_rate,
        threshold_db=-40.0,
        attack_ms=1.0,
        hold_ms=10.0,
        release_ms=10.0,
        range_db=-60.0,
    )

    y = gate.apply(x)
    assert len(y) == len(x)
    assert not np.isnan(y).any()
    
    # First part should be significantly attenuated
    rms_x_quiet = np.sqrt(np.mean(x[:1000]**2))
    rms_y_quiet = np.sqrt(np.mean(y[:1000]**2))
    assert rms_y_quiet < rms_x_quiet * 0.01  # range is -60 dB (0.001 gain)


def test_gain_pan():
    sample_rate = 44100
    x = np.ones(100)

    # 1. apply_gain
    y = apply_gain(x, -6.0)
    assert np.allclose(y, x * (10.0 ** (-6.0 / 20.0)))

    # 2. apply_pan (mono to stereo)
    y_l, y_r = apply_pan(x, None, -1.0)  # hard left
    assert np.allclose(y_l, x)
    assert np.allclose(y_r, 0.0)

    y_l_c, y_r_c = apply_pan(x, None, 0.0)  # center
    assert np.allclose(y_l_c, y_r_c)
    assert np.allclose(y_l_c, x * math.cos(math.pi / 4.0))

    # Constant-power panning preserves total power across the pan range.
    for position in np.linspace(-1.0, 1.0, 21):
        pan_l, pan_r = apply_pan(x, None, float(position))
        assert np.sum(pan_l**2 + pan_r**2) == pytest.approx(np.sum(x**2), rel=1e-12)

    # 3. apply_stereo_width
    left = np.ones(100)
    right = -np.ones(100)  # fully out of phase (pure side)
    # width = 0 should collapse to mono (which is 0 since left and right sum to 0)
    mono_l, mono_r = apply_stereo_width(left, right, 0.0)
    assert np.allclose(mono_l, 0.0)
    assert np.allclose(mono_r, 0.0)
    unity_l, unity_r = apply_stereo_width(left, right, 1.0)
    assert np.allclose(unity_l, left)
    assert np.allclose(unity_r, right)

    # 4. mono_below_frequency
    left = np.random.randn(1000)
    right = np.random.randn(1000)
    # Below 200Hz should be mono (same left and right)
    y_l, y_r = mono_below_frequency(left, right, 200.0, sample_rate)
    assert len(y_l) == len(left)


def test_spatial():
    sample_rate = 44100
    x = np.zeros(2000)
    x[0] = 1.0  # impulse

    # Reverb
    reverb = Reverb(sample_rate=sample_rate, wet_dry=0.5)
    y_l, y_r = reverb.apply(x)
    assert len(y_l) == len(x)
    assert not np.allclose(y_l, x)  # should have reverb tail

    # Delay
    delay = Delay(sample_rate=sample_rate, delay_time_ms=10.0, feedback=0.5, wet_dry=0.5)
    y_l, y_r = delay.apply(x)
    # Should see delay echo at 10ms (441 samples)
    idx = int(441)  # account for delay line offset
    assert np.abs(y_l[idx]) > 0.0


def test_reverb_tail_energy_decays():
    sample_rate = 8_000
    impulse = np.zeros(sample_rate * 3)
    impulse[0] = 1.0
    wet_l, _ = Reverb(
        sample_rate=sample_rate,
        pre_delay_ms=0.0,
        decay_time=0.8,
        wet_dry=1.0,
    ).apply(impulse)

    early_rms = np.sqrt(np.mean(wet_l[sample_rate // 10 : sample_rate] ** 2))
    late_rms = np.sqrt(np.mean(wet_l[sample_rate * 2 : sample_rate * 3] ** 2))
    assert early_rms > 0.0
    assert late_rms < early_rms * 0.2


def test_saturation():
    x = np.linspace(-1.0, 1.0, 1000)
    
    # Without oversampling
    y_no_os = apply_saturation(x, drive_db=10.0, even_harmonics=0.2, oversample=False)
    assert len(y_no_os) == len(x)
    assert not np.isnan(y_no_os).any()

    # With oversampling
    y_os = apply_saturation(x, drive_db=10.0, even_harmonics=0.2, oversample=True)
    assert len(y_os) == len(x)
    assert not np.isnan(y_os).any()
    assert np.max(np.abs(y_os)) <= 1.0


def test_saturation_harmonics_increase_with_drive():
    sample_rate = 48_000
    sample_count = sample_rate
    fundamental_bin = 1_000
    signal = 0.8 * np.sin(2.0 * np.pi * fundamental_bin * np.arange(sample_count) / sample_rate)

    low_drive = apply_saturation(signal, drive_db=1.0, even_harmonics=0.0, oversample=False)
    high_drive = apply_saturation(signal, drive_db=18.0, even_harmonics=0.0, oversample=False)

    low_spectrum = np.abs(np.fft.rfft(low_drive))
    high_spectrum = np.abs(np.fft.rfft(high_drive))
    low_third_ratio = low_spectrum[3 * fundamental_bin] / low_spectrum[fundamental_bin]
    high_third_ratio = high_spectrum[3 * fundamental_bin] / high_spectrum[fundamental_bin]
    assert high_third_ratio > low_third_ratio * 2.0
