"""Offline-only DSP auditioning for bounded Relationship v1 candidates."""

from __future__ import annotations

import copy
import math

import numpy as np

from audio_analysis.dsp_engine.dynamic_eq import apply_dynamic_eq_band
from audio_analysis.dsp_engine.eq import ParametricEQ

from .relationships import RELATIONSHIP_CANDIDATE_SCHEMA, RELATIONSHIP_SCHEMA

AUDITION_SCHEMA = "audio-too.relationship-candidate-audition.v1"
_ALLOWED_STRATEGIES = {
    "section_level_automation",
    "static_eq",
    "dynamic_eq",
    "sidechain_ducking",
}
_PARAMETER_KEYS = {
    "section_level_automation": {"gain_db", "attack_ms", "release_ms"},
    "static_eq": {"frequency_hz", "gain_db", "q"},
    "dynamic_eq": {
        "frequency_hz", "max_reduction_db", "q", "attack_ms", "release_ms",
    },
    "sidechain_ducking": {"max_reduction_db", "attack_ms", "release_ms"},
}


def _finite_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric.")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite.")
    return number


def build_section_mask(
    length: int,
    sample_rate: int,
    ranges: list[dict],
    *,
    attack_ms: float,
    release_ms: float,
) -> np.ndarray:
    mask = np.zeros(length, dtype=np.float64)
    attack = max(1, int(sample_rate * attack_ms / 1_000.0))
    release = max(1, int(sample_rate * release_ms / 1_000.0))
    previous_end = -1
    for index, section in enumerate(ranges):
        if set(section) != {"section_id", "start_seconds", "end_seconds"}:
            raise ValueError(f"section_ranges[{index}] has an invalid shape.")
        start_seconds = _finite_number(section["start_seconds"], "start_seconds")
        end_seconds = _finite_number(section["end_seconds"], "end_seconds")
        start = max(0, min(length, int(round(start_seconds * sample_rate))))
        end = max(0, min(length, int(round(end_seconds * sample_rate))))
        if end <= start or start < previous_end:
            raise ValueError("Candidate section ranges must be ordered, positive, and non-overlapping.")
        previous_end = end
        mask[start:end] = 1.0
        fade_in = min(attack, end - start)
        fade_out = min(release, end - start)
        mask[start:start + fade_in] = np.linspace(0.0, 1.0, fade_in, endpoint=True)
        mask[end - fade_out:end] = np.minimum(
            mask[end - fade_out:end], np.linspace(1.0, 0.0, fade_out, endpoint=True)
        )
    return mask


def _blend(original: np.ndarray, processed: np.ndarray, mask: np.ndarray) -> np.ndarray:
    return original + (processed - original) * mask


def _smooth_detector(
    values: np.ndarray, sample_rate: int, attack_ms: float, release_ms: float
) -> np.ndarray:
    attack = math.exp(-1.0 / (sample_rate * attack_ms / 1_000.0))
    release = math.exp(-1.0 / (sample_rate * release_ms / 1_000.0))
    output = np.zeros_like(values)
    current = 0.0
    for index, value in enumerate(values):
        coefficient = attack if value > current else release
        current = coefficient * current + (1.0 - coefficient) * float(value)
        output[index] = current
    return output


def _validate_candidate(relationship: dict, candidate_id: str) -> dict:
    if relationship.get("schema") != RELATIONSHIP_SCHEMA:
        raise ValueError("Unsupported relationship schema.")
    if relationship.get("applies_automatically") is not False:
        raise ValueError("Auditions require an explicitly advisory-only relationship.")
    candidates = relationship.get("candidate_strategies")
    if not isinstance(candidates, list):
        raise ValueError("Relationship candidates must be a list.")
    matches = [candidate for candidate in candidates if candidate.get("candidate_id") == candidate_id]
    if len(matches) != 1:
        raise ValueError("Candidate ID must identify exactly one relationship candidate.")
    candidate = matches[0]
    if candidate.get("schema") != RELATIONSHIP_CANDIDATE_SCHEMA:
        raise ValueError("Unsupported relationship candidate schema.")
    if candidate.get("applies_automatically") is not False:
        raise ValueError("Audition candidates must be explicitly advisory-only.")
    if candidate.get("strategy") not in _ALLOWED_STRATEGIES:
        raise ValueError("Unsupported relationship candidate strategy.")
    if not isinstance(candidate.get("parameters"), dict):
        raise ValueError("Candidate parameters must be an object.")
    if set(candidate["parameters"]) != _PARAMETER_KEYS[candidate["strategy"]]:
        raise ValueError("Candidate parameters do not exactly match the strategy contract.")
    if not isinstance(candidate.get("section_ranges"), list) or not candidate["section_ranges"]:
        raise ValueError("Candidate must contain exact non-empty section ranges.")
    section_ids = candidate.get("section_ids")
    range_ids = [section.get("section_id") for section in candidate["section_ranges"]]
    if not isinstance(section_ids, list) or section_ids != range_ids or len(set(range_ids)) != len(range_ids):
        raise ValueError("Candidate section IDs and ranges must match exactly.")
    return candidate


def apply_candidate_to_prepared_stems(
    prepared_stems: list[dict],
    relationship: dict,
    candidate_id: str,
) -> tuple[list[dict], dict]:
    """Return a copied stem set with one candidate applied for offline rendering."""
    candidate = _validate_candidate(relationship, candidate_id)
    target_name = str(candidate.get("target_stem", ""))
    by_name = {str(stem.get("name", "")): stem for stem in prepared_stems}
    if not target_name or target_name not in by_name:
        raise ValueError("Candidate target stem is missing from prepared audio.")
    if relationship.get("intervention_target") != target_name:
        raise ValueError("Candidate target conflicts with its parent relationship.")

    target = by_name[target_name]
    sample_rate = int(target.get("sample_rate", 0))
    original = np.asarray(target.get("samples", []), dtype=np.float64)
    if sample_rate <= 0 or original.size == 0 or not np.isfinite(original).all():
        raise ValueError("Candidate target audio must be finite and non-empty.")
    stereo_source = bool(target.get("stereo_preserved"))
    if stereo_source:
        original_left = np.asarray(target.get("left_samples", []), dtype=np.float64)
        original_right = np.asarray(target.get("right_samples", []), dtype=np.float64)
        if (
            original_left.shape != original.shape
            or original_right.shape != original.shape
            or not np.isfinite(original_left).all()
            or not np.isfinite(original_right).all()
        ):
            raise ValueError("Candidate target stereo channels must be finite and sample-aligned.")
    parameters = candidate["parameters"]
    attack_ms = _finite_number(parameters.get("attack_ms", 20.0), "attack_ms")
    release_ms = _finite_number(parameters.get("release_ms", 140.0), "release_ms")
    if not 0.0 < attack_ms <= 500.0 or not 0.0 < release_ms <= 2_000.0:
        raise ValueError("Candidate timing is outside audition safety bounds.")
    mask = build_section_mask(
        len(original), sample_rate, candidate["section_ranges"],
        attack_ms=attack_ms, release_ms=release_ms,
    )
    strategy = candidate["strategy"]

    if strategy == "section_level_automation":
        gain_db = _finite_number(parameters.get("gain_db"), "gain_db")
        if not -2.5 <= gain_db <= -0.75:
            raise ValueError("Section automation gain is outside audition safety bounds.")
        wet = original * (10.0 ** (gain_db / 20.0))
        if stereo_source:
            wet_left = original_left * (10.0 ** (gain_db / 20.0))
            wet_right = original_right * (10.0 ** (gain_db / 20.0))
    elif strategy == "static_eq":
        frequency = _finite_number(parameters.get("frequency_hz"), "frequency_hz")
        gain_db = _finite_number(parameters.get("gain_db"), "gain_db")
        q = _finite_number(parameters.get("q"), "q")
        if not 20.0 <= frequency < sample_rate * 0.5 or not -2.5 <= gain_db <= -1.0 or not 0.5 <= q <= 3.0:
            raise ValueError("Static EQ parameters are outside audition safety bounds.")
        wet = ParametricEQ(sample_rate).add_band("peaking", frequency, gain_db, q).apply(original)
        if stereo_source:
            eq = ParametricEQ(sample_rate).add_band("peaking", frequency, gain_db, q)
            wet_left = eq.apply(original_left)
            wet_right = eq.apply(original_right)
    elif strategy == "dynamic_eq":
        frequency = _finite_number(parameters.get("frequency_hz"), "frequency_hz")
        reduction = _finite_number(parameters.get("max_reduction_db"), "max_reduction_db")
        q = _finite_number(parameters.get("q"), "q")
        if not 20.0 <= frequency < sample_rate * 0.5 or not 1.5 <= reduction <= 3.5 or not 0.5 <= q <= 3.0:
            raise ValueError("Dynamic EQ parameters are outside audition safety bounds.")
        wet, _ = apply_dynamic_eq_band(
            original, original.copy(), frequency_hz=frequency, sample_rate=sample_rate,
            q=q, threshold_db=-30.0, ratio=3.0, max_reduction_db=reduction,
            attack_ms=attack_ms, release_ms=release_ms,
        )
        if stereo_source:
            wet_left, wet_right = apply_dynamic_eq_band(
                original_left, original_right, frequency_hz=frequency,
                sample_rate=sample_rate, q=q, threshold_db=-30.0, ratio=3.0,
                max_reduction_db=reduction, attack_ms=attack_ms, release_ms=release_ms,
            )
    else:
        reduction = _finite_number(parameters.get("max_reduction_db"), "max_reduction_db")
        if not 1.5 <= reduction <= 4.0:
            raise ValueError("Sidechain reduction is outside audition safety bounds.")
        protected = str(relationship.get("protected_stem", ""))
        trigger = by_name.get(protected)
        if trigger is None:
            raise ValueError("Sidechain candidate trigger stem is missing.")
        if int(trigger.get("sample_rate", 0)) != sample_rate:
            raise ValueError("Sidechain target and trigger sample rates differ.")
        trigger_samples = np.asarray(trigger.get("samples", []), dtype=np.float64)
        if trigger_samples.shape != original.shape or not np.isfinite(trigger_samples).all():
            raise ValueError("Sidechain target and trigger must be finite and sample-aligned.")
        peak = float(np.max(np.abs(trigger_samples)))
        detector = np.abs(trigger_samples) / peak if peak > 1e-12 else np.zeros_like(original)
        detector = np.clip((detector - 0.08) / 0.92, 0.0, 1.0)
        detector = _smooth_detector(detector, sample_rate, attack_ms, release_ms)
        gain = 10.0 ** ((-reduction * detector) / 20.0)
        wet = original * gain
        if stereo_source:
            wet_left = original_left * gain
            wet_right = original_right * gain

    processed = _blend(original, np.asarray(wet, dtype=np.float64), mask)
    if stereo_source:
        processed_left = _blend(original_left, np.asarray(wet_left, dtype=np.float64), mask)
        processed_right = _blend(original_right, np.asarray(wet_right, dtype=np.float64), mask)
        processed = 0.5 * (processed_left + processed_right)
    if processed.shape != original.shape or not np.isfinite(processed).all():
        raise ValueError("Candidate processing produced invalid audio.")
    copied = copy.deepcopy(prepared_stems)
    copied_by_name = {str(stem.get("name", "")): stem for stem in copied}
    copied_by_name[target_name]["samples"] = processed.tolist()
    changed_samples = int(np.count_nonzero(np.abs(processed - original) > 1e-12))
    if stereo_source:
        copied_by_name[target_name]["left_samples"] = processed_left.tolist()
        copied_by_name[target_name]["right_samples"] = processed_right.tolist()
        changed_samples = max(
            changed_samples,
            int(np.count_nonzero(np.abs(processed_left - original_left) > 1e-12)),
            int(np.count_nonzero(np.abs(processed_right - original_right) > 1e-12)),
        )
    if changed_samples == 0:
        raise ValueError("Candidate processing is effectively identical to the control.")
    audit = {
        "schema": AUDITION_SCHEMA,
        "relationship_id": relationship.get("relationship_id"),
        "candidate_id": candidate_id,
        "strategy": strategy,
        "target_stem": target_name,
        "section_ranges": candidate["section_ranges"],
        "changed_samples": changed_samples,
        "total_samples": len(original),
        "applies_to_production": False,
    }
    return copied, audit
