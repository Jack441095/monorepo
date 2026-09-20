"""Public failure contracts must remain stable and redact internal detail."""

from __future__ import annotations

import json
from unittest.mock import patch

from nite_core import (
    PublicError,
    PublicErrorCode,
    public_error_details,
    public_error_payload,
)
from app.api_errors import exception_payload
from studio.kenn.kenn.server import safe_error_payload
from thursday import bridge, session_manager
from thursday.command_gateway import command_for_text, execute_command
from thursday.formatter import format_response
from thursday.main import execute_cli_request
from thursday.orchestrator import handle
from thursday.voice import execute_voice_command_result


SECRET = "postgres://admin:super-secret@internal/private-path"


def test_shared_error_mapper_never_copies_exception_text() -> None:
    details = public_error_details(RuntimeError(SECRET))
    assert details.code is PublicErrorCode.INTERNAL_ERROR
    assert SECRET not in details.message

    status, payload = public_error_payload(RuntimeError(SECRET), error_id="request-1")
    assert status == 500
    assert payload == {
        "error": "The request could not be completed.",
        "error_code": "internal_error",
        "retryable": False,
        "error_id": "request-1",
    }


def test_explicit_public_errors_keep_only_the_declared_safe_message() -> None:
    error = PublicError(
        PublicErrorCode.RATE_LIMITED,
        "Too many requests. Try again shortly.",
        retryable=True,
        http_status=429,
    )
    details = public_error_details(error)
    assert details.code is PublicErrorCode.RATE_LIMITED
    assert details.retryable is True
    assert details.http_status == 429


def test_gateway_maps_typed_and_untyped_failures_without_raw_detail() -> None:
    typed = execute_command(
        command_for_text("test"),
        handle_fn=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            PublicError(
                PublicErrorCode.SERVICE_UNAVAILABLE,
                "The test service is unavailable.",
                retryable=True,
                http_status=503,
            )
        ),
    )
    assert typed.error is not None
    assert typed.error.code == "service_unavailable"
    assert typed.error.retryable is True

    untyped = execute_command(
        command_for_text("test"),
        handle_fn=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(SECRET)),
    )
    assert untyped.error is not None
    assert untyped.error.code == "execution_error"
    assert SECRET not in json.dumps(untyped.to_dict())


def test_structured_service_errors_do_not_leak_raw_detail() -> None:
    rendered = format_response(
        {"ok": False, "error": SECRET}, "Private Service", "search", {}
    )
    assert SECRET not in rendered
    assert "service_unavailable" in rendered


def test_kenn_500_payload_has_stable_code_and_redacts_detail() -> None:
    payload = safe_error_payload(
        500,
        {"ok": False, "error": SECRET, "traceback": SECRET, "path": "/private"},
        "kenn-request-1",
    )
    assert payload["error_code"] == "internal_error"
    assert payload["error_id"] == "kenn-request-1"
    assert SECRET not in json.dumps(payload)


def test_business_exception_boundary_uses_shared_redaction() -> None:
    status, payload = exception_payload(RuntimeError(SECRET), request_id="business-1")
    assert status == 500
    assert payload["error_code"] == "internal_error"
    assert payload["error_id"] == "business-1"
    assert SECRET not in json.dumps(payload)


def test_service_exception_is_safe_across_sync_sse_cli_and_voice(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(session_manager, "SESSION_DIR", tmp_path / "sessions")
    monkeypatch.setattr(session_manager, "SESSION_FILE", tmp_path / ".session")

    with (
        patch("thursday.orchestrator.should_check", return_value=False),
        patch("thursday.orchestrator.get_pending_alerts", return_value=[]),
        patch("thursday.client.business_status", side_effect=RuntimeError(SECRET)),
    ):
        sync = bridge.ask("how's business", session_id="error-sync")
        stream = list(bridge.ask_stream("how's business", session_id="error-stream"))
        cli = execute_cli_request(
            "how's business", session_manager.get_or_create_session("error-cli")
        )
        voice = execute_voice_command_result(
            "how's business",
            session_manager.get_or_create_session("error-voice"),
            handle,
        )

    assert sync["status"] == "failed"
    assert sync["error_code"] == "service_unavailable"
    assert any(
        event.get("event") == "metadata"
        and event.get("data", {}).get("error_code") == "service_unavailable"
        for event in stream
    )
    assert cli.error is not None and cli.error.code == "service_unavailable"
    assert voice.error is not None and voice.error.code == "service_unavailable"
    assert SECRET not in json.dumps(
        {
            "sync": sync,
            "stream": stream,
            "cli": cli.to_dict(),
            "voice": voice.to_dict(),
        }
    )
