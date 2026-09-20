"""Audio I/O wrapper functions — delegates to :mod:`audio_analysis_tool.audio_io`.

These are simple pass-through wrappers that bind the project-level
configuration (``WAV_SUFFIXES``, ``BUSINESS_ROOT``, etc.) for
convenience calls from :mod:`audio_analysis_tool.mix_review`.
"""

from __future__ import annotations

from pathlib import Path

from audio_analysis.utils.audio_io import (
    _decode_with_ffmpeg_bytes as _audio_io_decode_with_ffmpeg_bytes,
    _decode_with_ffmpeg_path as _audio_io_decode_with_ffmpeg_path,
    _decode_with_soundfile_bytes as _audio_io_decode_with_soundfile_bytes,
    _decode_with_soundfile_path as _audio_io_decode_with_soundfile_path,
    _write_wav_from_float_array as _audio_io_write_wav_from_float_array,
    ffmpeg_path as _audio_io_ffmpeg_path,
    read_wav_mono as _audio_io_read_wav_mono,
)
import numpy as np

BUSINESS_ROOT = Path(__file__).resolve().parent.parent
WAV_SUFFIXES = {".wav", ".wave"}
DECODABLE_SUFFIXES = WAV_SUFFIXES | {".aif", ".aiff", ".flac", ".m4a", ".mp3"}


def read_wav_mono(file_bytes: bytes, *, max_samples: int = 65536, as_arrays: bool = False) -> dict:
    """Read WAV file as mono floating-point samples.

    as_arrays: forwards to audio_io.read_wav_mono's own as_arrays -- False
    (list output) by default to match every existing caller's expectations
    unchanged; a caller that threads numpy arrays straight through to
    numpy-native consumers (e.g. analysis_core.py's LUFS re-read) can opt
    in to skip a redundant list<->array round trip.
    """
    return _audio_io_read_wav_mono(file_bytes, max_samples=max_samples, as_arrays=as_arrays)


def _write_wav_from_float_array(samples: np.ndarray, sample_rate: int) -> bytes:
    """Convert a float numpy array to WAV bytes."""
    return _audio_io_write_wav_from_float_array(samples, sample_rate)


def _decode_with_soundfile_bytes(file_bytes: bytes) -> tuple[bytes, str] | None:
    """Decode audio bytes using soundfile (libsndfile)."""
    return _audio_io_decode_with_soundfile_bytes(file_bytes)


def _decode_with_soundfile_path(path: Path) -> tuple[bytes, str] | None:
    """Decode audio from a file path using soundfile (libsndfile)."""
    return _audio_io_decode_with_soundfile_path(path)


def ffmpeg_path() -> str:
    """Return path to ffmpeg binary, or empty string if not found."""
    return _audio_io_ffmpeg_path()


def _decode_with_ffmpeg_path(path: Path) -> tuple[bytes, str] | None:
    """Decode audio from a file path using ffmpeg."""
    return _audio_io_decode_with_ffmpeg_path(path)


def _decode_with_ffmpeg_bytes(file_bytes: bytes, suffix: str) -> tuple[bytes, str] | None:
    """Decode audio bytes using ffmpeg."""
    return _audio_io_decode_with_ffmpeg_bytes(file_bytes, suffix)


def decode_audio_bytes(file_bytes: bytes, filename: str) -> dict:
    """Return WAV PCM bytes for supported audio formats.

    Tries wave module first for WAV/RIFF, then soundfile, then ffmpeg.
    Raises ValueError if no decoder is available.
    """
    suffix = Path(filename or "").suffix.lower()
    if file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WAVE":
        return {
            "wav_bytes": file_bytes,
            "decoder": "wave",
            "source_format": suffix.lstrip(".") or "wav",
        }
    if suffix in WAV_SUFFIXES:
        return {
            "wav_bytes": file_bytes,
            "decoder": "wave",
            "source_format": suffix.lstrip(".") or "wav",
        }
    decoded = _decode_with_soundfile_bytes(file_bytes)
    if decoded is None:
        decoded = _decode_with_ffmpeg_bytes(file_bytes, suffix)
    if decoded is None:
        raise ValueError(
            "Could not decode audio. Install soundfile/libsndfile or ffmpeg, or convert the file to WAV."
        )
    wav_bytes, decoder = decoded
    return {
        "wav_bytes": wav_bytes,
        "decoder": decoder,
        "source_format": suffix.lstrip(".") or "audio",
    }


def decode_audio_file(path: Path) -> dict:
    """Return WAV PCM bytes for a path without loading through upload validation."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in WAV_SUFFIXES:
        return {
            "wav_bytes": path.read_bytes(),
            "decoder": "wave",
            "source_format": suffix.lstrip(".") or "wav",
        }
    decoded = _decode_with_soundfile_path(path)
    if decoded is None:
        decoded = _decode_with_ffmpeg_path(path)
    if decoded is None:
        raise ValueError(
            "Could not decode audio. Install soundfile/libsndfile or ffmpeg, or convert the file to WAV."
        )
    wav_bytes, decoder = decoded
    return {
        "wav_bytes": wav_bytes,
        "decoder": decoder,
        "source_format": suffix.lstrip(".") or "audio",
    }
