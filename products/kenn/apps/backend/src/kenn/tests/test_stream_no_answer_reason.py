"""A stream that ends with no text says so, rather than the bare "generation returned no answer".

The payload path has named its cause since 8 Oct (`: request failed`, `: structure check`, `: llm disabled`), so a
probe can tell the 128-token cap from a dead request. The stream kept the bare reason for a model that returned
nothing at all, which the C1 harness then counts beside the named causes as if it were a different fault.
"""

from __future__ import annotations

from kenn.tests.test_streamed_generation_prefix_guard import _stream, _text_and_metadata


def test_an_empty_stream_names_its_cause(monkeypatch):
    def empty(*args, **kwargs):
        return
        yield  # pragma: no cover - makes this a generator, which the stream closes when done

    _text, metadata = _text_and_metadata(list(_stream(monkeypatch, empty)))
    assert metadata["generation_validation"]["warnings"] == ["generation returned no answer: empty reply"]
    # Still transient: an empty reply says nothing about the next try, so the template must not be cached.
    assert metadata["generation_validation"]["transient"] is True


def test_a_stream_that_dies_keeps_its_exception_as_the_cause(monkeypatch):
    def dies(*args, **kwargs):
        raise TimeoutError("read timed out")
        yield  # pragma: no cover - makes this a generator

    _text, metadata = _text_and_metadata(list(_stream(monkeypatch, dies)))
    assert metadata["generation_validation"]["warnings"][0].startswith("generation stream cut short: TimeoutError")
