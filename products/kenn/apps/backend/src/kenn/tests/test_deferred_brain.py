"""Chat sends the template at once and the model's rewrite arrives later, only if it passed validation."""

from __future__ import annotations

import threading
import time

import pytest

from kenn.core import chat_answer, deferred_brain, route_log


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(route_log, "LOG", tmp_path / "routes.jsonl")
    monkeypatch.setattr(deferred_brain, "_JOBS", {})


def wait_for(job_id: str, timeout: float = 3.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = deferred_brain.status(job_id)
        if state["status"] in {"ready", "rejected"}:
            return state
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} never finished: {deferred_brain.status(job_id)}")


def test_a_finished_rewrite_can_be_polled_by_its_job_id() -> None:
    job = deferred_brain.submit(lambda: "the model's answer")
    state = wait_for(job)
    assert state["status"] == "ready" and state["answer"] == "the model's answer"


def test_a_rewrite_that_failed_validation_is_rejected_and_carries_no_text() -> None:
    state = wait_for(deferred_brain.submit(lambda: None))
    assert state == {"status": "rejected", "ms": state["ms"]}


def test_a_rewrite_that_blows_up_leaves_the_template_standing() -> None:
    def boom() -> str:
        raise RuntimeError("ollama went away")

    assert wait_for(deferred_brain.submit(boom))["status"] == "rejected"


def test_an_unknown_job_says_so() -> None:
    assert deferred_brain.status("nope") == {"status": "unknown"}


def test_a_third_rewrite_is_not_queued_behind_two_slow_ones() -> None:
    release = threading.Event()
    first = deferred_brain.submit(lambda: release.wait(3) and "a")
    second = deferred_brain.submit(lambda: "b")
    assert first and second
    assert deferred_brain.submit(lambda: "c") is None
    release.set()
    wait_for(first), wait_for(second)


def test_each_rewrite_is_timed_in_the_route_log() -> None:
    wait_for(deferred_brain.submit(lambda: "x"))
    time.sleep(0.05)
    assert route_log.summary()["brain_deferred"]["brain"] == 1


def test_defer_does_nothing_unless_the_server_asked_for_it() -> None:
    assert deferred_brain.defer(lambda: "x") is False


def test_the_server_gets_back_the_step_make_answer_deferred() -> None:
    token = deferred_brain.begin()
    deferred_brain.defer(lambda: "later")
    step = deferred_brain.end(token)
    assert step() == "later"
    assert deferred_brain.defer(lambda: "x") is False


def stub_the_answer_path(monkeypatch, rewrite):
    monkeypatch.setattr(chat_answer, "build_template_answer", lambda *a, **k: "template answer")
    monkeypatch.setattr(chat_answer, "results_are_weak", lambda *a, **k: False)
    monkeypatch.setattr(chat_answer, "intent_guard_failed", lambda *a, **k: False)
    monkeypatch.setattr(chat_answer, "_uncovered_hardware_caveat", lambda *a, **k: False)
    monkeypatch.setattr(chat_answer, "confidence_level", lambda *a, **k: "high")
    monkeypatch.setattr(chat_answer, "grounding_report", lambda *a, **k: {})
    monkeypatch.setattr(chat_answer, "answer_quality_report", lambda *a, **k: {"score": 90})
    monkeypatch.setattr(chat_answer, "should_use_llm_rewrite", lambda *a, **k: True)
    monkeypatch.setattr(chat_answer, "llm_enabled", lambda: True)
    monkeypatch.setattr(chat_answer, "llm_enhance_answer", rewrite)
    monkeypatch.setattr(chat_answer, "generated_answer_validation", lambda *a, **k: {"accepted": True})
    monkeypatch.setattr(chat_answer, "_skill_level_for_session", lambda *a, **k: "")


def test_make_answer_returns_the_template_and_hands_back_the_model_step(monkeypatch) -> None:
    calls = []
    stub_the_answer_path(monkeypatch, lambda *a, **k: calls.append(1) or "model answer")
    token = deferred_brain.begin()
    answer, used = chat_answer.make_answer("how do I sidechain", [(5.0, {"text": "x"})])
    step = deferred_brain.end(token)
    assert (answer, used) == ("template answer", False)
    assert calls == [] and step is not None
    assert step() == "model answer" and calls == [1]


def test_make_answer_still_runs_the_model_inline_when_nothing_defers_it(monkeypatch) -> None:
    stub_the_answer_path(monkeypatch, lambda *a, **k: "model answer")
    answer, used = chat_answer.make_answer("how do I sidechain", [(5.0, {"text": "x"})])
    assert used is True and answer.startswith("model answer")


def test_a_deferred_rewrite_that_fails_the_grounding_check_never_reaches_the_page(monkeypatch) -> None:
    stub_the_answer_path(monkeypatch, lambda *a, **k: "I've turned the bass down")
    monkeypatch.setattr(chat_answer, "generated_answer_validation", lambda *a, **k: {"accepted": False})
    token = deferred_brain.begin()
    chat_answer.make_answer("how do I sidechain", [(5.0, {"text": "x"})])
    step = deferred_brain.end(token)
    assert wait_for(deferred_brain.submit(step))["status"] == "rejected"


def test_the_brain_route_reports_a_job_by_id() -> None:
    import json
    import threading
    import urllib.request

    import kenn.server as server_module

    job = deferred_brain.submit(lambda: "model answer")
    wait_for(job)
    httpd = server_module.ThreadingHTTPServer(("127.0.0.1", 0), server_module.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{httpd.server_address[1]}/kenn/api/ask/brain"
        with urllib.request.urlopen(f"{base}?job_id={job}", timeout=5) as reply:
            assert json.load(reply)["answer"] == "model answer"
        with urllib.request.urlopen(f"{base}?job_id=missing", timeout=5) as reply:
            assert json.load(reply) == {"status": "unknown"}
    finally:
        httpd.shutdown()
        httpd.server_close()
