from __future__ import annotations

import json
from pathlib import Path

import pytest

from audio_analysis.analysis_core.genre_profiles import (
    GENRE_SEED_PROFILES,
    build_reference_envelope,
    classify_reference_profile,
    compute_tonal_balance_envelope_score,
    compute_tonal_balance_score,
    solve_parametric_eq,
)


def test_curated_library_contains_normalized_40_band_archetypes() -> None:
    assert len(GENRE_SEED_PROFILES) >= 20
    for seed in GENRE_SEED_PROFILES.values():
        assert len(seed["profile"]) == 40
        assert sum(seed["profile"]) == pytest.approx(1.0, abs=5e-4)
    library = Path(__file__).resolve().parents[2] / "studio/audio_analysis/audio_analysis/reference_profiles/genre_archetypes.json"
    stored = json.loads(library.read_text(encoding="utf-8"))
    assert stored["bands"] == 40
    assert stored["profiles"] == GENRE_SEED_PROFILES


def test_reference_classification_recovers_curated_profile() -> None:
    seed = GENRE_SEED_PROFILES["jazz"]
    result = classify_reference_profile(
        seed["profile"],
        {"crest_factor_db": seed["crest_factor_db"], "integrated_lufs": seed["lufs_max"]},
    )
    assert result["genre_key"] == "jazz"
    assert result["confidence"] > 0.95


def test_statistical_envelope_scores_inside_and_outside_profiles() -> None:
    pop = GENRE_SEED_PROFILES["pop"]["profile"]
    nearby = list(pop)
    nearby[10] *= 1.02
    envelope = build_reference_envelope([pop, nearby])

    assert envelope["sample_count"] == 2
    assert compute_tonal_balance_envelope_score(pop, envelope) > 95.0

    distant = list(pop)
    distant[20] *= 20.0
    assert compute_tonal_balance_envelope_score(distant, envelope) < 95.0
    assert compute_tonal_balance_score(pop, pop) == 100.0


def test_parametric_solver_validates_and_constrains_output() -> None:
    pop = GENRE_SEED_PROFILES["pop"]["profile"]
    rock = GENRE_SEED_PROFILES["rock"]["profile"]
    bands = solve_parametric_eq(pop, rock)
    assert len(bands) == 4
    assert all(20.0 <= band["freq"] <= 20_000.0 for band in bands)
    assert all(-6.0 <= band["gain"] <= 6.0 for band in bands)
    assert all(0.3 <= band["q"] <= 8.0 for band in bands)
    for frequency in [band["freq"] for band in bands]:
        overlaps = 0
        for band in bands:
            half_octaves = 0.5 / band["q"]
            if band["freq"] / (2**half_octaves) <= frequency <= band["freq"] * (2**half_octaves):
                overlaps += 1
        assert overlaps <= 2

    with pytest.raises(ValueError, match="40-band"):
        solve_parametric_eq(pop[:-1], rock)
