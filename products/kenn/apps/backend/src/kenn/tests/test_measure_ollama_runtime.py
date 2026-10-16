"""C2 receipts name the Ollama runner and digest that actually served the run, and say so when they cannot.

Ollama 0.40 runs supported models on MLX by default and unsupported ones on llama.cpp, and a tag can
resolve to either, so a model name alone does not identify what was timed. These tests stand a
loopback server in for Ollama; none of them talks to a real one.
"""

from __future__ import annotations

import importlib.util
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
from threading import Thread

import pytest

SCRIPT = Path(__file__).resolve().parents[5] / "tooling" / "scripts" / "measure_chat_latency.py"

DIGEST = "8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7"
OTHER_DIGEST = "90a5eaf166fdda7e95441577e6ae96ebacf3248772a4366d1199b7b6ac0b0405"


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("kenn_measure_ollama_runtime", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def fake_ollama(monkeypatch):
    """A loopback Ollama whose /api/ps answer the test can change between calls."""
    state = {"loaded": [{"name": "qwen3:1.7b-q4_K_M", "digest": DIGEST, "runner": "mlx",
                         "expires_at": "2026-10-16T12:00:00+01:00"}]}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            routes = {
                "/api/version": {"version": "0.40.4"},
                "/api/tags": {"models": [{"name": "qwen3:1.7b-q4_K_M", "digest": DIGEST}]},
                "/api/ps": {"models": state["loaded"]},
            }
            body = json.dumps(routes.get(self.path, {})).encode()
            self.send_response(200 if self.path in routes else 404)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    Thread(target=httpd.serve_forever, daemon=True).start()
    monkeypatch.setenv("KENN_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("KENN_LLM_BASE_URL", f"http://127.0.0.1:{httpd.server_port}/v1")
    monkeypatch.setenv("KENN_LLM_MODEL", "qwen3:1.7b-q4_K_M")
    for task in ("ROUTE", "PARAPHRASE", "FOLLOWUPS"):
        monkeypatch.delenv(f"KENN_LLM_MODEL_{task}", raising=False)
    try:
        yield state
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_the_runner_and_digest_of_a_loaded_model_reach_the_receipt(tool, fake_ollama):
    runtime = tool._ollama_runtime()
    assert runtime["error"] is None and runtime["version"] == "0.40.4"
    assert runtime["digests"] == {"qwen3:1.7b-q4_K_M": DIGEST}
    assert [(m["name"], m["digest"], m["runner"]) for m in runtime["loaded"]] == [("qwen3:1.7b-q4_K_M", DIGEST, "mlx")]


def test_a_second_resident_model_is_visible_so_a_timing_run_can_be_discounted(tool, fake_ollama):
    # Two resident models is what keep_alive 0 exists to prevent; the receipt has to be able to show it.
    fake_ollama["loaded"].append({"name": "kenn-brain-qwen3-8b:latest", "digest": OTHER_DIGEST, "runner": "llamacpp"})
    assert {m["runner"] for m in tool._ollama_runtime()["loaded"]} == {"mlx", "llamacpp"}


def test_an_unloaded_model_reads_as_not_observed_rather_than_a_runner(tool, fake_ollama):
    fake_ollama["loaded"].clear()
    runtime = tool._ollama_runtime()
    assert runtime["loaded"] == [] and runtime["digests"] == {"qwen3:1.7b-q4_K_M": DIGEST}


def test_an_unreachable_ollama_is_recorded_as_an_error_and_never_raised(tool, monkeypatch):
    # Port 1 is reserved, so the connection is refused immediately.
    monkeypatch.setenv("KENN_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("KENN_LLM_BASE_URL", "http://127.0.0.1:1/v1")
    runtime = tool._ollama_runtime(timeout=0.5)
    assert runtime["loaded"] == [] and runtime["version"] is None and runtime["error"]


def test_a_remote_base_url_is_refused_without_a_request(tool, monkeypatch):
    monkeypatch.setenv("KENN_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("KENN_LLM_BASE_URL", "http://example.invalid:11434/v1")
    assert "loopback" in tool._ollama_runtime()["error"]


def test_a_non_ollama_provider_has_no_runtime_to_report(tool, monkeypatch):
    monkeypatch.setenv("KENN_LLM_PROVIDER", "openai")
    assert tool._ollama_runtime() is None


def test_measure_samples_runtime_before_and_after_and_records_the_keep_alive(tool, fake_ollama, monkeypatch):
    monkeypatch.setattr(tool, "_drop_semantic_cache", lambda: None)
    monkeypatch.setattr(tool, "_index_version", lambda: "test")
    reply = {"generation_validation": {"attempted": True, "accepted": True, "warnings": []}, "llm_enhanced": True}
    monkeypatch.setattr(tool, "_ask", lambda *a, **k: (reply, 0, None))

    # Resident while the question is asked (the "before" sample sees it) and gone once the run ends, which is
    # how a keep_alive 0 run looks to `ollama ps` afterwards.
    real = tool._ollama_runtime
    samples = []

    def sample(*args, **kwargs):
        samples.append(1)
        if len(samples) > 1:
            fake_ollama["loaded"].clear()
        return real(*args, **kwargs)

    monkeypatch.setattr(tool, "_ollama_runtime", sample)
    report = tool.measure([{"id": "c-1", "question": "Synthetic"}])

    runtime = report["provenance"]["ollama_runtime"]
    assert runtime["before_run"]["loaded"][0]["runner"] == "mlx"
    assert runtime["after_run"]["loaded"] == []
    assert runtime["after_run"]["digests"] == {"qwen3:1.7b-q4_K_M": DIGEST}
    assert report["provenance"]["ollama_keep_alive"]


def test_an_http_run_does_not_claim_this_process_s_ollama(tool, monkeypatch):
    # The companion answering over HTTP has its own Ollama; sampling ours would label someone else's runner.
    monkeypatch.setattr(tool, "_drop_semantic_cache", lambda: None)
    monkeypatch.setattr(tool, "_ollama_runtime", lambda *a, **k: pytest.fail("must not probe for an HTTP run"))
    monkeypatch.setattr(tool, "_ask_http", lambda *a, **k: (
        {"answer": "Synthetic", "delivery_outcome": "accepted",
         "generation_validation": {"attempted": True, "accepted": True}}, 0, None))
    report = tool.measure([{"id": "c-1", "question": "Synthetic"}], surface="background",
                          endpoint="http://127.0.0.1:1", cache_condition="warm")
    assert report["provenance"]["ollama_runtime"] == {"before_run": None, "after_run": None}
    assert report["provenance"]["ollama_keep_alive"] is None
