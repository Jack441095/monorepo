"""Offline-only coordination of bounded section-level AutoMix automation previews."""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
import math

import numpy as np

from .relationship_audition import build_section_mask
from .relationships import RELATIONSHIP_CANDIDATE_SCHEMA, RELATIONSHIP_SCHEMA

AUTOMATION_PREVIEW_SCHEMA = "audio-too.automation-preview.v1"
MAX_MOVES = 8
MAX_MOVES_PER_STEM = 3
MAX_TARGETS_PER_SECTION = 2
MIN_SEGMENT_SECONDS = 1.0


@dataclass(frozen=True)
class AutomationMove:
    move_id: str
    target_stem: str
    section_id: str
    start_seconds: float
    end_seconds: float
    gain_db: float
    attack_ms: float
    release_ms: float
    source_relationship_id: str
    source_candidate_id: str
    selection_score: float
    rationale: str


@dataclass(frozen=True)
class SuppressedAutomationMove:
    source_relationship_id: str
    source_candidate_id: str
    target_stem: str
    section_id: str
    reason: str


@dataclass(frozen=True)
class AutomationPreview:
    schema: str
    status: str
    moves: list[AutomationMove] = field(default_factory=list)
    suppressed_moves: list[SuppressedAutomationMove] = field(default_factory=list)
    limits: dict = field(default_factory=dict)
    applies_automatically: bool = False
    production_processing_enabled: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _suppressed(source: dict, section_id: str, reason: str) -> SuppressedAutomationMove:
    candidate = source["candidate"]
    relationship = source["relationship"]
    return SuppressedAutomationMove(
        source_relationship_id=relationship["relationship_id"],
        source_candidate_id=candidate["candidate_id"],
        target_stem=candidate["target_stem"],
        section_id=section_id,
        reason=reason,
    )


def build_automation_preview(relationships: list[dict]) -> AutomationPreview:
    """Coordinate independent relationship moves into one sparse, reviewable preview."""
    protected_by_section: dict[str, set[str]] = {}
    sources = []
    for relationship in relationships:
        if not isinstance(relationship, dict) or relationship.get("schema") != RELATIONSHIP_SCHEMA:
            raise ValueError("Automation preview requires Relationship v1 dictionaries.")
        if relationship.get("applies_automatically") is not False:
            raise ValueError("Automation preview relationships must be advisory-only.")
        protected = relationship.get("protected_stem")
        evidence = relationship.get("evidence")
        if not isinstance(evidence, dict):
            raise ValueError("Automation preview relationship evidence is missing.")
        section_ids = evidence.get("section_ids")
        if not isinstance(section_ids, list):
            raise ValueError("Automation preview relationship sections must be a list.")
        if isinstance(protected, str) and protected:
            for section_id in section_ids:
                protected_by_section.setdefault(str(section_id), set()).add(protected)
        candidates = relationship.get("candidate_strategies")
        if not isinstance(candidates, list):
            raise ValueError("Automation preview relationship candidates must be a list.")
        for candidate in candidates:
            if not isinstance(candidate, dict) or candidate.get("strategy") != "section_level_automation":
                continue
            if (
                candidate.get("schema") != RELATIONSHIP_CANDIDATE_SCHEMA
                or candidate.get("applies_automatically") is not False
            ):
                raise ValueError("Automation candidate must satisfy the advisory v1 contract.")
            ranges = candidate.get("section_ranges")
            candidate_sections = candidate.get("section_ids")
            parameters = candidate.get("parameters")
            if (
                not isinstance(ranges, list)
                or not isinstance(candidate_sections, list)
                or [item.get("section_id") for item in ranges] != candidate_sections
                or not isinstance(parameters, dict)
                or set(parameters) != {"gain_db", "attack_ms", "release_ms"}
            ):
                raise ValueError("Automation candidate scope or parameters are malformed.")
            gain_db = float(parameters["gain_db"])
            attack_ms = float(parameters["attack_ms"])
            release_ms = float(parameters["release_ms"])
            candidate_score = float(candidate.get("score", 0.0))
            if (
                not all(math.isfinite(value) for value in (
                    gain_db, attack_ms, release_ms, candidate_score
                ))
                or not -2.5 <= gain_db <= -0.75
                or not 0.0 < attack_ms <= 500.0
                or not 0.0 < release_ms <= 2_000.0
                or not 0.0 <= candidate_score <= 1.0
            ):
                raise ValueError("Automation candidate values are outside preview bounds.")
            section_scores = evidence.get("section_collision_scores", {})
            if not isinstance(section_scores, dict):
                raise ValueError("Automation candidate section scores must be an object.")
            for section_range in ranges:
                if set(section_range) != {"section_id", "start_seconds", "end_seconds"}:
                    raise ValueError("Automation candidate section range is malformed.")
                section_id = str(section_range["section_id"])
                start = float(section_range["start_seconds"])
                end = float(section_range["end_seconds"])
                collision = float(section_scores.get(section_id, evidence.get("collision_score", 0.0)))
                if not all(math.isfinite(value) for value in (start, end, collision)) or end <= start:
                    raise ValueError("Automation candidate section range is invalid.")
                sources.append({
                    "relationship": relationship,
                    "candidate": candidate,
                    "section_id": section_id,
                    "start_seconds": start,
                    "end_seconds": end,
                    "gain_db": gain_db,
                    "attack_ms": attack_ms,
                    "release_ms": release_ms,
                    "selection_score": max(0.0, min(1.0, candidate_score * collision)),
                })

    sources.sort(key=lambda source: (
        -source["selection_score"],
        source["relationship"]["relationship_id"],
        source["candidate"]["candidate_id"],
        source["section_id"],
        source["candidate"]["target_stem"],
    ))
    selected = []
    suppressed = []
    selected_keys: set[tuple[str, str]] = set()
    moves_per_stem: dict[str, int] = {}
    targets_per_section: dict[str, set[str]] = {}
    for source in sources:
        candidate = source["candidate"]
        target = str(candidate.get("target_stem", ""))
        section_id = source["section_id"]
        key = (target, section_id)
        if not target:
            raise ValueError("Automation candidate target stem is missing.")
        if source["end_seconds"] - source["start_seconds"] < MIN_SEGMENT_SECONDS:
            suppressed.append(_suppressed(source, section_id, "segment_too_short"))
        elif target in protected_by_section.get(section_id, set()):
            suppressed.append(_suppressed(source, section_id, "target_protected_by_another_relationship"))
        elif key in selected_keys:
            suppressed.append(_suppressed(source, section_id, "lower_ranked_duplicate_target_section"))
        elif len(selected) >= MAX_MOVES:
            suppressed.append(_suppressed(source, section_id, "song_move_budget_exhausted"))
        elif moves_per_stem.get(target, 0) >= MAX_MOVES_PER_STEM:
            suppressed.append(_suppressed(source, section_id, "stem_move_budget_exhausted"))
        elif (
            target not in targets_per_section.get(section_id, set())
            and len(targets_per_section.get(section_id, set())) >= MAX_TARGETS_PER_SECTION
        ):
            suppressed.append(_suppressed(source, section_id, "section_target_budget_exhausted"))
        else:
            selected.append(source)
            selected_keys.add(key)
            moves_per_stem[target] = moves_per_stem.get(target, 0) + 1
            targets_per_section.setdefault(section_id, set()).add(target)

    moves = [
        AutomationMove(
            move_id=f"move-{index:03d}",
            target_stem=source["candidate"]["target_stem"],
            section_id=source["section_id"],
            start_seconds=round(source["start_seconds"], 6),
            end_seconds=round(source["end_seconds"], 6),
            gain_db=round(source["gain_db"], 3),
            attack_ms=round(source["attack_ms"], 3),
            release_ms=round(source["release_ms"], 3),
            source_relationship_id=source["relationship"]["relationship_id"],
            source_candidate_id=source["candidate"]["candidate_id"],
            selection_score=round(source["selection_score"], 4),
            rationale=(
                "Highest eligible section-level move after protected-source, duplicate, "
                "per-stem, per-section, and whole-song budget checks."
            ),
        )
        for index, source in enumerate(selected, 1)
    ]
    return AutomationPreview(
        schema=AUTOMATION_PREVIEW_SCHEMA,
        status="ready_for_offline_audition" if moves else "no_safe_moves",
        moves=moves,
        suppressed_moves=suppressed,
        limits={
            "max_moves": MAX_MOVES,
            "max_moves_per_stem": MAX_MOVES_PER_STEM,
            "max_targets_per_section": MAX_TARGETS_PER_SECTION,
            "minimum_segment_seconds": MIN_SEGMENT_SECONDS,
            "maximum_gain_reduction_db": 2.5,
        },
    )


def apply_automation_preview(
    prepared_stems: list[dict], preview: AutomationPreview | dict
) -> tuple[list[dict], dict]:
    """Apply a validated preview to copied stems for offline A/B rendering only."""
    payload = preview.to_dict() if isinstance(preview, AutomationPreview) else preview
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != AUTOMATION_PREVIEW_SCHEMA
        or payload.get("applies_automatically") is not False
        or payload.get("production_processing_enabled") is not False
    ):
        raise ValueError("Automation preview must satisfy the offline-only v1 contract.")
    moves = payload.get("moves")
    if not isinstance(moves, list) or not 1 <= len(moves) <= MAX_MOVES:
        raise ValueError("Automation preview must contain a bounded non-empty move list.")
    copied = copy.deepcopy(prepared_stems)
    by_name = {str(stem.get("name", "")): stem for stem in copied}
    if len(by_name) != len(copied):
        raise ValueError("Automation preview requires unique prepared stem names.")
    changed_samples = 0
    seen_keys = set()
    moves_per_stem: dict[str, int] = {}
    targets_per_section: dict[str, set[str]] = {}
    for move in moves:
        required = {
            "move_id", "target_stem", "section_id", "start_seconds", "end_seconds",
            "gain_db", "attack_ms", "release_ms", "source_relationship_id",
            "source_candidate_id", "selection_score", "rationale",
        }
        if not isinstance(move, dict) or set(move) != required:
            raise ValueError("Automation preview move shape is invalid.")
        target = move["target_stem"]
        section_id = move["section_id"]
        key = (target, section_id)
        if target not in by_name or key in seen_keys:
            raise ValueError("Automation preview target is missing or duplicated by section.")
        seen_keys.add(key)
        moves_per_stem[target] = moves_per_stem.get(target, 0) + 1
        targets_per_section.setdefault(section_id, set()).add(target)
        if (
            moves_per_stem[target] > MAX_MOVES_PER_STEM
            or len(targets_per_section[section_id]) > MAX_TARGETS_PER_SECTION
        ):
            raise ValueError("Automation preview exceeds stem or section move budgets.")
        stem = by_name[target]
        sample_rate = int(stem.get("sample_rate", 0))
        original = np.asarray(stem.get("samples", []), dtype=np.float64)
        gain_db = float(move["gain_db"])
        start = float(move["start_seconds"])
        end = float(move["end_seconds"])
        attack = float(move["attack_ms"])
        release = float(move["release_ms"])
        if (
            sample_rate <= 0
            or original.size == 0
            or not np.isfinite(original).all()
            or not all(math.isfinite(value) for value in (gain_db, start, end, attack, release))
            or not -2.5 <= gain_db <= -0.75
            or end - start < MIN_SEGMENT_SECONDS
            or not 0.0 < attack <= 500.0
            or not 0.0 < release <= 2_000.0
        ):
            raise ValueError("Automation preview move values are outside safety bounds.")
        mask = build_section_mask(
            len(original), sample_rate,
            [{"section_id": section_id, "start_seconds": start, "end_seconds": end}],
            attack_ms=attack, release_ms=release,
        )
        gain = 1.0 + (10.0 ** (gain_db / 20.0) - 1.0) * mask
        processed = original * gain
        changed = int(np.count_nonzero(np.abs(processed - original) > 1e-12))
        if stem.get("stereo_preserved"):
            left = np.asarray(stem.get("left_samples", []), dtype=np.float64)
            right = np.asarray(stem.get("right_samples", []), dtype=np.float64)
            if left.shape != original.shape or right.shape != original.shape:
                raise ValueError("Automation preview stereo channels are not sample-aligned.")
            processed_left = left * gain
            processed_right = right * gain
            changed = max(
                changed,
                int(np.count_nonzero(np.abs(processed_left - left) > 1e-12)),
                int(np.count_nonzero(np.abs(processed_right - right) > 1e-12)),
            )
            stem["left_samples"] = processed_left.tolist()
            stem["right_samples"] = processed_right.tolist()
            processed = 0.5 * (processed_left + processed_right)
        changed_samples += changed
        stem["samples"] = processed.tolist()
    if changed_samples == 0:
        raise ValueError("Automation preview is effectively identical to the control.")
    return copied, {
        "schema": "audio-too.automation-preview-audition.v1",
        "move_count": len(moves),
        "changed_samples": changed_samples,
        "production_processing_enabled": False,
    }
