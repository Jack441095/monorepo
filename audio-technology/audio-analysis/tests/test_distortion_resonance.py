"""Unit tests for the distortion and resonance analysis module."""

from __future__ import annotations
import math
import numpy as np

from audio_analysis.analysis_core.distortion_resonance import (
    detect_fundamental_pitch,
    analyze_thd_n,
    detect_resonances,
    detect_isp
)


class TestFundamentalPitch:
    """Test autocorrelation pitch detector."""

    def test_pure_sine_pitch(self):
        """Dominate pitch of a pure 440 Hz sine wave should be detected."""
        fs = 44100
        t = np.arange(4096) / fs
        sine = np.sin(2 * math.pi * 440.0 * t)
        
        pitch = detect_fundamental_pitch(sine, fs)
        assert abs(pitch - 440.0) < 5.0

    def test_silence_returns_zero(self):
        """Silent buffers return zero fundamental pitch."""
        silence = np.zeros(2048)
        assert detect_fundamental_pitch(silence, 44100) == 0.0


class TestTHDAndDistortion:
    """Test total harmonic distortion calculations."""

    def test_clean_sine_low_thd(self):
        """A pure sine wave has near-zero harmonic distortion."""
        fs = 44100
        t = np.arange(8192) / fs
        # Normal clean sine
        sine = 0.5 * np.sin(2 * math.pi * 500.0 * t)
        
        res = analyze_thd_n(sine, fs)
        assert abs(res["fundamental_hz"] - 500.0) < 5.0
        assert res["thd"] < 0.005
        assert res["thd_n"] < 0.01

    def test_harmonic_injections(self):
        """Injected harmonics are correctly categorized and calculated."""
        fs = 44100
        t = np.arange(8192) / fs
        f0 = 200.0
        # Fundamental (A1 = 0.8)
        fundamental = 0.8 * np.sin(2 * math.pi * f0 * t)
        # Even Harmonic (2nd harmonic at 400 Hz, A2 = 0.08, which is 10% ratio)
        h2 = 0.08 * np.sin(2 * math.pi * 2 * f0 * t)
        # Odd Harmonic (3rd harmonic at 600 Hz, A3 = 0.04, which is 5% ratio)
        h3 = 0.04 * np.sin(2 * math.pi * 3 * f0 * t)
        
        distorted = fundamental + h2 + h3
        
        res = analyze_thd_n(distorted, fs)
        
        # Expected THD = sqrt(0.08^2 + 0.04^2) / 0.8 = sqrt(0.0080) / 0.8 = 0.0894 / 0.8 = 0.1118
        assert abs(res["thd"] - 0.1118) < 0.01
        assert abs(res["even_thd"] - 0.10) < 0.01
        assert abs(res["odd_thd"] - 0.05) < 0.01
        assert res["thd_n"] >= res["thd"]


class TestResonanceDetector:
    """Test spectral resonance peak detector."""

    def test_resonance_peak_detection(self):
        """Adding a high-amplitude sine tone to noise simulates a sharp resonance."""
        fs = 44100
        t = np.arange(4096) / fs
        
        # White noise background + strong narrow tone at 1000 Hz
        np.random.seed(42)
        noise = np.random.normal(0, 0.02, 4096)
        tone = 0.6 * np.sin(2 * math.pi * 1000.0 * t)
        signal = noise + tone
        
        resonances = detect_resonances(signal, fs)
        
        assert len(resonances) > 0
        peak = resonances[0]
        # Should be centered around 1000 Hz
        assert abs(peak["frequency_hz"] - 1000.0) < 20.0
        assert peak["severity_db"] > 10.0
        # Resonance should have high Q factor (sharp peak)
        assert peak["q"] >= 10.0

    def test_resonance_persistence_filtering(self):
        """A resonance that is only temporary is filtered out, while a persistent one is kept."""
        fs = 44100
        # 50,000 samples total
        total_len = 50000
        t = np.arange(total_len) / fs
        
        # Background noise
        np.random.seed(42)
        noise = np.random.normal(0, 0.02, total_len)
        
        # 1. Add a persistent tone at 1000 Hz across the entire signal
        persistent_tone = 0.5 * np.sin(2 * math.pi * 1000.0 * t)
        
        # 2. Add a temporary tone at 3000 Hz only in the first 4096 samples
        temp_tone = np.zeros(total_len)
        temp_tone[:4096] = 0.8 * np.sin(2 * math.pi * 3000.0 * t[:4096])
        
        signal = noise + persistent_tone + temp_tone
        
        resonances = detect_resonances(signal, fs)
        
        detected_freqs = [r["frequency_hz"] for r in resonances]
        # The persistent tone at 1000 Hz should be detected
        assert any(abs(f - 1000.0) < 20.0 for f in detected_freqs)
        
        # The temporary tone at 3000 Hz should NOT be detected because it is not persistent
        assert not any(abs(f - 3000.0) < 20.0 for f in detected_freqs)



class TestOversamplingAndISP:
    """Test 4x oversampling and inter-sample peak detection."""

    def test_oversampling_retains_envelope(self):
        """Oversampling does not distort a mid-frequency sine wave's peak amplitude."""
        fs = 44100
        t = np.arange(1024) / fs
        sine = 0.7 * np.sin(2 * math.pi * 200.0 * t)
        
        sample_peak, isp = detect_isp(sine)
        assert abs(sample_peak - 0.7) < 0.02
        assert abs(isp - 0.7) < 0.02

    def test_inter_sample_peak_overshoot(self):
        """A high frequency signal should show an inter-sample peak overshoot."""
        # A signal sampled at 45, 135, 225, 315 degrees of a sine wave
        # Peak sample is 0.707, but continuous peak amplitude is 1.0 (41% overshoot)
        samples = np.array([0.7071, 0.7071, -0.7071, -0.7071] * 64)
        
        sample_peak, isp = detect_isp(samples)
        
        assert abs(sample_peak - 0.7071) < 0.01
        assert abs(isp - 1.0) < 0.01
