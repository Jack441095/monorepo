"""The advanced-question probe must say who wrote each answer, and stop when the model never runs."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from scripts import probe_advanced_questions as tool


def _stub(model_on: bool, upgrade_status: str = "accepted"):
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
            if self.path.startswith("/api/health"):
                self._send({"ok": True})
            else:
                self._send({"status": upgrade_status, "answer": "Model text about attack and release.", "seconds": 4,
                            "reason": "generated answer introduced unsupported measurements"})

        def do_POST(self):
            question = json.loads(self.rfile.read(int(self.headers["Content-Length"])))["question"]
            body = {"answer": f"Template for {question}", "sources": [{"title": "note.md"}], "route": "knowledge"}
            if model_on:
                body.update(llm_available=True, answer_upgrade={"id": "abc", "poll_ms": 500})
            self._send(body)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_port}"


@pytest.fixture
def model_on():
    httpd, url = _stub(True)
    yield url
    httpd.shutdown()


@pytest.fixture
def model_off():
    httpd, url = _stub(False)
    yield url
    httpd.shutdown()


CASE = {"id": "dyn-attack-release", "category": "dynamics", "expect": "answer", "question": "How do I set attack?"}


def test_a_background_model_answer_replaces_the_template_and_is_credited_to_the_model(model_on):
    row = tool.ask(model_on, "probe-1", CASE, wait=5)
    assert row["delivered_by"] == "model"
    assert row["answer"].startswith("Model text")
    assert row["model_attempted"] is True
    assert row["final_seconds"] >= row["template_seconds"]


def test_a_rejected_model_answer_leaves_the_template_in_place():
    httpd, url = _stub(True, upgrade_status="rejected")
    try:
        row = tool.ask(url, "probe-1", CASE, wait=5)
    finally:
        httpd.shutdown()
    assert row["delivered_by"] == "template"
    assert row["model_attempted"] is True
    assert row["rejection_reason"] == "generated answer introduced unsupported measurements"
    summary = tool.summarise([{**row, "concept_recall": None}], "http://x", tool.DEFAULT_CASES)
    assert summary["overall"]["rejection_reasons"] == {"generated answer introduced unsupported measurements": 1}


def test_an_accepted_answer_has_no_rejection_reason(model_on):
    assert tool.ask(model_on, "probe-1", CASE, wait=5)["rejection_reason"] == ""


def test_with_the_model_off_the_answer_is_marked_as_the_template(model_off):
    row = tool.ask(model_off, "probe-1", CASE, wait=5)
    assert row["delivered_by"] == "template"
    assert row["model_attempted"] is False


def test_the_probe_stops_after_three_questions_when_the_model_never_runs(model_off, tmp_path, monkeypatch, capsys):
    cases = tmp_path / "cases.json"
    cases.write_text(json.dumps({"cases": [{**CASE, "id": f"c{i}"} for i in range(6)]}))
    monkeypatch.setattr("sys.argv", ["probe", "--endpoint", model_off, "--cases", str(cases),
                                     "--output", str(tmp_path / "out"), "--pause", "0"])
    assert tool.main() == 3
    assert capsys.readouterr().out.count("template") == 3


def test_allow_template_measures_the_template_path_on_purpose(model_off, tmp_path, monkeypatch):
    cases = tmp_path / "cases.json"
    cases.write_text(json.dumps({"cases": [{**CASE, "id": f"c{i}"} for i in range(4)]}))
    monkeypatch.setattr("sys.argv", ["probe", "--endpoint", model_off, "--cases", str(cases),
                                     "--output", str(tmp_path / "out"), "--pause", "0", "--allow-template"])
    assert tool.main() == 0
    summary = json.loads((tmp_path / "out.summary.json").read_text())
    assert summary["overall"]["delivered_by_template"] == 4
    assert "Template for" not in json.dumps(summary)


def test_the_same_answer_to_a_different_question_is_flagged():
    seen: dict[str, str] = {}
    first = {"id": "drums", "answer": "Parallel compression adds density."}
    second = {"id": "bass", "answer": "Parallel  compression adds density."}
    tool.judge(first, {"must_name": []}, seen)
    tool.judge(second, {"must_name": []}, seen)
    assert first["repeats_answer_of"] is None
    assert second["repeats_answer_of"] == "drums"


def test_expected_ideas_accept_alternatives():
    hit, missed = tool.concept_hits("Use a linear-phase EQ; watch for pre-ringing.",
                                    ["pre-ring|pre-echo", "latency", "linear"])
    assert hit == ["pre-ring|pre-echo", "linear"]
    assert missed == ["latency"]


def test_an_answer_that_names_a_plugin_the_user_never_mentioned_is_flagged():
    row = {"id": "lowend", "answer": "Cut the mud with FabFilter Pro-Q3, then add the Timeless reverb."}
    tool.judge(row, {"must_name": [], "must_not_name": ["fabfilter|pro-q", "waves"]}, {})
    assert row["forbidden_named"] == ["fabfilter|pro-q"]


ABSTAIN_CASE = {"id": "trap-offtopic", "category": "scope", "expect": "abstain_or_clarify", "must_name": ["dynamic eq"]}


def test_a_clarifying_template_reply_counts_as_handling_a_case_that_should_abstain():
    row = {"id": "trap-offtopic", "answer": "I don't have a solid note on that one.", "weak_match": True,
           "delivered_by": "template", "abstained": False}
    tool.judge(row, ABSTAIN_CASE, {})
    assert row["handled_as_expected"] is True
    assert row["concept_recall"] is None


def test_a_model_answer_over_a_clarifying_reply_is_not_credited_as_handling_it():
    row = {"id": "trap-offtopic", "answer": "A Fab Filter is a type of audio processing tool.", "weak_match": True,
           "delivered_by": "model", "abstained": False}
    tool.judge(row, ABSTAIN_CASE, {})
    assert row["handled_as_expected"] is False
    assert row["concept_recall"] == 0.0


def test_an_explicit_abstention_counts_as_handling_it():
    row = {"id": "x", "answer": "", "weak_match": False, "delivered_by": "model", "abstained": True}
    tool.judge(row, ABSTAIN_CASE, {})
    assert row["handled_as_expected"] is True


def test_ordinary_questions_are_not_scored_for_abstaining():
    row = {"id": "d", "answer": "Attack sets how fast it clamps.", "weak_match": True, "delivered_by": "template"}
    tool.judge(row, {"expect": "answer", "must_name": ["attack"]}, {})
    assert row["handled_as_expected"] is None
    assert row["concept_recall"] == 1.0


def test_the_summary_counts_expected_abstentions_and_leaves_them_out_of_recall():
    handled = {"category": "scope", "handled_as_expected": True, "concept_recall": None, "final_seconds": 1}
    missed = {"category": "scope", "handled_as_expected": False, "concept_recall": 0.5, "final_seconds": 1}
    plain = {"category": "dynamics", "handled_as_expected": None, "concept_recall": 1.0, "final_seconds": 1}
    summary = tool.summarise([handled, missed, plain], "http://x", tool.DEFAULT_CASES)
    assert summary["by_category"]["scope"]["expected_abstain_handled"] == "1 of 2"
    assert summary["overall"]["expected_abstain_handled"] == "1 of 2"
    assert "expected_abstain_handled" not in summary["by_category"]["dynamics"]


def test_a_real_rejection_travels_from_make_answer_to_the_probe_row(monkeypatch):
    # Review 5 Oct 2026: the reason tests stubbed every hop, so none showed the real check's words reaching the row.
    import time

    from kenn.core import answer_upgrades, chat_answer, route_log

    monkeypatch.setattr(route_log, "record", lambda *a, **k: None)
    monkeypatch.setattr(chat_answer, "build_template_answer", lambda *a, **k: "template")
    monkeypatch.setattr(chat_answer, "results_are_weak", lambda *a: False)
    monkeypatch.setattr(chat_answer, "intent_guard_failed", lambda *a: False)
    monkeypatch.setattr(chat_answer, "should_use_llm_rewrite", lambda *a, **k: True)
    monkeypatch.setattr(chat_answer, "llm_enhance_answer", lambda *a, **k: (
        "Short answer: cut 7 dB at 315 Hz on the bass.\n\nTry this:\n1. Cut 7 dB at 315 Hz.\n"
        "2. Compare it in mono.\n\nCheck: the kick should sit clearer."))
    results = [(1.0, {"text": "Cut the mud on the bass and check it in mono.", "source": "bass.md", "title": "Bass"})]

    def write():
        answer, used = chat_answer.make_answer("how do I clean up a muddy bass", results)
        return {"llm_enhanced": used, "answer": answer}

    upgrade_id = answer_upgrades.start(write)
    for _ in range(300):
        upgrade = answer_upgrades.get(upgrade_id)
        if upgrade["status"] != "pending":
            break
        time.sleep(0.01)

    reason = tool.rejection_reason({}, upgrade, delivered_by_model=False)
    assert upgrade["status"] == "rejected"
    assert reason == "generated answer introduced unsupported measurements"


def test_a_broken_poll_and_an_upgrade_that_never_settled_are_counted():
    assert tool.rejection_reason({}, {"status": "error", "error": "URLError"}, False) == "probe poll failed: URLError"
    assert tool.rejection_reason({}, {"status": "pending"}, False) == "upgrade still pending when the wait ran out"


def test_an_inline_rejection_carries_its_reason_without_an_upgrade():
    payload = {"generation_outcome": "generated answer introduced unsupported measurements"}
    assert tool.rejection_reason(payload, {}, False) == "generated answer introduced unsupported measurements"
    payload = {"generation_validation": {"warnings": ["generation returned no answer"]}}
    assert tool.rejection_reason(payload, {}, False) == "generation returned no answer"
