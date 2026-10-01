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

from kenn.core import chat_answer, route_log


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
    ]
    routes = [f"generation:{r}" for r in reasons]
    assert max(len(r) for r in routes) <= 64, routes
    assert len({r[:64] for r in routes}) == len(routes), "two rejection reasons truncate to the same route"