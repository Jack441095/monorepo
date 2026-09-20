"""Tests for dependency-free, versioned platform boundary contracts."""

from __future__ import annotations

import json

import pytest

from nite_core import (
    AssistantConfidence,
    AssistantResponse,
    AudioFeatureSet,
    ArtifactRef,
    Capability,
    CommandEnvelope,
    ContractError,
    ContractValidationError,
    DomainEvent,
    JobSnapshot,
    JobStatus,
    PermissionScope,
    ProjectContext,
    ResultEnvelope,
    ResultStatus,
)


def test_assistant_response_is_versioned_and_confirmation_safe() -> None:
    response = AssistantResponse(
        answer="Reduce the sidechain release until the bass recovers in time.",
        session_id="session-1",
        intent="production_qa",
        route="production",
        service="kenn",
        confidence=AssistantConfidence.HIGH,
        grounding={"score": 92, "mode": "strong"},
        sources=({"label": "Sidechain Bass To Kick", "source": "sidechain.md"},),
        suggestions=({"label": "Ask about attack", "url": "/kenn"},),
        metadata={"interface": "http"},
    )

    assert AssistantResponse.from_dict(response.to_dict()) == response
    assert response.schema_version == 1

    with pytest.raises(ContractValidationError, match="confirmation_token"):
        AssistantResponse(answer="Send it?", requires_confirmation=True)

    confirmed = AssistantResponse(
        answer="Send it?",
        requires_confirmation=True,
        confirmation_token="confirm-123",
    )
    assert confirmed.confirmation_token == "confirm-123"


def artifact() -> ArtifactRef:
    return ArtifactRef(
        artifact_id="artifact-1",
        kind="audio.mix",
        media_type="audio/wav",
        content_hash="sha256:" + "a" * 64,
        uri="artifacts/aa/mix.wav",
        producer="audio-analysis",
        producer_version="1.0.0",
        parent_ids=("source-1",),
        metadata={"sample_rate": 48_000},
    )


def test_command_round_trips_through_json() -> None:
    command = CommandEnvelope.new(
        "audio.analyze",
        "user:local",
        {"artifact_id": "artifact-1"},
        project_id="project-1",
        idempotency_key="request-1",
    )
    decoded = json.loads(json.dumps(command.to_dict()))
    assert CommandEnvelope.from_dict(decoded) == command
    assert command.correlation_id == command.command_id
    assert command.schema_version == 1


def test_contracts_reject_unknown_fields_and_non_json_values() -> None:
    command = CommandEnvelope.new("audio.analyze", "user:local", {})
    payload = command.to_dict()
    payload["surprise"] = True
    with pytest.raises(ContractValidationError, match="surprise"):
        CommandEnvelope.from_dict(payload)

    with pytest.raises(ContractValidationError, match="finite JSON"):
        CommandEnvelope.new("audio.analyze", "user:local", {"value": float("nan")})

    payload = command.to_dict()
    payload["schema_version"] = 1.5
    with pytest.raises(ContractValidationError, match="positive integer"):
        CommandEnvelope.from_dict(payload)


def test_artifact_requires_a_sha256_identity_and_preserves_lineage() -> None:
    ref = artifact()
    assert ArtifactRef.from_dict(ref.to_dict()) == ref
    assert ref.parent_ids == ("source-1",)

    with pytest.raises(ContractValidationError, match="sha256"):
        ArtifactRef(
            artifact_id="artifact-1",
            kind="audio.mix",
            media_type="audio/wav",
            content_hash="not-a-hash",
            uri="mix.wav",
            producer="test",
            producer_version="1",
        )


def test_audio_feature_set_binds_measurements_to_source_and_profile() -> None:
    features = AudioFeatureSet(
        source_hash="sha256:" + "b" * 64,
        source_artifact_id="source-1",
        sample_rate=48_000,
        channels=2,
        duration_seconds=123.45,
        measurements={"integrated_lufs": -12.4, "true_peak_dbfs": -1.0},
        analysis_profile="mix_review.full.v1",
        producer="audio-analysis",
        diagnostics=("Reference was not supplied.",),
    )
    assert AudioFeatureSet.from_dict(features.to_dict()) == features

    with pytest.raises(ContractValidationError, match="source_hash"):
        AudioFeatureSet(
            source_hash="not-a-hash", sample_rate=48_000, channels=2,
            duration_seconds=1.0, measurements={}, analysis_profile="mix_review.full.v1",
            producer="audio-analysis",
        )


def test_result_enforces_error_semantics_and_round_trips_artifacts() -> None:
    success = ResultEnvelope(
        command_id="command-1",
        status=ResultStatus.SUCCEEDED,
        result={"score": 91},
        correlation_id="trace-1",
        artifacts=(artifact(),),
        warnings=("Reference track was unavailable.",),
    )
    assert ResultEnvelope.from_dict(success.to_dict()) == success

    with pytest.raises(ContractValidationError, match="required"):
        ResultEnvelope(
            command_id="command-1",
            status=ResultStatus.FAILED,
            result={},
            correlation_id="trace-1",
        )

    failed = ResultEnvelope(
        command_id="command-1",
        status=ResultStatus.FAILED,
        result={},
        correlation_id="trace-1",
        error=ContractError("worker_timeout", "Analysis exceeded its deadline.", True),
    )
    assert ResultEnvelope.from_dict(failed.to_dict()) == failed


def test_job_snapshot_has_generic_lifecycle_and_domain_stage() -> None:
    job = JobSnapshot(
        job_id="job-1",
        capability="automix.render",
        status=JobStatus.RUNNING,
        stage="analysing",
        progress=42,
        command_id="command-1",
        correlation_id="trace-1",
        project_id="project-1",
        worker_id="worker-1",
    )
    assert JobSnapshot.from_dict(job.to_dict()) == job

    with pytest.raises(ContractValidationError, match="0 to 100"):
        JobSnapshot(
            job_id="job-1",
            capability="automix.render",
            status=JobStatus.RUNNING,
            stage="analysing",
            progress=101,
        )

    payload = job.to_dict()
    payload["result_artifact_ids"] = "artifact-1"
    with pytest.raises(ContractValidationError, match="must be an array"):
        JobSnapshot.from_dict(payload)


def test_event_capability_and_project_context_are_versioned_json_contracts() -> None:
    event = DomainEvent(
        event_id="event-1",
        event_type="audio.analysis.completed",
        aggregate_id="project-1",
        correlation_id="trace-1",
        actor_id="worker:analysis",
        payload={"artifact_id": "report-1"},
    )
    assert DomainEvent.from_dict(event.to_dict()) == event

    capability = Capability(
        name="audio.analyze",
        version="1.0.0",
        description="Analyze an immutable audio artifact.",
        permissions=(PermissionScope.READ, PermissionScope.ANALYZE),
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        resource_needs={"audio_device": False},
    )
    assert Capability.from_dict(capability.to_dict()) == capability

    context = ProjectContext(
        project_id="project-1",
        intent="Warm, dynamic master with an open vocal.",
        reference_artifact_ids=("reference-1",),
        preferences={"target_lufs": -12},
        decisions=({"decision_id": "decision-1", "outcome": "accepted"},),
    )
    assert ProjectContext.from_dict(context.to_dict()) == context


def test_capability_rejects_duplicate_or_unknown_permissions() -> None:
    with pytest.raises(ContractValidationError, match="duplicates"):
        Capability(
            name="audio.analyze",
            version="1",
            description="Analyze audio.",
            permissions=(PermissionScope.READ, PermissionScope.READ),
            input_schema={},
            output_schema={},
        )

    with pytest.raises(ContractValidationError, match="must be one of"):
        Capability.from_dict(
            {
                "name": "audio.analyze",
                "version": "1",
                "description": "Analyze audio.",
                "permissions": ["delete_everything"],
                "input_schema": {},
                "output_schema": {},
            }
        )

    with pytest.raises(ContractValidationError, match="must be an array"):
        Capability.from_dict(
            {
                "name": "audio.analyze",
                "version": "1",
                "description": "Analyze audio.",
                "permissions": "read",
                "input_schema": {},
                "output_schema": {},
            }
        )


def test_wire_booleans_are_not_coerced_from_strings() -> None:
    error = ContractError("timeout", "Timed out.").to_dict()
    error["retryable"] = "false"
    with pytest.raises(ContractValidationError, match="must be a boolean"):
        ContractError.from_dict(error)
