from __future__ import annotations

import json
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

import pytest

from kenn.core.deliberative_plan import PLAN_SKETCH_SCHEMA
from kenn.core.ollama_deliberative import OllamaDeliberativeGenerator, validate_ollama_base_url


class _Response:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_ollama_generator_posts_constrained_sketch_to_loopback() -> None:
    calls = []

    def opener(request, *, timeout):
        calls.append((request, timeout))
        return _Response({"message": {"content": '{"schema":"kenn.deliberative_plan_sketch.v1"}'}})

    generator = OllamaDeliberativeGenerator(
        model="qwen-test", timeout=30, max_output_tokens=240, opener=opener,
    )

    result = generator.generate("plan this", allowed_actions=["inspect_live"])

    assert result == '{"schema":"kenn.deliberative_plan_sketch.v1"}'
    request, timeout = calls[0]
    body = json.loads(request.data)
    assert request.full_url == "http://127.0.0.1:11434/api/chat"
    assert timeout == 30
    assert body["model"] == "qwen-test"
    assert body["stream"] is False
    assert body["options"]["num_predict"] == 240
    assert body["format"]["properties"]["schema"]["const"] == PLAN_SKETCH_SCHEMA
    assert set(body["format"]["properties"]["steps"]["items"]["properties"]["action"]["enum"]) == {
        "inspect_live", "refuse",
    }
    assert "execution_authorized" not in body["format"]["properties"]


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:11434",
        "http://example.com:11434",
        "http://user:pass@127.0.0.1:11434",
        "http://127.0.0.1:11434/path",
        "file:///tmp/ollama.sock",
    ],
)
def test_ollama_generator_rejects_non_loopback_or_credentialed_origins(url: str) -> None:
    with pytest.raises(ValueError, match="loopback"):
        OllamaDeliberativeGenerator(base_url=url)


def test_ollama_generator_reports_local_transport_failure_without_retrying() -> None:
    calls = []

    def unavailable(_request, *, timeout):
        calls.append(timeout)
        raise urllib.error.URLError("offline")

    generator = OllamaDeliberativeGenerator(opener=unavailable)

    with pytest.raises(RuntimeError, match="unavailable or timed out"):
        generator("plan this")
    assert calls == [45.0]


def test_ollama_generator_never_follows_redirects_with_prompt_payload() -> None:
    paths: list[str] = []

    class RedirectHandler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            paths.append(self.path)
            self.send_response(307)
            self.send_header("Location", "/prompt-leak")
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"redirect rejected"}')

        def log_message(self, *_args):
            return

    server = HTTPServer(("127.0.0.1", 0), RedirectHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        generator = OllamaDeliberativeGenerator(
            base_url=f"http://127.0.0.1:{server.server_port}"
        )
        with pytest.raises(RuntimeError, match="HTTP 307"):
            generator.generate("private session context")
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

    assert paths == ["/api/chat"]


def test_public_url_validator_accepts_only_plain_loopback_origins() -> None:
    assert validate_ollama_base_url("http://localhost:11434/") == "http://localhost:11434"
    with pytest.raises(ValueError, match="loopback"):
        validate_ollama_base_url("http://127.0.0.1:11434/api/chat")
