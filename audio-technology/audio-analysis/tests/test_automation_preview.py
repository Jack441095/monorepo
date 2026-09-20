"""Sparse coordinated section-automation preview contract tests."""

from __future__ import annotations

import copy

import numpy as np
import pytest

from audio_analysis.mixdown.automation_preview import (
    AUTOMATION_PREVIEW_SCHEMA,
    MAX_MOVES,
    apply_automation_preview,
    build_automation_preview,
)


def _relationship(
    relationship_id: str,
    *,
    target: str,
    protected: str | None,
    section_id: str = "section-001",
    start: float = 0.0,
    end: float = 2.0,
    score: float = 0.9,
    collision: float = 0.9,
) -> dict:
    candidate_id = f"{relationship_id}-candidate-01"
    return {
        "schema": "audio-too.relationship.v1",
        "relationship_id": relationship_id,
        "relationship_type": "vocal_instrument_competition",
        "source_stems": [protected or "Other.wav", target],
        "protected_stem": protected,
        "intervention_target": target,
        "status": "candidate",
        "evidence": {
            "section_ids": [section_id],
            "section_collision_scores": {section_id: collision},
            "collision_score": collision,
        },
        "candidate_strategies": [{
            "schema": "audio-too.relationship-candidate.v1",
            "candidate_id": candidate_id,
            "strategy": "section_level_automation",
            "target_stem": target,
            "section_ids": [section_id],
            "section_ranges": [{
                "section_id": section_id,
                "start_seconds": start,
                "end_seconds": end,
            }],
            "parameters": {"gain_db": -1.5, "attack_ms": 80.0, "release_ms": 180.0},
            "score": score,
            "applies_automatically": False,
        }],
        "applies_automatically": False,
    }


def test_preview_selects_highest_duplicate_and_respects_protected_source() -> None:
    lower = _relationship("rel-001", target="Pad.wav", protected="Vocal.wav", score=0.7)
    higher = _relationship("rel-002", target="Pad.wav", protected="Vocal.wav", score=0.95)
    protects_bass = _relationship(
        "rel-003", target="Texture.wav", protected="Bass.wav", score=0.8
    )
    cuts_bass = _relationship("rel-004", target="Bass.wav", protected="Kick.wav", score=0.9)

    preview = build_automation_preview([lower, higher, protects_bass, cuts_bass])

    assert preview.schema == AUTOMATION_PREVIEW_SCHEMA
    assert preview.status == "ready_for_offline_audition"
    assert preview.applies_automatically is False
    assert preview.production_processing_enabled is False
    assert [(move.source_relationship_id, move.target_stem) for move in preview.moves] == [
        ("rel-002", "Pad.wav"),
        ("rel-003", "Texture.wav"),
    ]
    reasons = {item.source_relationship_id: item.reason for item in preview.suppressed_moves}
    assert reasons["rel-001"] == "lower_ranked_duplicate_target_section"
    assert reasons["rel-004"] == "target_protected_by_another_relationship"


def test_preview_enforces_minimum_length_and_whole_song_move_budget() -> None:
    relationships = [
        _relationship(
            f"rel-{index:03d}",
            target=f"Stem {index}.wav",
            protected=None,
            section_id=f"section-{index:03d}",
            start=float(index * 2),
            end=float(index * 2 + 2),
            score=1.0 - index * 0.01,
        )
        for index in range(1, 11)
    ]
    relationships.append(_relationship(
        "rel-099", target="Short.wav", protected=None,
        section_id="section-short", start=0.0, end=0.5, score=1.0,
    ))

    preview = build_automation_preview(relationships)

    assert len(preview.moves) == MAX_MOVES
    reasons = [item.reason for item in preview.suppressed_moves]
    assert "segment_too_short" in reasons
    assert reasons.count("song_move_budget_exhausted") == 2


def test_apply_preview_changes_only_declared_ranges_on_copied_stems() -> None:
    preview = build_automation_preview([
        _relationship(
            "rel-001", target="Pad.wav", protected="Vocal.wav",
            section_id="section-002", start=1.0, end=2.0,
        )
    ])
    sample_rate = 1_000
    prepared = [
        {"name": "Vocal.wav", "samples": [0.4] * 3_000, "sample_rate": sample_rate},
        {"name": "Pad.wav", "samples": [0.3] * 3_000, "sample_rate": sample_rate},
    ]
    before = copy.deepcopy(prepared)

    rendered, audit = apply_automation_preview(prepared, preview)

    assert prepared == before
    assert rendered[0] == prepared[0]
    original = np.asarray(prepared[1]["samples"])
    processed = np.asarray(rendered[1]["samples"])
    assert np.array_equal(processed[:1_000], original[:1_000])
    assert np.array_equal(processed[2_000:], original[2_000:])
    assert not np.array_equal(processed[1_000:2_000], original[1_000:2_000])
    assert float(np.max(np.abs(np.diff(processed)))) < 0.001
    assert audit["move_count"] == 1
    assert audit["production_processing_enabled"] is False


def test_apply_preview_fails_closed_on_tampered_gain() -> None:
    preview = build_automation_preview([
        _relationship("rel-001", target="Pad.wav", protected="Vocal.wav")
    ]).to_dict()
    preview["moves"][0]["gain_db"] = -8.0
    prepared = [{"name": "Pad.wav", "samples": [0.3] * 3_000, "sample_rate": 1_000}]

    with pytest.raises(ValueError, match="outside safety bounds"):
        apply_automation_preview(prepared, preview)


def test_apply_preview_uses_one_linked_gain_curve_for_stereo_channels() -> None:
    preview = build_automation_preview([
        _relationship("rel-001", target="Pad.wav", protected="Vocal.wav")
    ])
    left = np.full(3_000, 0.3)
    right = np.full(3_000, -0.15)
    prepared = [{
        "name": "Pad.wav",
        "samples": (0.5 * (left + right)).tolist(),
        "left_samples": left.tolist(),
        "right_samples": right.tolist(),
        "stereo_preserved": True,
        "sample_rate": 1_000,
    }]

    rendered, _ = apply_automation_preview(prepared, preview)
    left_gain = np.asarray(rendered[0]["left_samples"]) / left
    right_gain = np.asarray(rendered[0]["right_samples"]) / right

    assert np.allclose(left_gain, right_gain)
    assert np.allclose(
        rendered[0]["samples"],
        0.5 * (
            np.asarray(rendered[0]["left_samples"])
            + np.asarray(rendered[0]["right_samples"])
        ),
    )
