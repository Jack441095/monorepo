"""Integration tests for server.Handler._maybe_handle_mix_revision() --
the fix for a real gap found live 2026-08-06: is_mix_revision_request()
and ableton_bridge._handle_mix_revision() were built and tested this same
session, but were only ever reachable via business/app's OWN
/api/ableton/ask route (a separate dashboard chat surface, port 8080),
never from KENN's own /api/ask (this file, port 8090 -- what the actual
KENN chat UI calls). "make the vocals warmer" through the real server
just returned generic RAG advice with no revision job queued."""

from __future__ import annotations

import sys
import types
from pathlib import Path

LM = Path(__file__).resolve().parent.parent.parent / "studio" / "kenn" / "kenn"
sys.path.insert(0, str(LM))

import server  # noqa: E402


def _call(question: str, session_id: str = "s1", project_id: str = "proj-1") -> dict | None:
    return server.Handler._maybe_handle_mix_revision(None, question, session_id, project_id)


def test_non_revision_question_falls_through() -> None:
    assert _call("how do I saturate sub bass?") is None


def test_revision_request_denied_by_default(monkeypatch) -> None:
    # Security review finding, 2026-08-08: this dispatch bypassed
    # action_allowed("daw_control") entirely -- unlike every other
    # write-capable action reachable from this same unauthenticated
    # /api/ask, a mix-revision request could queue a real AutoMix render
    # job for any project_id in the request body with zero gate at all.
    monkeypatch.delenv("AUDIO_TOO_ALLOW_DAW_CONTROL", raising=False)

    def _fail_if_called(*_a, **_kw):
        raise AssertionError("ableton_bridge should never be reached when denied")

    monkeypatch.setitem(sys.modules, "ableton_bridge", types.SimpleNamespace(_handle_mix_revision=_fail_if_called))

    result = _call("make the vocals warmer")

    assert result["found"] is False
    assert "AUDIO_TOO_ALLOW_DAW_CONTROL" in result["answer"]


def test_revision_request_dispatches_to_ableton_bridge(monkeypatch) -> None:
    monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
    calls = []

    def fake_handle_mix_revision(question, *, session_id, project_id):
        calls.append((question, session_id, project_id))
        return {"answer": "Got it -- re-rendering the mix now.", "found": True, "route": "revise_mix"}

    fake_ableton_bridge = types.SimpleNamespace(_handle_mix_revision=fake_handle_mix_revision)
    monkeypatch.setitem(sys.modules, "ableton_bridge", fake_ableton_bridge)

    result = _call("make the vocals warmer", session_id="s1", project_id="proj-1")

    assert result == {"answer": "Got it -- re-rendering the mix now.", "found": True, "route": "revise_mix"}
    assert calls == [("make the vocals warmer", "s1", "proj-1")]


def test_revision_request_with_no_explicit_project_id_uses_resolve_session_project(monkeypatch) -> None:
    monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
    calls = []

    def fake_handle_mix_revision(question, *, session_id, project_id):
        calls.append((question, session_id, project_id))
        return {"answer": "ok", "found": True}

    fake_ableton_bridge = types.SimpleNamespace(_handle_mix_revision=fake_handle_mix_revision)
    monkeypatch.setitem(sys.modules, "ableton_bridge", fake_ableton_bridge)
    monkeypatch.setattr(server, "resolve_session_project", lambda session_id: "auto-resolved-project")

    _call("make it brighter", session_id="s1", project_id="")

    assert calls == [("make it brighter", "s1", "auto-resolved-project")]


def test_revision_request_with_no_session_id_passes_empty_project_id(monkeypatch) -> None:
    monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
    calls = []

    def fake_handle_mix_revision(question, *, session_id, project_id):
        calls.append((question, session_id, project_id))
        return {"answer": "ok", "found": True}

    fake_ableton_bridge = types.SimpleNamespace(_handle_mix_revision=fake_handle_mix_revision)
    monkeypatch.setitem(sys.modules, "ableton_bridge", fake_ableton_bridge)

    _call("make it brighter", session_id="", project_id="")

    assert calls == [("make it brighter", "", "")]


def test_missing_ableton_bridge_module_falls_through_safely(monkeypatch) -> None:
    monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
    monkeypatch.setitem(sys.modules, "ableton_bridge", None)
    assert _call("make the vocals warmer") is None
