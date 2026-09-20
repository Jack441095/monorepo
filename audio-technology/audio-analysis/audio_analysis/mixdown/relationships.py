"""Section-aware, evidence-only relationships between AutoMix stems."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from itertools import combinations
from pathlib import Path

import numpy as np

from .musical_roles import MusicalRole
from .stem_classifier import StemProfile
from audio_analysis.analysis_core.dsp_metrics import spectrum_magnitudes
from audio_analysis.analysis_core.erb_masking import compute_erb_profile, get_erb_bands

RELATIONSHIP_SCHEMA = "audio-too.relationship.v1"
RELATIONSHIP_CANDIDATE_SCHEMA = "audio-too.relationship-candidate.v1"
_PRIORITY_RANK = {"unknown": 0, "background": 1, "support": 2, "foreground": 3}
ACTIONABLE_COLLISION_SCORE = 0.20
ACTIONABLE_CONFIDENCE = 0.55
_MEASUREMENT_RELIABILITY = {
    "section_local_erb": 1.0,
    "track_level_masking_fallback": 0.75,
}


@dataclass(frozen=True)
class RelationshipEvidence:
    measurement_scope: str
    masking_index: float
    simultaneous_activity_ratio: float
    collision_score: float
    coactive_seconds: float
    dominant_overlap_bands: list[str]
    section_ids: list[str]
    section_collision_scores: dict[str, float]
    existing_dynamics_treatment: dict
    group_size: int = 2
    pairwise_max_collision: float | None = None
    cumulative_overlap_index: float | None = None
    incremental_group_pressure: float | None = None


@dataclass(frozen=True)
class RelationshipCandidate:
    schema: str
    candidate_id: str
    strategy: str
    target_stem: str
    section_ids: list[str]
    section_ranges: list[dict]
    parameters: dict
    estimated_problem_reduction: float
    collateral_change_risk: float
    intent_preservation: float
    artifact_risk: float
    score: float
    rationale: str
    applies_automatically: bool = False


@dataclass(frozen=True)
class StemRelationship:
    schema: str
    relationship_id: str
    relationship_type: str
    source_stems: list[str]
    protected_stem: str | None
    intervention_target: str | None
    status: str
    confidence: float
    evidence: RelationshipEvidence
    least_destructive_intervention: str | None
    intervention_order: list[str] = field(default_factory=list)
    candidate_strategies: list[RelationshipCandidate] = field(default_factory=list)
    selection_rationale: str | None = None
    applies_automatically: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _masking_name(name: str) -> str:
    return Path(name).name.rsplit(".", 1)[0]


def _relationship_type(a: str, b: str) -> str:
    instruments = {a, b}
    if instruments & {"kick"} and instruments & {"bass", "sub_bass"}:
        return "kick_bass_competition"
    if instruments <= {"vocal", "backing_vocal"}:
        return "lead_backing_voice_competition"
    if instruments & {"vocal", "backing_vocal"}:
        return "vocal_instrument_competition"
    if instruments & {"guitar", "keys", "synth_lead", "synth_pad", "strings"}:
        return "harmonic_layer_competition"
    return "spectral_competition"


def _choose_priority(
    first: MusicalRole, second: MusicalRole, first_instrument: str, second_instrument: str
) -> tuple[str | None, str | None]:
    if first.ambiguous or second.ambiguous:
        return None, None
    first_rank = _PRIORITY_RANK[first.priority]
    second_rank = _PRIORITY_RANK[second.priority]
    if first_rank > second_rank:
        return first.stem_name, second.stem_name
    if second_rank > first_rank:
        return second.stem_name, first.stem_name
    if first_instrument == "vocal" and second_instrument != "vocal":
        return first.stem_name, second.stem_name
    if second_instrument == "vocal" and first_instrument != "vocal":
        return second.stem_name, first.stem_name
    if first_instrument == "kick" and second_instrument in {"bass", "sub_bass"}:
        return first.stem_name, second.stem_name
    if second_instrument == "kick" and first_instrument in {"bass", "sub_bass"}:
        return second.stem_name, first.stem_name

    # Fallback precedence order when priority ranks are equal
    precedence = {
        "vocal": 15,
        "kick": 14,
        "bass": 13,
        "sub_bass": 12,
        "snare": 11,
        "full_drum_bus": 10,
        "hihat": 9,
        "percussion": 8,
        "brass": 7,
        "guitar": 6,
        "keys": 5,
        "synth_lead": 4,
        "synth_pad": 3,
        "strings": 2,
        "ambient": 1,
        "fx": 0,
    }
    first_prec = precedence.get(first_instrument, -1)
    second_prec = precedence.get(second_instrument, -1)
    if first_prec > second_prec:
        return first.stem_name, second.stem_name
    if second_prec > first_prec:
        return second.stem_name, first.stem_name

    return None, None


def _named_band(frequency_hz: float) -> str:
    if frequency_hz < 60.0:
        return "sub"
    if frequency_hz < 150.0:
        return "bass"
    if frequency_hz < 400.0:
        return "low_mids"
    if frequency_hz < 2_000.0:
        return "mids"
    if frequency_hz < 6_000.0:
        return "presence"
    if frequency_hz < 8_000.0:
        return "sibilance"
    return "air"


def _relationship_confidence(
    first_role: MusicalRole,
    second_role: MusicalRole,
    *,
    masking_index: float,
    simultaneous_ratio: float,
    measurement_scope: str,
) -> float:
    """Calibrate decision confidence from independent evidence dimensions."""
    role_certainty = min(first_role.confidence, second_role.confidence)
    coactivity_support = 0.5 + 0.5 * simultaneous_ratio
    overlap_support = 0.5 + 0.5 * masking_index
    measurement_reliability = _MEASUREMENT_RELIABILITY.get(measurement_scope, 0.5)
    return max(
        0.0,
        min(
            1.0,
            role_certainty
            * coactivity_support
            * overlap_support
            * measurement_reliability,
        ),
    )


_BAND_CENTRES_HZ = {
    "sub": 45.0,
    "bass": 100.0,
    "low_mids": 250.0,
    "mids": 1_000.0,
    "presence": 3_500.0,
    "sibilance": 7_000.0,
    "air": 12_000.0,
}


def _candidate_score(
    problem_reduction: float,
    collateral_risk: float,
    intent_preservation: float,
    artifact_risk: float,
) -> float:
    return max(0.0, min(1.0,
        0.45 * problem_reduction
        + 0.30 * intent_preservation
        + 0.15 * (1.0 - collateral_risk)
        + 0.10 * (1.0 - artifact_risk)
    ))


def _candidate_strategies(
    *,
    relationship_id: str,
    relationship_type: str,
    target_stem: str,
    section_ids: list[str],
    sections: list[dict],
    dominant_bands: list[str],
    collision_score: float,
) -> list[RelationshipCandidate]:
    """Generate bounded, advisory-only alternatives for isolated A/B evaluation."""
    strength = max(0.0, min(1.0, collision_score))
    gain_db = -round(min(2.5, max(0.75, 0.5 + 2.0 * strength)), 2)
    eq_cut_db = -round(min(2.5, max(1.0, 0.75 + 2.0 * strength)), 2)
    dynamic_reduction_db = round(min(3.5, max(1.5, 1.0 + 3.0 * strength)), 2)
    primary_band = dominant_bands[0] if dominant_bands else "mids"
    frequency_hz = _BAND_CENTRES_HZ[primary_band]
    section_id_set = set(section_ids)
    section_ranges = [
        {
            "section_id": str(section.get("section_id", "")),
            "start_seconds": round(float(section.get("start_seconds", 0.0)), 6),
            "end_seconds": round(float(section.get("end_seconds", 0.0)), 6),
        }
        for section in sections
        if str(section.get("section_id", "")) in section_id_set
    ]
    specs = [
        (
            "section_level_automation",
            {"gain_db": gain_db, "attack_ms": 80.0, "release_ms": 180.0},
            0.55 + 0.30 * strength, 0.10, 0.95, 0.05,
            "Reduce only the lower-priority source in measured coactive sections.",
        ),
        (
            "static_eq",
            {"frequency_hz": frequency_hz, "gain_db": eq_cut_db, "q": 1.0},
            0.50 + 0.25 * strength, 0.38, 0.68, 0.08,
            f"Apply a broad bounded cut around the dominant {primary_band} overlap.",
        ),
        (
            "dynamic_eq",
            {
                "frequency_hz": frequency_hz,
                "max_reduction_db": dynamic_reduction_db,
                "q": 1.2,
                "attack_ms": 20.0,
                "release_ms": 140.0,
            },
            0.62 + 0.28 * strength, 0.20, 0.82, 0.18,
            f"Reduce the dominant {primary_band} overlap only when it becomes excessive.",
        ),
    ]
    if relationship_type == "kick_bass_competition":
        specs.append((
            "sidechain_ducking",
            {
                "max_reduction_db": round(min(4.0, max(1.5, 1.0 + 3.0 * strength)), 2),
                "attack_ms": 8.0,
                "release_ms": 120.0,
            },
            0.70 + 0.25 * strength, 0.24, 0.78, 0.30,
            "Duck the lower-priority low-end source from the paired rhythmic trigger.",
        ))
    candidates = []
    for index, (strategy, parameters, reduction, collateral, intent, artifact, rationale) in enumerate(specs, 1):
        reduction = min(1.0, reduction)
        candidates.append(RelationshipCandidate(
            schema=RELATIONSHIP_CANDIDATE_SCHEMA,
            candidate_id=f"{relationship_id}-candidate-{index:02d}",
            strategy=strategy,
            target_stem=target_stem,
            section_ids=list(section_ids),
            section_ranges=section_ranges,
            parameters=parameters,
            estimated_problem_reduction=round(reduction, 4),
            collateral_change_risk=round(collateral, 4),
            intent_preservation=round(intent, 4),
            artifact_risk=round(artifact, 4),
            score=round(_candidate_score(reduction, collateral, intent, artifact), 4),
            rationale=rationale,
        ))
    return sorted(candidates, key=lambda candidate: (-candidate.score, candidate.candidate_id))


def _section_erb_profile(
    stem: dict,
    section: dict,
    *,
    max_frames: int = 8,
    frame_size: int = 4096,
) -> list[float]:
    """Bounded average ERB profile sampled only inside one arrangement section."""
    sample_values = stem.get("samples", [])
    sample_count = len(sample_values)
    sample_rate = int(stem.get("sample_rate", 0))
    if sample_count < 256 or sample_rate <= 0:
        return [0.0] * 40
    start = max(0, int(float(section.get("start_seconds", 0.0)) * sample_rate))
    end = min(sample_count, int(float(section.get("end_seconds", 0.0)) * sample_rate))
    if end - start < 256:
        return [0.0] * 40
    # Convert only the measured section. Converting a multi-minute Python list
    # once per stem/section cache entry made real projects scale with repeated
    # full-song copies even though the FFT frames below are strictly local.
    samples = np.asarray(sample_values[start:end], dtype=np.float64)
    stereo_channels = None
    if stem.get("stereo_preserved"):
        left_values = stem.get("left_samples", [])
        right_values = stem.get("right_samples", [])
        if len(left_values) == sample_count and len(right_values) == sample_count:
            stereo_channels = (
                np.asarray(left_values[start:end], dtype=np.float64),
                np.asarray(right_values[start:end], dtype=np.float64),
            )
    actual_frame = min(frame_size, end - start)
    fft_size = 1
    while fft_size * 2 <= actual_frame:
        fft_size *= 2
    if fft_size < 256:
        return [0.0] * 40
    latest_start = samples.size - fft_size
    if latest_start <= 0:
        starts = [0]
    else:
        starts = sorted(set(
            int(value) for value in np.linspace(0, latest_start, num=max_frames)
        ))
    average = np.zeros(40, dtype=np.float64)
    used = 0
    for frame_start in starts:
        channels = stereo_channels or (samples,)
        for channel in channels:
            frame = channel[frame_start:frame_start + fft_size]
            if frame.size < fft_size or float(np.max(np.abs(frame))) < 1e-9:
                continue
            magnitudes, fft_n = spectrum_magnitudes(
                frame.tolist(), sample_rate, size=fft_size
            )
            if not magnitudes or fft_n <= 0:
                continue
            average += np.asarray(
                compute_erb_profile(magnitudes, sample_rate, fft_n, num_bands=40),
                dtype=np.float64,
            )
            used += 1
    if not used or float(np.sum(average)) <= 0.0:
        return [0.0] * 40
    average /= float(np.sum(average))
    return average.tolist()


def infer_relationships(
    profiles: list[StemProfile],
    masking_results: dict,
    roles: list[MusicalRole],
    arrangement: dict,
    prepared_stems: list[dict] | None = None,
    existing_dynamics: dict[str, dict] | None = None,
    *,
    minimum_collision_score: float = 0.10,
    minimum_group_overlap: float = 0.35,
) -> list[StemRelationship]:
    """Combine spectral masking with actual coactivity; never modify the mix."""
    if (
        not np.isfinite(minimum_collision_score)
        or not 0.0 <= minimum_collision_score <= 1.0
        or not np.isfinite(minimum_group_overlap)
        or not 0.0 <= minimum_group_overlap <= 1.0
    ):
        raise ValueError("Relationship collision thresholds must be finite values within 0-1.")
    profile_by_name = {profile.name: profile for profile in profiles}
    role_by_name = {role.stem_name: role for role in roles}
    if len(profile_by_name) != len(profiles) or len(role_by_name) != len(roles):
        raise ValueError("Relationship inference requires unique profile and role stem names.")
    if set(profile_by_name) != set(role_by_name):
        raise ValueError("Relationship inference requires one role for every profile.")
    masking = masking_results.get("masking_matrix", {}) if isinstance(masking_results, dict) else {}
    stem_rows = {
        row.get("name"): row for row in masking_results.get("stems", [])
        if isinstance(row, dict)
    } if isinstance(masking_results, dict) else {}
    sections = arrangement.get("sections", []) if isinstance(arrangement, dict) else []
    prepared_by_name = {
        str(stem.get("name")): stem for stem in (prepared_stems or [])
    }
    use_section_local = bool(prepared_stems) and set(prepared_by_name) == set(profile_by_name)
    erb_cache: dict[tuple[str, str], list[float]] = {}
    erb_bands = get_erb_bands(num_bands=40)
    relationships = []
    for first_name, second_name in combinations(sorted(profile_by_name), 2):
        active_sections = []
        union_seconds = 0.0
        coactive_seconds = 0.0
        for section in sections:
            active = set(section.get("active_stems", []))
            duration = max(0.0, float(section.get("end_seconds", 0.0)) - float(section.get("start_seconds", 0.0)))
            if first_name in active or second_name in active:
                union_seconds += duration
            if first_name in active and second_name in active:
                coactive_seconds += duration
                active_sections.append(str(section.get("section_id", "")))
        simultaneous_ratio = coactive_seconds / union_seconds if union_seconds else 0.0
        first_key = _masking_name(first_name)
        second_key = _masking_name(second_name)
        section_scores: dict[str, float] = {}
        aggregate_overlap = np.zeros(40, dtype=np.float64)
        if use_section_local and coactive_seconds > 0.0:
            weighted_score = 0.0
            for section in sections:
                section_id = str(section.get("section_id", ""))
                if section_id not in active_sections:
                    continue
                duration = max(
                    0.0,
                    float(section.get("end_seconds", 0.0))
                    - float(section.get("start_seconds", 0.0)),
                )
                profiles_for_pair = []
                for name in (first_name, second_name):
                    cache_key = (name, section_id)
                    if cache_key not in erb_cache:
                        erb_cache[cache_key] = _section_erb_profile(
                            prepared_by_name[name], section
                        )
                    profiles_for_pair.append(np.asarray(erb_cache[cache_key]))
                overlap = np.minimum(profiles_for_pair[0], profiles_for_pair[1])
                score = float(np.sum(overlap))
                section_scores[section_id] = round(score, 4)
                weighted_score += score * duration
                aggregate_overlap += overlap * duration
            masking_index = weighted_score / coactive_seconds
            measurement_scope = "section_local_erb"
        else:
            forward = float(masking.get(first_key, {}).get(second_key, 0.0))
            reverse = float(masking.get(second_key, {}).get(first_key, forward))
            masking_index = max(0.0, min(1.0, (forward + reverse) / 2.0))
            measurement_scope = "track_level_masking_fallback"
        collision = masking_index * simultaneous_ratio
        if collision < minimum_collision_score:
            continue
        first_bands = stem_rows.get(first_key, {}).get("bands", {})
        second_bands = stem_rows.get(second_key, {}).get("bands", {})
        if use_section_local and float(np.sum(aggregate_overlap)) > 0.0:
            band_overlap: dict[str, float] = {}
            for index, value in enumerate(aggregate_overlap):
                band = _named_band(float(erb_bands[index][0]))
                band_overlap[band] = band_overlap.get(band, 0.0) + float(value)
        else:
            band_overlap = {
                band: min(float(value), float(second_bands.get(band, 0.0)))
                for band, value in first_bands.items()
            }
        dominant = [
            band for band, value in sorted(band_overlap.items(), key=lambda item: (-item[1], item[0]))
            if value > 0.0
        ][:3]
        first_profile = profile_by_name[first_name]
        second_profile = profile_by_name[second_name]
        relationship_type = _relationship_type(
            first_profile.instrument, second_profile.instrument
        )
        first_role = role_by_name[first_name]
        second_role = role_by_name[second_name]
        protected, target = _choose_priority(
            first_role, second_role, first_profile.instrument, second_profile.instrument
        )
        confidence = _relationship_confidence(
            first_role,
            second_role,
            masking_index=masking_index,
            simultaneous_ratio=simultaneous_ratio,
            measurement_scope=measurement_scope,
        )
        actionable = bool(
            target
            and collision >= ACTIONABLE_COLLISION_SCORE
            and confidence >= ACTIONABLE_CONFIDENCE
        )
        status = "candidate" if actionable else "review_required"
        intervention = "section_level_automation" if actionable else None
        treatment = {}
        if actionable:
            dynamics = (existing_dynamics or {}).get(target, {})
            other = first_name if target == second_name else second_name
            if dynamics.get("sidechain_detected") and dynamics.get("sidechain_trigger") == other:
                treatment = {
                    "type": "sidechain_ducking",
                    "target_stem": target,
                    "trigger_stem": other,
                    "correlation": float(dynamics.get("sidechain_correlation", 0.0)),
                    "mean_dip_db": float(dynamics.get("sidechain_mean_dip_db", 0.0)),
                }
                status = "existing_treatment_detected"
                intervention = None
        relationship_id = f"rel-{len(relationships) + 1:03d}"
        candidates = (
            _candidate_strategies(
                relationship_id=relationship_id,
                relationship_type=relationship_type,
                target_stem=target,
                section_ids=active_sections,
                sections=sections,
                dominant_bands=dominant,
                collision_score=collision,
            )
            if actionable and not treatment else []
        )
        selection_rationale = None
        if candidates:
            selected = candidates[0]
            intervention = selected.strategy
            alternatives = ", ".join(
                f"{candidate.strategy} ({candidate.score:.4f})"
                for candidate in candidates[1:]
            )
            selection_rationale = (
                f"Selected {selected.strategy} for {target} because it has the highest bounded "
                f"candidate score ({selected.score:.4f}); the protected source {protected} is "
                f"left unchanged. Lower-ranked alternatives: {alternatives}. Isolated A/B "
                "review is still required."
            )
        if status == "review_required":
            confidence = min(confidence, 0.5)
        relationships.append(StemRelationship(
            schema=RELATIONSHIP_SCHEMA,
            relationship_id=relationship_id,
            relationship_type=relationship_type,
            source_stems=[first_name, second_name],
            protected_stem=protected,
            intervention_target=target,
            status=status,
            confidence=round(confidence, 4),
            evidence=RelationshipEvidence(
                measurement_scope=measurement_scope,
                masking_index=round(masking_index, 4),
                simultaneous_activity_ratio=round(simultaneous_ratio, 4),
                collision_score=round(collision, 4),
                coactive_seconds=round(coactive_seconds, 3),
                dominant_overlap_bands=dominant,
                section_ids=active_sections,
                section_collision_scores=section_scores,
                existing_dynamics_treatment=treatment,
            ),
            least_destructive_intervention=intervention,
            intervention_order=(
                [
                    strategy
                    for strategy in (
                        "section_level_automation",
                        "static_eq",
                        "dynamic_eq",
                        "sidechain_ducking",
                    )
                    if strategy in {candidate.strategy for candidate in candidates}
                ]
            ),
            candidate_strategies=candidates,
            selection_rationale=selection_rationale,
        ))

    if use_section_local:
        sections_by_group: dict[tuple[str, ...], list[dict]] = {}
        for section in sections:
            active_group = tuple(sorted(
                name for name in section.get("active_stems", []) if name in profile_by_name
            ))
            if len(active_group) >= 3:
                sections_by_group.setdefault(active_group, []).append(section)
        for source_names, group_sections in sorted(sections_by_group.items()):
            group_size = len(source_names)
            weighted_overlap = 0.0
            weighted_pair_max = 0.0
            coactive_seconds = 0.0
            section_scores: dict[str, float] = {}
            aggregate_redundancy = np.zeros(40, dtype=np.float64)
            for section in group_sections:
                section_id = str(section.get("section_id", ""))
                duration = max(
                    0.0,
                    float(section.get("end_seconds", 0.0))
                    - float(section.get("start_seconds", 0.0)),
                )
                section_profiles = []
                for name in source_names:
                    cache_key = (name, section_id)
                    if cache_key not in erb_cache:
                        erb_cache[cache_key] = _section_erb_profile(
                            prepared_by_name[name], section
                        )
                    section_profiles.append(np.asarray(erb_cache[cache_key]))
                matrix = np.vstack(section_profiles)
                redundancy = np.sum(matrix, axis=0) - np.max(matrix, axis=0)
                overlap = float(np.sum(redundancy) / (group_size - 1))
                pair_max = max(
                    float(np.sum(np.minimum(matrix[first], matrix[second])))
                    for first, second in combinations(range(group_size), 2)
                )
                section_scores[section_id] = round(overlap, 4)
                weighted_overlap += overlap * duration
                weighted_pair_max += pair_max * duration
                aggregate_redundancy += redundancy * duration
                coactive_seconds += duration
            if coactive_seconds <= 0.0:
                continue
            cumulative_overlap = weighted_overlap / coactive_seconds
            if cumulative_overlap < minimum_group_overlap:
                continue
            pairwise_max = weighted_pair_max / coactive_seconds
            incremental_pressure = cumulative_overlap * (group_size - 2) / (group_size - 1)
            band_overlap: dict[str, float] = {}
            for index, value in enumerate(aggregate_redundancy):
                band = _named_band(float(erb_bands[index][0]))
                band_overlap[band] = band_overlap.get(band, 0.0) + float(value)
            dominant = [
                band
                for band, value in sorted(
                    band_overlap.items(), key=lambda item: (-item[1], item[0])
                )
                if value > 0.0
            ][:3]
            group_roles = [role_by_name[name] for name in source_names]
            protected = None
            eligible_priorities = [
                (_PRIORITY_RANK[role.priority], role.stem_name)
                for role in group_roles
                if not role.ambiguous and _PRIORITY_RANK[role.priority] > 0
            ]
            if eligible_priorities:
                highest = max(rank for rank, _ in eligible_priorities)
                leaders = [name for rank, name in eligible_priorities if rank == highest]
                if len(leaders) == 1:
                    protected = leaders[0]
            confidence = min(role.confidence for role in group_roles)
            confidence *= 0.5 + 0.5 * cumulative_overlap
            confidence = min(confidence, 0.5)
            relationship_id = f"rel-{len(relationships) + 1:03d}"
            relationships.append(StemRelationship(
                schema=RELATIONSHIP_SCHEMA,
                relationship_id=relationship_id,
                relationship_type="cumulative_spectral_buildup",
                source_stems=list(source_names),
                protected_stem=protected,
                intervention_target=None,
                status="review_required",
                confidence=round(confidence, 4),
                evidence=RelationshipEvidence(
                    measurement_scope="section_local_erb_group",
                    masking_index=round(cumulative_overlap, 4),
                    simultaneous_activity_ratio=1.0,
                    collision_score=round(cumulative_overlap, 4),
                    coactive_seconds=round(coactive_seconds, 3),
                    dominant_overlap_bands=dominant,
                    section_ids=[
                        str(section.get("section_id", "")) for section in group_sections
                    ],
                    section_collision_scores=section_scores,
                    existing_dynamics_treatment={},
                    group_size=group_size,
                    pairwise_max_collision=round(pairwise_max, 4),
                    cumulative_overlap_index=round(cumulative_overlap, 4),
                    incremental_group_pressure=round(incremental_pressure, 4),
                ),
                least_destructive_intervention=None,
                intervention_order=[],
                candidate_strategies=[],
                selection_rationale=(
                    "Cumulative section-local overlap spans multiple sources; no single target "
                    "or processor is justified. Review the protected focal source and group "
                    "balance before creating isolated candidates."
                ),
            ))
    return relationships
