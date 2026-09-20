"""Unit tests for KENN Multi-Genre Target Profiles and Loudness-Matched A/B."""

import pytest
from kenn.core.target_curves import (
    GENRE_PROFILES,
    calculate_genre_expected_curve,
    calculate_genre_spectral_deviation,
    calculate_loudness_matched_gain_delta,
    get_genre_profile,
    list_available_genres,
    normalize_genre_key,
)


def test_genre_normalization():
    assert normalize_genre_key("EDM") == "edm_club"
    assert normalize_genre_key("House track") == "edm_club"
    assert normalize_genre_key("Trap 808") == "hip_hop_808"
    assert normalize_genre_key("Heavy Metal") == "rock_metal"
    assert normalize_genre_key("Acoustic Trio") == "acoustic_jazz"
    assert normalize_genre_key("Cinematic Score") == "film_cinematic"
    assert normalize_genre_key("Radio hit") == "modern_pop"


def test_all_genre_profiles_present():
    genres = list_available_genres()
    assert len(genres) == 6
    ids = {g["id"] for g in genres}
    assert ids == {"edm_club", "modern_pop", "hip_hop_808", "rock_metal", "acoustic_jazz", "film_cinematic"}


def test_genre_expected_curves():
    fcs = [30.0, 60.0, 100.0, 250.0, 1000.0, 3000.0, 10000.0]
    edm_curve = calculate_genre_expected_curve(fcs, "edm_club")
    assert len(edm_curve) == len(fcs)
    # At 1 kHz, octave slope is 0, no contour modifier -> should be 0.0
    idx_1k = fcs.index(1000.0)
    assert edm_curve[idx_1k] == 0.0
    # In EDM, sub (30-60 Hz) should have sub_emphasis_db applied (+4.5 dB base)
    assert edm_curve[0] > edm_curve[idx_1k]


def test_genre_spectral_deviation():
    fcs = [round(20.0 * ((20000.0 / 20.0) ** (i / 39.0)), 2) for i in range(40)]
    synthetic_ltas = [
        {"index": i, "center_hz": fc, "relative_db": round(-3.0 * (i / 4.0), 2)}
        for i, fc in enumerate(fcs)
    ]
    res = calculate_genre_spectral_deviation(synthetic_ltas, "edm_club")
    assert res["status"] == "complete"
    assert res["genre_id"] == "edm_club"
    assert "largest_deviation" in res
    assert "rms_spectral_deviation_db" in res
    assert len(res["bands"]) == 40


def test_loudness_matched_gain_delta():
    # Dry is -14 LUFS, Wet is -11 LUFS (3 dB louder)
    # Gain adjustment should be -3 dB to match dry
    res = calculate_loudness_matched_gain_delta(dry_lufs=-14.0, wet_lufs=-11.0)
    assert res["status"] == "success"
    assert res["gain_adjustment_db"] == -3.0
    assert res["compensated_wet_lufs"] == -14.0
    assert res["unbiased_audition_ready"] is True

    # Safety clamp: if delta > 6 dB, clamp to 6.0
    clamped_res = calculate_loudness_matched_gain_delta(dry_lufs=-14.0, wet_lufs=-4.0, max_compensation_db=6.0)
    assert clamped_res["clamped"] is True
    assert clamped_res["gain_adjustment_db"] == -6.0

