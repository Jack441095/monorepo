"""Adversarial tests for the versioned KENN-to-AutoMix contract."""

from __future__ import annotations

import copy
import json
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import pytest

from audio_analysis.integration import kenn_advisor
from audio_analysis.integration.kenn_advisor import (
    AdvisorContractError,
    advise_mix_plan,
    evaluate_advisor_shadow,
    get_kenn_adjustments,
    mix_plan_revision,
    validate_advisor_proposal,
)
from audio_analysis.mixdown.mix_decision_engine import (
    BusMixConfig,
    MixPlan,
    StemMixConfig,
    generate_mix_plan,
)
from audio_analysis.mixdown.stem_classifier import StemProfile


def _plan_with_one_stem(**stem_overrides) -> MixPlan:
    stem_values = {
        "stem_name": "vocal_lead",
        "instrument": "vocal",
        "gain_db": 0.0,
        "compressor": {
            "ratio": 3.0,
            "attack_ms": 10.0,
            "release_ms": 100.0,
            "threshold_db": -18.0,
            "makeup_gain_db": 0.0,
        },
    }
    stem_values.update(stem_overrides)
    stem = StemMixConfig(**stem_values)
    return MixPlan(stems=[stem], bus=BusMixConfig(), genre="pop", target_lufs=-14.0)


def _operation(operation: str = "gain_delta", **overrides) -> dict:
    units = {"gain_delta": "dB", "compressor_ratio": "ratio", "eq_gain_delta": "dB"}
    raw = {
        "stem_id": "vocal_lead",
        "operation": operation,
        "value": 1.0 if operation != "compressor_ratio" else 4.0,
        "unit": units[operation],
        "evidence_source_ids": ["kenn-note:balance-v2"],
        "confidence": 0.91,
        "reason": "The measured vocal is below the target balance.",
    }
    if operation == "eq_gain_delta":
        raw.update({"frequency_hz": 2000.0, "q": 1.0, "filter_type": "peaking"})
    raw.update(overrides)
    return raw


def _proposal(plan: MixPlan, operations: list[dict] | None = None, **overrides) -> dict:
    raw = {
        "schema": kenn_advisor.CONTRACT_SCHEMA,
        "source_plan_revision": mix_plan_revision(plan),
        "model_version": "kenn-advisor-shadow-1",
        "prompt_version": "advisor-v1",
        "correlation_id": "automix-job:test-123",
        "operations": operations or [_operation()],
    }
    raw.update(overrides)
    return raw


def _advise(plan: MixPlan, proposal: object, **kwargs) -> MixPlan:
    with patch.object(kenn_advisor, "get_kenn_adjustments", return_value=proposal):
        return advise_mix_plan(
            plan,
            profiles=[],
            genre="pop",
            target_lufs=-14.0,
            correlation_id="automix-job:test-123",
            **kwargs,
        )


def test_disabled_provider_returns_equal_but_independent_plan() -> None:
    plan = _plan_with_one_stem()
    result = advise_mix_plan(plan, profiles=[], genre="pop", target_lufs=-14.0)
    assert result == plan
    assert result is not plan
    assert result.stems[0] is not plan.stems[0]


@pytest.mark.parametrize(
    ("operation", "expected"),
    [
        (_operation("gain_delta", value=2.0), 2.0),
        (_operation("compressor_ratio", value=4.5), 4.5),
    ],
)
def test_supported_operations_apply_to_copy(operation: dict, expected: float) -> None:
    plan = _plan_with_one_stem()
    result = _advise(plan, _proposal(plan, [operation]))
    assert result is not plan
    assert plan.stems[0].gain_db == 0.0
    assert plan.stems[0].compressor["ratio"] == 3.0
    if operation["operation"] == "gain_delta":
        assert result.stems[0].gain_db == pytest.approx(expected)
    else:
        assert result.stems[0].compressor["ratio"] == pytest.approx(expected)
    assert "sources=kenn-note:balance-v2" in result.decisions_log[-1]
    assert "correlation=automix-job:test-123" in result.decisions_log[-1]


def test_supported_eq_operation_preserves_evidence() -> None:
    plan = _plan_with_one_stem()
    result = _advise(
        plan,
        _proposal(plan, [_operation("eq_gain_delta", value=-2.5)]),
        stem_bands_hz={"vocal_lead": (100.0, 12_000.0)},
    )
    assert plan.stems[0].eq_bands == []
    assert result.stems[0].eq_bands == [
        {
            "type": "peaking",
            "frequency": 2000.0,
            "gain_db": -2.5,
            "q": 1.0,
            "advisor_evidence_source_ids": ["kenn-note:balance-v2"],
        }
    ]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda proposal: proposal.update({"schema": "future/v99"}),
        lambda proposal: proposal.update({"source_plan_revision": "sha256:stale"}),
        lambda proposal: proposal.update({"surprise": True}),
        lambda proposal: proposal.pop("model_version"),
        lambda proposal: proposal.update({"correlation_id": "automix-job:other"}),
        lambda proposal: proposal["operations"][0].update({"unknown": 1}),
        lambda proposal: proposal["operations"][0].update({"stem_id": "missing"}),
        lambda proposal: proposal["operations"][0].update({"unit": "linear"}),
        lambda proposal: proposal["operations"][0].update({"value": float("nan")}),
        lambda proposal: proposal["operations"][0].update({"confidence": float("inf")}),
        lambda proposal: proposal["operations"][0].update({"confidence": 0.69}),
        lambda proposal: proposal["operations"][0].update({"evidence_source_ids": []}),
        lambda proposal: proposal["operations"][0].update({"reason": ""}),
    ],
    ids=[
        "unknown-schema",
        "stale-plan",
        "unknown-envelope-key",
        "missing-provenance",
        "wrong-correlation",
        "unknown-operation-key",
        "missing-stem",
        "wrong-unit",
        "nan",
        "infinity",
        "weak-confidence",
        "missing-evidence",
        "missing-reason",
    ],
)
def test_malformed_proposal_is_rejected_atomically(mutation) -> None:
    plan = _plan_with_one_stem()
    original = copy.deepcopy(plan)
    proposal = _proposal(plan)
    mutation(proposal)
    result = _advise(plan, proposal)
    assert plan == original
    assert result.stems == original.stems
    assert "proposal rejected" in result.decisions_log[-1]


@pytest.mark.parametrize(
    "operation",
    [
        _operation("gain_delta", value=3.01),
        _operation("compressor_ratio", value=8.01),
        _operation("eq_gain_delta", value=12.01),
        _operation("eq_gain_delta", frequency_hz=50.0),
    ],
)
def test_out_of_bounds_operation_rejects_whole_proposal(operation: dict) -> None:
    plan = _plan_with_one_stem()
    operations = [_operation("gain_delta", value=1.0), operation]
    result = _advise(
        plan,
        _proposal(plan, operations),
        stem_bands_hz={"vocal_lead": (100.0, 12_000.0)},
    )
    assert plan.stems[0].gain_db == 0.0
    assert result.stems[0].gain_db == 0.0
    assert result.stems[0].eq_bands == []
    assert "proposal rejected" in result.decisions_log[-1]


def test_duplicate_operations_are_rejected() -> None:
    plan = _plan_with_one_stem()
    proposal = _proposal(plan, [_operation(value=1.0), _operation(value=-1.0)])
    with pytest.raises(AdvisorContractError, match="duplicate/conflicting"):
        validate_advisor_proposal(proposal, plan)


def test_compressor_operation_requires_existing_processor() -> None:
    plan = _plan_with_one_stem(compressor=None)
    result = _advise(plan, _proposal(plan, [_operation("compressor_ratio")]))
    assert result.stems[0].compressor is None
    assert "has no compressor" in result.decisions_log[-1]


def test_provider_failure_does_not_mutate_original() -> None:
    plan = _plan_with_one_stem()
    with patch.object(kenn_advisor, "get_kenn_adjustments", side_effect=RuntimeError("KENN down")):
        result = advise_mix_plan(plan, profiles=[], genre="pop", target_lufs=-14.0)
    assert result is not plan
    assert plan.decisions_log == []
    assert "KENN down" in result.decisions_log[-1]


def test_published_json_schema_accepts_the_runtime_contract() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema_path = (
        Path(kenn_advisor.__file__).parent / "schemas" / "kenn_advisor_v1.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    plan = _plan_with_one_stem()
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(_proposal(plan), schema)


def test_published_schema_rejects_eq_fields_on_gain_operation() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema_path = (
        Path(kenn_advisor.__file__).parent / "schemas" / "kenn_advisor_v1.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    plan = _plan_with_one_stem()
    invalid = _proposal(plan, [_operation(frequency_hz=1000.0)])
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(invalid, schema)


def test_shadow_evaluates_valid_proposal_without_mutating_plan() -> None:
    plan = _plan_with_one_stem()
    original = copy.deepcopy(plan)
    proposal = _proposal(plan, [_operation(value=1.5)])
    with patch.object(kenn_advisor, "get_kenn_adjustments", return_value=proposal):
        receipt = evaluate_advisor_shadow(
            plan,
            profiles=[],
            genre="pop",
            target_lufs=-14.0,
            correlation_id="automix-job:test-123",
        )
    assert plan == original
    assert receipt["status"] == "valid"
    assert receipt["source_plan"] == asdict(plan)
    assert receipt["operation_count"] == 1
    assert receipt["would_change"] == [
        {
            "stem_id": "vocal_lead",
            "operation": "gain_delta",
            "before": 0.0,
            "after": 1.5,
            "delta": 1.5,
            "unit": "dB",
        }
    ]
    assert receipt["latency_ms"] >= 0


def test_shadow_records_rejection_without_mutating_plan() -> None:
    plan = _plan_with_one_stem()
    proposal = _proposal(plan, [_operation(value=99.0)])
    with patch.object(kenn_advisor, "get_kenn_adjustments", return_value=proposal):
        receipt = evaluate_advisor_shadow(
            plan,
            profiles=[],
            genre="pop",
            target_lufs=-14.0,
            correlation_id="automix-job:test-123",
        )
    assert plan.stems[0].gain_db == 0.0
    assert receipt["status"] == "rejected"
    assert "clamp" in receipt["rejection_reason"]


def test_shadow_records_disabled_provider() -> None:
    plan = _plan_with_one_stem()
    receipt = evaluate_advisor_shadow(
        plan,
        profiles=[],
        genre="pop",
        target_lufs=-14.0,
        correlation_id="automix-job:test-123",
    )
    assert receipt["status"] == "no_proposal"
    assert receipt["proposal"] is None


def _measured_profiles(*, confidence: float = 0.95) -> list[StemProfile]:
    return [
        StemProfile(
            name="kick.wav",
            instrument="kick",
            classification_confidence=confidence,
            peak_dbfs=-8.0,
            rms_dbfs=-20.0,
            crest_factor_db=12.0,
        ),
        StemProfile(
            name="vocal.wav",
            instrument="vocal",
            classification_confidence=confidence,
            peak_dbfs=-10.0,
            rms_dbfs=-24.0,
            crest_factor_db=14.0,
        ),
    ]


def test_grounded_producer_abstains_on_canonical_plan() -> None:
    profiles = _measured_profiles()
    plan = generate_mix_plan(profiles, masking_results=None, genre="pop", target_lufs=-14.0)
    with patch.object(
        kenn_advisor,
        "_retrieve_approved_evidence",
        return_value=("approved-source", 0.97),
    ) as retrieve:
        proposal = get_kenn_adjustments(
            plan,
            profiles,
            "pop",
            -14.0,
            correlation_id="automix-job:canonical",
        )
    assert proposal is None
    retrieve.assert_not_called()


def test_grounded_producer_emits_bounded_gain_and_ratio_drift() -> None:
    profiles = _measured_profiles()
    plan = generate_mix_plan(profiles, masking_results=None, genre="pop", target_lufs=-14.0)
    vocal = next(stem for stem in plan.stems if stem.stem_name == "vocal.wav")
    canonical_gain = vocal.gain_db
    vocal.gain_db += 1.25
    assert vocal.compressor is not None
    vocal.compressor["ratio"] = 5.0

    def evidence(_query: str, *, expected_source: str):
        return f"{expected_source}:approved", 0.98

    with patch.object(kenn_advisor, "_retrieve_approved_evidence", side_effect=evidence):
        proposal = get_kenn_adjustments(
            plan,
            profiles,
            "pop",
            -14.0,
            correlation_id="automix-job:drift",
        )
    assert proposal is not None
    validated = validate_advisor_proposal(proposal, plan)
    operations = {operation.operation: operation for operation in validated.operations}
    assert operations["gain_delta"].value == pytest.approx(-1.25)
    assert operations["compressor_ratio"].value == pytest.approx(3.5)
    assert operations["gain_delta"].evidence_source_ids == (
        "automix-gain-staging.md:approved",
    )

    with patch.object(kenn_advisor, "get_kenn_adjustments", return_value=proposal):
        receipt = evaluate_advisor_shadow(
            plan,
            profiles,
            "pop",
            -14.0,
            correlation_id="automix-job:drift",
        )
    assert receipt["status"] == "valid"
    assert vocal.gain_db == pytest.approx(canonical_gain + 1.25)
    assert {delta["operation"] for delta in receipt["would_change"]} == {
        "gain_delta",
        "compressor_ratio",
    }


def test_grounded_producer_abstains_on_weak_classification() -> None:
    profiles = _measured_profiles(confidence=0.69)
    plan = generate_mix_plan(profiles, masking_results=None, genre="pop", target_lufs=-14.0)
    plan.stems[0].gain_db += 1.0
    assert (
        get_kenn_adjustments(
            plan,
            profiles,
            "pop",
            -14.0,
            correlation_id="automix-job:weak",
        )
        is None
    )


def test_grounded_producer_abstains_when_approved_evidence_is_missing() -> None:
    profiles = _measured_profiles()
    plan = generate_mix_plan(profiles, masking_results=None, genre="pop", target_lufs=-14.0)
    plan.stems[0].gain_db += 1.0
    with patch.object(kenn_advisor, "_retrieve_approved_evidence", return_value=None):
        proposal = get_kenn_adjustments(
            plan,
            profiles,
            "pop",
            -14.0,
            correlation_id="automix-job:no-evidence",
        )
    assert proposal is None


@pytest.mark.parametrize(
    ("query", "source"),
    [
        ("AutoMix gain staging anchor relative RMS peak", "automix-gain-staging.md"),
        (
            "AutoMix compression ratio per instrument genre",
            "automix-compression-ratios.md",
        ),
    ],
)
def test_real_index_returns_exact_approved_advisor_evidence(query: str, source: str) -> None:
    evidence = kenn_advisor._retrieve_approved_evidence(query, expected_source=source)
    assert evidence is not None
    evidence_id, confidence = evidence
    assert evidence_id.startswith(source.removesuffix(".md"))
    assert "@index:v-" in evidence_id
    assert confidence >= kenn_advisor.MIN_ADVISOR_CONFIDENCE
