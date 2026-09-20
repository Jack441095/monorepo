"""Versioned, confidence-bearing musical-role inference for AutoMix stems."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
import re

import numpy as np

from .stem_classifier import StemProfile

MUSICAL_ROLE_SCHEMA = "audio-too.musical-role.v1"
# Reverted to 0.70 (2026-07-18) -- a 2026-07-17 calibration pass lowered this
# to 0.60 alongside several unrelated threshold changes, with no stated reason
# tied to this specific value. 0.64 and 0.68 are the only role_weight values
# in the whole role table between 0.60 and 0.70 (accompaniment/guitar/keys,
# and dense/busy fx respectively) -- they were deliberately capped there so
# they'd read as ambiguous under the original 0.70 threshold ("uncertain
# accompaniment is surfaced, not guessed" -- see
# test_uncertain_accompaniment_is_surfaced_not_guessed). Lowering the
# threshold to 0.60 silently undid that contract for both role tiers with no
# compensating fix elsewhere; restored rather than updating the tests, since
# the tests encode the intended product behavior, not stale expectations.
ROLE_CONFIDENCE_THRESHOLD = 0.70
ALLOWED_ROLES = frozenset({
    "focal_element",
    "supporting_voice",
    "rhythmic_anchor",
    "rhythmic_layer",
    "accompaniment",
    "sustained_texture",
    "texture",
    "transition",
    "unknown",
})
ALLOWED_PRIORITIES = frozenset({"foreground", "support", "background", "unknown"})


@dataclass(frozen=True)
class ActivityEvidence:
    active_ratio: float
    first_active_seconds: float | None
    last_active_seconds: float | None
    segment_count: int
    window_seconds: float


@dataclass(frozen=True)
class RoleEvidence:
    source: str
    value: str
    weight: float


@dataclass(frozen=True)
class MusicalRole:
    schema: str
    stem_name: str
    instrument: str
    role: str
    priority: str
    confidence: float
    ambiguous: bool
    activity: ActivityEvidence
    provenance: list[RoleEvidence] = field(default_factory=list)
    inference_source: str = "deterministic_v1"
    user_corrected: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def analyze_activity(
    samples, sample_rate: int, *, window_seconds: float = 0.5
) -> ActivityEvidence:
    """Summarize arrangement activity using relative, windowed RMS evidence.

    ``samples`` accepts either a Python list or a numpy array and is converted
    once here (numpy operations dominate the body regardless). Callers pass the
    prepared stem's numpy array directly rather than a ``.tolist()`` copy -- the
    ``.tolist()`` on a multi-million-sample stem was measured at ~2.6s across the
    roles + arrangement stages combined, a pure lossless float64 round-trip since
    this function immediately re-converted with ``np.asarray``. See
    docs/audits/2026-07-20-activity-analysis-list-roundtrip.md.
    """
    audio = (
        np.asarray(samples, dtype=np.float64)
        if samples is not None
        else np.empty(0, dtype=np.float64)
    )
    if audio.size == 0 or sample_rate <= 0:
        return ActivityEvidence(0.0, None, None, 0, window_seconds)
    window = max(1, int(sample_rate * window_seconds))
    peak = float(np.max(np.abs(audio)))
    if peak < 1e-9:
        return ActivityEvidence(0.0, None, None, 0, window_seconds)
    threshold = max(10.0 ** (-60.0 / 20.0), peak * 10.0 ** (-36.0 / 20.0))
    active: list[bool] = []
    for start in range(0, len(audio), window):
        block = audio[start:start + window]
        rms = float(np.sqrt(np.mean(np.square(block)))) if block.size else 0.0
        active.append(rms > threshold)
    indices = [index for index, value in enumerate(active) if value]
    if not indices:
        return ActivityEvidence(0.0, None, None, 0, window_seconds)
    segments = 1 + sum(
        1 for previous, current in zip(indices, indices[1:]) if current != previous + 1
    )
    return ActivityEvidence(
        active_ratio=round(len(indices) / len(active), 4),
        first_active_seconds=round(indices[0] * window_seconds, 3),
        last_active_seconds=round(
            min(audio.size / sample_rate, (indices[-1] + 1) * window_seconds), 3
        ),
        segment_count=segments,
        window_seconds=window_seconds,
    )


def _name_tokens(name: str) -> set[str]:
    normalized = re.sub(r"[^a-z0-9]+", " ", Path(name).stem.lower())
    return set(normalized.split())


def infer_musical_role(profile: StemProfile, prepared_stem: dict | None = None) -> MusicalRole:
    """Infer a conservative role; low-confidence results remain explicitly ambiguous."""
    if (prepared_stem or {}).get("stereo_preserved"):
        # Mono activity proxy = per-sample max(|L|, |R|). Kept as a numpy array
        # and handed straight to analyze_activity (which converts internally),
        # rather than round-tripping through .tolist() -- see analyze_activity's
        # docstring for the measured cost.
        samples = np.maximum(
            np.abs(np.asarray((prepared_stem or {}).get("left_samples", []))),
            np.abs(np.asarray((prepared_stem or {}).get("right_samples", []))),
        )
    else:
        samples = (prepared_stem or {}).get("samples", [])
    sample_rate = int((prepared_stem or {}).get("sample_rate", profile.sample_rate))
    activity = analyze_activity(samples, sample_rate)
    tokens = _name_tokens(profile.name)
    instrument = profile.instrument
    role = "unknown"
    priority = "unknown"
    role_weight = 0.45
    evidence = [
        RoleEvidence("instrument_classifier", instrument, profile.classification_confidence),
        RoleEvidence("classification_method", profile.classification_method, 1.0),
        RoleEvidence("activity_ratio", f"{activity.active_ratio:.4f}", 0.6),
    ]

    if tokens & {"lead", "main", "solo", "front"}:
        role, priority, role_weight = "focal_element", "foreground", 0.92
        evidence.append(RoleEvidence("filename_role_token", "lead/main/solo/front", 0.92))
    elif tokens & {"backing", "background", "bgv", "bvox", "harmony", "double"}:
        role, priority, role_weight = "supporting_voice", "support", 0.90
        evidence.append(RoleEvidence("filename_role_token", "backing/harmony/double", 0.90))
    elif instrument == "vocal":
        role, priority, role_weight = "focal_element", "foreground", 0.76
    elif instrument in {"kick", "snare", "bass", "sub_bass", "full_drum_bus"}:
        role, priority, role_weight = "rhythmic_anchor", "support", 0.84
    elif instrument in {"hihat", "percussion"}:
        role, priority, role_weight = "rhythmic_layer", "background", 0.78
    elif instrument in {"synth_lead", "brass"}:
        role, priority, role_weight = "focal_element", "foreground", 0.72
    elif instrument in {"synth_pad", "strings", "ambient"}:
        role, priority, role_weight = "sustained_texture", "background", 0.80
    elif instrument == "fx":
        if activity.active_ratio and activity.active_ratio <= 0.35:
            role, priority, role_weight = "transition", "background", 0.82
        else:
            role, priority, role_weight = "texture", "background", 0.68
    elif instrument in {"guitar", "keys"}:
        role, priority, role_weight = "accompaniment", "support", 0.64

    confidence = round(min(profile.classification_confidence, role_weight), 4)
    ambiguous = confidence < ROLE_CONFIDENCE_THRESHOLD or role == "unknown"
    if ambiguous:
        priority = "unknown"
    return MusicalRole(
        schema=MUSICAL_ROLE_SCHEMA,
        stem_name=profile.name,
        instrument=instrument,
        role=role,
        priority=priority,
        confidence=confidence,
        ambiguous=ambiguous,
        activity=activity,
        provenance=evidence,
    )


def infer_musical_roles(
    profiles: list[StemProfile], prepared_stems: list[dict]
) -> list[MusicalRole]:
    prepared_by_name = {str(stem.get("name")): stem for stem in prepared_stems}
    return [infer_musical_role(profile, prepared_by_name.get(profile.name)) for profile in profiles]


def apply_role_corrections(
    roles: list[MusicalRole], corrections: dict | None
) -> list[MusicalRole]:
    """Apply exact-name user corrections without mutating inferred role objects.

    The accepted shape is ``{stem_name: {"role": ..., "priority": ...}}``.
    Both fields are required so a correction cannot leave a contradictory mix
    of inferred role and user priority. Unknown stems and keys fail closed.
    """
    if corrections in (None, {}):
        return list(roles)
    if not isinstance(corrections, dict):
        raise ValueError("Musical-role corrections must be an object keyed by stem name.")
    by_name = {role.stem_name: role for role in roles}
    unknown_stems = sorted(set(corrections) - set(by_name))
    if unknown_stems:
        raise ValueError(f"Musical-role correction references unknown stem: {unknown_stems[0]!r}.")

    corrected: list[MusicalRole] = []
    for inferred in roles:
        payload = corrections.get(inferred.stem_name)
        if payload is None:
            corrected.append(inferred)
            continue
        if not isinstance(payload, dict):
            raise ValueError(f"Correction for {inferred.stem_name!r} must be an object.")
        if set(payload) != {"role", "priority"}:
            raise ValueError(
                f"Correction for {inferred.stem_name!r} must contain exactly role and priority."
            )
        role = payload["role"]
        priority = payload["priority"]
        if role not in ALLOWED_ROLES:
            raise ValueError(f"Unsupported musical role for {inferred.stem_name!r}: {role!r}.")
        if priority not in ALLOWED_PRIORITIES:
            raise ValueError(
                f"Unsupported musical priority for {inferred.stem_name!r}: {priority!r}."
            )
        corrected.append(replace(
            inferred,
            role=role,
            priority=priority,
            confidence=1.0,
            ambiguous=False,
            provenance=[
                *inferred.provenance,
                RoleEvidence("user_correction", f"{role}:{priority}", 1.0),
            ],
            inference_source="user_correction_v1",
            user_corrected=True,
        ))
    return corrected


def validate_role_correction_payload(corrections: object) -> dict:
    """Validate correction shape/enums before a job is allowed into the queue."""
    if not isinstance(corrections, dict):
        raise ValueError("Musical-role corrections must be an object keyed by stem name.")
    for stem_name, payload in corrections.items():
        if not isinstance(stem_name, str) or not stem_name.strip():
            raise ValueError("Musical-role correction stem names must be non-empty strings.")
        if not isinstance(payload, dict) or set(payload) != {"role", "priority"}:
            raise ValueError(
                f"Correction for {stem_name!r} must contain exactly role and priority."
            )
        if payload["role"] not in ALLOWED_ROLES:
            raise ValueError(f"Unsupported musical role for {stem_name!r}: {payload['role']!r}.")
        if payload["priority"] not in ALLOWED_PRIORITIES:
            raise ValueError(
                f"Unsupported musical priority for {stem_name!r}: {payload['priority']!r}."
            )
    return corrections
