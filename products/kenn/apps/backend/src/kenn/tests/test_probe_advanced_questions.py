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
                self._send({"status": upgrade_status, "answer": "Model text about attack and release.", "seconds": 4})

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
