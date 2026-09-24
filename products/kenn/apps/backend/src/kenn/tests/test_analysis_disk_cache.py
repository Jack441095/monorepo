"""Audio-analysis results survive a companion restart (measured results only, keyed by content hash)."""

from __future__ import annotations

import io
import math
import struct
import wave

from kenn.core import live_session_advice as advice


def _wav(seconds: float = 1.0, rate: int = 44100) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        frames = (int(12000 * math.sin(2 * math.pi * 110 * n / rate)) for n in range(int(seconds * rate)))
        handle.writeframes(b"".join(struct.pack("<h", f) for f in frames))
    return buffer.getvalue()


def test_restart_reads_the_persisted_analysis(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("KENN_ANALYSIS_CACHE_DIR", str(tmp_path))
    advice._ANALYSIS_CACHE.clear()
    payload = _wav()
    first, digest, cached = advice._analyze_cached(payload, filename="mix.wav")
    assert first.get("ok") and cached is False
    assert (tmp_path / f"{digest}.wav.json").exists()
    persisted = (tmp_path / f"{digest}.wav.json").read_bytes()
    assert payload[44:1000] not in persisted  # measured results, not audio

    advice._ANALYSIS_CACHE.clear()  # what a restart does to the memory cache
    second, _digest, cached = advice._analyze_cached(payload, filename="mix.wav")
    assert cached is True and second.get("ok")


def test_disk_cache_is_bounded(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("KENN_ANALYSIS_CACHE_DIR", str(tmp_path))
    for number in range(advice._DISK_CACHE_MAX_FILES + 3):
        advice._write_disk_cache((f"{number:064x}", ".wav"), {"ok": True})
    assert len(list(tmp_path.glob("*.json"))) == advice._DISK_CACHE_MAX_FILES
