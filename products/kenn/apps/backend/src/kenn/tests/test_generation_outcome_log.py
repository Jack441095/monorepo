"""A rejected generated answer must record why it was rejected.

Track D's standing question is "how often does the model's answer land, and when it doesn't, why". Measured 1 Oct
2026 on the owner's M3, 26 of 30 background swaps were rejected and nothing said why: `make_answer` printed
`(fallback)` with a timing and dropped `validation["warnings"]` on the floor. Establishing that the dominant
rejection was `unsupported measurements` meant reading that dict out of a monkeypatched harness, which is not
something the monthly measure can be built on.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kenn.core import chat_answer, route_log
from kenn.llm import llm_rewrite


@pytest.fixture(autouse=True)
def _no_earlier_model_calls(monkeypatch):
    # The log adds the last call's timing; these tests are about the reason, so start from no calls on record.
    monkeypatch.setattr(llm_rewrite, "_global_usage", [])


def _read(log: Path) -> list[dict]:
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_a_rejected_answer_records_the_reason_it_was_rejected(tmp_path, monkeypatch):
    """The warning text belongs in the log: without it, a 0% landing rate has no diagnosis attached."""
    log = tmp_path / "routes.jsonl"
    monkeypatch.setattr(route_log, "LOG", log)

    chat_answer._log_generation_outcome(
        False, {"warnings": ["generated answer introduced unsupported measurements"]}, 61.2)

    (row,) = _read(log)
    assert row["route"] == "generation:generated answer introduced unsupported measurements"
    assert row["ms"] == 61200.0
    assert row["brain"] is False


def test_an_accepted_answer_is_recorded_as_brain_work(tmp_path, monkeypatch):
    """`brain=True` is what makes these rows countable as "the model wrote this" in the route report."""
    log = tmp_path / "routes.jsonl"
    monkeypatch.setattr(route_log, "LOG", log)

    chat_answer._log_generation_outcome(True, {"warnings": []}, 74.0)

    (row,) = _read(log)
    assert row["route"] == "generation:accepted"
    assert row["brain"] is True


def test_a_model_that_wrote_nothing_is_distinct_from_an_answer_that_was_rejected(tmp_path, monkeypatch):
    """Timeout, unavailable model, and a structure-check failure are not the same as a grounding rejection.

    Averaging them into one "the swap failed" number hides which one is happening -- and on this hardware the
    timeout was a real defect that looked exactly like a quality problem until it was separated out.
    """
    log = tmp_path / "routes.jsonl"
    monkeypatch.setattr(route_log, "LOG", log)

    chat_answer._log_generation_outcome(False, {"warnings": ["generation returned no answer"]}, 20.0)

    (row,) = _read(log)
    assert row["route"] == "generation:generation returned no answer"


def test_the_log_records_no_question_or_answer_text(tmp_path, monkeypatch):
    """route_log's rule is that it holds timings and outcomes, never the producer's words.

    The warning strings are KENN's own fixed vocabulary, so putting one in a route name is safe; a model answer or
    a question would not be.
    """
    log = tmp_path / "routes.jsonl"
    monkeypatch.setattr(route_log, "LOG", log)

    chat_answer._log_generation_outcome(
        False, {"warnings": ["generated answer introduced unsupported measurements"]}, 1.0)

    body = log.read_text(encoding="utf-8")
    assert "mix bus" not in body and "sidechain" not in body


def test_logging_failure_does_not_cost_the_producer_an_answer(tmp_path, monkeypatch):
    """A broken log must not be able to break the answer path -- that is the whole point of the template fallback."""
    monkeypatch.setattr(route_log, "LOG", tmp_path / "does-not-exist-dir" / "deep" / "routes.jsonl")
    monkeypatch.setattr(
        route_log, "record",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("the disk is full")),
    )
    chat_answer._log_generation_outcome(False, {"warnings": ["anything"]}, 1.0)


def test_a_rejection_records_which_measurement_the_notes_never_gave(tmp_path, monkeypatch):
    """A reason alone cannot be acted on: "unsupported measurements" does not say which one.

    The 1 Oct rejections were counted but never attributable, because the harness logs the route and its
    metadata but not what tripped the gate. Recording the extracted value is what lets a landing rate be
    diagnosed, and the values come from the grounding regexes, so they cannot carry the answer's prose.
    """
    log = tmp_path / "routes.jsonl"
    monkeypatch.setattr(route_log, "LOG", log)

    chat_answer._log_generation_outcome(
        False,
        {
            "warnings": ["generated answer introduced unsupported measurements"],
            "unsupported_measurements": ["500 hz"],
            "fabricated_sources": ["invented-reverb-guide.md"],
        },
        61.2,
    )

    (row,) = _read(log)
    assert row["detail"] == ["unsupported measurement: 500 hz", "fabricated source: invented-reverb-guide.md"]


def test_the_measurement_does_not_go_in_the_route_name(tmp_path, monkeypatch):
    """Routes are truncated at 64 chars and the report groups by them, so a measurement there would
    split one rejection reason across as many routes as there are measurements."""
    log = tmp_path / "routes.jsonl"
    monkeypatch.setattr(route_log, "LOG", log)

    for measurement in ("500 hz", "-18 dbfs", "12%"):
        chat_answer._log_generation_outcome(
            False,
            {
                "warnings": ["generated answer introduced unsupported measurements"],
                "unsupported_measurements": [measurement],
            },
            1.0,
        )

    rows = _read(log)
    assert {row["route"] for row in rows} == {"generation:generated answer introduced unsupported measurements"}
    report = route_log.summary(log)
    rejected = {r: v["requests"] for r, v in report.items() if not r.endswith(":accepted")}
    assert rejected == {"generation:generated answer introduced unsupported measurements": 3}


def test_an_accepted_answer_records_no_detail(tmp_path, monkeypatch):
    """Nothing to attribute when the answer landed, so the field is absent rather than an empty list."""
    log = tmp_path / "routes.jsonl"
    monkeypatch.setattr(route_log, "LOG", log)

    chat_answer._log_generation_outcome(True, {"warnings": [], "unsupported_measurements": []}, 74.0)

    (row,) = _read(log)
    assert "detail" not in row


def test_the_route_report_groups_rejections_without_re_deriving_them(tmp_path):
    """route_latency_report.py must count the rows chat_answer already wrote, not recompute anything."""
    log = tmp_path / "routes.jsonl"
    log.write_text("".join(json.dumps(r) + "\n" for r in [
        {"at": 1.0, "route": "generation:generated answer introduced unsupported measurements", "ms": 61_200.0,
         "brain": False, "proposal": False},
        {"at": 2.0, "route": "generation:generated answer introduced unsupported measurements", "ms": 55_000.0,
         "brain": False, "proposal": False},
        {"at": 3.0, "route": "generation:accepted", "ms": 74_000.0, "brain": True, "proposal": False},
    ]), encoding="utf-8")

    report = route_log.summary(log)
    dropped = {r.split(":", 1)[1]: row["requests"] for r, row in report.items()
               if r.startswith("generation:") and not r.endswith(":accepted")}
    assert dropped == {"generated answer introduced unsupported measurements": 2}


def test_the_longest_rejection_route_name_survives_the_logs_64_char_field():
    """route_log truncates route names to 64 characters. Two reasons sharing a prefix must not collapse into one."""
    reasons = [
        "generated answer introduced unsupported measurements",
        "generated answer is below the quality threshold",
        "generated answer has insufficient evidence overlap",
        "generation returned no answer: request failed",
        "generation returned no answer: structure check",
    ]
    routes = [f"generation:{r}" for r in reasons]
    assert max(len(r) for r in routes) <= 64, routes
    assert len({r[:64] for r in routes}) == len(routes), "two rejection reasons truncate to the same route"


def test_a_model_answer_the_quality_gate_swaps_out_is_not_credited_to_the_model(tmp_path, monkeypatch):
    # Audit, 5 Oct 2026: llm_enhanced stayed True after the swap, so the upgrade offered the clarifying reply
    # as the model's answer.
    from kenn.core import chat_retrieval, session_memory
    from kenn.tests.test_streamed_generation_prefix_guard import CHUNKS, QUERY

    monkeypatch.setattr(session_memory, "DB_PATH", tmp_path / "memory.db")
    monkeypatch.setattr(route_log, "record", lambda *a, **k: None)
    monkeypatch.setattr(chat_answer, "_critique_and_save_trace", lambda **kwargs: None)
    terms = {"total_docs": 0, "avg_len": 1.0, "lengths": [], "idf": {}, "postings": {}}
    for module in (chat_retrieval, chat_answer):
        monkeypatch.setattr(module, "load_chunks", lambda: [c for _, c in CHUNKS])
        monkeypatch.setattr(module, "load_terms", lambda: terms)
        monkeypatch.setattr(module, "search", lambda *args, **kwargs: list(CHUNKS))
    monkeypatch.setattr(chat_answer, "results_are_weak", lambda *a: False)
    monkeypatch.setattr(chat_answer, "intent_guard_failed", lambda *a: False)

    def model_answered(*args, **kwargs):
        chat_answer._log_generation_outcome(True, {"warnings": []}, 1.0)
        return "Short answer: a model answer the gate will not like.", True

    monkeypatch.setattr(chat_answer, "make_answer", model_answered)
    monkeypatch.setattr(chat_answer, "answer_quality_report", lambda *a, **k: {"score": 0, "warnings": []})

    payload = chat_answer.answer_payload(QUERY, session_id="gate", record_session=False)

    assert payload["weak_match"] is True
    assert payload["llm_enhanced"] is False
    assert chat_answer.last_generation_outcome() == "quality gate: answer quality below threshold"
    # The text the producer never saw is kept for a bench to read, with no figures because the grounding gate passed it.
    assert chat_answer.last_rejected_generation() == {
        "answer": "Short answer: a model answer the gate will not like.", "refused_figures": []}


def _payload_with_model_answer(tmp_path, monkeypatch, score: int) -> list[tuple[str, bool]]:
    """answer_payload() with a model answer the quality check scores as given; returns the (route, brain) rows logged."""
    from kenn.core import chat_retrieval, session_memory
    from kenn.tests.test_streamed_generation_prefix_guard import CHUNKS, QUERY

    rows: list[tuple[str, bool]] = []
    monkeypatch.setattr(session_memory, "DB_PATH", tmp_path / "memory.db")
    monkeypatch.setattr(route_log, "record", lambda route, ms, **k: rows.append((route, bool(k.get("brain")))))
    monkeypatch.setattr(chat_answer, "_critique_and_save_trace", lambda **kwargs: None)
    terms = {"total_docs": 0, "avg_len": 1.0, "lengths": [], "idf": {}, "postings": {}}
    for module in (chat_retrieval, chat_answer):
        monkeypatch.setattr(module, "load_chunks", lambda: [c for _, c in CHUNKS])
        monkeypatch.setattr(module, "load_terms", lambda: terms)
        monkeypatch.setattr(module, "search", lambda *args, **kwargs: list(CHUNKS))
    monkeypatch.setattr(chat_answer, "results_are_weak", lambda *a: False)
    monkeypatch.setattr(chat_answer, "intent_guard_failed", lambda *a: False)

    def model_answered(*args, **kwargs):
        chat_answer._log_generation_outcome(True, {"warnings": []}, 1.0)
        return "Short answer: a model answer.", True

    monkeypatch.setattr(chat_answer, "make_answer", model_answered)
    monkeypatch.setattr(chat_answer, "answer_quality_report", lambda *a, **k: {"score": score, "warnings": []})
    chat_answer.answer_payload(QUERY, session_id="gate-rows", record_session=False)
    return [row for row in rows if row[0].startswith("generation:")]


def test_a_swapped_out_model_answer_leaves_no_brain_row_in_the_route_log(tmp_path, monkeypatch):
    # 25c31773 (5 Oct 2026) made llm_enhanced and the outcome truthful after the quality gate's swap, but
    # make_answer had already logged "generation:accepted" with brain=True, so the route report still counted the
    # template as the model's work.
    rows = _payload_with_model_answer(tmp_path, monkeypatch, score=0)

    assert rows == [("generation:quality gate: answer quality below threshold", False)]


def test_a_model_answer_the_quality_gate_keeps_is_still_logged_as_brain_work(tmp_path, monkeypatch):
    rows = _payload_with_model_answer(tmp_path, monkeypatch, score=100)

    assert rows == [("generation:accepted", True)]


def _enhance_with(monkeypatch, completion):
    monkeypatch.setattr(llm_rewrite, "is_enabled", lambda *a: True)
    monkeypatch.setattr(llm_rewrite, "_chat_completion", completion)
    return llm_rewrite.enhance(
        "how do I tame a harsh vocal", "Short answer: template.", [], None, "",
        lambda chunk: chunk.get("title", ""), lambda _history: [], answer_mode="quick_fix",
    )


def test_a_request_that_failed_is_told_apart_from_an_answer_that_failed_the_structure_check(monkeypatch):
    """5 Oct probe: three rows said only "generation returned no answer", so truncation couldn't be confirmed."""
    def times_out(*a, **k):
        raise RuntimeError("ollama read timed out")

    assert _enhance_with(monkeypatch, times_out) is None
    assert llm_rewrite.last_enhance_failure() == "request failed"

    # Cut off by the token cap before it reached a Try this step.
    assert _enhance_with(monkeypatch, lambda *a, **k: ("Short answer: pull 3 dB out around", None)) is None
    assert llm_rewrite.last_enhance_failure() == "structure check"


def test_make_answer_names_why_the_model_wrote_nothing(tmp_path, monkeypatch):
    log = tmp_path / "routes.jsonl"
    monkeypatch.setattr(route_log, "LOG", log)
    monkeypatch.setattr(chat_answer, "build_template_answer", lambda *a, **k: "template")
    monkeypatch.setattr(chat_answer, "results_are_weak", lambda *a: False)
    monkeypatch.setattr(chat_answer, "intent_guard_failed", lambda *a: False)
    monkeypatch.setattr(chat_answer, "should_use_llm_rewrite", lambda *a, **k: True)

    def cut_off(*a, **k):
        # monkeypatch, so the reason doesn't stay set on the pytest thread for the next make_answer test.
        monkeypatch.setattr(llm_rewrite._enhance_failure, "reason", "structure check", raising=False)
        return None

    monkeypatch.setattr(chat_answer, "llm_enhance_answer", cut_off)

    assert chat_answer.make_answer("how do I tame a harsh vocal", [(1.0, {"text": "x"})]) == ("template", False)
    assert chat_answer.last_generation_outcome() == "generation returned no answer: structure check"
    (row,) = _read(log)
    assert row["route"] == "generation:generation returned no answer: structure check"
