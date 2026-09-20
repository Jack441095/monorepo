"""Unit and integration tests for ERB critical band masking analysis."""

from __future__ import annotations

from audio_analysis.analysis_core.erb_masking import (
    hz_to_erb,
    erb_to_hz,
    absolute_threshold_of_hearing,
    get_erb_bands,
    compute_combined_masking_threshold,
    calculate_visibility,
    generate_carving_suggestions,
    simulate_clarity_improvement
)
from audio_analysis.mixdown.stem_analysis import analyze_stems_masking


class TestERBMath:
    """Test Glasberg & Moore ERB rate math conversions."""

    def test_erb_math_roundtrip(self):
        """Converting Hz to ERB and back to Hz should be close."""
        for freq in [50.0, 100.0, 500.0, 1000.0, 5000.0, 10000.0, 15000.0]:
            erb = hz_to_erb(freq)
            freq_back = erb_to_hz(erb)
            assert abs(freq - freq_back) < 1e-4

    def test_erb_math_edge_cases(self):
        """Negative and zero boundaries return zero."""
        assert hz_to_erb(0.0) == 0.0
        assert hz_to_erb(-100.0) == 0.0
        assert erb_to_hz(0.0) == 0.0
        assert erb_to_hz(-5.0) == 0.0


class TestATHCurve:
    """Test Terhardt's Absolute Threshold of Hearing curve."""

    def test_ath_curve_sensitivity(self):
        """Auditory system is more sensitive around 3-4 kHz than extreme frequencies."""
        ath_mid = absolute_threshold_of_hearing(3500.0)
        ath_low = absolute_threshold_of_hearing(50.0)
        ath_high = absolute_threshold_of_hearing(18000.0)
        assert ath_mid < ath_low
        assert ath_mid < ath_high

    def test_ath_edge_cases(self):
        """ATH doesn't crash on invalid/negative frequencies."""
        assert absolute_threshold_of_hearing(0.0) == 100.0
        assert absolute_threshold_of_hearing(-10.0) == 100.0


class TestSchroederSpreading:
    """Test Schroeder spreading function leakage."""

    def test_spreading_leaks_correctly(self):
        """A masker at one band should spread masking to adjacent target bands."""
        erb_bands = get_erb_bands(num_bands=40)
        
        # Other stem has high energy in band index 20 (middle freq)
        other_energies = [[0.0] * 40]
        other_energies[0][20] = 0.5  # loud tone
        
        threshold = compute_combined_masking_threshold(other_energies, erb_bands)
        
        # Band 20 should have high threshold
        assert threshold[20] > 60.0
        # Adjacent band 21 should also get significant masking due to spreading
        assert threshold[21] > 30.0
        # Extreme band 0 should be at noise floor/ATH level
        ath_0 = absolute_threshold_of_hearing(erb_bands[0][0])
        assert abs(threshold[0] - ath_0) < 1.0


class TestVisibilityCalculation:
    """Test perceptual visibility and clarity scores."""

    def test_calculate_visibility_quiet(self):
        """Very quiet signal below masking threshold has 0 visibility."""
        stem_energy = [1e-15] * 40  # silent
        threshold = [60.0] * 40
        vis, band_vis = calculate_visibility(stem_energy, threshold)
        assert vis == 0.0
        assert all(v == 0.0 for v in band_vis)

    def test_calculate_visibility_loud(self):
        """Loud signal way above masking threshold has near 1.0 visibility."""
        stem_energy = [1.0] * 40  # loud (0 dBFS = 90 dB SPL)
        threshold = [20.0] * 40  # quiet threshold
        vis, band_vis = calculate_visibility(stem_energy, threshold)
        assert vis > 0.95
        assert all(v > 0.95 for v in band_vis)


class TestSuggestionsAndSimulation:
    """Test correction recommendations and simulated clarity improvements."""

    def test_generate_suggestions(self):
        """Verify that suggestions are correctly categorized by frequency range."""
        erb_bands = get_erb_bands(num_bands=40)
        
        # Stem A has energy in low range (bass, idx 2) -> masks Stem B
        # Stem C has energy in mid range (idx 20) -> masks Stem D
        stems = [
            {"name": "kick", "erb_profile": [0.0] * 40},
            {"name": "bass", "erb_profile": [0.0] * 40},
            {"name": "guitar", "erb_profile": [0.0] * 40},
            {"name": "vocal", "erb_profile": [0.0] * 40}
        ]
        # Low conflict: kick (idx 0) masks bass (idx 1)
        stems[0]["erb_profile"][2] = 0.8
        stems[1]["erb_profile"][2] = 0.1
        
        # Mid conflict: guitar (idx 2) masks vocal (idx 3)
        stems[2]["erb_profile"][20] = 0.8
        stems[3]["erb_profile"][20] = 0.1
        
        # Build a dummy heatmap
        heatmap = {
            "kick": {"bass": [0.0] * 40, "guitar": [0.0] * 40, "vocal": [0.0] * 40},
            "bass": {"kick": [0.0] * 40, "guitar": [0.0] * 40, "vocal": [0.0] * 40},
            "guitar": {"kick": [0.0] * 40, "bass": [0.0] * 40, "vocal": [0.0] * 40},
            "vocal": {"kick": [0.0] * 40, "bass": [0.0] * 40, "guitar": [0.0] * 40}
        }
        heatmap["kick"]["bass"][2] = 0.85
        heatmap["guitar"]["vocal"][20] = 0.85
        
        sugs = generate_carving_suggestions(stems, heatmap, erb_bands)
        
        assert len(sugs) >= 2
        # Bass conflict should recommend sidechain compression
        assert any(s["type"] == "sidechain_compression" for s in sugs)
        # Mid conflict should recommend dynamic EQ
        assert any(s["type"] == "dynamic_eq" for s in sugs)

    def test_simulate_clarity_improvement(self):
        """Applying corrective cuts should show an increase in visibility/clarity."""
        erb_bands = get_erb_bands(num_bands=40)
        stems = [
            {
                "name": "guitar",
                "overall_visibility": 0.50,
                "erb_profiles": [[0.1] * 40] * 16
            },
            {
                "name": "vocal",
                "overall_visibility": 0.40,
                "erb_profiles": [[0.1] * 40] * 16
            }
        ]
        suggestions = [
            {
                "masker": "guitar",
                "masked": "vocal",
                "type": "dynamic_eq",
                "frequency_hz": 1000.0,
                "description": "Cut guitar at 1000 Hz",
                "daw_move": "Dynamic EQ cut at 1000 Hz"
            }
        ]
        
        imp = simulate_clarity_improvement(stems, suggestions, erb_bands)
        
        # Vocal (masked) should have increased clarity
        assert imp["vocal"]["after"] > imp["vocal"]["before"]
        # Guitar (masker/uncut) should remain unchanged
        assert imp["guitar"]["after"] == imp["guitar"]["before"]


class TestStemsAnalysisIntegration:
    """Test analyze_stems_masking integration returns the new ERB keys."""

    def test_stems_analysis_output_erb_keys(self):
        """Upgraded analyze_stems_masking returns the erb_details dictionary."""
        def mock_read(file_bytes, max_samples):
            return {
                "samples": [0.1, -0.05, 0.2, -0.15] * 2000,
                "sample_rate": 44100,
                "channels": 1,
                "duration_seconds": 0.2,
                "peak": 0.2,
            }
            
        def mock_bands(samples, sample_rate, size=4096):
            return {
                "sub": 0.15, "bass": 0.25, "low_mids": 0.20,
                "mids": 0.20, "presence": 0.10, "sibilance": 0.05, "air": 0.05,
            }
            
        stems = [
            {"name": "kick.wav", "file_bytes": b"fake"},
            {"name": "bass.wav", "file_bytes": b"fake"}
        ]
        
        res = analyze_stems_masking(stems, read_wav_mono=mock_read, spectral_bands=mock_bands)
        
        assert "erb_details" in res
        erb = res["erb_details"]
        assert "erb_frequencies" in erb
        assert len(erb["erb_frequencies"]) == 40
        assert "heatmap" in erb
        assert "carving_suggestions" in erb
        assert "clarity_improvement" in erb
        
        # Verify stem entries contain visibility keys
        for stem in res["stems"]:
            assert "overall_visibility" in stem
            assert "visibility_per_band" in stem
            assert len(stem["visibility_per_band"]) == 40
