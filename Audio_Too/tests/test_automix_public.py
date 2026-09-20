"""Tests for automix_public.start_public_automix() -- the public,
self-serve "upload stems, start a job" flow (no dashboard session
needed), mirroring stem_separation_bridge.enqueue_separation()'s shape.
"""

from __future__ import annotations

import math
import struct
import sys
import wave
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server" / "app"))

import automix_public  # noqa: E402
import automix_jobs  # noqa: E402
import db  # noqa: E402
import stem_uploads  # noqa: E402


def _sine_wav_bytes(*, freq: float = 220.0, seconds: float = 1.0, sr: int = 44100) -> bytes:
    import io
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(2)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sr)
        for i in range(int(seconds * sr)):
            value = int(0.3 * 32767 * math.sin(2 * math.pi * freq * i / sr))
            wav_file.writeframesraw(struct.pack("<hh", value, value))
    return buf.getvalue()


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "audio_too.db")
    monkeypatch.setattr(db, "AGENT_DATA", tmp_path / "legacy-json")
    monkeypatch.setattr(db, "_migration_done", False)
    monkeypatch.setattr(stem_uploads, "UPLOAD_ROOT", tmp_path / "stem_uploads")
    yield


def test_start_public_automix_with_no_files_is_rejected():
    result = automix_public.start_public_automix([])
    assert result["ok"] is False
    assert "no files" in result["error"].lower()


def test_start_public_automix_rejects_too_many_files():
    files = [(_sine_wav_bytes(), f"stem_{i}.wav") for i in range(automix_public.MAX_STEM_FILES + 1)]
    result = automix_public.start_public_automix(files)
    assert result["ok"] is False
    assert "too many" in result["error"].lower()


def test_start_public_automix_rejects_invalid_audio():
    result = automix_public.start_public_automix([(b"not audio", "stem_0.wav")])
    assert result["ok"] is False
    assert "error" in result


def test_start_public_automix_creates_a_real_queued_job():
    files = [
        (_sine_wav_bytes(freq=110.0), "bass.wav"),
        (_sine_wav_bytes(freq=440.0), "vocal.wav"),
    ]
    result = automix_public.start_public_automix(files, genre="edm")

    assert result["ok"] is True
    assert result["project_id"].startswith("kenn-")
    assert result["job_id"]
    assert result["status"] == "queued"

    job = automix_jobs.get_job_status(result["job_id"])
    assert job is not None
    assert job["project_id"] == result["project_id"]
    assert job["genre"] == "edm"
    assert job["status"] == "queued"


def test_start_public_automix_defaults_genre_to_pop():
    files = [(_sine_wav_bytes(), "stem_0.wav")]
    result = automix_public.start_public_automix(files)
    job = automix_jobs.get_job_status(result["job_id"])
    assert job["genre"] == "pop"


def test_two_calls_create_two_independent_projects():
    files_a = [(_sine_wav_bytes(), "stem_0.wav")]
    files_b = [(_sine_wav_bytes(), "stem_0.wav")]
    result_a = automix_public.start_public_automix(files_a)
    result_b = automix_public.start_public_automix(files_b)
    assert result_a["project_id"] != result_b["project_id"]
    assert result_a["job_id"] != result_b["job_id"]


def _mark_complete(job_id: str, result_path: str) -> None:
    with db.connect() as conn:
        conn.execute(
            "UPDATE automix_jobs SET status = 'complete', result_path = ? WHERE id = ?",
            (result_path, job_id),
        )
        conn.commit()


def _build_delivery_zip(tmp_path, *, version: int = 1) -> Path:
    import zipfile
    zip_path = tmp_path / "delivery.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(f"mixdown_v{version}.wav", _sine_wav_bytes())
        zf.writestr("report.html", "<html>report</html>")
    return zip_path


class TestDeliveryZipPath:
    def test_returns_none_for_a_non_complete_job(self):
        files = [(_sine_wav_bytes(), "stem_0.wav")]
        result = automix_public.start_public_automix(files)
        assert automix_public.delivery_zip_path(result["job_id"]) is None

    def test_returns_none_for_an_unknown_job(self):
        # Establishes the schema first (a fresh isolated DB has no tables
        # until something creates them) via an unrelated real job, then
        # checks a genuinely different, never-created id.
        automix_public.start_public_automix([(_sine_wav_bytes(), "stem_0.wav")])
        assert automix_public.delivery_zip_path("does-not-exist") is None

    def test_returns_the_path_for_a_complete_job_with_a_real_file(self, tmp_path):
        files = [(_sine_wav_bytes(), "stem_0.wav")]
        result = automix_public.start_public_automix(files)
        zip_path = _build_delivery_zip(tmp_path)
        _mark_complete(result["job_id"], str(zip_path))

        assert automix_public.delivery_zip_path(result["job_id"]) == zip_path

    def test_returns_none_if_the_file_no_longer_exists(self, tmp_path):
        files = [(_sine_wav_bytes(), "stem_0.wav")]
        result = automix_public.start_public_automix(files)
        _mark_complete(result["job_id"], str(tmp_path / "gone.zip"))

        assert automix_public.delivery_zip_path(result["job_id"]) is None


class TestDeliveryWavBytes:
    def test_extracts_the_mixdown_wav_from_the_zip(self, tmp_path):
        files = [(_sine_wav_bytes(), "stem_0.wav")]
        result = automix_public.start_public_automix(files)
        zip_path = _build_delivery_zip(tmp_path, version=3)
        _mark_complete(result["job_id"], str(zip_path))

        extracted = automix_public.delivery_wav_bytes(result["job_id"])

        assert extracted is not None
        wav_bytes, filename = extracted
        assert filename == "mixdown_v3.wav"
        assert wav_bytes == _sine_wav_bytes()

    def test_returns_none_for_a_non_complete_job(self):
        files = [(_sine_wav_bytes(), "stem_0.wav")]
        result = automix_public.start_public_automix(files)
        assert automix_public.delivery_wav_bytes(result["job_id"]) is None

    def test_returns_none_for_a_corrupt_zip(self, tmp_path):
        files = [(_sine_wav_bytes(), "stem_0.wav")]
        result = automix_public.start_public_automix(files)
        bad_zip = tmp_path / "bad.zip"
        bad_zip.write_bytes(b"not actually a zip")
        _mark_complete(result["job_id"], str(bad_zip))

        assert automix_public.delivery_wav_bytes(result["job_id"]) is None
