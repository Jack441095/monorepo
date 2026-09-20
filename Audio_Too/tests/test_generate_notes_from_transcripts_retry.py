"""_ollama_extract() retries transient connection/timeout failures instead
of silently dropping a transcript chunk forever on the first hiccup,
indistinguishable from a legitimate NO_TECHNIQUE response (P4 fix,
2026-07-13)."""

from __future__ import annotations

import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import generate_notes_from_transcripts as gnt  # noqa: E402

# _ollama_extract() does `import time` / `import urllib.request` locally
# inside the function body -- those bind to the same module objects already
# in sys.modules, so patching the real urllib.request/time modules here
# (not attributes on gnt) is what actually takes effect.


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _ok_body() -> bytes:
    return b'{"response": "# Title\\n\\nreal note content"}'


def test_succeeds_on_first_try_with_no_retry(monkeypatch):
    calls = []

    def fake_urlopen(req, timeout):
        calls.append(1)
        return _FakeResponse(_ok_body())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(time, "sleep", lambda *_: None)

    result = gnt._ollama_extract("chunk text")

    assert result == "# Title\n\nreal note content"
    assert len(calls) == 1


def test_retries_transient_url_error_and_succeeds(monkeypatch):
    calls = []

    def fake_urlopen(req, timeout):
        calls.append(1)
        if len(calls) == 1:
            raise urllib.error.URLError("connection refused")
        return _FakeResponse(_ok_body())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(time, "sleep", lambda *_: None)

    result = gnt._ollama_extract("chunk text")

    assert result == "# Title\n\nreal note content"
    assert len(calls) == 2


def test_gives_up_after_max_attempts_on_persistent_failure(monkeypatch):
    calls = []

    def fake_urlopen(req, timeout):
        calls.append(1)
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(time, "sleep", lambda *_: None)

    result = gnt._ollama_extract("chunk text", max_attempts=3)

    assert result == ""
    assert len(calls) == 3


def test_non_transient_error_does_not_retry(monkeypatch):
    calls = []

    def fake_urlopen(req, timeout):
        calls.append(1)
        raise ValueError("malformed response")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(time, "sleep", lambda *_: None)

    result = gnt._ollama_extract("chunk text", max_attempts=3)

    assert result == ""
    assert len(calls) == 1
