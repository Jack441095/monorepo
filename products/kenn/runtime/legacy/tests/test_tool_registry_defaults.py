"""Tests for the real audio-tool registrations (Phase 3 of
docs/KENN_HUB_UNIFICATION_PLAN_2026-08-05.md). Mocks the underlying
already-tested functions (mix_review.save_review, stem_separation_bridge.
enqueue_separation, automix_public.start_public_automix) -- this file only
verifies the registry wiring calls through with the right arguments and
respects the no-confirmation-needed ANALYSIS tier, not the DSP/business
logic itself (that's covered by each function's own test suite)."""

from __future__ import annotations

import sys
import types

import pytest

from kenn.core import tool_registry
from kenn.core.tool_registry_defaults import register_defaults


@pytest.fixture(autouse=True)
def _isolated_registry(monkeypatch):
    monkeypatch.setattr(tool_registry, "_REGISTRY", {})
    register_defaults()


def test_all_three_tools_registered_as_analysis_no_gate() -> None:
    tools = {t["name"]: t for t in tool_registry.list_tools()}
    for name in ("run_mix_review", "run_stem_separation", "run_automix"):
        assert tools[name]["risk"] == "analysis"
        assert tools[name]["confirmation_required"] is False


def test_run_stem_separation_calls_through(monkeypatch) -> None:
    calls = []
    fake_module = types.SimpleNamespace(
        enqueue_separation=lambda file_bytes, filename, *, project_id="", chain_to_automix=False: calls.append(
            (file_bytes, filename, project_id, chain_to_automix)
        )
        or {"ok": True, "job": {"id": "job-1"}}
    )
    monkeypatch.setitem(sys.modules, "stem_separation_bridge", fake_module)

    result = tool_registry.invoke_tool(
        "run_stem_separation",
        session_id="s1",
        file_bytes=b"wav-bytes",
        filename="mix.wav",
        project_id="kenn-abc123",
    )
    assert result == {"ok": True, "job": {"id": "job-1"}}
    assert calls == [(b"wav-bytes", "mix.wav", "kenn-abc123", False)]


def test_run_stem_separation_forwards_chain_to_automix_flag(monkeypatch) -> None:
    calls = []
    fake_module = types.SimpleNamespace(
        enqueue_separation=lambda file_bytes, filename, *, project_id="", chain_to_automix=False: calls.append(
            (file_bytes, filename, project_id, chain_to_automix)
        )
        or {"ok": True, "job": {"id": "job-1"}}
    )
    monkeypatch.setitem(sys.modules, "stem_separation_bridge", fake_module)

    tool_registry.invoke_tool(
        "run_stem_separation",
        session_id="s1",
        file_bytes=b"wav-bytes",
        filename="mix.wav",
        project_id="kenn-abc123",
        chain_to_automix=True,
    )
    assert calls == [(b"wav-bytes", "mix.wav", "kenn-abc123", True)]


def test_run_automix_calls_through(monkeypatch) -> None:
    calls = []
    fake_module = types.SimpleNamespace(
        start_public_automix=lambda files, *, genre="pop", project_id="": calls.append(
            (files, genre, project_id)
        )
        or {"ok": True, "project_id": project_id}
    )
    monkeypatch.setitem(sys.modules, "automix_public", fake_module)

    files = [(b"stem-a", "a.wav"), (b"stem-b", "b.wav")]
    result = tool_registry.invoke_tool(
        "run_automix", session_id="s1", files=files, genre="edm", project_id="kenn-xyz"
    )
    assert result == {"ok": True, "project_id": "kenn-xyz"}
    assert calls == [(files, "edm", "kenn-xyz")]


def test_run_mix_review_calls_through(monkeypatch) -> None:
    calls = []

    def fake_save_review(**kwargs):
        calls.append(kwargs)
        return {"ok": True, "review": {"id": "review-1"}}

    fake_mix_review_module = types.SimpleNamespace(save_review=fake_save_review)
    fake_package = types.SimpleNamespace(mix_review=fake_mix_review_module)
    monkeypatch.setitem(sys.modules, "audio_analysis.mix_review", fake_package)

    result = tool_registry.invoke_tool(
        "run_mix_review",
        session_id="s1",
        file_bytes=b"wav-bytes",
        filename="mix.wav",
        project_id="kenn-abc123",
    )
    assert result == {"ok": True, "review": {"id": "review-1"}}
    assert calls == [
        {
            "file_bytes": b"wav-bytes",
            "filename": "mix.wav",
            "project_id": "kenn-abc123",
            "background": True,
        }
    ]
