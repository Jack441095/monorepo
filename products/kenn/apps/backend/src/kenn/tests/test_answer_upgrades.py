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


def test_a_rejected_upgrade_says_why_it_was_rejected(monkeypatch) -> None:
    # 4 Oct 2026: 34 rejected probe rows carried no reason, so nobody could say which check was failing them.
    from kenn.core import chat_answer, route_log

    monkeypatch.setattr(route_log, "record", lambda *a, **k: None)

    def write():
        chat_answer._log_generation_outcome(
            False, {"warnings": ["generated answer introduced unsupported measurements"]}, 1.0)
        return {"llm_enhanced": False, "answer": "template"}

    result = _wait(answer_upgrades.start(write))
    assert result["status"] == "rejected"
    assert result["reason"] == "generated answer introduced unsupported measurements"


def test_a_weak_match_says_the_model_was_not_asked_and_forgets_the_last_answer(monkeypatch) -> None:
    # Review 5 Oct 2026: this early return set no reason, so an older answer's reason on the thread could stand in.
    from kenn.core import chat_answer, route_log

    monkeypatch.setattr(route_log, "record", lambda *a, **k: None)
    monkeypatch.setattr(chat_answer, "build_template_answer", lambda *a, **k: "template")
    monkeypatch.setattr(chat_answer, "results_are_weak", lambda *a: True)
    chat_answer._log_generation_outcome(False, {"warnings": ["an earlier answer's reason"]}, 1.0)

    assert chat_answer.make_answer("what is a pad", []) == ("template", False)
    assert chat_answer.last_generation_outcome() == "model not asked: weak results or intent guard"


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


def test_every_attempt_leaves_a_timing_row_with_no_text(tmp_path, monkeypatch) -> None:
    import json

    from kenn.core import route_log

    monkeypatch.setattr(route_log, "LOG", tmp_path / "routes.jsonl")
    _wait(answer_upgrades.start(lambda: {"llm_enhanced": True, "answer": "secret question answer"}))
    _wait(answer_upgrades.start(lambda: {"llm_enhanced": False, "answer": "template"}))

    def broken():
        raise TimeoutError("ollama")

    _wait(answer_upgrades.start(broken))
    time.sleep(0.05)
    rows = [json.loads(line) for line in (tmp_path / "routes.jsonl").read_text().splitlines()]
    assert sorted(row["route"] for row in rows) == ["answer_upgrade:accepted", "answer_upgrade:error", "answer_upgrade:rejected"]
    assert all(set(row) == {"at", "route", "ms", "brain", "proposal"} for row in rows)
    assert "secret" not in (tmp_path / "routes.jsonl").read_text()


def test_the_landing_rate_and_time_are_read_from_the_log(tmp_path) -> None:
    from kenn.core import route_log

    log = tmp_path / "routes.jsonl"
    for outcome, seconds in [("accepted", 9.0), ("accepted", 14.0), ("accepted", 11.0), ("rejected", 12.0), ("busy", 0.0), ("error", 3.0)]:
        route_log.record(f"answer_upgrade:{outcome}", seconds * 1000, brain=outcome == "accepted", proposal=False, path=log)
    route_log.record("production", 25.0, brain=False, proposal=False, path=log)
    report = route_log.upgrade_summary(log)
    assert report == {"attempts": 6, "accepted": 3, "abstained": 0, "rejected": 1, "error": 1, "busy": 1, "expired": 0, "accepted_rate": 0.5,
                      "accepted_p50_s": 11.0, "accepted_p95_s": 11.0}
    assert route_log.upgrade_summary(tmp_path / "none.jsonl")["accepted_rate"] is None
