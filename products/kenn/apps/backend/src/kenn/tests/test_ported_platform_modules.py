"""Tests for the KENN-owned modules ported to replace hard external
dependencies (audio_too, thursday) that blocked server.py, tool_registry.py,
and response_contract.py from importing standalone -- see
docs/KNOWN_ISSUES.md ISSUE-08 and docs/KENN_BETA_GAP_MATRIX.md GAP-04.

This is the first test file under apps/backend/src/kenn/ -- that package previously
had zero test coverage of its own.
"""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest  # noqa: E402

from kenn.core import action_policy, confirmation, path_safety, request_validation  # noqa: E402
from kenn.core.endpoint_policy import EndpointAccess, EndpointEffect, endpoint_policy  # noqa: E402
from kenn.core.platform_contracts import (  # noqa: E402
    AssistantResponse,
    CommandEnvelope,
    ContractValidationError,
    ResultEnvelope,
    ResultStatus,
)
from kenn.core.response_contract import augment_payload  # noqa: E402


# --- platform_contracts.py ---------------------------------------------


def test_assistant_response_round_trips_through_dict() -> None:
    response = AssistantResponse(answer="Use a high-pass filter.", session_id="s1", intent="troubleshooting")
    payload = response.to_dict()
    restored = AssistantResponse.from_dict(payload)
    assert restored == response


def test_assistant_response_rejects_confirmation_without_token() -> None:
    with pytest.raises(ContractValidationError):
        AssistantResponse(answer="x", requires_confirmation=True)


def test_command_and_result_envelope_round_trip() -> None:
    command = CommandEnvelope.new("kenn.ask", "kenn.http", {"question": "hi"})
    result = ResultEnvelope(
        command_id=command.command_id,
        status=ResultStatus.SUCCEEDED,
        result={"answer": "ok"},
        correlation_id=command.correlation_id,
    )
    restored = ResultEnvelope.from_dict(result.to_dict())
    assert restored.status == ResultStatus.SUCCEEDED
    assert restored.command_id == command.command_id


def test_result_envelope_requires_error_when_failed() -> None:
    with pytest.raises(ContractValidationError):
        ResultEnvelope(
            command_id="abc",
            status=ResultStatus.FAILED,
            result={},
            correlation_id="abc",
        )


# --- response_contract.py -----------------------------------------------


def test_augment_payload_adds_envelope_fields() -> None:
    payload = {"answer": "Use a reference track.", "found": True, "confidence": "high"}
    augmented = augment_payload(payload, question="how do I mix vocals?", session_id="s1")
    assert augmented["answer"] == "Use a reference track."
    assert augmented["schema_version"] == 1
    assert augmented["status"] == "succeeded"
    assert "envelope" in augmented
    assert augmented["envelope"]["result"]["capability"] == "kenn.ask"


# --- endpoint_policy.py ---------------------------------------------------


def test_kenn_surface_is_loopback_only() -> None:
    policy = endpoint_policy("kenn", "GET", "/api/health")
    assert policy.access == EndpointAccess.LOOPBACK
    assert policy.effect == EndpointEffect.READ_ONLY
    assert policy.mutates is False


def test_kenn_ask_route_is_analysis_not_mutation() -> None:
    policy = endpoint_policy("kenn", "POST", "/api/ask")
    assert policy.effect == EndpointEffect.ANALYSIS
    # ANALYSIS is deliberately excluded from .mutates (only LOCAL_MUTATION/
    # EXTERNAL_COMMUNICATION/DESTRUCTIVE/ORCHESTRATED count) -- answering a
    # question doesn't change any state.
    assert policy.mutates is False
    assert policy.rate_limit_required is True


def test_unknown_surface_raises() -> None:
    with pytest.raises(ValueError):
        endpoint_policy("unknown", "GET", "/x")


# --- request_validation.py -------------------------------------------------


def test_validate_json_payload_accepts_normal_object() -> None:
    result = request_validation.validate_json_payload({"question": "hi", "history": []})
    assert result == {"question": "hi", "history": []}


def test_validate_json_payload_rejects_non_object_at_top_level() -> None:
    with pytest.raises(ValueError):
        request_validation.validate_json_payload("not an object")


def test_validate_json_payload_rejects_too_deep_nesting() -> None:
    value: object = "leaf"
    for _ in range(request_validation.MAX_JSON_DEPTH + 2):
        value = {"nested": value}
    with pytest.raises(ValueError):
        request_validation.validate_json_payload(value)


# --- action_policy.py -------------------------------------------------------


def test_action_allowed_defaults_to_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUDIO_TOO_ALLOW_DAW_CONTROL", raising=False)
    assert action_policy.action_allowed("daw_control") is False


def test_action_allowed_respects_explicit_env_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
    assert action_policy.action_allowed("daw_control") is True


def test_action_allowed_unknown_action_is_false() -> None:
    assert action_policy.action_allowed("not_a_real_action") is False


# --- path_safety.py ----------------------------------------------------------


def test_safe_child_rejects_path_escape(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(ValueError):
        path_safety.safe_child(root, "..", "..", "etc", "passwd")


def test_safe_child_accepts_nested_child(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    result = path_safety.safe_child(root, "project123", "file.json")
    assert result == (root / "project123" / "file.json").resolve()


# --- confirmation.py ---------------------------------------------------------


def test_confirmation_round_trip_verifies() -> None:
    token, record = confirmation.issue_confirmation(
        session_id="s1", service_id="kenn", text="delete the render"
    )
    assert record["token"] == token
    assert confirmation.verify_confirmation(token, session_id="s1", service_id="kenn", text="delete the render")


def test_confirmation_rejects_mismatched_text() -> None:
    token, _ = confirmation.issue_confirmation(session_id="s1", service_id="kenn", text="delete the render")
    assert not confirmation.verify_confirmation(token, session_id="s1", service_id="kenn", text="a different action")


def test_confirmation_rejects_expired_token() -> None:
    token, record = confirmation.issue_confirmation(
        session_id="s1", service_id="kenn", text="delete the render", ttl_seconds=1
    )
    assert not confirmation.verify_confirmation(
        token, session_id="s1", service_id="kenn", text="delete the render", now=record["expires_at"] + 1
    )


def test_confirmation_rejects_malformed_token() -> None:
    assert not confirmation.verify_confirmation("not-a-real-token", session_id="s1", service_id="kenn", text="x")
