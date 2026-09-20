"""Section-aware relationship inference and intervention-safety tests."""

from __future__ import annotations

import numpy as np
import pytest

from audio_analysis.mixdown.arrangement import infer_arrangement
from audio_analysis.mixdown.musical_roles import infer_musical_roles
from audio_analysis.mixdown.relationships import RELATIONSHIP_SCHEMA, infer_relationships
from audio_analysis.mixdown.stem_classifier import StemProfile


def profile(name: str, instrument: str, confidence: float = 0.9) -> StemProfile:
    return StemProfile(
        name=name,
        instrument=instrument,
        classification_confidence=confidence,
        classification_method="combined",
        sample_rate=10,
    )


def masking(first: str, second: str, score: float = 0.8) -> dict:
    bands_a = {"sub": 0.4, "bass": 0.3, "mids": 0.1}
    bands_b = {"sub": 0.3, "bass": 0.4, "mids": 0.2}
    return {
        "masking_matrix": {
            first: {first: 1.0, second: score},
            second: {first: score, second: 1.0},
        },
        "stems": [
            {"name": first, "bands": bands_a},
            {"name": second, "bands": bands_b},
        ],
    }


def infer(
    profiles: list[StemProfile],
    prepared: list[dict],
    evidence: dict,
    existing_dynamics: dict | None = None,
):
    roles = infer_musical_roles(profiles, prepared)
    arrangement = infer_arrangement(prepared).to_dict()
    return infer_relationships(
        profiles, evidence, roles, arrangement, existing_dynamics=existing_dynamics
    )


def test_kick_bass_collision_uses_only_simultaneous_sections() -> None:
    profiles = [profile("Kick.wav", "kick"), profile("Bass.wav", "bass")]
    prepared = [
        {"name": "Kick.wav", "samples": [0.5] * 20, "sample_rate": 10},
        {"name": "Bass.wav", "samples": [0.0] * 10 + [0.5] * 10, "sample_rate": 10},
    ]

    relationships = infer(profiles, prepared, masking("Kick", "Bass"))

    assert len(relationships) == 1
    relation = relationships[0]
    assert relation.schema == RELATIONSHIP_SCHEMA
    assert relation.relationship_type == "kick_bass_competition"
    assert relation.evidence.simultaneous_activity_ratio == 0.5
    assert relation.evidence.collision_score == 0.4
    assert relation.evidence.section_ids == ["section-002"]
    assert relation.protected_stem == "Kick.wav"
    assert relation.intervention_target == "Bass.wav"
    assert relation.status == "review_required"
    assert relation.least_destructive_intervention is None
    assert relation.intervention_order == []
    assert relation.applies_automatically is False


def test_global_spectral_overlap_without_coactivity_is_not_a_relationship() -> None:
    profiles = [profile("Kick.wav", "kick"), profile("Bass.wav", "bass")]
    prepared = [
        {"name": "Kick.wav", "samples": [0.5] * 10 + [0.0] * 10, "sample_rate": 10},
        {"name": "Bass.wav", "samples": [0.0] * 10 + [0.5] * 10, "sample_rate": 10},
    ]

    assert infer(profiles, prepared, masking("Kick", "Bass", 1.0)) == []


def test_ambiguous_roles_require_review_and_never_get_a_target() -> None:
    profiles = [profile("Guitar.wav", "guitar", confidence=0.5), profile("Keys.wav", "keys", confidence=0.5)]
    prepared = [
        {"name": "Guitar.wav", "samples": [0.5] * 20, "sample_rate": 10},
        {"name": "Keys.wav", "samples": [0.5] * 20, "sample_rate": 10},
    ]

    relation = infer(profiles, prepared, masking("Guitar", "Keys"))[0]

    assert relation.status == "review_required"
    assert relation.protected_stem is None
    assert relation.intervention_target is None
    assert relation.least_destructive_intervention is None
    assert relation.intervention_order == []
    assert relation.confidence <= 0.5


def test_foreground_vocal_is_protected_from_background_texture() -> None:
    profiles = [profile("Lead Vocal.wav", "vocal"), profile("Pad.wav", "synth_pad")]
    prepared = [
        {"name": "Lead Vocal.wav", "samples": [0.5] * 20, "sample_rate": 10},
        {"name": "Pad.wav", "samples": [0.5] * 20, "sample_rate": 10},
    ]

    relation = infer(profiles, prepared, masking("Lead Vocal", "Pad"))[0]

    assert relation.relationship_type == "vocal_instrument_competition"
    assert relation.protected_stem == "Lead Vocal.wav"
    assert relation.intervention_target == "Pad.wav"
    assert relation.evidence.dominant_overlap_bands == ["bass", "sub", "mids"]


def test_low_collision_is_filtered_out() -> None:
    profiles = [profile("Kick.wav", "kick"), profile("Bass.wav", "bass")]
    prepared = [
        {"name": "Kick.wav", "samples": [0.5] * 20, "sample_rate": 10},
        {"name": "Bass.wav", "samples": [0.5] * 20, "sample_rate": 10},
    ]

    assert infer(profiles, prepared, masking("Kick", "Bass", 0.09)) == []


def test_section_local_erb_replaces_conflicting_global_proxy() -> None:
    sample_rate = 8_000
    time = np.arange(sample_rate * 2) / sample_rate
    tone = (0.5 * np.sin(2.0 * np.pi * 100.0 * time)).tolist()
    profiles = [
        StemProfile(name="Kick.wav", instrument="kick", classification_confidence=0.9,
                    classification_method="combined", sample_rate=sample_rate),
        StemProfile(name="Bass.wav", instrument="bass", classification_confidence=0.9,
                    classification_method="combined", sample_rate=sample_rate),
    ]
    prepared = [
        {"name": "Kick.wav", "samples": tone, "sample_rate": sample_rate},
        {"name": "Bass.wav", "samples": tone, "sample_rate": sample_rate},
    ]
    roles = infer_musical_roles(profiles, prepared)
    arrangement = infer_arrangement(prepared).to_dict()
    global_proxy = masking("Kick", "Bass", 0.01)

    relationships = infer_relationships(
        profiles, global_proxy, roles, arrangement, prepared
    )

    assert len(relationships) == 1
    evidence = relationships[0].evidence
    assert evidence.measurement_scope == "section_local_erb"
    assert evidence.masking_index > 0.95
    assert evidence.collision_score > 0.95
    assert evidence.section_collision_scores == {"section-001": 1.0}


def test_section_local_profiles_are_cached_per_stem_and_section(monkeypatch) -> None:
    import audio_analysis.mixdown.relationships as relationships_module

    profiles = [
        profile("Kick.wav", "kick"),
        profile("Bass.wav", "bass"),
        profile("Pad.wav", "synth_pad"),
    ]
    prepared = [
        {"name": item.name, "samples": [0.5] * 20, "sample_rate": 10}
        for item in profiles
    ]
    roles = infer_musical_roles(profiles, prepared)
    arrangement = infer_arrangement(prepared).to_dict()
    calls = []

    def fake_profile(stem_data, section, **kwargs):
        calls.append((stem_data["name"], section["section_id"]))
        return [1.0 / 40.0] * 40

    monkeypatch.setattr(relationships_module, "_section_erb_profile", fake_profile)
    evidence = {
        "masking_matrix": {},
        "stems": [],
    }

    found = infer_relationships(profiles, evidence, roles, arrangement, prepared)

    assert len(found) == 4
    assert sorted(calls) == [
        ("Bass.wav", "section-001"),
        ("Kick.wav", "section-001"),
        ("Pad.wav", "section-001"),
    ]


def test_three_coactive_layers_emit_one_bounded_group_finding() -> None:
    sample_rate = 8_000
    time = np.arange(sample_rate * 2) / sample_rate
    tone = (0.4 * np.sin(2.0 * np.pi * 250.0 * time)).tolist()
    profiles = [
        StemProfile("Lead Vocal.wav", "vocal", 0.95, "fixture", sample_rate),
        StemProfile("Pad A.wav", "synth_pad", 0.90, "fixture", sample_rate),
        StemProfile("Pad B.wav", "strings", 0.90, "fixture", sample_rate),
    ]
    prepared = [
        {"name": item.name, "samples": tone, "sample_rate": sample_rate}
        for item in profiles
    ]
    roles = infer_musical_roles(profiles, prepared)
    arrangement = infer_arrangement(prepared).to_dict()

    found = infer_relationships(profiles, {}, roles, arrangement, prepared)
    groups = [item for item in found if item.relationship_type == "cumulative_spectral_buildup"]

    assert len(groups) == 1
    group = groups[0]
    assert group.source_stems == ["Lead Vocal.wav", "Pad A.wav", "Pad B.wav"]
    assert group.protected_stem == "Lead Vocal.wav"
    assert group.intervention_target is None
    assert group.status == "review_required"
    assert group.confidence <= 0.5
    assert group.evidence.measurement_scope == "section_local_erb_group"
    assert group.evidence.group_size == 3
    assert group.evidence.cumulative_overlap_index > 0.99
    assert group.evidence.pairwise_max_collision > 0.99
    assert group.evidence.incremental_group_pressure > 0.49
    assert group.evidence.section_ids == ["section-001"]
    assert group.candidate_strategies == []
    assert group.intervention_order == []
    assert group.applies_automatically is False
    assert "no single target" in group.selection_rationale


def test_group_masking_requires_three_stems_active_in_the_same_section() -> None:
    sample_rate = 1_000
    profiles = [
        StemProfile("Vocal.wav", "vocal", 0.95, "fixture", sample_rate),
        StemProfile("Pad.wav", "synth_pad", 0.90, "fixture", sample_rate),
        StemProfile("Strings.wav", "strings", 0.90, "fixture", sample_rate),
    ]
    prepared = [
        {"name": "Vocal.wav", "samples": [0.5] * 1_000 + [0.0] * 1_000,
         "sample_rate": sample_rate},
        {"name": "Pad.wav", "samples": [0.5] * 2_000, "sample_rate": sample_rate},
        {"name": "Strings.wav", "samples": [0.0] * 1_000 + [0.5] * 1_000,
         "sample_rate": sample_rate},
    ]
    roles = infer_musical_roles(profiles, prepared)
    arrangement = infer_arrangement(prepared).to_dict()

    found = infer_relationships(profiles, {}, roles, arrangement, prepared)

    assert all(item.relationship_type != "cumulative_spectral_buildup" for item in found)


def test_relationship_thresholds_and_duplicate_names_fail_closed() -> None:
    profiles = [profile("Kick.wav", "kick"), profile("Bass.wav", "bass")]
    prepared = [
        {"name": item.name, "samples": [0.5] * 20, "sample_rate": 10}
        for item in profiles
    ]
    roles = infer_musical_roles(profiles, prepared)
    arrangement = infer_arrangement(prepared).to_dict()

    with pytest.raises(ValueError, match="finite values within 0-1"):
        infer_relationships(
            profiles, {}, roles, arrangement, minimum_group_overlap=float("nan")
        )
    with pytest.raises(ValueError, match="unique profile and role stem names"):
        infer_relationships(
            [profiles[0], profiles[0]], {}, [roles[0], roles[0]], arrangement
        )


def test_existing_kick_bass_sidechain_suppresses_redundant_intervention() -> None:
    profiles = [profile("Kick.wav", "kick"), profile("Bass.wav", "bass")]
    prepared = [
        {"name": "Kick.wav", "samples": [0.5] * 20, "sample_rate": 10},
        {"name": "Bass.wav", "samples": [0.5] * 20, "sample_rate": 10},
    ]
    dynamics = {
        "Bass.wav": {
            "sidechain_detected": True,
            "sidechain_trigger": "Kick.wav",
            "sidechain_correlation": 0.82,
            "sidechain_mean_dip_db": 8.4,
        }
    }

    relation = infer(
        profiles, prepared, masking("Kick", "Bass"), existing_dynamics=dynamics
    )[0]

    assert relation.status == "existing_treatment_detected"
    assert relation.intervention_target == "Bass.wav"
    assert relation.least_destructive_intervention is None
    assert relation.intervention_order == []
    assert relation.evidence.existing_dynamics_treatment == {
        "type": "sidechain_ducking",
        "target_stem": "Bass.wav",
        "trigger_stem": "Kick.wav",
        "correlation": 0.82,
        "mean_dip_db": 8.4,
    }
    assert relation.applies_automatically is False


def test_sidechain_from_different_trigger_does_not_suppress_pair() -> None:
    profiles = [profile("Kick.wav", "kick"), profile("Bass.wav", "bass")]
    prepared = [
        {"name": "Kick.wav", "samples": [0.5] * 20, "sample_rate": 10},
        {"name": "Bass.wav", "samples": [0.5] * 20, "sample_rate": 10},
    ]
    dynamics = {
        "Bass.wav": {
            "sidechain_detected": True,
            "sidechain_trigger": "Snare.wav",
            "sidechain_correlation": 0.9,
            "sidechain_mean_dip_db": 12.0,
        }
    }

    relation = infer(
        profiles, prepared, masking("Kick", "Bass"), existing_dynamics=dynamics
    )[0]

    assert relation.status == "candidate"
    assert relation.least_destructive_intervention == "section_level_automation"
    assert relation.evidence.existing_dynamics_treatment == {}


def test_actionable_relationship_exposes_ranked_bounded_advisory_candidates() -> None:
    profiles = [profile("Kick.wav", "kick"), profile("Bass.wav", "bass")]
    prepared = [
        {"name": "Kick.wav", "samples": [0.5] * 20, "sample_rate": 10},
        {"name": "Bass.wav", "samples": [0.5] * 20, "sample_rate": 10},
    ]

    relation = infer(profiles, prepared, masking("Kick", "Bass", 0.9))[0]
    candidates = relation.candidate_strategies

    assert len(candidates) == 4
    assert [candidate.score for candidate in candidates] == sorted(
        (candidate.score for candidate in candidates), reverse=True
    )
    assert len({candidate.candidate_id for candidate in candidates}) == len(candidates)
    assert relation.least_destructive_intervention == candidates[0].strategy
    assert "highest bounded candidate score" in relation.selection_rationale
    assert all(candidate.target_stem == "Bass.wav" for candidate in candidates)
    assert all(candidate.section_ids == ["section-001"] for candidate in candidates)
    assert all(candidate.section_ranges == [{
        "section_id": "section-001", "start_seconds": 0.0, "end_seconds": 2.0,
    }] for candidate in candidates)
    assert all(candidate.applies_automatically is False for candidate in candidates)

    by_strategy = {candidate.strategy: candidate for candidate in candidates}
    assert -2.5 <= by_strategy["section_level_automation"].parameters["gain_db"] <= -0.75
    assert -2.5 <= by_strategy["static_eq"].parameters["gain_db"] <= -1.0
    assert 1.5 <= by_strategy["dynamic_eq"].parameters["max_reduction_db"] <= 3.5
    assert 1.5 <= by_strategy["sidechain_ducking"].parameters["max_reduction_db"] <= 4.0
    assert all(0.0 <= candidate.score <= 1.0 for candidate in candidates)


def test_review_required_relationship_has_no_processor_candidates() -> None:
    profiles = [profile("Kick.wav", "kick"), profile("Bass.wav", "bass")]
    prepared = [
        {"name": "Kick.wav", "samples": [0.5] * 20, "sample_rate": 10},
        {"name": "Bass.wav", "samples": [0.5] * 20, "sample_rate": 10},
    ]

    relation = infer(profiles, prepared, masking("Kick", "Bass", 0.6))[0]

    assert relation.status == "review_required"
    assert relation.candidate_strategies == []
    assert relation.selection_rationale is None


def test_choose_priority_equal_ranks_tie_breaker() -> None:
    # Bass (priority rank support) vs Drums (priority rank support).
    # Fallback precedence: Bass > Drums, so Bass protects and Drums is targeted.
    profiles = [
        profile("Bass.wav", "bass", confidence=0.75),
        profile("Drums.wav", "full_drum_bus", confidence=0.75),
    ]
    prepared = [
        {"name": "Bass.wav", "samples": [0.5] * 20, "sample_rate": 10},
        {"name": "Drums.wav", "samples": [0.5] * 20, "sample_rate": 10},
    ]

    relation = infer(profiles, prepared, masking("Bass", "Drums", 0.9))[0]
    
    assert relation.protected_stem == "Bass.wav"
    assert relation.intervention_target == "Drums.wav"

