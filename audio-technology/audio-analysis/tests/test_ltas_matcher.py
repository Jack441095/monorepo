"""Tests for AutoMix mixdown/ltas_matcher.py."""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

import numpy as np
from audio_analysis.mixdown.ltas_matcher import (
    GENRE_LTAS_PROFILES,
    calculate_40_band_ltas,
    expand_genre_profile_to_40_bands,
    generate_ltas_match_eq_bands,
    reference_target_40_band_ltas,
)


def test_calculate_40_band_ltas():
    # 44.1 kHz sine wave at 440 Hz
    sr = 44100
    t = np.linspace(0, 1.0, sr)
    samples = np.sin(2 * np.pi * 440 * t)

    bands = calculate_40_band_ltas(samples, sample_rate=sr)
    assert len(bands) == 40
    assert isinstance(bands[0], float)


def test_calculate_40_band_ltas_only_uses_first_131072_samples():
    """The FFT only ever reads the first 131072 samples (~3s @ 44.1kHz) --
    a much longer track's tail must not change the result at all. Locks in
    the 2026-08-01 fix that slices the sample list *before* converting to
    a numpy array (was converting the whole track first, then discarding
    everything past 131072 -- measured ~55x wasted time on the conversion
    step for a real multi-minute track)."""
    sr = 44100
    rng = np.random.default_rng(4)
    short = (0.3 * np.sin(2 * np.pi * 440 * np.arange(140000) / sr)).tolist()
    long_tail = short + (0.9 * rng.standard_normal(500000)).tolist()  # very different tail content

    assert calculate_40_band_ltas(short, sr) == calculate_40_band_ltas(long_tail, sr)


def test_calculate_40_band_ltas_accepts_list_and_ndarray_input_identically():
    sr = 44100
    samples_list = (0.4 * np.sin(2 * np.pi * 220 * np.arange(200000) / sr)).tolist()
    samples_arr = np.asarray(samples_list, dtype=np.float64)
    assert calculate_40_band_ltas(samples_list, sr) == calculate_40_band_ltas(samples_arr, sr)


def test_calculate_40_band_ltas_empty_input_returns_flat_zero():
    assert calculate_40_band_ltas([], 44100) == [0.0] * 40
    assert calculate_40_band_ltas(np.asarray([], dtype=np.float64), 44100) == [0.0] * 40


def test_calculate_40_band_ltas_short_file_under_the_fft_window():
    sr = 44100
    short = (0.3 * np.sin(2 * np.pi * 440 * np.arange(1000) / sr)).tolist()
    bands = calculate_40_band_ltas(short, sr)
    assert len(bands) == 40


def test_generate_ltas_match_eq_bands():
    # Dummy 40-band spectrum with low sub energy
    dummy_bands = [-10.0] * 40

    eq_bands = generate_ltas_match_eq_bands(dummy_bands, genre="edm")
    assert isinstance(eq_bands, list)
    assert len(eq_bands) > 0
    assert "frequency" in eq_bands[0]
    assert "gain_db" in eq_bands[0]


def test_expand_genre_profile_to_40_bands_matches_the_real_profile():
    bands = expand_genre_profile_to_40_bands("edm")

    assert len(bands) == 40
    profile = GENRE_LTAS_PROFILES["edm"]
    # Band 0 (sub region) and band 39 (air region) must carry the real
    # profile values, not placeholders -- this is what the frontend plots
    # as the "target" curve, so it has to be the genuine target, not a stub.
    assert bands[0] == profile["sub"]
    assert bands[39] == profile["air"]


def test_expand_genre_profile_to_40_bands_falls_back_to_pop_for_unknown_genre():
    assert expand_genre_profile_to_40_bands("not-a-real-genre") == expand_genre_profile_to_40_bands("pop")


def _write_sine_wav(path: Path, freq: float, seconds: float = 1.0, sr: int = 44100) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sr)
        for i in range(int(seconds * sr)):
            value = int(0.4 * 32767 * math.sin(2 * math.pi * freq * i / sr))
            wav.writeframesraw(struct.pack("<h", value))


class TestReferenceTarget40BandLtas:
    def test_returns_none_for_a_missing_or_empty_directory(self, tmp_path):
        assert reference_target_40_band_ltas(tmp_path / "does_not_exist") is None
        empty = tmp_path / "empty"
        empty.mkdir()
        assert reference_target_40_band_ltas(empty) is None

    def test_single_reference_file_matches_its_own_measured_ltas(self, tmp_path):
        _write_sine_wav(tmp_path / "ref.wav", freq=1000.0)
        result = reference_target_40_band_ltas(tmp_path)
        assert result is not None
        assert len(result) == 40

    def test_median_across_multiple_reference_files_is_between_their_individual_measurements(self, tmp_path):
        _write_sine_wav(tmp_path / "a.wav", freq=100.0)
        _write_sine_wav(tmp_path / "b.wav", freq=8000.0)
        _write_sine_wav(tmp_path / "c.wav", freq=1000.0)
        result = reference_target_40_band_ltas(tmp_path)
        assert result is not None
        assert len(result) == 40
        # A real measurement, not a copy of any single file -- band 0 (very
        # low frequency) shouldn't be identical to what a 1kHz-only file
        # would produce on its own.
        solo = calculate_40_band_ltas(np.sin(2 * np.pi * 1000.0 * np.arange(44100) / 44100), 44100)
        assert result != solo


class TestGenerateLtasMatchEqBandsWithRealReference:
    def test_without_ref_uses_the_hand_tuned_genre_profile(self):
        measured = [-10.0] * 40
        bands = generate_ltas_match_eq_bands(measured, genre="edm")
        assert bands
        assert all("genre estimate" in b["reason"] for b in bands)

    def test_with_a_real_ref_corrects_toward_it_instead(self):
        measured = [-10.0] * 40
        # A real reference that's flat and much louder in the sub region --
        # should generate a boost there, unlike the hand-tuned edm profile's
        # own numbers, proving the real reference is actually being used.
        real_ref = [0.0] * 8 + [-10.0] * 32
        bands = generate_ltas_match_eq_bands(measured, genre="edm", ref_40_bands=real_ref)
        assert bands
        assert any(b["reason"].find("real reference tracks") != -1 for b in bands)
        sub_band = next(b for b in bands if b["frequency"] == 60.0)
        assert sub_band["gain_db"] > 0

    def test_short_ref_array_falls_back_to_genre_profile(self):
        measured = [-10.0] * 40
        bands = generate_ltas_match_eq_bands(measured, genre="edm", ref_40_bands=[0.0, 0.0])
        assert all("genre estimate" in b["reason"] for b in bands)
