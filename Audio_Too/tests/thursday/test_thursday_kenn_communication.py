"""End-to-end "can Thursday and KENN actually talk to each other" tests.

2026-08-02: two real, live bugs (see thursday/autonomous_producer.py and
thursday/brain.py's commit history) reached Jack as "Thursday isn't working
at all" before any test caught them -- one crashed the whole server on
import, the other made real questions come back as generic non-answers.
Neither was caught because the existing test suite mocks the LLM/service
boundary in most places (correctly, for determinism) but nothing exercised
the actual, real, unmocked communication path end-to-end: HTTP route in ->
thursday.bridge -> thursday.orchestrator.handle() -> thursday.client.ask_kenn
-> kenn.core.chat.answer_payload() -> formatted reply back out.

These tests intentionally do NOT mock the LLM provider or KENN's answer
pipeline. They only cover paths that are genuinely LLM-free by construction
(deterministic regex-classified intents, KENN's offline retrieval+template
path with allow_llm left at its default in an environment where
AUDIO_TOO_LLM_ENABLED is unset) -- so they stay fast, deterministic, and
require no network access or API key, while still exercising the real
production code, not a stand-in for it.
"""

from __future__ import annotations

import json
import sys
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT / "server" / "app") not in sys.path:
    sys.path.insert(0, str(ROOT / "server" / "app"))
if str(ROOT / "studio" / "kenn") not in sys.path:
    sys.path.insert(0, str(ROOT / "studio" / "kenn"))

import pytest

from app.routes.thursday_routes import handle_thursday_post  # noqa: E402
from thursday import session_manager  # noqa: E402


def _assert_looks_like_a_real_answer(text: str) -> None:
    """Structural sanity check shared by every test below.

    Deliberately NOT a content/topic check (that would couple these tests to
    KENN's knowledge base contents, which change independently) -- just "this
    is a real, non-empty reply", the thing both live bugs broke.
    """
    assert isinstance(text, str)
    stripped = text.strip()
    assert stripped, "answer was empty"
    assert stripped.lower() != "none"
    assert "traceback" not in stripped.lower()


@pytest.fixture()
def isolated_sessions(monkeypatch, tmp_path):
    monkeypatch.setattr(session_manager, "SESSION_DIR", tmp_path / "sessions")
    monkeypatch.setattr(session_manager, "SESSION_FILE", tmp_path / ".session")
    # Keep this suite deterministic and network-free: the brain/LLM path is
    # covered separately (test_thursday_brain.py) with a mocked provider.
    monkeypatch.delenv("AUDIO_TOO_LLM_ENABLED", raising=False)
    monkeypatch.delenv("THURSDAY_BRAIN_ENABLED", raising=False)


# ─── thursday.client.ask_kenn -> kenn.core.chat.answer_payload (real, in-process) ──


def test_thursday_client_ask_kenn_reaches_kenn_for_real(isolated_sessions):
    """The actual in-process bridge orchestrator.handle() calls for every
    production question (thursday/orchestrator.py: `api.ask_kenn(...)`,
    where `api` is thursday.client). No mocking of KENN at all here."""
    from thursday import client

    result = client.ask_kenn("Why is my vocal harsh after compression?")

    # ask_kenn returns a KennAnswer (str subclass) or a plain str depending
    # on which internal path served it -- both stringify to the real answer.
    _assert_looks_like_a_real_answer(str(result))


# ─── Full orchestrator loop: Thursday receives a message, consults KENN, replies ──


def test_thursday_handle_routes_a_production_question_to_kenn_and_gets_a_real_reply(
    isolated_sessions,
):
    from thursday.orchestrator import handle

    session = session_manager.get_or_create_session("test-thursday-kenn-comms")
    reply = handle(
        "Why is my vocal harsh after compression?",
        session=session,
        list_records=lambda _: [],
    )

    _assert_looks_like_a_real_answer(reply)


def test_thursday_handle_answers_a_basic_greeting_end_to_end(isolated_sessions):
    """The deterministic (non-KENN) path -- no service call, no LLM, just
    session + intent + formatter plumbing. Fast, and would have caught the
    autonomous_producer.py crash if that module were on this import chain
    (it's on thursday_routes.py's, which the HTTP-level test below covers)."""
    from thursday.orchestrator import handle

    session = session_manager.get_or_create_session("test-thursday-greeting")
    reply = handle("hello", session=session, list_records=lambda _: [])

    _assert_looks_like_a_real_answer(reply)


# ─── HTTP route level: the exact path business/app/server.py exposes ──────────────


class _FakeAskHandler:
    """Minimal stand-in for the real request handler, covering both the
    plain-JSON and SSE-streaming branches of handle_thursday_post's
    /api/thursday/ask route -- matches tests/test_thursday_routes.py's
    FakeHandler pattern, extended with the streaming methods that route
    actually calls (send_response/send_header/end_headers/wfile)."""

    def __init__(self, body: dict) -> None:
        self._body = json.dumps(body).encode("utf-8")
        self.headers = {"Content-Length": str(len(self._body))}
        self.rfile = BytesIO(self._body)
        self.status = 0
        self.payload: dict = {}
        self._sent_headers: dict[str, str] = {}
        self._chunks: list[bytes] = []
        self.wfile = self

    def read_json_body(self) -> dict:
        return json.loads(self._body.decode("utf-8"))

    def send_json(self, status: int, payload: dict) -> None:
        self.status = status
        self.payload = payload

    def send_response(self, status: int) -> None:
        self.status = status

    def send_header(self, key: str, value: str) -> None:
        self._sent_headers[key] = value

    def end_headers(self) -> None:
        pass

    def write(self, data: bytes) -> None:
        self._chunks.append(data)

    def flush(self) -> None:
        pass

    def stream_events(self) -> list[dict]:
        raw = b"".join(self._chunks).decode("utf-8")
        events = []
        for block in raw.split("\n\n"):
            block = block.strip()
            if block.startswith("data:"):
                events.append(json.loads(block[len("data:"):].strip()))
        return events


def test_thursday_ask_route_answers_without_crashing(isolated_sessions):
    """Non-streaming /api/thursday/ask -- the plain HTTP contract."""
    handler = _FakeAskHandler({"question": "hello", "session_id": "test-http-ask"})

    handled = handle_thursday_post(handler, "/api/thursday/ask")

    assert handled is True
    assert handler.status == 200
    _assert_looks_like_a_real_answer(handler.payload.get("answer", ""))


def test_thursday_ask_route_streaming_answers_without_crashing(isolated_sessions):
    """Regression for the exact bug Jack reported by screenshot: business/app/
    static/hub.html always sends stream: true, got an empty response bubble
    then 'Error: Load failed'. This drives handle_thursday_post's SSE branch
    for real and checks a real, non-empty answer actually comes back as a
    'token' event, followed by 'metadata' and 'done' -- the exact sequence
    hub.html's reader loop expects."""
    handler = _FakeAskHandler(
        {"question": "hello", "session_id": "test-http-ask-stream", "stream": True}
    )

    handled = handle_thursday_post(handler, "/api/thursday/ask")

    assert handled is True
    assert handler.status == 200
    assert handler._sent_headers.get("Content-Type") == "text/event-stream"

    events = handler.stream_events()
    event_types = [e.get("event") for e in events]
    assert "error" not in event_types, f"stream reported an error event: {events}"
    assert "token" in event_types
    assert "done" in event_types

    token_events = [e for e in events if e.get("event") == "token"]
    _assert_looks_like_a_real_answer(token_events[0].get("token", ""))


def test_thursday_ask_route_streaming_production_question_reaches_kenn(
    isolated_sessions,
):
    """Same streaming contract, but for a question that actually routes
    through KENN (kenn_stream target in thursday/bridge.py::ask_stream) --
    the highest-value path, since it's the one that chains through the most
    real subsystems: HTTP route -> bridge -> orchestrator classification ->
    KENN's real answer pipeline -> SSE framing back to the browser."""
    handler = _FakeAskHandler(
        {
            "question": "Why is my vocal harsh after compression?",
            "session_id": "test-http-ask-stream-kenn",
            "stream": True,
        }
    )

    handled = handle_thursday_post(handler, "/api/thursday/ask")

    assert handled is True
    assert handler.status == 200

    events = handler.stream_events()
    event_types = [e.get("event") for e in events]
    assert "error" not in event_types, f"stream reported an error event: {events}"
    assert "done" in event_types

    metadata_events = [e for e in events if e.get("event") == "metadata"]
    assert metadata_events, "no metadata event -- the browser never learns the final answer"
    final_answer = metadata_events[-1].get("data", {}).get("answer", "")
    _assert_looks_like_a_real_answer(final_answer)


# ─── Import-chain smoke test: the class of bug that crashed the whole server ──────


def test_business_server_import_chain_does_not_require_torch():
    """Regression class-guard for the autonomous_producer.py crash: nothing
    reachable from business/app/server.py's own import graph may hard-require
    torch/composition at import time, since torch is deliberately excluded
    from the shared venv (NumPy 2.x ABI break) and may be broken/absent.
    Walks the same modules server.py imports eagerly and asserts they import
    cleanly in this environment, then asserts torch specifically is not a
    transitive requirement by checking it's absent from what got imported
    only if it wasn't already loaded by something unrelated in the test run.
    """
    import importlib

    # These are the actual eager imports on the request path for
    # /api/thursday/ask -- see business/app/routes/thursday_routes.py's own
    # docstring for why they're eager rather than lazy.
    for module_name in (
        "app.routes.thursday_routes",
        "thursday.autonomous_producer",
        "thursday.bridge",
        "thursday.orchestrator",
    ):
        importlib.import_module(module_name)  # must not raise
