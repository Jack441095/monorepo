"""Tests for the Thursday command/result envelope gateway.

Verifies that Thursday execution flows through the versioned CommandEnvelope →
ResultEnvelope contract, that the correlation_id is propagated end to end (so a
whole workflow shares one trace id), and that failures resolve to a typed
ResultEnvelope rather than raising.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nite_core import ResultStatus  # noqa: E402
from thursday import command_gateway as gw  # noqa: E402


def test_successful_command_returns_result_envelope_with_answer():
    cmd = gw.command_for_text("how's business")
    result = gw.execute_command(cmd, handle_fn=lambda text, session, **_kwargs: f"answer: {text}")

    assert result.status == ResultStatus.SUCCEEDED
    assert result.command_id == cmd.command_id
    assert result.result["answer"] == "answer: how's business"
    assert result.result["capability"] == "thursday.ask"
    assert result.result["schema_version"] == 1
    assert result.result["confidence"] == "unknown"
    assert result.result["requires_confirmation"] is False
    assert result.error is None


def test_correlation_id_propagates_command_to_result():
    cmd = gw.command_for_text("review this mix", correlation_id="trace-abc123")
    result = gw.execute_command(cmd, handle_fn=lambda text, session, **_kwargs: "reviewing…")
    assert cmd.correlation_id == "trace-abc123"
    assert result.correlation_id == "trace-abc123"


def test_default_correlation_id_is_the_command_id():
    cmd = gw.command_for_text("open audiogen")
    # CommandEnvelope.new defaults correlation_id to command_id when unset.
    assert cmd.correlation_id == cmd.command_id
    result = gw.execute_command(cmd, handle_fn=lambda text, session, **_kwargs: "ok")
    assert result.correlation_id == cmd.command_id


def test_empty_text_is_a_typed_invalid_command():
    cmd = gw.command_for_text("   ")
    result = gw.execute_command(cmd, handle_fn=lambda text, session, **_kwargs: "should not run")
    assert result.status == ResultStatus.FAILED
    assert result.error is not None
    assert result.error.code == "invalid_command"
    assert result.correlation_id == cmd.correlation_id


def test_handler_exception_becomes_a_failed_result_not_a_raise():
    cmd = gw.command_for_text("break please")

    def boom(text, session, **_kwargs):
        raise RuntimeError("kaboom")

    result = gw.execute_command(cmd, handle_fn=boom)
    assert result.status == ResultStatus.FAILED
    assert result.error.code == "execution_error"
    assert result.error.retryable is True
    assert result.error.message == "Thursday could not complete the request."
    assert "kaboom" not in result.error.message


def test_legacy_dict_is_normalized_into_assistant_response_contract():
    cmd = gw.command_for_text("review this mix")
    session = {
        "session_id": "session-1",
        "turns": [
            {
                "role": "user",
                "intent": "mix_review_audio_analysis",
                "service_used": "audio_analysis",
            }
        ],
    }
    result = gw.execute_command(
        cmd,
        session=session,
        handle_fn=lambda _text, _session, **_kwargs: {
            "answer": "The low mids are masking the vocal.",
            "confidence": "high",
            "grounding": {"score": 90},
            "sources": [{"label": "Mix review metrics"}],
            "suggestions": [{"label": "Open review", "url": "/audio-analysis"}],
            "navigate_url": "/audio-analysis",
        },
    )

    assert result.result["session_id"] == "session-1"
    assert result.result["intent"] == "mix_review_audio_analysis"
    assert result.result["service"] == "audio_analysis"
    assert result.result["confidence"] == "high"
    assert result.result["metadata"]["navigate_url"] == "/audio-analysis"


def test_studio_workflow_routes_through_the_contract():
    # One complete studio workflow (a mix-review request) via the typed contract.
    cmd = gw.command_for_text(
        "review this mix",
        capability="studio.mix_review",
        project_id="proj01",
        correlation_id="wf-1",
    )
    result = gw.execute_command(
        cmd, handle_fn=lambda text, session, **_kwargs: "Mix review: low end is muddy; cut 250 Hz."
    )
    assert result.status == ResultStatus.SUCCEEDED
    assert result.result["capability"] == "studio.mix_review"
    assert result.correlation_id == "wf-1"
    # Round-trips through JSON like every other contract.
    from nite_core import ResultEnvelope
    assert ResultEnvelope.from_dict(result.to_dict()).correlation_id == "wf-1"


def test_wire_roundtrip_matches_the_command_endpoint():
    # Simulates POST /command: raw dict in → CommandEnvelope → ResultEnvelope → dict out.
    from nite_core import CommandEnvelope, ResultEnvelope

    raw_in = gw.command_for_text("how's business", correlation_id="wf-9").to_dict()
    envelope = CommandEnvelope.from_dict(raw_in)  # endpoint parses the body
    result = gw.execute_command(envelope, handle_fn=lambda t, s, **_kwargs: "Revenue is up.")
    raw_out = result.to_dict()  # endpoint serialises the response

    assert raw_out["status"] == "succeeded"
    assert raw_out["correlation_id"] == "wf-9"
    assert ResultEnvelope.from_dict(raw_out).result["answer"] == "Revenue is up."
