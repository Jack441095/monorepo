"""Tests for the audio-domain tool-call registry (Phase 3 of
docs/KENN_HUB_UNIFICATION_PLAN_2026-08-05.md)."""

from __future__ import annotations

import pytest

from kenn.core import tool_registry


@pytest.fixture(autouse=True)
def _isolated_registry(monkeypatch):
    """Each test gets its own empty registry -- don't let test tools leak
    into other tests or the real KENN tool set."""
    monkeypatch.setattr(tool_registry, "_REGISTRY", {})


def test_read_only_tool_executes_immediately_no_gate() -> None:
    calls = []

    def handler(**kwargs):
        calls.append(kwargs)
        return {"ok": True, "value": 42}

    tool_registry.register(
        tool_registry.ToolDef(
            name="run_mix_review",
            description="run a mix review",
            risk=tool_registry.ActionRisk.ANALYSIS,
            handler=handler,
        )
    )

    result = tool_registry.invoke_tool("run_mix_review", session_id="s1", file="mix.wav")
    assert result == {"ok": True, "value": 42}
    assert calls == [{"file": "mix.wav"}]


def test_unknown_tool_returns_error() -> None:
    result = tool_registry.invoke_tool("does_not_exist", session_id="s1")
    assert result["ok"] is False
    assert "Unknown tool" in result["error"]


def test_mutation_tool_without_token_is_blocked_and_issues_one() -> None:
    calls = []

    def handler(**kwargs):
        calls.append(kwargs)
        return {"ok": True}

    tool_registry.register(
        tool_registry.ToolDef(
            name="apply_eq_move",
            description="Boost the highshelf EQ by 1.5 dB",
            risk=tool_registry.ActionRisk.LOCAL_MUTATION,
            handler=handler,
        )
    )

    result = tool_registry.invoke_tool("apply_eq_move", session_id="s1", track="master")
    assert result["ok"] is False
    assert result["confirmation_required"] is True
    assert result["confirm_token"]
    assert "confirm " + result["confirm_token"] in result["message"]
    assert calls == []  # handler must NOT have run yet


def test_mutation_tool_with_valid_token_executes() -> None:
    calls = []

    def handler(**kwargs):
        calls.append(kwargs)
        return {"ok": True}

    tool_registry.register(
        tool_registry.ToolDef(
            name="apply_eq_move",
            description="Boost the highshelf EQ",
            risk=tool_registry.ActionRisk.LOCAL_MUTATION,
            handler=handler,
        )
    )

    first = tool_registry.invoke_tool("apply_eq_move", session_id="s1", track="master")
    token = first["confirm_token"]

    result = tool_registry.invoke_tool(
        "apply_eq_move", session_id="s1", confirm_token=token, track="master"
    )
    assert result == {"ok": True}
    assert calls == [{"track": "master"}]


def test_mutation_tool_rejects_wrong_session_token() -> None:
    tool_registry.register(
        tool_registry.ToolDef(
            name="apply_eq_move",
            description="Boost the highshelf EQ",
            risk=tool_registry.ActionRisk.LOCAL_MUTATION,
            handler=lambda **kwargs: {"ok": True},
        )
    )

    first = tool_registry.invoke_tool("apply_eq_move", session_id="session-a", track="master")
    token = first["confirm_token"]

    result = tool_registry.invoke_tool(
        "apply_eq_move", session_id="session-b", confirm_token=token, track="master"
    )
    assert result == {"ok": False, "error": "Invalid or expired confirmation token."}


def test_mutation_tool_rejects_token_for_different_request() -> None:
    """A token issued for one set of kwargs must not authorize a
    DIFFERENT request -- confirming what was actually shown to the user,
    not just any subsequent call to the same tool."""
    tool_registry.register(
        tool_registry.ToolDef(
            name="apply_eq_move",
            description="Boost the highshelf EQ",
            risk=tool_registry.ActionRisk.LOCAL_MUTATION,
            handler=lambda **kwargs: {"ok": True},
        )
    )

    first = tool_registry.invoke_tool("apply_eq_move", session_id="s1", track="master")
    token = first["confirm_token"]

    result = tool_registry.invoke_tool(
        "apply_eq_move", session_id="s1", confirm_token=token, track="vocals"
    )
    assert result == {"ok": False, "error": "Invalid or expired confirmation token."}


def test_list_tools_reports_risk_and_confirmation_flag() -> None:
    tool_registry.register(
        tool_registry.ToolDef(
            name="run_mix_review",
            description="run a mix review",
            risk=tool_registry.ActionRisk.ANALYSIS,
            handler=lambda **kwargs: {"ok": True},
        )
    )
    tool_registry.register(
        tool_registry.ToolDef(
            name="apply_eq_move",
            description="apply an EQ move",
            risk=tool_registry.ActionRisk.LOCAL_MUTATION,
            handler=lambda **kwargs: {"ok": True},
        )
    )

    tools = {t["name"]: t for t in tool_registry.list_tools()}
    assert tools["run_mix_review"]["confirmation_required"] is False
    assert tools["apply_eq_move"]["confirmation_required"] is True
    assert tools["apply_eq_move"]["risk"] == "local_mutation"
