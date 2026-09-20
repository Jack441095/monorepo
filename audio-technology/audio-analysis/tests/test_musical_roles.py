"""MusicalRole v1 contract, confidence, provenance, and activity tests."""

from __future__ import annotations

import numpy as np
import pytest

from audio_analysis.mixdown.musical_roles import (
    MUSICAL_ROLE_SCHEMA,
    apply_role_corrections,
    analyze_activity,
    infer_musical_role,
    infer_musical_roles,
    validate_role_correction_payload,
)
from audio_analysis.mixdown.stem_classifier import StemProfile


def profile(name: str, instrument: str, confidence: float = 0.9) -> StemProfile:
    return StemProfile(
        name=name,
        instrument=instrument,
        classification_confidence=confidence,
        classification_method="combined",
        sample_rate=1_000,
    )


def test_activity_contract_tracks_entrance_dropout_and_segments() -> None:
    samples = [0.0] * 500 + [0.5] * 500 + [0.0] * 500 + [0.5] * 500

    activity = analyze_activity(samples, 1_000, window_seconds=0.5)

    assert activity.active_ratio == 0.5
    assert activity.first_active_seconds == 0.5
    assert activity.last_active_seconds == 2.0
    assert activity.segment_count == 2


def test_analyze_activity_array_input_matches_list_input() -> None:
    """Regression guard (2026-07-20): infer_musical_role/infer_arrangement used
    to .tolist() the prepared stem's numpy array before calling this (a ~2.6s
    lossless float64 round-trip on real stems, since this function immediately
    re-converts with np.asarray). Now the array is passed directly. This locks
    in that array and list inputs produce identical evidence -- if they ever
    diverge, the round-trip removal changed behavior."""
    rng = np.random.default_rng(7)
    sr = 44_100
    arr = np.concatenate([
        np.zeros(sr),
        rng.uniform(-1, 1, 3 * sr) * 0.4,
        np.zeros(sr // 2),
        rng.uniform(-1, 1, 2 * sr) * 0.6,
    ]).astype(np.float64)

    assert analyze_activity(arr, sr) == analyze_activity(arr.tolist(), sr)


def test_analyze_activity_handles_empty_and_none_without_numpy_truthiness_error() -> None:
    # The guard was `if not samples` (raises ValueError on a numpy array); it is
    # now a size check so array inputs are safe.
    empty = analyze_activity(np.empty(0, dtype=np.float64), 44_100)
    assert empty.active_ratio == 0.0
    assert analyze_activity([], 44_100) == empty
    assert analyze_activity(None, 44_100).active_ratio == 0.0


def test_explicit_lead_role_has_versioned_provenance() -> None:
    role = infer_musical_role(
        profile("Lead Vocal.wav", "vocal", 0.95),
        {"samples": [0.2] * 1_000, "sample_rate": 1_000},
    )

    assert role.schema == MUSICAL_ROLE_SCHEMA
    assert role.role == "focal_element"
    assert role.priority == "foreground"
    assert role.ambiguous is False
    assert role.confidence == 0.92
    assert {item.source for item in role.provenance} >= {
        "instrument_classifier",
        "classification_method",
        "filename_role_token",
    }


def test_backing_vocal_is_not_promoted_to_focal_element() -> None:
    role = infer_musical_role(profile("BGV Harmony.wav", "backing_vocal", 0.9))

    assert role.role == "supporting_voice"
    assert role.priority == "support"
    assert role.ambiguous is False


def test_uncertain_accompaniment_is_surfaced_not_guessed() -> None:
    role = infer_musical_role(profile("Guitar 04.wav", "guitar", 0.82))

    assert role.role == "accompaniment"
    assert role.ambiguous is True
    assert role.priority == "unknown"
    assert role.confidence == 0.64


def test_sparse_fx_is_inferred_as_transition_from_activity() -> None:
    samples = [0.0] * 1_500 + [0.8] * 500
    role = infer_musical_role(
        profile("Riser FX.wav", "fx", 0.9),
        {"samples": samples, "sample_rate": 1_000},
    )

    assert role.role == "transition"
    assert role.priority == "background"
    assert role.activity.active_ratio == 0.25


def test_batch_inference_keeps_profile_order_and_serializes_contract() -> None:
    profiles = [profile("Kick.wav", "kick"), profile("Mystery.wav", "other", 0.4)]
    prepared = [
        {"name": "Mystery.wav", "samples": [0.1] * 100, "sample_rate": 1_000},
        {"name": "Kick.wav", "samples": [0.2] * 100, "sample_rate": 1_000},
    ]

    roles = infer_musical_roles(profiles, prepared)
    payloads = [role.to_dict() for role in roles]

    assert [role.stem_name for role in roles] == ["Kick.wav", "Mystery.wav"]
    assert roles[1].role == "unknown"
    assert roles[1].ambiguous is True
    assert payloads[0]["schema"] == MUSICAL_ROLE_SCHEMA
    assert payloads[0]["activity"]["active_ratio"] == 1.0


def test_user_correction_is_immutable_explicit_and_deterministic() -> None:
    inferred = infer_musical_role(profile("Guitar 04.wav", "guitar", 0.82))
    corrections = {
        "Guitar 04.wav": {"role": "focal_element", "priority": "foreground"}
    }

    first = apply_role_corrections([inferred], corrections)[0]
    second = apply_role_corrections([inferred], corrections)[0]

    assert inferred.ambiguous is True
    assert first == second
    assert first.role == "focal_element"
    assert first.priority == "foreground"
    assert first.confidence == 1.0
    assert first.ambiguous is False
    assert first.user_corrected is True
    assert first.inference_source == "user_correction_v1"
    assert first.provenance[-1].source == "user_correction"


def test_correction_rejects_unknown_stem_and_partial_or_invalid_values() -> None:
    inferred = infer_musical_role(profile("Guitar.wav", "guitar", 0.82))

    with pytest.raises(ValueError, match="unknown stem"):
        apply_role_corrections(
            [inferred], {"Other.wav": {"role": "focal_element", "priority": "foreground"}}
        )
    with pytest.raises(ValueError, match="exactly role and priority"):
        validate_role_correction_payload({"Guitar.wav": {"role": "focal_element"}})
    with pytest.raises(ValueError, match="Unsupported musical role"):
        validate_role_correction_payload({
            "Guitar.wav": {"role": "make_it_magic", "priority": "foreground"}
        })
