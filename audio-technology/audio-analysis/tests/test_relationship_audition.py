"""Offline-only Relationship candidate audition DSP tests."""

from __future__ import annotations

import copy

import numpy as np
import pytest

from audio_analysis.mixdown.arrangement import infer_arrangement
from audio_analysis.mixdown.musical_roles import infer_musical_roles
from audio_analysis.mixdown.relationship_audition import apply_candidate_to_prepared_stems
from audio_analysis.mixdown.relationships import infer_relationships
from audio_analysis.mixdown.stem_classifier import StemProfile


SAMPLE_RATE = 8_000


def _relationship() -> tuple[list[dict], dict]:
    time = np.arange(SAMPLE_RATE * 2) / SAMPLE_RATE
    kick = (0.6 * np.sin(2.0 * np.pi * 100.0 * time)).tolist()
    bass = (0.5 * np.sin(2.0 * np.pi * 100.0 * time)).tolist()
    prepared = [
        {"name": "Kick.wav", "samples": kick, "sample_rate": SAMPLE_RATE},
        {"name": "Bass.wav", "samples": bass, "sample_rate": SAMPLE_RATE},
    ]
    profiles = [
        StemProfile("Kick.wav", "kick", 0.95, "fixture", SAMPLE_RATE),
        StemProfile("Bass.wav", "bass", 0.92, "fixture", SAMPLE_RATE),
    ]
    roles = infer_musical_roles(profiles, prepared)
    arrangement = infer_arrangement(prepared).to_dict()
    relationship = infer_relationships(
        profiles, {"masking_matrix": {}}, roles, arrangement, prepared
    )[0].to_dict()
    return prepared, relationship


@pytest.mark.parametrize(
    "strategy",
    ["section_level_automation", "static_eq", "dynamic_eq", "sidechain_ducking"],
)
def test_every_candidate_strategy_renders_a_finite_isolated_change(strategy: str) -> None:
    prepared, relationship = _relationship()
    candidate = next(
        item for item in relationship["candidate_strategies"] if item["strategy"] == strategy
    )
    before = copy.deepcopy(prepared)

    rendered, audit = apply_candidate_to_prepared_stems(
        prepared, relationship, candidate["candidate_id"]
    )

    assert prepared == before
    assert rendered[0] == prepared[0]
    target = np.asarray(rendered[1]["samples"])
    assert np.isfinite(target).all()
    assert not np.allclose(target, np.asarray(prepared[1]["samples"]))
    assert audit["strategy"] == strategy
    assert audit["changed_samples"] > 0
    assert audit["applies_to_production"] is False


def test_candidate_processing_is_confined_to_declared_section_range() -> None:
    prepared, relationship = _relationship()
    candidate = relationship["candidate_strategies"][0]
    candidate["section_ids"] = ["audition-range"]
    candidate["section_ranges"] = [{
        "section_id": "audition-range",
        "start_seconds": 0.5,
        "end_seconds": 1.0,
    }]

    rendered, _ = apply_candidate_to_prepared_stems(
        prepared, relationship, candidate["candidate_id"]
    )

    original = np.asarray(prepared[1]["samples"])
    processed = np.asarray(rendered[1]["samples"])
    assert np.array_equal(processed[: SAMPLE_RATE // 2], original[: SAMPLE_RATE // 2])
    assert np.array_equal(processed[SAMPLE_RATE:], original[SAMPLE_RATE:])
    assert not np.array_equal(processed[SAMPLE_RATE // 2:SAMPLE_RATE], original[SAMPLE_RATE // 2:SAMPLE_RATE])


def test_audition_fails_closed_on_tampered_bounds_and_never_changes_input() -> None:
    prepared, relationship = _relationship()
    candidate = relationship["candidate_strategies"][0]
    candidate["parameters"]["gain_db"] = -8.0
    before = copy.deepcopy(prepared)

    with pytest.raises(ValueError, match="outside audition safety bounds"):
        apply_candidate_to_prepared_stems(prepared, relationship, candidate["candidate_id"])

    assert prepared == before


def test_audition_rejects_section_id_range_mismatch() -> None:
    prepared, relationship = _relationship()
    candidate = relationship["candidate_strategies"][0]
    candidate["section_ranges"][0]["section_id"] = "wrong"

    with pytest.raises(ValueError, match="must match exactly"):
        apply_candidate_to_prepared_stems(prepared, relationship, candidate["candidate_id"])
