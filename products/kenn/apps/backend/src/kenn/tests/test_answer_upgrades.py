"""Template now, the model's answer when it's ready: only an answer KENN's gate accepted is offered."""

from __future__ import annotations

import threading
import time

from kenn.core import answer_upgrades


def _wait(upgrade_id: str) -> dict:
    for _ in range(200):
        result = answer_upgrades.get(upgrade_id)
        if result["status"] != "pending":
            return result
        time.sleep(0.01)
    raise AssertionError("still pending")


def test_an_accepted_model_answer_is_offered() -> None:
    upgrade_id = answer_upgrades.start(lambda: {"llm_enhanced": True, "answer": "Model answer.\n\nSources:\n- a.md"})
    result = _wait(upgrade_id)
    assert result["status"] == "accepted" and result["answer"].startswith("Model answer")


def test_a_rejected_answer_leaves_the_template_standing() -> None:
    # KENN fell back to its template: nothing to swap in, and the rejected text is never sent.
    result = _wait(answer_upgrades.start(lambda: {"llm_enhanced": False, "answer": "template"}))
    assert result["status"] == "rejected" and result["answer"] == ""


def test_a_model_failure_is_a_rejection_not_a_crash() -> None:
    def broken():
        raise TimeoutError("ollama")

    assert _wait(answer_upgrades.start(broken))["status"] == "rejected"


def test_only_one_model_answer_is_written_at_a_time() -> None:
    release = threading.Event()
    first = answer_upgrades.start(lambda: (release.wait(2), {"llm_enhanced": False})[1])
    assert first and answer_upgrades.start(lambda: {"llm_enhanced": True}) is None
    release.set()
    _wait(first)
    assert answer_upgrades.start(lambda: {"llm_enhanced": False}) is not None


def test_an_unknown_id_has_expired() -> None:
    assert answer_upgrades.get("nope") == {"status": "expired"}
