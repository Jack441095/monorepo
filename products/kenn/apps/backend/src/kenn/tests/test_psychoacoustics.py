"""Unit tests for KENN Psychoacoustic Masking Engine."""

import math
import numpy as np
import pytest

from kenn.core.psychoacoustics import (
    hz_to_erb,
    erb_to_hz,
    absolute_threshold_of_hearing,
    get_erb_bands,
    compute_erb_spectrum,
    compute_combined_masking_threshold,
    calculate_auditory_visibility,
    compute_track_masking_matrix,
    generate_spectral_carving_proposals,
)


def test_erb_hz_round_trip():
    """Verify hz_to_erb and erb_to_hz are exact mathematical inverses."""
    for freq in [50.0, 100.0, 440.0, 1000.0, 3500.0, 10000.0]:
        erb = hz_to_erb(freq)
        recovered_hz = erb_to_hz(erb)
        assert abs(freq - recovered_hz) < 1e-4, f"Failed at {freq} Hz"


def test_erb_bands_monotonic_and_bounded():
    """Verify 40 ERB bands cover 20 Hz to 20,000 Hz monotonically."""
    bands = get_erb_bands(40)
    assert len(bands) == 40

    prev_end = 19.9
    for center, start, end in bands:
        assert start < center < end
        assert start >= prev_end - 0.1
        prev_end = end

    assert bands[0][1] == pytest.approx(20.0, rel=1e-3)
    assert bands[-1][2] == pytest.approx(20000.0, rel=1e-3)


def test_absolute_threshold_of_hearing_shape():
    """Verify human ear is most sensitive around 3-4 kHz and least at 20 Hz / 18 kHz."""
    ath_20hz = absolute_threshold_of_hearing(20.0)
    ath_1khz = absolute_threshold_of_hearing(1000.0)
    ath_3khz = absolute_threshold_of_hearing(3500.0)
    ath_16khz = absolute_threshold_of_hearing(16000.0)

    # 3.5 kHz is the ear canal resonance, should be lowest threshold (most sensitive)
    assert ath_3khz < ath_1khz
    assert ath_1khz < ath_20hz
    assert ath_3khz < ath_16khz


def test_compute_erb_spectrum_tone_localization():
    """Verify a pure 1 kHz sinusoidal bin maps into the correct ERB band."""
    sample_rate = 44100
    fft_size = 4096
    bin_width = sample_rate / fft_size  # ~10.76 Hz
    target_bin = int(1000.0 / bin_width)

    magnitudes = [0.0] * (fft_size // 2)
    magnitudes[target_bin] = 1.0

    energies = compute_erb_spectrum(magnitudes, sample_rate, fft_size, num_bands=40)
    bands = get_erb_bands(40)

    # Find which band contains 1000 Hz
    expected_band = next(i for i, (c, s, e) in enumerate(bands) if s <= 1000.0 <= e)
    max_energy_band = np.argmax(energies)

    assert max_energy_band == expected_band
    assert energies[max_energy_band] > 0.95


def test_track_masking_matrix_and_carving_proposals():
    """Verify masking detection between competing Bass and Synth tracks."""
    bands = get_erb_bands(40)

    # Track 1: Heavy Bass centered at 150 Hz
    # Track 2: Synth with muddy low-end clashing at 150 Hz
    band_150hz = next(i for i, (c, s, e) in enumerate(bands) if s <= 150.0 <= e)

    energy_bass = [0.0] * 40
    energy_bass[band_150hz] = 1.0  # Dominant masker

    energy_synth = [0.0] * 40
    energy_synth[band_150hz] = 0.15  # Masked victim
    energy_synth[25] = 0.8  # Clean mid/high presence

    tracks = [
        {"index": 0, "name": "Sub Bass", "erb_profile": energy_bass},
        {"index": 1, "name": "Synth Chords", "erb_profile": energy_synth},
    ]

    matrix_res = compute_track_masking_matrix(tracks, bands)
    assert matrix_res["status"] == "success"
    assert "Sub Bass" in matrix_res["track_visibilities"]
    assert "Synth Chords" in matrix_res["track_visibilities"]

    # Sub Bass should be highly visible, Synth low-mid should register clash
    clashes = matrix_res["pairwise_clashes"]
    assert len(clashes) >= 1
    assert clashes[0]["masker_track"] == "Sub Bass"
    assert clashes[0]["victim_track"] == "Synth Chords"

    # Generate carving proposals
    proposals = generate_spectral_carving_proposals(matrix_res)
    assert len(proposals) >= 1
    prop = proposals[0]

    assert prop["code"] == "PSYCHOACOUSTIC_SPECTRAL_CARVE"
    assert prop["masker_track"] == "Sub Bass"
    assert prop["victim_track"] == "Synth Chords"
    # Strict Hardware Safety Policy check: cut must be <= 3.0 dB
    assert -3.0 <= prop["suggested_cut_db"] < 0.0
    assert prop["proposed_osc_mutation"]["gain_delta_db"] >= -3.0

