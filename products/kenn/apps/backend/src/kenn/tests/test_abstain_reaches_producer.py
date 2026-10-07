"""An honest "Insufficient context" reply has to reach the producer instead of being swapped for the template.

5 Oct 2026 replay against the 4B: when retrieval ranked the wrong notes, the model wrote "Insufficient context: the
excerpts do not address ..." and cited what it was shown. That line has no "Short answer:" section, so the
structure check in enhance() threw it away and the template went out, answering a question the notes never covered.
The grounding gate already accepts a named-gap abstain; these tests pin the rest of the path (structure check,
quality gate, upgrade, probe, held-out runner) so the decline arrives, is marked as a decline, and is never
counted as a model answer.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from scripts import probe_advanced_questions as probe

from kenn.core import answer_upgrades, chat_answer, chat_retrieval, route_log, session_memory
from kenn.core.chat_grounding import generated_answer_validation
from kenn.llm import llm_rewrite as llm
from kenn.tests.test_streamed_generation_prefix_guard import (
    ACCEPTED_ANSWER,
    CHUNKS,
    QUERY,
    _stream,
    _text_and_metadata,
)

GAP = "the excerpts do not address how a linear-phase EQ differs from a minimum-phase one."
ABSTAIN = f"Insufficient context: {GAP}"


def _validate(reply: str) -> dict:
    return generated_answer_validation(QUERY, list(CHUNKS), reply, route="production", confidence="high",
                                       answer_mode="mix_diagnosis")


def _model_writes(monkeypatch, text: str) -> None:
    """Run the real enhance() and its structure check, with only the model's reply faked."""
    monkeypatch.setattr(llm, "is_enabled", lambda *a, **k: True)
    monkeypatch.setattr(llm, "_build_synthesis_messages", lambda *a, **k: ([{"role": "user", "content": "q"}], []))
    monkeypatch.setattr(llm, "_chat_completion", lambda *a, **k: (text, None))
    monkeypatch.setattr(chat_answer, "llm_enhance_answer", llm.enhance)
    monkeypatch.setattr(chat_answer, "should_use_llm_rewrite", lambda *a, **k: True)
    monkeypatch.setattr(chat_answer, "results_are_weak", lambda *a: False)
    monkeypatch.setattr(chat_answer, "intent_guard_failed", lambda *a: False)


def _ask_for_payload(monkeypatch, tmp_path) -> dict:
    """answer_payload() over fixture retrieval, with nothing written to the repo's data dir."""
    monkeypatch.setattr(session_memory, "DB_PATH", tmp_path / "memory.db")
    monkeypatch.setattr(route_log, "record", lambda *a, **k: None)
    monkeypatch.setattr(chat_answer, "_critique_and_save_trace", lambda **kwargs: None)
    terms = {"total_docs": 0, "avg_len": 1.0, "lengths": [], "idf": {}, "postings": {}}
    for module in (chat_retrieval, chat_answer):
        monkeypatch.setattr(module, "load_chunks", lambda: [c for _, c in CHUNKS])
        monkeypatch.setattr(module, "load_terms", lambda: terms)
        monkeypatch.setattr(module, "search", lambda *args, **kwargs: list(CHUNKS))
    return chat_answer.answer_payload(QUERY, session_id="abstain", record_session=False)


def test_the_structure_check_lets_a_named_gap_abstain_through() -> None:
    assert llm.valid_response(ABSTAIN) is True
    # An abstain with no gap named is the model acknowledging the rule without obeying it.
    assert llm.valid_response("Insufficient context:") is False
    # Unrelated prose with no sections still fails, so the bypass is not a general loosening.
    assert llm.valid_response("Use a linear-phase EQ on the master bus.") is False


def test_an_abstain_is_not_given_a_sources_list_it_did_not_use() -> None:
    shown = [(1.0, CHUNKS[0][1], "body")]
    assert llm._with_sources(ABSTAIN, shown, lambda chunk: "Sidechain Bass To Kick (sidechain-bass-to-kick.md)") == ABSTAIN


def test_a_declined_answer_reaches_the_producer_marked_as_a_decline(monkeypatch, tmp_path) -> None:
    _model_writes(monkeypatch, ABSTAIN)

    payload = _ask_for_payload(monkeypatch, tmp_path)

    assert payload["answer"] == ABSTAIN
    assert payload["answer_abstained"] is True
    assert payload["abstain_gap"] == GAP
    # Not a model answer: nothing counting llm_enhanced may credit a decline as one.
    assert payload["llm_enhanced"] is False
    assert payload["weak_match"] is False


def test_an_abstain_that_slips_in_a_number_is_still_dropped(monkeypatch, tmp_path) -> None:
    _model_writes(monkeypatch, f"Insufficient context: {GAP[:-1]}, but go for 45%.")

    payload = _ask_for_payload(monkeypatch, tmp_path)

    assert payload["answer_abstained"] is False
    assert "45%" not in payload["answer"]
    assert payload["llm_enhanced"] is False


def test_an_abstain_cannot_excuse_a_claimed_live_change(monkeypatch, tmp_path) -> None:
    _model_writes(monkeypatch, f"{ABSTAIN}\n\nI've already muted the hats.")

    payload = _ask_for_payload(monkeypatch, tmp_path)

    assert payload["answer_abstained"] is False
    assert "muted the hats" not in payload["answer"]


def test_an_ordinary_answer_is_not_marked_as_a_decline(monkeypatch, tmp_path) -> None:
    _model_writes(monkeypatch, ACCEPTED_ANSWER)

    payload = _ask_for_payload(monkeypatch, tmp_path)

    assert payload["answer_abstained"] is False
    assert payload["abstain_gap"] == ""


def _wait(upgrade_id: str) -> dict:
    for _ in range(300):
        result = answer_upgrades.get(upgrade_id)
        if result["status"] != "pending":
            return result
        time.sleep(0.01)
    raise AssertionError("still pending")


def test_the_upgrade_offers_a_decline_and_says_it_is_one(monkeypatch) -> None:
    logged = []
    monkeypatch.setattr(route_log, "record", lambda route, *a, **k: logged.append(route))

    result = _wait(answer_upgrades.start(
        lambda: {"llm_enhanced": False, "answer_abstained": True, "answer": ABSTAIN}))

    assert result["status"] == "accepted" and result["answer"] == ABSTAIN
    assert result["abstained"] is True
    # Its own outcome row, so the upgrade landing rate does not count a decline as the model answering.
    assert logged == ["answer_upgrade:abstained"]


def test_the_upgrade_landing_rate_leaves_declines_out_of_accepted(tmp_path) -> None:
    log = tmp_path / "routes.jsonl"
    for outcome in ("accepted", "abstained", "rejected"):
        route_log.record(f"answer_upgrade:{outcome}", 5000.0, brain=outcome == "accepted", proposal=False, path=log)

    summary = route_log.upgrade_summary(log)

    assert summary["accepted"] == 1 and summary["abstained"] == 1
    assert summary["attempts"] == 3
    assert summary["accepted_rate"] == 0.333


def _stub_with_upgrade(upgrade: dict):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, body):
            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self._send(upgrade)

        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            self._send({"answer": "Template.", "llm_available": True, "route": "knowledge",
                        "answer_upgrade": {"id": "abc", "poll_ms": 500}})

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_port}"


CASE = {"id": "eq-linear-vs-min-phase", "category": "eq", "expect": "answer", "question": "Linear or minimum phase?"}


def test_the_probe_reports_a_decline_apart_from_model_and_template_answers() -> None:
    httpd, url = _stub_with_upgrade({"status": "accepted", "answer": ABSTAIN, "abstained": True, "seconds": 3})
    try:
        row = probe.ask(url, "probe-1", CASE, wait=5)
    finally:
        httpd.shutdown()

    assert row["delivered_by"] == "abstain"
    assert row["abstained"] is True
    assert row["model_attempted"] is True
    assert row["rejection_reason"] == ""

    answered = {"category": "eq", "expect": "answer", "delivered_by": "model", "model_attempted": True,
                "concept_recall": None, "final_seconds": 3.0}
    row = {**row, "category": "eq", "concept_recall": None, "final_seconds": 3.0}
    overall = probe.summarise([row, answered], "http://x", probe.DEFAULT_CASES)["overall"]
    # The decline is not a correct answer: it stays out of the model's gate count and its acceptance rate.
    assert overall["delivered_by_model"] == 1
    assert overall["delivered_by_abstain"] == 1
    assert overall["delivered_by_template"] == 0
    assert overall["gate_model_within_15s"] == 1
    assert overall["model_accepted_when_attempted"] == "1 of 2"


def test_the_stream_marks_a_decline_and_does_not_credit_it_to_the_model(monkeypatch) -> None:
    def fake_stream(*args, **kwargs):
        for word in ABSTAIN.split(" "):
            yield {"event": "token", "token": word + " "}

    text, metadata = _text_and_metadata(list(_stream(monkeypatch, fake_stream)))

    assert text.strip().startswith(ABSTAIN)
    # No "Sources:" list pasted under a decline, and no medium-grounding caveat appended to it either.
    assert "Sources:" not in text
    assert metadata["generation_validation"]["abstained"] is True
    assert metadata["generation_validation"]["abstain_gap"] == GAP
    assert metadata["llm_enhanced"] is False


def _load_latency_tool():
    root = Path(__file__).resolve().parents[5]
    spec = importlib.util.spec_from_file_location("kenn_measure_chat_latency_abstain", root / "tooling/scripts/measure_chat_latency.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_held_out_runner_counts_a_decline_apart_from_accepted_and_rejected(monkeypatch) -> None:
    tool = _load_latency_tool()
    monkeypatch.setattr(tool, "_drop_semantic_cache", lambda: None)
    monkeypatch.setattr(tool, "_index_version", lambda: "test")
    replies = iter([
        {"generation_validation": {"attempted": True, "accepted": True, "warnings": []}, "llm_enhanced": True},
        {"generation_validation": {"attempted": True, "accepted": True, "warnings": [], "abstained": True,
                                   "abstain_gap": GAP}, "llm_enhanced": False},
        {"generation_validation": {"attempted": True, "accepted": False, "warnings": ["generation returned no answer"]},
         "llm_enhanced": False},
    ])
    monkeypatch.setattr(tool, "_ask", lambda *a, **k: (next(replies), 0, None))

    report = tool.measure([{"id": f"q{i}", "question": f"question {i}"} for i in range(3)])

    counts = report["counts"]
    assert counts["llm_attempted"] == 3
    assert counts["llm_accepted"] == 1
    assert counts["llm_abstained"] == 1
    assert counts["llm_rejected"] == 1
    assert [r["abstained"] for r in report["rows"]] == [False, True, False]
    assert "brain abstained    1" in tool.render(report)


def test_the_background_swap_measure_reports_a_decline_as_its_own_status() -> None:
    root = Path(__file__).resolve().parents[5]
    spec = importlib.util.spec_from_file_location("kenn_measure_background_swap_abstain",
                                                  root / "tooling/scripts/measure_background_swap.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    assert module.swap_status_of({"status": "accepted", "abstained": True}) == "abstained"
    assert module.swap_status_of({"status": "accepted"}) == "accepted"
    assert module.swap_status_of({"status": "rejected"}) == "rejected"


# 7 Oct 2026 adversary review: abstain was "any line starts with the prefix", so each of these replies, which
# still advises, cites or answers, was kept as a decline and skipped the quality gate, calibration and Sources.
NOT_A_DECLINE = {
    "answer_with_the_prefix_as_its_last_line": (
        "Short answer: Use a slow release.\n\nTry this:\n1. Set the release to 200 ms.\n2. Lower the ratio.\n\n"
        f"{ABSTAIN}"
    ),
    "advice_after_the_decline": f"{ABSTAIN}\n\nTry a slow release and a gentle ratio on the bus.",
    "invented_sources_after_the_decline": f"{ABSTAIN}\n\nSources:\n- Fake Note (fake-note.md)",
    "a_plugin_recommendation_after_the_decline": f"{ABSTAIN}\nTry Serum or FabFilter Pro-C.",
    "a_ratio_after_the_decline": f"{ABSTAIN}\nUse a ratio of four to one.",
    "lowercase_prefix": f"insufficient context: {GAP}",
    "no_gap_but_a_full_stop": "Insufficient context: .",
    "one_word_gap": "Insufficient context: more.",
    "two_word_gap": "Insufficient context: more detail.",
}


@pytest.mark.parametrize("reply", NOT_A_DECLINE.values(), ids=NOT_A_DECLINE.keys())
def test_only_a_whole_one_line_decline_counts_as_one(reply, monkeypatch, tmp_path) -> None:
    assert llm.is_abstain_reply(reply) is False
    assert _validate(reply)["abstained"] is False

    # Through the real producer path: it must not be kept as a marked decline, and the reply's own text must not
    # have skipped the checks the same text gets without the prefix.
    _model_writes(monkeypatch, reply)
    payload = _ask_for_payload(monkeypatch, tmp_path)
    assert payload["answer_abstained"] is False
    assert payload["abstain_gap"] == ""
    assert "fake-note.md" not in payload["answer"]


def test_a_decline_with_a_three_word_gap_is_a_decline() -> None:
    reply = "Insufficient context: the notes never cover phase."

    assert llm.is_abstain_reply(reply) is True
    assert _validate(reply)["abstained"] is True
    # Surrounding blank space is not content.
    assert llm.is_abstain_reply(f"\n  {reply}\n") is True


# 7 Oct 2026 second review: advice on the same line as the prefix still read as a decline and skipped the gate,
# which hid the unasked-product, fabricated-source and overlap warnings it would otherwise have earned.
ADVICE_ON_THE_SAME_LINE = {
    "a_second_sentence_of_advice": (
        "Insufficient context: the notes do not cover release times. Try a slow release and a gentle ratio on "
        "the bass bus."),
    "so_try_a_plugin": (
        "Insufficient context: the notes do not cover bass compression, so try Serum or FabFilter Pro-C on the bass."),
    "so_use_a_ratio": (
        "Insufficient context: the notes do not cover release, so use four to one with a release of one fifty "
        "milliseconds."),
    "a_filename": "Insufficient context: see fake-note.md for release times on the bass bus.",
    "a_gap_that_runs_to_advice": (
        "Insufficient context: the notes do not say how the release should sit against the kick on a dense "
        "bass bus in a sparse arrangement with a long reverb tail while the sidechain is also pulling the "
        "whole mix down and the master is limiting."),
    "a_unit_word": "Insufficient context: the notes give no attack time in ms for this compressor.",
}


@pytest.mark.parametrize("reply", ADVICE_ON_THE_SAME_LINE.values(), ids=ADVICE_ON_THE_SAME_LINE.keys())
def test_advice_on_the_decline_line_makes_it_an_answer_not_a_decline(reply, monkeypatch, tmp_path) -> None:
    assert llm.is_abstain_reply(reply) is False
    assert _validate(reply)["abstained"] is False

    _model_writes(monkeypatch, reply)
    payload = _ask_for_payload(monkeypatch, tmp_path)
    assert payload["answer_abstained"] is False
    assert "fake-note.md" not in payload["answer"]


def test_the_real_5_oct_declines_still_count_as_declines() -> None:
    for reply in (
        "Insufficient context: the excerpts do not address linear-phase pre-ringing on transients",
        "Insufficient context: the excerpts do not address linear-phase pre-ringing on transients.",
        "Insufficient context: the excerpts do not address how a linear-phase EQ differs from a minimum-phase one.",
    ):
        assert llm.is_abstain_reply(reply) is True, reply
        assert _validate(reply)["abstained"] is True, reply


def test_a_decline_that_names_a_product_nobody_asked_about_is_still_rejected() -> None:
    # Only the overlap and structure warnings are irrelevant to a one-line decline. A product name the question never
    # mentioned is the model reaching for outside knowledge, which the decline is not allowed to excuse.
    result = _validate("Insufficient context: the notes do not say how Serum handles this.")

    assert "generated answer names a product that nobody mentioned" in result["warnings"]
    assert result["accepted"] is False


# 7 Oct 2026 third review: a figure tucked into the gap, or open-ended advice the denylist never names, still rode
# through as a decline. A decline has to name something missing and say no number at all.
NUMBER_IN_THE_GAP = {
    "a_digit": "Insufficient context: the notes do not cover release times for a bass bus compressor, though 150 would suit.",
    "a_spelled_figure": "Insufficient context: the notes do not cover release times for a bass bus, the sweet spot is one fifty.",
    "a_spelled_range": "Insufficient context: the notes do not cover release times for a bass bus, around four or five is typical.",
}
ADVICE_WITH_NO_ABSENCE_WORD = {
    "i_would_reach_for": "Insufficient context: the notes cover little here, so I'd reach for a slow release on the bass bus.",
    "maybe_a_plugin_type": "Insufficient context: the notes cover little here, maybe a multiband compressor on the bass bus.",
    "i_would_sidechain": "Insufficient context: the notes cover little here, I would sidechain the bass to the kick.",
    "generally_a_setting": "Insufficient context: the notes cover little here, generally a slower setting suits bass.",
}


@pytest.mark.parametrize("reply", [*NUMBER_IN_THE_GAP.values(), *ADVICE_WITH_NO_ABSENCE_WORD.values()],
                         ids=[*NUMBER_IN_THE_GAP, *ADVICE_WITH_NO_ABSENCE_WORD])
def test_a_figure_or_unflagged_advice_in_the_gap_is_not_a_decline(reply) -> None:
    assert llm.is_abstain_reply(reply) is False
    assert _validate(reply)["abstained"] is False


@pytest.mark.parametrize("reply", [
    "Insufficient context: the excerpts do not cover how to set sidechain in Live",
    "Insufficient context: nothing on attack and release in the notes",
    "Insufficient context: the notes do not mention how to use sidechain compression on a return track",
    "Insufficient context: the notes don't explain what a limiter ceiling is",
    "Insufficient context: the notes cover EQ Eight but not how to set up a send in Live",
])
def test_a_gap_that_names_what_is_missing_stays_a_decline(reply) -> None:
    assert llm.is_abstain_reply(reply) is True
    assert _validate(reply)["abstained"] is True
