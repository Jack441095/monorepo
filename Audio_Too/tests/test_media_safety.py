"""Content validation tests for uploaded audio and archives."""

from __future__ import annotations

import io
import wave
import zipfile

import pytest

from audio_analysis.utils.media_safety import validate_media_upload, write_private_file


def wav_bytes(seconds: float = 0.01, rate: int = 8_000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(b"\0\0" * max(1, int(seconds * rate)))
    return buffer.getvalue()


def zip_bytes(name: str = "stems/kick.wav") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, wav_bytes())
    return buffer.getvalue()


def test_audio_signature_must_match_extension() -> None:
    assert validate_media_upload(wav_bytes(), "mix.wav") == ".wav"
    with pytest.raises(ValueError, match="does not match"):
        validate_media_upload(b"not audio", "mix.wav")


def test_archive_must_be_valid_and_not_nested() -> None:
    assert validate_media_upload(zip_bytes(), "stems.zip", allow_zip=True) == ".zip"
    with pytest.raises(ValueError, match="Nested archives"):
        validate_media_upload(zip_bytes("nested/archive.zip"), "stems.zip", allow_zip=True)
    with pytest.raises(ValueError, match="invalid or truncated"):
        validate_media_upload(b"PK\x03\x04broken", "stems.zip", allow_zip=True)


def test_private_file_permissions(tmp_path) -> None:
    target = write_private_file(tmp_path / "private" / "mix.wav", wav_bytes())
    assert target.stat().st_mode & 0o777 == 0o600
    assert target.parent.stat().st_mode & 0o777 == 0o700
