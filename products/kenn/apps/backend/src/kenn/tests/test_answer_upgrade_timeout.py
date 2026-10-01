"""The background answer upgrade must be allowed to outlast the interactive LLM timeout.

Found 1 Oct 2026 measuring Track D1 on the owner's M3: `answer_upgrades` accepted 0 of 30, while the streaming
path accepted 7 of 30 on the same questions. The background thread was calling `enhance()` under the ask path's
20 s HTTP timeout, and an answer on that hardware takes about 60 s, so every one of them timed out and returned
None -- the swap offered back the same template the producer was already looking at.

These tests pin the two halves of that: the ask path still fails fast, and the background thread does not.
"""

from __future__ import annotations

import threading

import pytest

from kenn.llm import llm_rewrite


def test_the_ask_path_still_times_out_at_the_interactive_budget(monkeypatch):
    """A producer watching a spinner must fall back to the template in ~20 s, not two minutes.

    This is the behaviour the 2026-08-10 comment on the 20 s default was written for. Raising it globally to
    unblock the background path would put a 120 s wait back in front of someone who already has an answer.
    """
    monkeypatch.delenv("KENN_LLM_TIMEOUT", raising=False)
    monkeypatch.delenv("KENN_LLM_TIMEOUT_REWRITE", raising=False)
    monkeypatch.setenv("AUDIO_TOO_LLM_TIMEOUT", "20")
    assert llm_rewrite.config("rewrite")["timeout"] == 20


def test_the_background_upgrade_gets_its_own_longer_budget(monkeypatch):
    """The whole point of the fix: 120 s in the background thread, 20 s on the ask path."""
    monkeypatch.delenv("KENN_LLM_TIMEOUT", raising=False)
    monkeypatch.delenv("KENN_LLM_TIMEOUT_REWRITE", raising=False)
    monkeypatch.setenv("AUDIO_TOO_LLM_TIMEOUT", "20")

    with llm_rewrite.background_budget():
        assert llm_rewrite.config("rewrite")["timeout"] == 120
    assert llm_rewrite.config("rewrite")["timeout"] == 20, "budget must not leak back onto the ask path"


def test_the_background_budget_is_configurable_and_honours_an_explicit_value(monkeypatch):
    """A slower machine, or a larger model, needs a different ceiling without a code change."""
    monkeypatch.setenv("KENN_LLM_BACKGROUND_TIMEOUT", "240")
    with llm_rewrite.background_budget():
        assert llm_rewrite.config("rewrite")["timeout"] == 240
    with llm_rewrite.background_budget(45):
        assert llm_rewrite.config("rewrite")["timeout"] == 45


def test_the_budget_is_per_thread_so_a_slow_upgrade_cannot_stall_the_next_question(monkeypatch):
    """answer_upgrades runs on its own thread while the producer's next question is answered on the request thread.

    A module-level global would hand the 120 s budget to the ask path as well, which is the exact regression the
    ContextVar exists to prevent.
    """
    monkeypatch.setenv("AUDIO_TOO_LLM_TIMEOUT", "20")
    seen: dict[str, int] = {}

    def background() -> None:
        with llm_rewrite.background_budget():
            seen["background"] = llm_rewrite.config("rewrite")["timeout"]
            threading.Event().wait(0.05)

    def ask_path() -> None:
        threading.Event().wait(0.01)  # let the background thread enter its block first
        seen["ask"] = llm_rewrite.config("rewrite")["timeout"]

    threads = [threading.Thread(target=background), threading.Thread(target=ask_path)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert seen == {"background": 120, "ask": 20}


def test_an_exception_inside_the_budget_still_restores_the_ask_path_budget(monkeypatch):
    """The context manager has a finally; a model failure must not leave the long budget armed."""
    monkeypatch.setenv("AUDIO_TOO_LLM_TIMEOUT", "20")

    with pytest.raises(RuntimeError):
        with llm_rewrite.background_budget():
            raise RuntimeError("the model was unreachable")

    assert llm_rewrite.config("rewrite")["timeout"] == 20


def test_a_per_task_timeout_overrides_the_global_but_not_the_background_budget(monkeypatch):
    """Per-task routing already worked for model and provider; timeout now follows the same suffix rule."""
    monkeypatch.delenv("KENN_LLM_TIMEOUT", raising=False)
    monkeypatch.setenv("AUDIO_TOO_LLM_TIMEOUT", "20")
    monkeypatch.setenv("KENN_LLM_TIMEOUT_PARAPHRASE", "8")
    assert llm_rewrite.config("paraphrase")["timeout"] == 8
    assert llm_rewrite.config("rewrite")["timeout"] == 20


def test_the_upgrade_thread_runs_its_write_under_the_background_budget(monkeypatch):
    """The fix only counts if `answer_upgrades.start` actually opens the budget, not just that the helper exists.

    This is the test that would have caught the original 0-of-30: it asserts on the timeout the write actually
    observes, which is the value that made every upgrade time out.
    """
    from kenn.core import answer_upgrades

    monkeypatch.setenv("AUDIO_TOO_LLM_TIMEOUT", "20")
    seen: dict[str, int] = {}

    def write() -> dict:
        seen["timeout"] = llm_rewrite.config("rewrite")["timeout"]
        return {"llm_enhanced": True, "answer": "Model answer.\n\nSources:\n- a.md"}

    upgrade_id = answer_upgrades.start(write)
    assert upgrade_id is not None
    for _ in range(200):
        if answer_upgrades.get(upgrade_id).get("status") in {"accepted", "rejected"}:
            break
        threading.Event().wait(0.05)

    assert seen.get("timeout") == 120, "the upgrade wrote under the ask path's 20 s budget"
    assert answer_upgrades.get(upgrade_id)["status"] == "accepted"
