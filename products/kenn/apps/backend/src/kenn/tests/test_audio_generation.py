from __future__ import annotations

import base64
import io
import wave

import pytest

from kenn.core.audio_generation import (
    AudioGenerationError,
    MiniMaxMusic3Backend,
    build_request,
    build_structured_caption,
)


def _wav(seconds: float = 1.0, rate: int = 8000) -> bytes:
    target = io.BytesIO()
    with wave.open(target, "wb") as handle:
        handle.setnchannels(1); handle.setsampwidth(2); handle.setframerate(rate)
        handle.writeframes(b"\0\0" * int(seconds * rate))
    return target.getvalue()


def _request(**overrides):
    values = {"request_id": "gen-1", "lyrics": "A short original line", "brief": {},
              "duration_seconds": 2, "seed": 42}
    values.update(overrides)
    return build_request(**values)


def test_caption_preserves_unknown_values_instead_of_inventing_them() -> None:
    caption = build_structured_caption({"genre": "ambient", "vocals": {"presence": "none"}})
    assert caption["genre"] == "ambient"
    assert caption["bpm"] is None and caption["key"] is None
    assert "bpm" in caption["unknown_fields_preserved"]
    assert "vocal_identity" in caption["unknown_fields_preserved"]


def test_request_is_bounded_and_non_streaming_wav_only() -> None:
    request = _request()
    assert request["stream"] is False and request["output_format"] == "wav"
    with pytest.raises(AudioGenerationError, match="duration_seconds"):
        _request(duration_seconds=301)
    with pytest.raises(AudioGenerationError, match="WAV"):
        _request(output_format="mp3")


def test_backend_is_disabled_by_default_and_never_calls_transport() -> None:
    calls = []
    backend = MiniMaxMusic3Backend(lambda *args: calls.append(args) or {}, "revision-1")
    with pytest.raises(AudioGenerationError, match="disabled"):
        backend.generate(_request())
    assert calls == []


def test_backend_hashes_and_labels_a_valid_generated_wav() -> None:
    audio = _wav()
    backend = MiniMaxMusic3Backend(
        lambda request, timeout: {"audio_base64": base64.b64encode(audio).decode()},
        "revision-1", enabled=True, timeout_seconds=3,
    )
    result = backend.generate(_request())
    assert result["status"] == "complete"
    assert result["artifact"]["sha256"].startswith("sha256:")
    assert result["artifact"]["duration_seconds"] == 1
    assert result["provenance"] == {"generated": True, "provider": "minimax_music3",
                                    "model_revision": "revision-1", "user_source_audio": False}


@pytest.mark.parametrize("response", [{}, {"audio_base64": "not base64"},
                                      {"audio_base64": base64.b64encode(b"not wav").decode()}])
def test_backend_rejects_malformed_provider_responses(response) -> None:
    backend = MiniMaxMusic3Backend(lambda *_: response, "revision-1", enabled=True)
    with pytest.raises(AudioGenerationError):
        backend.generate(_request())


def test_backend_normalizes_timeout_without_returning_false_success() -> None:
    def timeout(*_):
        raise TimeoutError
    with pytest.raises(AudioGenerationError, match="timed out"):
        MiniMaxMusic3Backend(timeout, "revision-1", enabled=True).generate(_request())


def test_backend_rejects_forged_request_that_bypasses_builder() -> None:
    backend = MiniMaxMusic3Backend(lambda *_: {}, "revision-1", enabled=True)
    with pytest.raises(AudioGenerationError, match="non-streaming WAV"):
        backend.generate({**_request(), "stream": True})


def test_backend_rejects_provider_revision_mismatch() -> None:
    audio = _wav()
    backend = MiniMaxMusic3Backend(
        lambda *_: {"audio_base64": base64.b64encode(audio).decode(), "model_revision": "unexpected"},
        "pinned-revision", enabled=True,
    )
    with pytest.raises(AudioGenerationError, match="configured revision"):
        backend.generate(_request())
