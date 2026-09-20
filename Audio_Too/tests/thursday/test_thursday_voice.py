from __future__ import annotations

import sys

from thursday.voice import normalize_transcript


def test_normalize_transcript_corrects_kenn_voice_command() -> None:
    assert normalize_transcript("Speak with Ken about compression.") == (
        "Speak with KENN about compression."
    )


def test_normalize_transcript_does_not_rewrite_unrelated_name() -> None:
    assert normalize_transcript("The client is Ken.") == "The client is Ken."


def test_persistent_stt_worker_lifecycle() -> None:
    from thursday.voice import _get_persistent_stt_worker, _cleanup_stt_worker, _mlx_available
    if not _mlx_available():
        return
    try:
        proc = _get_persistent_stt_worker()
        assert proc is not None
        assert proc.poll() is None
    finally:
        _cleanup_stt_worker()


def test_transcribe_with_metadata_fallback_keys() -> None:
    from thursday.voice import transcribe_with_metadata, analyze_clipping_noise
    
    # Missing file check
    res = transcribe_with_metadata("non-existent-file.wav")
    assert isinstance(res, dict)
    assert res["text"] == ""
    assert res["confidence"] == 0.0
    assert res["no_speech_prob"] == 1.0
    assert res["language"] == "en"
    assert res["duration"] == 0.0
    assert res["clipping"] is False
    assert res["noise_floor_db"] == -96.0

    # analyze_clipping_noise graceful exception/missing check
    analysis = analyze_clipping_noise("non-existent-file.wav")
    assert analysis["clipping"] is False
    assert analysis["noise_floor_db"] == -96.0
    assert analysis["duration"] == 0.0


def test_strip_wake_word() -> None:
    from thursday.voice import strip_wake_word

    assert strip_wake_word("Thursday, what is sidechaining?", "thursday") == "what is sidechaining?"
    assert strip_wake_word("Thursday's what is sidechaining?", "thursday") == "what is sidechaining?"
    assert strip_wake_word("Thursdays, what is sidechaining?", "thursday") == "what is sidechaining?"
    assert strip_wake_word("Thursday what is sidechaining?", "thursday") == "what is sidechaining?"
    assert strip_wake_word("What is sidechaining?", "thursday") == "What is sidechaining?"


def test_mlx_tts_disabled_by_default(monkeypatch) -> None:
    """Critical safety property: the GPL-adjacent MLX TTS fast path (see
    thursday/tts_worker_mlx.py's licensing note) must be a true no-op unless
    AUDIO_TOO_MLX_TTS=1 is explicitly set — a distributed build with no env
    config for this must stay on the MIT/Apache ONNX path with zero code
    changes needed."""
    from thursday.voice_output import _mlx_tts_enabled, _synthesise_mlx

    monkeypatch.delenv("AUDIO_TOO_MLX_TTS", raising=False)
    assert _mlx_tts_enabled() is False
    # Must return None immediately without attempting to spawn any subprocess.
    assert _synthesise_mlx("Hello.", "af_heart", None) is None


def test_mlx_tts_enabled_via_env_flag(monkeypatch) -> None:
    from thursday.voice_output import _mlx_tts_enabled

    monkeypatch.setenv("AUDIO_TOO_MLX_TTS", "1")
    assert _mlx_tts_enabled() is True


def test_tts_worker_python_respects_explicit_interpreter(monkeypatch, tmp_path) -> None:
    from thursday import voice_output

    explicit = tmp_path / "python"
    explicit.touch()
    monkeypatch.setenv("AUDIO_TOO_TTS_PYTHON", str(explicit))
    voice_output._tts_worker_python_command.cache_clear()
    try:
        assert voice_output._tts_worker_python_command() == (str(explicit),)
    finally:
        voice_output._tts_worker_python_command.cache_clear()


def test_tts_worker_python_uses_current_runtime_off_macos(monkeypatch) -> None:
    from thursday import voice_output

    monkeypatch.delenv("AUDIO_TOO_TTS_PYTHON", raising=False)
    monkeypatch.setattr(voice_output.sys, "platform", "linux")
    voice_output._tts_worker_python_command.cache_clear()
    try:
        assert voice_output._tts_worker_python_command() == (sys.executable,)
    finally:
        voice_output._tts_worker_python_command.cache_clear()

