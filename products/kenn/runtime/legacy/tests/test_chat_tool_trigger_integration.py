"""Integration tests for explicit-only tool triggering from KENN chat
(Phase 3 of docs/KENN_HUB_UNIFICATION_PLAN_2026-08-05.md) --
server.Handler._maybe_run_explicit_tool_trigger()."""

from __future__ import annotations

import sys
import types
from pathlib import Path

LM = Path(__file__).resolve().parent.parent.parent / "studio" / "kenn" / "kenn"
sys.path.insert(0, str(LM))

import server  # noqa: E402


def _call(question: str, session_id: str) -> dict | None:
    return server.Handler._maybe_run_explicit_tool_trigger(None, question, session_id)


def test_non_trigger_question_falls_through() -> None:
    assert _call("how do I saturate sub bass?", "s1") is None


def test_trigger_with_no_session_falls_through() -> None:
    assert _call("run a mix review on this", "") is None


def test_trigger_with_no_remembered_project_falls_through(monkeypatch) -> None:
    monkeypatch.setattr(server, "get_remembered_automix_project", lambda session_id: "")
    assert _call("run a mix review on this", "s1") is None


def test_trigger_with_project_but_no_resolvable_source_explains_instead_of_falling_through(monkeypatch) -> None:
    """Real finding, live-tested against an actual commercial track
    2026-08-05: mix_reviews' source WAV is deleted right after analysis, so
    "review this" then "separate this into stems" has a project_id but no
    resolvable file. Used to silently fall through to an unrelated generic
    answer; now explains directly instead."""
    monkeypatch.setattr(server, "get_remembered_automix_project", lambda session_id: "kenn-abc")
    fake_project_source = types.SimpleNamespace(resolve_project_source_audio=lambda pid: None)
    monkeypatch.setitem(sys.modules, "kenn.core.project_source", fake_project_source)

    result = _call("run a mix review on this", "s1")
    assert result is not None
    assert result["tool_invoked"] is None
    assert "don't have a file" in result["answer"]


def test_trigger_with_resolvable_source_invokes_tool_and_returns_chat_reply(monkeypatch) -> None:
    monkeypatch.setattr(server, "get_remembered_automix_project", lambda session_id: "kenn-abc")
    fake_project_source = types.SimpleNamespace(
        resolve_project_source_audio=lambda pid: (b"wav-bytes", "midnight_drive.wav")
    )
    monkeypatch.setitem(sys.modules, "kenn.core.project_source", fake_project_source)

    calls = []

    def fake_invoke_tool(name, **kwargs):
        calls.append((name, kwargs))
        return {"ok": True, "review": {"id": "review-1"}}

    fake_registry = types.SimpleNamespace(invoke_tool=fake_invoke_tool)
    monkeypatch.setitem(sys.modules, "kenn.core.tool_registry", fake_registry)

    result = _call("run a mix review on this", "s1")
    assert result["tool_invoked"] == "run_mix_review"
    assert "midnight_drive.wav" in result["answer"]
    assert calls == [
        (
            "run_mix_review",
            {
                "session_id": "s1",
                "file_bytes": b"wav-bytes",
                "filename": "midnight_drive.wav",
                "project_id": "kenn-abc",
            },
        )
    ]


def test_stem_separation_trigger_mentions_job_id(monkeypatch) -> None:
    monkeypatch.setattr(server, "get_remembered_automix_project", lambda session_id: "kenn-abc")
    fake_project_source = types.SimpleNamespace(
        resolve_project_source_audio=lambda pid: (b"wav-bytes", "track.wav")
    )
    monkeypatch.setitem(sys.modules, "kenn.core.project_source", fake_project_source)
    fake_registry = types.SimpleNamespace(
        invoke_tool=lambda name, **kwargs: {"ok": True, "job": {"id": "job-42"}}
    )
    monkeypatch.setitem(sys.modules, "kenn.core.tool_registry", fake_registry)

    result = _call("separate this into stems", "s1")
    assert result["tool_invoked"] == "run_stem_separation"
    assert "job-42" in result["answer"]


def test_stem_separation_trigger_forwards_automix_chain_flag(monkeypatch) -> None:
    # D3.3 (docs/KENN_FUTURE_PLAN.md Phase 3): "separate this into stems,
    # then automix it" should queue the separation with chain_to_automix=True.
    monkeypatch.setattr(server, "get_remembered_automix_project", lambda session_id: "kenn-abc")
    fake_project_source = types.SimpleNamespace(
        resolve_project_source_audio=lambda pid: (b"wav-bytes", "track.wav")
    )
    monkeypatch.setitem(sys.modules, "kenn.core.project_source", fake_project_source)
    captured = {}
    fake_registry = types.SimpleNamespace(
        invoke_tool=lambda name, **kwargs: captured.update(kwargs) or {"ok": True, "job": {"id": "job-42"}}
    )
    monkeypatch.setitem(sys.modules, "kenn.core.tool_registry", fake_registry)

    _call("separate this into stems, then automix it", "s1")

    assert captured["chain_to_automix"] is True


def test_stem_separation_trigger_defaults_chain_to_false(monkeypatch) -> None:
    monkeypatch.setattr(server, "get_remembered_automix_project", lambda session_id: "kenn-abc")
    fake_project_source = types.SimpleNamespace(
        resolve_project_source_audio=lambda pid: (b"wav-bytes", "track.wav")
    )
    monkeypatch.setitem(sys.modules, "kenn.core.project_source", fake_project_source)
    captured = {}
    fake_registry = types.SimpleNamespace(
        invoke_tool=lambda name, **kwargs: captured.update(kwargs) or {"ok": True, "job": {"id": "job-42"}}
    )
    monkeypatch.setitem(sys.modules, "kenn.core.tool_registry", fake_registry)

    _call("separate this into stems", "s1")

    assert captured["chain_to_automix"] is False


def test_run_automix_trigger_resolves_a_stem_set_and_invokes(monkeypatch) -> None:
    # G3 (docs/KENN_IMPROVEMENT_PLAN.md): unlike run_mix_review/
    # run_stem_separation, run_automix needs a resolved STEM SET, not a
    # single-file source -- previously only reachable via a direct file
    # attachment, never a plain "run automix on this" text trigger.
    monkeypatch.setattr(server, "get_remembered_automix_project", lambda session_id: "kenn-abc")
    fake_files = [(b"RIFF-drums", "drums.wav"), (b"RIFF-bass", "bass.wav")]
    fake_stem_bridge = types.SimpleNamespace(
        resolve_stem_files_for_project=lambda project_id: fake_files if project_id == "kenn-abc" else None
    )
    monkeypatch.setitem(sys.modules, "stem_separation_bridge", fake_stem_bridge)
    captured = {}
    fake_registry = types.SimpleNamespace(
        invoke_tool=lambda name, **kwargs: captured.update(kwargs) or {"ok": True, "project_id": "kenn-abc"}
    )
    monkeypatch.setitem(sys.modules, "kenn.core.tool_registry", fake_registry)

    result = _call("run an automix on this", "s1")

    assert result["tool_invoked"] == "run_automix"
    assert "AutoMix" in result["answer"]
    assert captured["files"] == fake_files
    assert captured["project_id"] == "kenn-abc"


def test_run_automix_trigger_without_a_completed_separation_explains_instead_of_failing(monkeypatch) -> None:
    monkeypatch.setattr(server, "get_remembered_automix_project", lambda session_id: "kenn-abc")
    fake_stem_bridge = types.SimpleNamespace(resolve_stem_files_for_project=lambda project_id: None)
    monkeypatch.setitem(sys.modules, "stem_separation_bridge", fake_stem_bridge)

    result = _call("run an automix on this", "s1")

    assert result["tool_invoked"] is None
    assert "stem set" in result["answer"].lower()


def test_run_automix_trigger_falls_through_without_a_remembered_project(monkeypatch) -> None:
    monkeypatch.setattr(server, "get_remembered_automix_project", lambda session_id: "")
    assert _call("run an automix on this", "s1") is None


def test_failed_tool_call_returns_readable_error(monkeypatch) -> None:
    monkeypatch.setattr(server, "get_remembered_automix_project", lambda session_id: "kenn-abc")
    fake_project_source = types.SimpleNamespace(
        resolve_project_source_audio=lambda pid: (b"wav-bytes", "track.wav")
    )
    monkeypatch.setitem(sys.modules, "kenn.core.project_source", fake_project_source)
    fake_registry = types.SimpleNamespace(
        invoke_tool=lambda name, **kwargs: {"ok": False, "error": "Upload is too large."}
    )
    monkeypatch.setitem(sys.modules, "kenn.core.tool_registry", fake_registry)

    result = _call("run a mix review on this", "s1")
    assert result["tool_invoked"] == "run_mix_review"
    assert "Upload is too large." in result["answer"]
