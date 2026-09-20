"""Arrangement v1 timing, density, transitions, and conservative-label tests."""

from __future__ import annotations

import pytest

from audio_analysis.mixdown.arrangement import (
    ARRANGEMENT_CORRECTION_SCHEMA,
    ARRANGEMENT_SCHEMA,
    apply_arrangement_corrections,
    infer_arrangement,
    validate_arrangement_correction_payload,
)


def stem(name: str, samples: list[float], sample_rate: int = 10) -> dict:
    return {"name": name, "samples": samples, "sample_rate": sample_rate}


def test_arrangement_segments_on_real_stem_entrance() -> None:
    arrangement = infer_arrangement([
        stem("kick.wav", [0.5] * 20),
        stem("vocal.wav", [0.0] * 10 + [0.5] * 10),
    ])

    assert arrangement.schema == ARRANGEMENT_SCHEMA
    assert arrangement.duration_seconds == 2.0
    assert len(arrangement.sections) == 2
    first, second = arrangement.sections
    assert (first.start_seconds, first.end_seconds) == (0.0, 1.0)
    assert first.active_stems == ["kick.wav"]
    assert first.entering_stems == ["kick.wav"]
    assert first.density_band == "moderate"
    assert second.active_stems == ["kick.wav", "vocal.wav"]
    assert second.entering_stems == ["vocal.wav"]
    assert second.exiting_stems == []
    assert second.density_band == "dense"
    assert all(section.semantic_label is None for section in arrangement.sections)
    assert arrangement.semantic_labels_inferred is False


def test_single_window_dropout_is_bridged_to_prevent_micro_sections() -> None:
    arrangement = infer_arrangement([
        stem("pad.wav", [0.5] * 5 + [0.0] * 5 + [0.5] * 5),
    ])

    assert len(arrangement.sections) == 1
    assert arrangement.sections[0].active_stems == ["pad.wav"]


def test_all_silent_session_is_explicit_not_invented_activity() -> None:
    arrangement = infer_arrangement([
        stem("empty-a.wav", [0.0] * 10),
        stem("empty-b.wav", [0.0] * 10),
    ])

    assert len(arrangement.sections) == 1
    section = arrangement.sections[0]
    assert section.active_stems == []
    assert section.density_ratio == 0.0
    assert section.density_band == "silent"


def test_arrangement_rejects_unaligned_rates_and_duplicate_names() -> None:
    with pytest.raises(ValueError, match="shared sample rate"):
        infer_arrangement([stem("one.wav", [0.1], 10), stem("two.wav", [0.1], 20)])
    with pytest.raises(ValueError, match="unique stem names"):
        infer_arrangement([stem("same.wav", [0.1]), stem("same.wav", [0.2])])


def test_empty_arrangement_contract_is_well_formed() -> None:
    arrangement = infer_arrangement([])

    assert arrangement.schema == ARRANGEMENT_SCHEMA
    assert arrangement.duration_seconds == 0.0
    assert arrangement.stem_count == 0
    assert arrangement.sections == []


def test_complete_manual_timeline_recomputes_transitions_and_density() -> None:
    inferred = infer_arrangement([
        stem("kick.wav", [0.5] * 20),
        stem("vocal.wav", [0.0] * 10 + [0.5] * 10),
    ])
    corrections = {
        "schema": ARRANGEMENT_CORRECTION_SCHEMA,
        "sections": [
            {"start_seconds": 0.0, "end_seconds": 0.8, "active_stems": ["kick.wav"]},
            {"start_seconds": 0.8, "end_seconds": 2.0,
             "active_stems": ["vocal.wav", "kick.wav"]},
        ],
    }

    corrected = apply_arrangement_corrections(
        inferred, corrections, ["kick.wav", "vocal.wav"]
    )

    assert corrected.user_corrected is True
    assert corrected.inference_source == "user_correction_v1"
    assert corrected.correction_schema == ARRANGEMENT_CORRECTION_SCHEMA
    assert corrected.semantic_labels_inferred is False
    assert [(item.start_seconds, item.end_seconds) for item in corrected.sections] == [
        (0.0, 0.8), (0.8, 2.0),
    ]
    assert corrected.sections[0].entering_stems == ["kick.wav"]
    assert corrected.sections[1].entering_stems == ["vocal.wav"]
    assert corrected.sections[1].density_ratio == 1.0
    assert corrected.sections[1].boundary_confidence == 1.0
    assert all(item.semantic_label is None for item in corrected.sections)


@pytest.mark.parametrize(
    ("sections", "message"),
    [
        ([{"start_seconds": 0.1, "end_seconds": 1.0, "active_stems": []}], "contiguous"),
        ([{"start_seconds": 0.0, "end_seconds": 0.05, "active_stems": []}], "at least 0.1"),
        ([
            {"start_seconds": 0.0, "end_seconds": 1.0, "active_stems": []},
            {"start_seconds": 0.9, "end_seconds": 2.0, "active_stems": []},
        ], "contiguous"),
        ([{
            "start_seconds": 0.0, "end_seconds": 1.0,
            "active_stems": ["kick.wav", "kick.wav"],
        }], "unique non-empty"),
    ],
)
def test_manual_timeline_shape_fails_closed(sections, message) -> None:
    with pytest.raises(ValueError, match=message):
        validate_arrangement_correction_payload({
            "schema": ARRANGEMENT_CORRECTION_SCHEMA,
            "sections": sections,
        })


def test_manual_timeline_rejects_unknown_stems_and_wrong_final_duration() -> None:
    inferred = infer_arrangement([stem("kick.wav", [0.5] * 20)])
    with pytest.raises(ValueError, match="unknown stem"):
        apply_arrangement_corrections(inferred, {
            "schema": ARRANGEMENT_CORRECTION_SCHEMA,
            "sections": [{
                "start_seconds": 0.0, "end_seconds": 2.0,
                "active_stems": ["bass.wav"],
            }],
        }, ["kick.wav"])
    with pytest.raises(ValueError, match="must end at"):
        apply_arrangement_corrections(inferred, {
            "schema": ARRANGEMENT_CORRECTION_SCHEMA,
            "sections": [{
                "start_seconds": 0.0, "end_seconds": 1.5,
                "active_stems": ["kick.wav"],
            }],
        }, ["kick.wav"])


def test_arrangement_merges_short_sections_with_high_jaccard_similarity() -> None:
    # 10 stems, sample rate 10.
    # section 1: duration 5.0 seconds (50 samples). Stems 1 to 10 are active.
    # section 2: duration 2.0 seconds (20 samples). Stems 1 to 9 are active.
    # Total duration is 7.0 seconds.
    # Jaccard similarity is 9/10 = 0.90, which is >= 0.70.
    # Section 2 is 2.0s < 4.0s min_duration, so it should merge with Section 1.
    stems = []
    for i in range(1, 11):
        # stem 10 is inactive in the last 2 seconds
        samples = [0.5] * 50 + ([0.0] * 20 if i == 10 else [0.5] * 20)
        stems.append(stem(f"stem_{i}.wav", samples, 10))
        
    arrangement = infer_arrangement(stems)
    # They should have been merged into 1 section containing stems 1 to 10.
    assert len(arrangement.sections) == 1
    sec = arrangement.sections[0]
    assert sec.start_seconds == 0.0
    assert sec.end_seconds == 7.0
    assert len(sec.active_stems) == 10

