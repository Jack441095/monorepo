from __future__ import annotations

from nite_core import AssistantResponse, ResultEnvelope
from thursday import main as thursday_main


def test_cli_request_uses_shared_assistant_contract(monkeypatch) -> None:
    session = {"session_id": "cli-1", "turns": []}
    monkeypatch.setattr(
        thursday_main, "handle", lambda _text, _session, **_kwargs: "All systems healthy."
    )

    result = thursday_main.execute_cli_request("system status", session)

    wire_result = ResultEnvelope.from_dict(result.to_dict())
    assistant = AssistantResponse.from_dict(
        {key: value for key, value in wire_result.result.items() if key != "capability"}
    )
    assert assistant.answer == "All systems healthy."
    assert assistant.session_id == "cli-1"
    assert wire_result.correlation_id == wire_result.command_id


def test_cli_request_redacts_internal_exception(monkeypatch) -> None:
    def fail(_text, _session, **_kwargs):
        raise RuntimeError("database password leaked here")

    monkeypatch.setattr(thursday_main, "handle", fail)
    result = thursday_main.execute_cli_request("system status", {"session_id": "cli-2"})

    assert result.error is not None
    assert result.error.code == "execution_error"
    assert "password" not in result.error.message
