"""Regression tests: enhance() and enhance_paraphrase_note() must degrade to
None on ANY _chat_completion() failure, never raise and crash the caller.

Found 2026-08-02 live-testing KENN with a misconfigured model name:
_chat_completion() wraps a persistent connection failure (after its own one
retry) and any non-timeout HTTP status error in a bare RuntimeError -- which
neither function's exception tuple caught (TimeoutError, ValueError,
httpx.HTTPError, httpx.TimeoutException -- no plain RuntimeError), so the
whole KENN answer crashed instead of falling back to the deterministic
template answer, exactly the failure mode this try/except exists to prevent.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT / "studio" / "kenn") not in sys.path:
    sys.path.insert(0, str(ROOT / "studio" / "kenn"))

from kenn.llm import llm_rewrite as lr  # noqa: E402


def _boom(*a, **k):
    raise RuntimeError("LLM returned 404: model 'gpt-4o-mini' not found")


def test_enhance_degrades_to_none_on_a_bare_runtime_error(monkeypatch):
    monkeypatch.setattr(lr, "is_enabled", lambda *a, **k: True)
    monkeypatch.setattr(lr, "_chat_completion", _boom)

    result = lr.enhance(
        query="how do I sidechain bass to the kick?",
        template_answer="",
        results=[],
        history=[],
        history_context="",
        source_label=lambda x: "Source",
        normalize_history=lambda x: [],
        answer_mode="quick_fix",
    )

    assert result is None


def test_enhance_paraphrase_note_degrades_to_none_on_a_bare_runtime_error(monkeypatch):
    monkeypatch.setattr(lr, "is_enabled", lambda *a, **k: True)
    monkeypatch.setattr(lr, "_chat_completion", _boom)

    result = lr.enhance_paraphrase_note(
        "draft note content",
        title="Test Note",
    )

    assert result is None


def test_enhance_still_degrades_to_none_on_a_timeout(monkeypatch):
    """Regression guard: the broadened except Exception must not lose the
    pre-existing timeout-handling behaviour."""
    def _timeout(*a, **k):
        raise TimeoutError("LLM timed out after 30s")

    monkeypatch.setattr(lr, "is_enabled", lambda *a, **k: True)
    monkeypatch.setattr(lr, "_chat_completion", _timeout)

    result = lr.enhance(
        query="how do I sidechain bass to the kick?",
        template_answer="",
        results=[],
        history=[],
        history_context="",
        source_label=lambda x: "Source",
        normalize_history=lambda x: [],
        answer_mode="quick_fix",
    )

    assert result is None
