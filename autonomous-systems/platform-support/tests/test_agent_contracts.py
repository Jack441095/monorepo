"""Tests for agent request/result contracts and validation invariants."""

import json

import pytest

from nite_ai.contracts import (
    AgentRequest,
    AgentResult,
    ArtifactKind,
    ArtifactRef,
    ExecutionMetadata,
    RequestPriority,
    ResultStatus,
)
from nite_ai.errors import AgentError, ErrorCategory, ValidationError
from nite_ai.permissions import PrivacyClass


def make_request(**overrides) -> AgentRequest:
    fields = dict(
        request_id="req-123",
        trace_id="trace-abc",
        capability_id="audio.mix.analyze",
        payload={"track": "synth-lead"},
    )
    fields.update(overrides)
    return AgentRequest(**fields)


def test_request_round_trip() -> None:
    req = make_request(priority=RequestPriority.HIGH)
    d = req.to_dict()
    text = json.dumps(d, sort_keys=True)
    assert json.loads(text)["capability_id"] == "audio.mix.analyze"


def test_bad_capability_id_rejected() -> None:
    with pytest.raises(ValidationError):
        make_request(capability_id="Analyze My Mix")
    with pytest.raises(ValidationError):
        make_request(capability_id="nodots")


def test_bad_locale_rejected() -> None:
    with pytest.raises(ValidationError):
        make_request(locale="not a locale")


def test_secret_payload_rejected() -> None:
    with pytest.raises(ValidationError):
        make_request(privacy_class=PrivacyClass.SECRET)


def test_success_requires_payload_or_artifacts() -> None:
    with pytest.raises(ValidationError):
        AgentResult(request_id="req-123", status=ResultStatus.SUCCESS)


def test_success_forbids_error() -> None:
    with pytest.raises(ValidationError):
        AgentResult(
            request_id="r",
            status=ResultStatus.SUCCESS,
            result={"ok": True},
            error=AgentError(ErrorCategory.INTERNAL_ERROR, "boom"),
        )


@pytest.mark.parametrize("status", [ResultStatus.FAILED, ResultStatus.CANCELLED, ResultStatus.TIMEOUT])
def test_terminal_failures_require_error(status: ResultStatus) -> None:
    with pytest.raises(ValidationError):
        AgentResult(request_id="r", status=status)


def test_failed_result_with_structured_error_ok() -> None:
    res = AgentResult(
        request_id="r",
        status=ResultStatus.FAILED,
        error=AgentError(ErrorCategory.TIMEOUT, "took too long"),
        execution=ExecutionMetadata(duration_ms=9000.0, attempt=2),
    )
    assert not res.ok
    assert res.to_dict()["error"]["category"] == "timeout"


def test_artifact_ref_rejects_blobs() -> None:
    with pytest.raises(ValidationError):
        ArtifactRef(artifact_id="bad id!", kind=ArtifactKind.JSON_RESULT, uri="")
    ref = ArtifactRef(artifact_id="art-001", kind=ArtifactKind.JSON_RESULT, uri="/tmp/report.json")
    assert ref.to_dict()["kind"] == "json_result"
