"""Versioned, bounded KENN-to-AutoMix adjustment boundary.

KENN suggestions are untrusted input.  This module validates a complete proposal
before applying any operation, applies accepted operations to a deep copy, and
keeps the rule-engine ``MixPlan`` untouched on every failure path.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, Mapping

from audio_analysis.mixdown.mix_decision_engine import MixPlan, bound_gain_to_rough_intent
from audio_analysis.mixdown.mix_rules import get_rule_for_instrument

CONTRACT_SCHEMA = "audio-too.kenn-advisor/v1"
SHADOW_RECEIPT_SCHEMA = "audio-too.kenn-advisor-shadow/v1"
GAIN_DELTA_CLAMP_DB = 3.0
COMPRESSOR_RATIO_RANGE = (1.0, 8.0)
EQ_GAIN_CLAMP_DB = 12.0
EQ_FREQUENCY_RANGE_HZ = (20.0, 20_000.0)
EQ_Q_RANGE = (0.1, 20.0)
MIN_ADVISOR_CONFIDENCE = 0.70
MIN_DRIFT_DB = 0.50
MIN_RATIO_DRIFT = 0.50
MAX_PROPOSAL_OPERATIONS = 8

OperationName = Literal["gain_delta", "compressor_ratio", "eq_gain_delta"]

_ENVELOPE_KEYS = {
    "schema",
    "source_plan_revision",
    "model_version",
    "prompt_version",
    "correlation_id",
    "operations",
}
_OPERATION_KEYS = {
    "stem_id",
    "operation",
    "value",
    "unit",
    "evidence_source_ids",
    "confidence",
    "reason",
    "frequency_hz",
    "q",
    "filter_type",
}
_FILTER_TYPES = {"peaking", "low_shelf", "high_shelf"}


class AdvisorContractError(ValueError):
    """Raised when an advisor proposal is unsafe, stale, or malformed."""


@dataclass(frozen=True)
class AdvisorOperation:
    stem_id: str
    operation: OperationName
    value: float
    unit: str
    evidence_source_ids: tuple[str, ...]
    confidence: float
    reason: str
    frequency_hz: float | None = None
    q: float | None = None
    filter_type: str | None = None


@dataclass(frozen=True)
class AdvisorProposal:
    schema: str
    source_plan_revision: str
    model_version: str
    prompt_version: str
    correlation_id: str
    operations: tuple[AdvisorOperation, ...]


def mix_plan_revision(plan: MixPlan) -> str:
    """Return a stable content revision for stale-proposal detection."""
    payload = json.dumps(asdict(plan), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_kenn_adjustments(
    plan: MixPlan,
    profiles: list,
    genre: str,
    target_lufs: float,
    *,
    correlation_id: str = "",
) -> Mapping[str, Any] | None:
    """Build a deterministic, retrieval-grounded canonical-drift proposal.

    This deliberately does not use the rejected KENN-LM checkpoint. It audits
    the current plan against the same measured, genre-specific rules that built
    the baseline, and only emits an operation when KENN retrieves the exact
    approved source describing that decision. A canonical plan abstains.
    """
    del target_lufs  # v1 has no master-bus operations
    if not correlation_id or not profiles or not plan.stems:
        return None

    profiles_by_name = {
        str(getattr(profile, "name", "")): profile
        for profile in profiles
        if str(getattr(profile, "name", ""))
    }
    if len(profiles_by_name) != len(profiles):
        return None
    expected_gains = _canonical_gain_targets(profiles, genre)
    gain_candidates: list[tuple[Any, Any, float]] = []
    ratio_candidates: list[tuple[Any, Any, float]] = []
    for stem in plan.stems:
        profile = profiles_by_name.get(stem.stem_name)
        if profile is None:
            continue
        classification_confidence = _finite_or_none(
            getattr(profile, "classification_confidence", None)
        )
        if classification_confidence is None or classification_confidence < MIN_ADVISOR_CONFIDENCE:
            continue
        expected_gain = expected_gains.get(stem.stem_name)
        if expected_gain is not None:
            delta = expected_gain - stem.gain_db
            if MIN_DRIFT_DB <= abs(delta) <= GAIN_DELTA_CLAMP_DB:
                gain_candidates.append((stem, profile, delta))
        rule = get_rule_for_instrument(stem.instrument, genre)
        compression = rule.get("compression")
        if stem.compressor is not None and isinstance(compression, Mapping):
            expected_ratio = _finite_or_none(compression.get("ratio"))
            current_ratio = _finite_or_none(stem.compressor.get("ratio"))
            if (
                expected_ratio is not None
                and current_ratio is not None
                and MIN_RATIO_DRIFT <= abs(expected_ratio - current_ratio)
                and COMPRESSOR_RATIO_RANGE[0] <= expected_ratio <= COMPRESSOR_RATIO_RANGE[1]
            ):
                ratio_candidates.append((stem, profile, expected_ratio))

    operations: list[dict[str, Any]] = []
    if gain_candidates:
        evidence = _retrieve_approved_evidence(
            "AutoMix gain staging anchor relative RMS peak",
            expected_source="automix-gain-staging.md",
        )
        if evidence is not None:
            evidence_id, retrieval_confidence = evidence
            for stem, profile, delta in gain_candidates:
                confidence = min(
                    retrieval_confidence,
                    float(profile.classification_confidence),
                )
                if confidence >= MIN_ADVISOR_CONFIDENCE:
                    operations.append(
                        {
                            "stem_id": stem.stem_name,
                            "operation": "gain_delta",
                            "value": round(delta, 4),
                            "unit": "dB",
                            "evidence_source_ids": [evidence_id],
                            "confidence": round(confidence, 4),
                            "reason": (
                                f"Restore the measured {stem.instrument} gain to the canonical "
                                f"{genre} anchor-relative target ({delta:+.2f} dB drift)."
                            ),
                        }
                    )
    if ratio_candidates:
        evidence = _retrieve_approved_evidence(
            "AutoMix compression ratio per instrument genre",
            expected_source="automix-compression-ratios.md",
        )
        if evidence is not None:
            evidence_id, retrieval_confidence = evidence
            for stem, profile, expected_ratio in ratio_candidates:
                confidence = min(
                    retrieval_confidence,
                    float(profile.classification_confidence),
                )
                if confidence >= MIN_ADVISOR_CONFIDENCE:
                    operations.append(
                        {
                            "stem_id": stem.stem_name,
                            "operation": "compressor_ratio",
                            "value": round(expected_ratio, 4),
                            "unit": "ratio",
                            "evidence_source_ids": [evidence_id],
                            "confidence": round(confidence, 4),
                            "reason": (
                                f"Restore the {stem.instrument} compressor to the canonical "
                                f"{genre} ratio of {expected_ratio:g}:1."
                            ),
                        }
                    )
    if not operations:
        return None
    return {
        "schema": CONTRACT_SCHEMA,
        "source_plan_revision": mix_plan_revision(plan),
        "model_version": "kenn-deterministic-advisor-v1",
        "prompt_version": "canonical-drift-policy-v1",
        "correlation_id": correlation_id,
        "operations": operations[:MAX_PROPOSAL_OPERATIONS],
    }


def _finite_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _canonical_gain_targets(profiles: list, genre: str) -> dict[str, float]:
    """Recompute the documented pre-feedback gain baseline from measurements."""
    usable = [
        profile
        for profile in profiles
        if _finite_or_none(getattr(profile, "peak_dbfs", None)) is not None
        and _finite_or_none(getattr(profile, "rms_dbfs", None)) is not None
    ]
    if not usable:
        return {}
    anchor = next(
        (
            profile
            for profile in usable
            if get_rule_for_instrument(str(profile.instrument), genre).get("gain_anchor", False)
        ),
        None,
    )
    if anchor is None:
        valid = [profile for profile in usable if float(profile.peak_dbfs) > -60.0]
        anchor = max(valid, key=lambda profile: float(profile.peak_dbfs)) if valid else usable[0]
    anchor_rule = get_rule_for_instrument(str(anchor.instrument), genre)
    anchor_target_peak = float(anchor_rule.get("target_peak_dbfs", -6.0))
    anchor_gain = anchor_target_peak - float(anchor.peak_dbfs)
    reference_rms = float(anchor.rms_dbfs) + anchor_gain
    transient_instruments = {"kick", "snare", "hihat", "percussion", "full_drum_bus"}
    targets = {}
    for profile in usable:
        rule = get_rule_for_instrument(str(profile.instrument), genre)
        if profile is anchor:
            target = anchor_gain
        elif profile.instrument in transient_instruments:
            target_peak = anchor_target_peak + float(
                rule.get("target_level_relative_to_anchor", -6.0)
            )
            target = target_peak - float(profile.peak_dbfs)
        else:
            target_rms = reference_rms + float(
                rule.get("target_level_relative_to_anchor", -8.0)
            )
            target = target_rms - float(profile.rms_dbfs)
        if profile is not anchor:
            target = bound_gain_to_rough_intent(target, anchor_gain)
        if math.isfinite(target):
            targets[str(profile.name)] = target
    return targets


def _retrieve_approved_evidence(
    query: str,
    *,
    expected_source: str,
) -> tuple[str, float] | None:
    """Return an exact approved KENN chunk identity or abstain."""
    kenn_parent = Path(__file__).resolve().parents[3] / "kenn"
    if str(kenn_parent) not in sys.path:
        sys.path.insert(0, str(kenn_parent))
    try:
        from kenn.core.chat_constants import CHUNKS_PATH
        from kenn.core.chat_retrieval import load_chunks, load_terms, search
        from kenn.retrieval.index_store import active_version_id

        results = search(query, load_chunks(), load_terms(), limit=5)
        index_version = active_version_id(CHUNKS_PATH.parent)
    except Exception:
        return None
    if not index_version:
        return None
    for score, chunk in results:
        if chunk.get("source") != expected_source:
            continue
        if "Status: Approved" not in str(chunk.get("text", "")):
            continue
        chunk_id = str(chunk.get("id", "")).strip()
        if not chunk_id or not math.isfinite(float(score)) or float(score) <= 0:
            continue
        # Exact source + approved status is the dominant confidence signal. The
        # score contributes only a bounded tie-strength component.
        confidence = min(0.99, 0.90 + (float(score) / (float(score) + 1000.0)) * 0.09)
        return f"{chunk_id}@index:{index_version}", confidence
    return None


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AdvisorContractError(f"{field} must be a non-empty string")
    return value.strip()


def _require_finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AdvisorContractError(f"{field} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise AdvisorContractError(f"{field} must be finite")
    return result


def _parse_operation(raw: Any, index: int) -> AdvisorOperation:
    field = f"operations[{index}]"
    if not isinstance(raw, Mapping):
        raise AdvisorContractError(f"{field} must be an object")
    unknown = set(raw) - _OPERATION_KEYS
    if unknown:
        raise AdvisorContractError(f"{field} has unknown keys: {sorted(unknown)}")

    stem_id = _require_text(raw.get("stem_id"), f"{field}.stem_id")
    operation = _require_text(raw.get("operation"), f"{field}.operation")
    if operation not in {"gain_delta", "compressor_ratio", "eq_gain_delta"}:
        raise AdvisorContractError(f"{field}.operation is unsupported: {operation}")
    value = _require_finite_number(raw.get("value"), f"{field}.value")
    unit = _require_text(raw.get("unit"), f"{field}.unit")
    expected_unit = "ratio" if operation == "compressor_ratio" else "dB"
    if unit != expected_unit:
        raise AdvisorContractError(f"{field}.unit must be {expected_unit!r}")

    source_ids = raw.get("evidence_source_ids")
    if not isinstance(source_ids, list) or not source_ids:
        raise AdvisorContractError(f"{field}.evidence_source_ids must be a non-empty list")
    normalized_ids = tuple(_require_text(item, f"{field}.evidence_source_ids") for item in source_ids)
    if len(set(normalized_ids)) != len(normalized_ids):
        raise AdvisorContractError(f"{field}.evidence_source_ids contains duplicates")

    confidence = _require_finite_number(raw.get("confidence"), f"{field}.confidence")
    if not MIN_ADVISOR_CONFIDENCE <= confidence <= 1.0:
        raise AdvisorContractError(
            f"{field}.confidence must be between {MIN_ADVISOR_CONFIDENCE:.2f} and 1"
        )
    reason = _require_text(raw.get("reason"), f"{field}.reason")

    frequency_hz = q = None
    filter_type = None
    eq_fields_present = any(key in raw for key in ("frequency_hz", "q", "filter_type"))
    if operation == "eq_gain_delta":
        frequency_hz = _require_finite_number(raw.get("frequency_hz"), f"{field}.frequency_hz")
        q = _require_finite_number(raw.get("q"), f"{field}.q")
        filter_type = _require_text(raw.get("filter_type"), f"{field}.filter_type")
        if filter_type not in _FILTER_TYPES:
            raise AdvisorContractError(f"{field}.filter_type is unsupported: {filter_type}")
        if not EQ_FREQUENCY_RANGE_HZ[0] <= frequency_hz <= EQ_FREQUENCY_RANGE_HZ[1]:
            raise AdvisorContractError(f"{field}.frequency_hz is outside the audible range")
        if not EQ_Q_RANGE[0] <= q <= EQ_Q_RANGE[1]:
            raise AdvisorContractError(f"{field}.q is outside the supported range")
    elif eq_fields_present:
        raise AdvisorContractError(f"{field} includes EQ-only fields for {operation}")

    return AdvisorOperation(
        stem_id=stem_id,
        operation=operation,  # type: ignore[arg-type]
        value=value,
        unit=unit,
        evidence_source_ids=normalized_ids,
        confidence=confidence,
        reason=reason,
        frequency_hz=frequency_hz,
        q=q,
        filter_type=filter_type,
    )


def validate_advisor_proposal(raw: Any, plan: MixPlan) -> AdvisorProposal:
    """Strictly validate the full proposal without mutating ``plan``."""
    if not isinstance(raw, Mapping):
        raise AdvisorContractError("proposal must be an object")
    unknown = set(raw) - _ENVELOPE_KEYS
    missing = _ENVELOPE_KEYS - set(raw)
    if unknown:
        raise AdvisorContractError(f"proposal has unknown keys: {sorted(unknown)}")
    if missing:
        raise AdvisorContractError(f"proposal is missing keys: {sorted(missing)}")
    if raw["schema"] != CONTRACT_SCHEMA:
        raise AdvisorContractError(f"unsupported schema: {raw['schema']!r}")

    revision = _require_text(raw["source_plan_revision"], "source_plan_revision")
    expected_revision = mix_plan_revision(plan)
    if revision != expected_revision:
        raise AdvisorContractError("source_plan_revision is stale or does not match this plan")

    operations_raw = raw["operations"]
    if not isinstance(operations_raw, list) or not operations_raw:
        raise AdvisorContractError("operations must be a non-empty list")
    operations = tuple(_parse_operation(item, i) for i, item in enumerate(operations_raw))

    stems = {stem.stem_name: stem for stem in plan.stems}
    seen: set[tuple[str, str, float | None]] = set()
    for operation in operations:
        stem = stems.get(operation.stem_id)
        if stem is None:
            raise AdvisorContractError(f"unknown stem_id: {operation.stem_id}")
        if operation.operation == "compressor_ratio" and stem.compressor is None:
            raise AdvisorContractError(f"stem {operation.stem_id!r} has no compressor")
        identity = (operation.stem_id, operation.operation, operation.frequency_hz)
        if identity in seen:
            raise AdvisorContractError(f"duplicate/conflicting operation: {identity}")
        seen.add(identity)

    return AdvisorProposal(
        schema=CONTRACT_SCHEMA,
        source_plan_revision=revision,
        model_version=_require_text(raw["model_version"], "model_version"),
        prompt_version=_require_text(raw["prompt_version"], "prompt_version"),
        correlation_id=_require_text(raw["correlation_id"], "correlation_id"),
        operations=operations,
    )


def _validate_bounds(operation: AdvisorOperation, stem_band_hz: tuple[float, float] | None) -> None:
    if operation.operation == "gain_delta" and abs(operation.value) > GAIN_DELTA_CLAMP_DB:
        raise AdvisorContractError(f"gain delta exceeds +/-{GAIN_DELTA_CLAMP_DB} dB clamp")
    if operation.operation == "compressor_ratio" and not (
        COMPRESSOR_RATIO_RANGE[0] <= operation.value <= COMPRESSOR_RATIO_RANGE[1]
    ):
        raise AdvisorContractError("compressor ratio is outside the supported clamp")
    if operation.operation == "eq_gain_delta":
        if abs(operation.value) > EQ_GAIN_CLAMP_DB:
            raise AdvisorContractError(f"EQ gain exceeds +/-{EQ_GAIN_CLAMP_DB} dB clamp")
        if stem_band_hz is not None and operation.frequency_hz is not None:
            low, high = stem_band_hz
            if not low <= operation.frequency_hz <= high:
                raise AdvisorContractError("EQ frequency is outside the stem's measured band")


def _apply_proposal(
    plan: MixPlan,
    proposal: AdvisorProposal,
    stem_bands_hz: Mapping[str, tuple[float, float]],
) -> MixPlan:
    result = copy.deepcopy(plan)
    stems = {stem.stem_name: stem for stem in result.stems}
    for operation in proposal.operations:
        _validate_bounds(operation, stem_bands_hz.get(operation.stem_id))
    for operation in proposal.operations:
        stem = stems[operation.stem_id]
        if operation.operation == "gain_delta":
            stem.gain_db += operation.value
        elif operation.operation == "compressor_ratio":
            assert stem.compressor is not None
            stem.compressor["ratio"] = operation.value
        else:
            stem.eq_bands.append(
                {
                    "type": operation.filter_type,
                    "frequency": operation.frequency_hz,
                    "gain_db": operation.value,
                    "q": operation.q,
                    "advisor_evidence_source_ids": list(operation.evidence_source_ids),
                }
            )
        result.decisions_log.append(
            f"KENN advisor {operation.operation} on '{operation.stem_id}': {operation.reason} "
            f"[confidence={operation.confidence:.2f}; sources={','.join(operation.evidence_source_ids)}; "
            f"model={proposal.model_version}; prompt={proposal.prompt_version}; "
            f"correlation={proposal.correlation_id}]"
        )
    return result


def apply_advisor_proposal(
    plan: MixPlan,
    raw: Any,
    *,
    stem_bands_hz: Mapping[str, tuple[float, float]] | None = None,
) -> MixPlan:
    """Validate and apply one complete proposal to a new plan copy."""
    proposal = validate_advisor_proposal(raw, plan)
    return _apply_proposal(plan, proposal, stem_bands_hz or {})


def _operation_deltas(original: MixPlan, advised: MixPlan) -> list[dict[str, Any]]:
    """Describe the exact plan changes a validated proposal would make."""
    before = {stem.stem_name: stem for stem in original.stems}
    deltas: list[dict[str, Any]] = []
    for stem in advised.stems:
        previous = before[stem.stem_name]
        if stem.gain_db != previous.gain_db:
            deltas.append(
                {
                    "stem_id": stem.stem_name,
                    "operation": "gain_delta",
                    "before": previous.gain_db,
                    "after": stem.gain_db,
                    "delta": stem.gain_db - previous.gain_db,
                    "unit": "dB",
                }
            )
        previous_ratio = (previous.compressor or {}).get("ratio")
        current_ratio = (stem.compressor or {}).get("ratio")
        if current_ratio != previous_ratio:
            deltas.append(
                {
                    "stem_id": stem.stem_name,
                    "operation": "compressor_ratio",
                    "before": previous_ratio,
                    "after": current_ratio,
                    "unit": "ratio",
                }
            )
        for band in stem.eq_bands[len(previous.eq_bands) :]:
            deltas.append(
                {
                    "stem_id": stem.stem_name,
                    "operation": "eq_gain_delta",
                    "before": None,
                    "after": band,
                    "unit": "dB",
                }
            )
    return deltas


def evaluate_advisor_shadow(
    plan: MixPlan,
    profiles: list,
    genre: str,
    target_lufs: float,
    *,
    correlation_id: str,
    stem_bands_hz: Mapping[str, tuple[float, float]] | None = None,
) -> dict[str, Any]:
    """Evaluate one proposal without returning or mutating an advised plan."""
    started = time.perf_counter()
    try:
        raw = get_kenn_adjustments(
            plan,
            profiles,
            genre,
            target_lufs,
            correlation_id=correlation_id,
        )
    except Exception as exc:
        return _evaluate_supplied_proposal_shadow(
            plan,
            None,
            correlation_id=correlation_id,
            stem_bands_hz=stem_bands_hz,
            provider_error=exc,
            started=started,
        )
    return _evaluate_supplied_proposal_shadow(
        plan,
        raw,
        correlation_id=correlation_id,
        stem_bands_hz=stem_bands_hz,
        started=started,
    )


def evaluate_supplied_proposal_shadow(
    plan: MixPlan,
    raw: Any,
    *,
    correlation_id: str,
    stem_bands_hz: Mapping[str, tuple[float, float]] | None = None,
) -> dict[str, Any]:
    """Replay supplied producer output through the exact non-applying boundary."""
    return _evaluate_supplied_proposal_shadow(
        plan,
        raw,
        correlation_id=correlation_id,
        stem_bands_hz=stem_bands_hz,
        started=time.perf_counter(),
    )


def _evaluate_supplied_proposal_shadow(
    plan: MixPlan,
    raw: Any,
    *,
    correlation_id: str,
    stem_bands_hz: Mapping[str, tuple[float, float]] | None,
    started: float,
    provider_error: Exception | None = None,
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "schema": SHADOW_RECEIPT_SCHEMA,
        "correlation_id": correlation_id,
        "source_plan_revision": mix_plan_revision(plan),
        "source_plan": asdict(plan),
        "status": "provider_error",
        "proposal": None,
        "operation_count": 0,
        "would_change": [],
        "rejection_reason": "",
    }
    try:
        if provider_error is not None:
            raise provider_error
        if raw is None:
            receipt["status"] = "no_proposal"
            return receipt
        # Only JSON-compatible producer output is eligible for persistence/replay.
        receipt["proposal"] = json.loads(json.dumps(raw, allow_nan=False))
        proposal = validate_advisor_proposal(raw, plan)
        if proposal.correlation_id != correlation_id:
            raise AdvisorContractError("proposal correlation_id does not match the active job")
        advised = _apply_proposal(plan, proposal, stem_bands_hz or {})
        receipt["status"] = "valid"
        receipt["operation_count"] = len(proposal.operations)
        receipt["would_change"] = _operation_deltas(plan, advised)
        return receipt
    except AdvisorContractError as exc:
        receipt["status"] = "rejected"
        receipt["rejection_reason"] = str(exc)
        return receipt
    except Exception as exc:
        receipt["status"] = "provider_error"
        receipt["rejection_reason"] = f"{type(exc).__name__}: {exc}"
        return receipt
    finally:
        receipt["latency_ms"] = round((time.perf_counter() - started) * 1000.0, 3)


def advise_mix_plan(
    plan: MixPlan,
    profiles: list,
    genre: str,
    target_lufs: float,
    stem_bands_hz: dict[str, tuple[float, float]] | None = None,
    *,
    correlation_id: str = "",
) -> MixPlan:
    """Return a safely advised copy, or a clean fallback copy on any failure."""
    fallback = copy.deepcopy(plan)
    try:
        raw = get_kenn_adjustments(
            plan,
            profiles,
            genre,
            target_lufs,
            correlation_id=correlation_id,
        )
        if raw is None:
            return fallback
        proposal = validate_advisor_proposal(raw, plan)
        if correlation_id and proposal.correlation_id != correlation_id:
            raise AdvisorContractError("proposal correlation_id does not match the active job")
        return _apply_proposal(plan, proposal, stem_bands_hz or {})
    except Exception as exc:
        fallback.decisions_log.append(
            f"KENN advisor proposal rejected ({exc}); using the rule-engine plan unchanged."
        )
        return fallback
