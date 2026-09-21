"""KENN Multi-Genre Spectral Target Profiles and Loudness-Matched A/B Engine.

Defines calibrated 40-band ERB target profiles and loudness compensation metrics
across 6 primary modern production genres:
1. EDM / Club
2. Modern Pop
3. Hip-Hop / 808
4. Rock / Metal
5. Acoustic / Jazz
6. Film / Cinematic
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional
import numpy as np

SCHEMA = "kenn.genre_target_curves.v1"
ANCHOR_FREQUENCY_HZ = 1000.0

GENRE_PROFILES: Dict[str, Dict[str, Any]] = {
    "edm_club": {
        "id": "edm_club",
        "name": "EDM / Club",
        "description": "High-impact sub-bass, sculpted mud reduction, wide high-frequency air, high density.",
        "target_integrated_lufs": (-8.0, -6.0),
        "target_crest_factor_db": (6.0, 8.5),
        "sub_emphasis_db": 4.5,
        "mud_dip_db": -3.0,
        "presence_boost_db": 0.5,
        "air_shelf_db": 2.0,
        "base_slope_db_per_oct": -3.2,
    },
    "modern_pop": {
        "id": "modern_pop",
        "name": "Modern Pop",
        "description": "Forward vocal clarity, punchy kick/bass balance, smooth high-end sparkle, radio ready.",
        "target_integrated_lufs": (-11.0, -9.0),
        "target_crest_factor_db": (8.0, 11.0),
        "sub_emphasis_db": 2.0,
        "mud_dip_db": -1.5,
        "presence_boost_db": 2.5,
        "air_shelf_db": 1.5,
        "base_slope_db_per_oct": -3.5,
    },
    "hip_hop_808": {
        "id": "hip_hop_808",
        "name": "Hip-Hop / 808",
        "description": "Prominent deep sub-bass (35-65 Hz), clean kick pocket, crisp hi-hat air, focused vocal.",
        "target_integrated_lufs": (-9.0, -7.0),
        "target_crest_factor_db": (7.0, 9.5),
        "sub_emphasis_db": 6.0,
        "mud_dip_db": -2.5,
        "presence_boost_db": 1.8,
        "air_shelf_db": 2.0,
        "base_slope_db_per_oct": -3.6,
    },
    "rock_metal": {
        "id": "rock_metal",
        "name": "Rock / Metal",
        "description": "Aggressive midrange presence (1.5-4 kHz), punchy low-end, controlled sub, natural highs.",
        "target_integrated_lufs": (-10.0, -8.0),
        "target_crest_factor_db": (8.0, 10.5),
        "sub_emphasis_db": 0.5,
        "mud_dip_db": 0.5,
        "presence_boost_db": 3.5,
        "air_shelf_db": 0.0,
        "base_slope_db_per_oct": -3.0,
    },
    "acoustic_jazz": {
        "id": "acoustic_jazz",
        "name": "Acoustic / Jazz",
        "description": "Natural acoustic dynamics, warm unhyped tonal balance, organic micro-dynamics.",
        "target_integrated_lufs": (-18.0, -14.0),
        "target_crest_factor_db": (14.0, 18.0),
        "sub_emphasis_db": -1.0,
        "mud_dip_db": 0.0,
        "presence_boost_db": 0.0,
        "air_shelf_db": -1.0,
        "base_slope_db_per_oct": -4.2,
    },
    "film_cinematic": {
        "id": "film_cinematic",
        "name": "Film / Cinematic",
        "description": "Extreme dynamic range, extended sub-bass depth, spacious transparent orchestral highs.",
        "target_integrated_lufs": (-24.0, -18.0),
        "target_crest_factor_db": (16.0, 22.0),
        "sub_emphasis_db": 3.0,
        "mud_dip_db": -0.5,
        "presence_boost_db": 1.0,
        "air_shelf_db": 0.5,
        "base_slope_db_per_oct": -3.8,
    },
}


def normalize_genre_key(genre: str) -> str:
    """Normalize user or tag string into a supported genre key."""
    g = (genre or "").lower().strip()
    if any(k in g for k in ("edm", "club", "dance", "electronic", "house", "techno", "dubstep")):
        return "edm_club"
    if any(k in g for k in ("hip", "hop", "trap", "808", "rap")):
        return "hip_hop_808"
    if any(k in g for k in ("rock", "metal", "punk", "guitar", "indie")):
        return "rock_metal"
    if any(k in g for k in ("jazz", "acoustic", "folk", "classical")):
        return "acoustic_jazz"
    if any(k in g for k in ("film", "cinematic", "score", "trailer", "ambient", "orchestral")):
        return "film_cinematic"
    return "modern_pop"


def get_genre_profile(genre: str = "modern_pop") -> Dict[str, Any]:
    """Retrieve the target profile for a specified genre."""
    key = normalize_genre_key(genre)
    return GENRE_PROFILES.get(key, GENRE_PROFILES["modern_pop"])


def list_available_genres() -> List[Dict[str, Any]]:
    """Return all supported genre profiles with metadata."""
    return [
        {
            "id": p["id"],
            "name": p["name"],
            "description": p["description"],
            "target_integrated_lufs": list(p["target_integrated_lufs"]),
            "target_crest_factor_db": list(p["target_crest_factor_db"]),
        }
        for p in GENRE_PROFILES.values()
    ]


def calculate_genre_expected_curve(
    center_frequencies: List[float],
    genre: str = "modern_pop",
) -> List[float]:
    """Compute expected relative dB values across given center frequencies for a genre."""
    profile = get_genre_profile(genre)
    slope = profile["base_slope_db_per_oct"]
    sub_boost = profile["sub_emphasis_db"]
    mud_cut = profile["mud_dip_db"]
    presence = profile["presence_boost_db"]
    air = profile["air_shelf_db"]

    expected = []
    for fc in center_frequencies:
        if fc <= 0.0:
            expected.append(0.0)
            continue
        # Base octave slope relative to anchor (1 kHz)
        octaves = math.log2(fc / ANCHOR_FREQUENCY_HZ)
        val = slope * octaves

        # Genre contour shaping
        if fc < 80.0:
            val += sub_boost
        elif 80.0 <= fc <= 140.0:
            val += sub_boost * 0.5
        elif 200.0 <= fc <= 450.0:
            val += mud_cut
        elif 1200.0 <= fc <= 4000.0:
            val += presence
        elif fc > 8000.0:
            val += air

        expected.append(round(val, 3))
    return expected


def calculate_genre_spectral_deviation(
    ltas: List[Dict[str, Any]],
    genre: str = "modern_pop",
) -> Dict[str, Any]:
    """Compare measured LTAS bands against a genre-specific spectral target curve."""
    usable = [
        row for row in ltas
        if isinstance(row, dict)
        and isinstance(row.get("center_hz"), (int, float))
        and isinstance(row.get("relative_db"), (int, float))
        and float(row["center_hz"]) > 0.0
    ]
    if not usable:
        return {
            "status": "abstained",
            "reason": "No usable LTAS bands were available for genre spectral comparison.",
        }

    profile = get_genre_profile(genre)
    anchor = min(usable, key=lambda row: abs(float(row["center_hz"]) - ANCHOR_FREQUENCY_HZ))
    anchor_freq = float(anchor["center_hz"])
    anchor_measured = float(anchor["relative_db"])

    bands: List[Dict[str, Any]] = []
    deviations: List[float] = []

    fcs = [float(row["center_hz"]) for row in usable]
    expected_curve = calculate_genre_expected_curve(fcs, genre)

    for row, expected in zip(usable, expected_curve):
        center = float(row["center_hz"])
        measured = float(row["relative_db"]) - anchor_measured  # Anchor normalized
        dev = round(measured - expected, 3)
        deviations.append(dev)
        bands.append({
            "index": row.get("index"),
            "center_hz": round(center, 2),
            "measured_relative_db": round(measured, 3),
            "target_expected_relative_db": expected,
            "deviation_db": dev,
        })

    largest = max(bands, key=lambda row: abs(float(row["deviation_db"])), default=None)
    rmse = round(float(np.sqrt(np.mean(np.array(deviations) ** 2))), 3)

    return {
        "status": "complete",
        "genre": profile["name"],
        "genre_id": profile["id"],
        "curve": f"{profile['name']} calibrated target curve",
        "anchor_frequency_hz": anchor_freq,
        "largest_deviation": largest,
        "rms_spectral_deviation_db": rmse,
        "target_integrated_lufs": list(profile["target_integrated_lufs"]),
        "target_crest_factor_db": list(profile["target_crest_factor_db"]),
        "bands": bands,
    }


def calculate_loudness_matched_gain_delta(
    dry_lufs: float,
    wet_lufs: float,
    *,
    max_compensation_db: float = 6.0,
) -> Dict[str, Any]:
    """Calculate exact gain compensation to eliminate Fletcher-Munson perceived volume bias.

    When comparing State A (dry) and State B (wet), returns the offset to apply
    so that both states have identical integrated loudness within +/- 0.05 dB.
    """
    if not (math.isfinite(dry_lufs) and math.isfinite(wet_lufs)):
        return {
            "status": "error",
            "reason": "Non-finite LUFS values provided.",
            "gain_adjustment_db": 0.0,
        }

    raw_delta = round(float(dry_lufs - wet_lufs), 2)
    # Clamp to prevent extreme jumps
    clamped_delta = max(-max_compensation_db, min(max_compensation_db, raw_delta))
    compensated_wet = round(wet_lufs + clamped_delta, 2)
    residual_error = round(abs(dry_lufs - compensated_wet), 3)

    return {
        "status": "success",
        "dry_lufs": round(dry_lufs, 2),
        "wet_lufs": round(wet_lufs, 2),
        "raw_delta_db": raw_delta,
        "gain_adjustment_db": clamped_delta,
        "clamped": abs(clamped_delta - raw_delta) > 0.001,
        "compensated_wet_lufs": compensated_wet,
        "residual_volume_bias_db": residual_error,
        "unbiased_audition_ready": residual_error <= 0.05,
    }


__all__ = [
    "SCHEMA",
    "GENRE_PROFILES",
    "normalize_genre_key",
    "get_genre_profile",
    "list_available_genres",
    "calculate_genre_expected_curve",
    "calculate_genre_spectral_deviation",
    "calculate_loudness_matched_gain_delta",
]
