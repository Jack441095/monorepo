"""Tests for the bounded stem_separation bridge.

Mirrors test_audiogen_bridge.py's isolation pattern: monkeypatch the
bridge's own higher-level function (separate_command) rather than the real
subprocess/torch/Demucs, plus a DB isolation fixture. This never needs the
isolated venv's torch/demucs installed -- only studio/stem_separation's own
tests/test_separator_real_inference.py (marked slow) does that.
"""

from __future__ import annotations

import math
import struct
import sys
import time
import wave
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server" / "app"))

import stem_separation_bridge  # noqa: E402
import stem_separation_job_store  # noqa: E402
import db  # noqa: E402


def _write_sine_wav(path: Path, *, seconds: float = 1.0, sr: int = 44100) -> None:
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(2)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sr)
        for i in range(int(seconds * sr)):
            value = int(0.3 * 32767 * math.sin(2 * math.pi * 220 * i / sr))
            wav_file.writeframesraw(struct.pack("<hh", value, value))


@pytest.fixture()
def isolated_bridge(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "audio_too.db")
    monkeypatch.setattr(db, "AGENT_DATA", tmp_path / "legacy-json")
    monkeypatch.setattr(db, "_migration_done", False)
    monkeypatch.setattr(stem_separation_bridge, "UPLOAD_ROOT", tmp_path / "stem_separation_jobs")
    stem_separation_job_store.reset_connection_state()
    stem_separation_job_store.ensure_schema()
    monkeypatch.setattr(stem_separation_bridge, "exists", lambda: True)
    yield
    stem_separation_bridge.stop_worker()
    stem_separation_job_store.reset_connection_state()


def _sample_wav_bytes(tmp_path) -> bytes:
    path = tmp_path / "mix.wav"
    _write_sine_wav(path)
    return path.read_bytes()


def test_enqueue_rejects_invalid_audio(isolated_bridge, tmp_path):
    result = stem_separation_bridge.enqueue_separation(b"not audio at all", "mix.wav")
    assert result["ok"] is False
    assert "error" in result


def test_enqueue_rejects_oversized_file(isolated_bridge, monkeypatch, tmp_path):
    monkeypatch.setattr(stem_separation_bridge, "MAX_SOURCE_BYTES", 10)
    data = _sample_wav_bytes(tmp_path)
    result = stem_separation_bridge.enqueue_separation(data, "mix.wav")
    assert result["ok"] is False
    assert "limit" in result["error"].lower()


def test_enqueue_and_completion_flow(isolated_bridge, monkeypatch, tmp_path):
    def fake_separate_command(input_path, output_dir, *, model="htdemucs", timeout=900):
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        stems = {}
        for name in stem_separation_bridge.STEM_NAMES:
            stem_path = output_dir / f"{name}.wav"
            stem_path.write_bytes(b"RIFF....WAVEfake")
            stems[name] = str(stem_path)
        return {"ok": True, "result": {"ok": True, "stems": stems, "model": model}}

    monkeypatch.setattr(stem_separation_bridge, "separate_command", fake_separate_command)

    data = _sample_wav_bytes(tmp_path)
    queued = stem_separation_bridge.enqueue_separation(data, "mix.wav", project_id="proj-1")
    assert queued["ok"] is True
    job_id = queued["job"]["id"]
    assert queued["job"]["status"] == "queued"

    deadline = time.time() + 5
    job = {}
    while time.time() < deadline:
        job = stem_separation_bridge.job_status(job_id)
        if job["status"] == "completed":
            break
        time.sleep(0.02)

    assert job["status"] == "completed"
    assert set(job["result"]["stems"]) == set(stem_separation_bridge.STEM_NAMES)

    drums_path = stem_separation_bridge.job_stem_path(job_id, "drums")
    assert drums_path is not None and drums_path.exists()

    zip_path = stem_separation_bridge.job_zip_path(job_id)
    assert zip_path is not None and zip_path.exists()
    import zipfile
    with zipfile.ZipFile(zip_path) as zf:
        assert set(zf.namelist()) == {f"{name}.wav" for name in stem_separation_bridge.STEM_NAMES}
        # Same fix as audiogen_bridge.py's chain: ZIP_STORED, not
        # ZIP_DEFLATED, so a near-silent stem can never trip
        # archive_safety.py's zip-bomb compression-ratio guard.
        for info in zf.infolist():
            assert info.compress_type == zipfile.ZIP_STORED


def test_enqueue_and_failure_flow(isolated_bridge, monkeypatch, tmp_path):
    def fake_separate_command(input_path, output_dir, *, model="htdemucs", timeout=900):
        return {"ok": False, "stderr": "model crashed", "result": {}}

    monkeypatch.setattr(stem_separation_bridge, "separate_command", fake_separate_command)

    data = _sample_wav_bytes(tmp_path)
    queued = stem_separation_bridge.enqueue_separation(data, "mix.wav")
    job_id = queued["job"]["id"]

    deadline = time.time() + 5
    job = {}
    while time.time() < deadline:
        job = stem_separation_bridge.job_status(job_id)
        if job["status"] == "failed":
            break
        time.sleep(0.02)

    assert job["status"] == "failed"
    assert "model crashed" in job["error"]
    assert stem_separation_bridge.job_stem_path(job_id, "drums") is None
    assert stem_separation_bridge.job_zip_path(job_id) is None


def test_job_stem_path_returns_none_for_unready_job(isolated_bridge, monkeypatch, tmp_path):
    # Never let the real subprocess-backed separate_command run in this unit
    # test -- block the worker on a lock so the job stays queued/running
    # long enough to observe the "not ready yet" state deterministically.
    import threading

    gate = threading.Event()

    def blocked_separate_command(input_path, output_dir, *, model="htdemucs", timeout=900):
        gate.wait(timeout=5)
        return {"ok": False, "result": {}}

    monkeypatch.setattr(stem_separation_bridge, "separate_command", blocked_separate_command)

    data = _sample_wav_bytes(tmp_path)
    result = stem_separation_bridge.enqueue_separation(data, "mix.wav")
    job_id = result["job"]["id"]
    try:
        assert stem_separation_bridge.job_stem_path(job_id, "drums") is None
    finally:
        gate.set()


def test_requests_automix_chain_detects_chaining_phrasing():
    # D3.3 (docs/KENN_FUTURE_PLAN.md Phase 3)
    assert stem_separation_bridge.requests_automix_chain(
        "separate this into stems, then automix it"
    ) is True
    assert stem_separation_bridge.requests_automix_chain("separate this and re-bake the mix") is True
    assert stem_separation_bridge.requests_automix_chain("separate this into stems") is False
    assert stem_separation_bridge.requests_automix_chain("") is False


def test_chain_to_automix_queues_a_real_automix_job_on_completion(isolated_bridge, monkeypatch, tmp_path):
    def fake_separate_command(input_path, output_dir, *, model="htdemucs", timeout=900):
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        stems = {}
        for name in stem_separation_bridge.STEM_NAMES:
            stem_path = output_dir / f"{name}.wav"
            stem_path.write_bytes(b"RIFF....WAVEfake")
            stems[name] = str(stem_path)
        return {"ok": True, "result": {"ok": True, "stems": stems, "model": model}}

    monkeypatch.setattr(stem_separation_bridge, "separate_command", fake_separate_command)

    captured = {}
    import types

    fake_audiogen_bridge = types.SimpleNamespace(
        queue_automix_from_stem_files=lambda **kwargs: (
            captured.update(kwargs) or {"ok": True, "job_id": "automix-job-1", "upload_id": "up-1"}
        )
    )
    monkeypatch.setitem(sys.modules, "audiogen_bridge", fake_audiogen_bridge)

    data = _sample_wav_bytes(tmp_path)
    queued = stem_separation_bridge.enqueue_separation(
        data, "mix.wav", project_id="proj-1", chain_to_automix=True, genre="techno",
    )
    job_id = queued["job"]["id"]

    deadline = time.time() + 5
    job = {}
    while time.time() < deadline:
        job = stem_separation_bridge.job_status(job_id)
        if job.get("automix_job_id"):
            break
        time.sleep(0.02)

    assert job["status"] == "completed"
    assert job["automix_job_id"] == "automix-job-1"
    assert captured["project_id"] == "proj-1"
    assert captured["genre"] == "techno"
    assert set(captured["stem_paths"]) == set(stem_separation_bridge.STEM_NAMES)


def test_chain_to_automix_is_not_attempted_when_not_requested(isolated_bridge, monkeypatch, tmp_path):
    def fake_separate_command(input_path, output_dir, *, model="htdemucs", timeout=900):
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        stem_path = output_dir / "drums.wav"
        stem_path.write_bytes(b"RIFF....WAVEfake")
        return {"ok": True, "result": {"ok": True, "stems": {"drums": str(stem_path)}, "model": model}}

    monkeypatch.setattr(stem_separation_bridge, "separate_command", fake_separate_command)

    def _fail_if_called(**kwargs):
        raise AssertionError("queue_automix_from_stem_files should never be reached")

    import types

    monkeypatch.setitem(
        sys.modules, "audiogen_bridge",
        types.SimpleNamespace(queue_automix_from_stem_files=_fail_if_called),
    )

    data = _sample_wav_bytes(tmp_path)
    queued = stem_separation_bridge.enqueue_separation(data, "mix.wav", project_id="proj-1")
    job_id = queued["job"]["id"]

    deadline = time.time() + 5
    job = {}
    while time.time() < deadline:
        job = stem_separation_bridge.job_status(job_id)
        if job["status"] == "completed":
            break
        time.sleep(0.02)

    assert job["status"] == "completed"
    assert job["automix_job_id"] == ""


def test_resolve_stem_files_for_project_reads_the_real_wav_bytes(isolated_bridge, monkeypatch, tmp_path):
    # G3 (docs/KENN_IMPROVEMENT_PLAN.md): a text-only "run automix on
    # this" chat trigger needs to resolve a stem set from a completed
    # separation job for the project, without a fresh attachment.
    def fake_separate_command(input_path, output_dir, *, model="htdemucs", timeout=900):
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        stems = {}
        for name in stem_separation_bridge.STEM_NAMES:
            stem_path = output_dir / f"{name}.wav"
            stem_path.write_bytes(f"RIFF-{name}".encode())
            stems[name] = str(stem_path)
        return {"ok": True, "result": {"ok": True, "stems": stems, "model": model}}

    monkeypatch.setattr(stem_separation_bridge, "separate_command", fake_separate_command)

    data = _sample_wav_bytes(tmp_path)
    queued = stem_separation_bridge.enqueue_separation(data, "mix.wav", project_id="proj-resolve")
    job_id = queued["job"]["id"]

    deadline = time.time() + 5
    while time.time() < deadline:
        if stem_separation_bridge.job_status(job_id)["status"] == "completed":
            break
        time.sleep(0.02)

    files = stem_separation_bridge.resolve_stem_files_for_project("proj-resolve")
    assert files is not None
    assert {name for _bytes, name in files} == {f"{n}.wav" for n in stem_separation_bridge.STEM_NAMES}
    drums_bytes = next(b for b, name in files if name == "drums.wav")
    assert drums_bytes == b"RIFF-drums"


def test_resolve_stem_files_for_project_returns_none_without_a_completed_job(isolated_bridge):
    assert stem_separation_bridge.resolve_stem_files_for_project("no-such-project") is None
