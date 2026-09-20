"""Tests for the typed reference-upload service (stem_uploads.store_reference).

Verifies the properties the raw route write lacked: source-artifact registration,
a `reference.uploaded` domain event, idempotent replay, atomic replacement (a
single canonical file survives), and typed validation — all in one transaction.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest

WEBSITE = Path(__file__).resolve().parent.parent / "server" / "app"
if str(WEBSITE) not in sys.path:
    sys.path.insert(0, str(WEBSITE))

import artifact_store  # noqa: E402
import db  # noqa: E402
import stem_uploads  # noqa: E402


def _wav_bytes(n_samples: int = 64) -> bytes:
    data = (b"\x01\x00") * n_samples
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(data), b"WAVE", b"fmt ", 16, 1, 1, 44100, 88200, 2, 16, b"data", len(data),
    )
    return header + data


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(stem_uploads, "UPLOAD_ROOT", tmp_path / "uploads")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "audio_too.db")
    monkeypatch.setattr(db, "AGENT_DATA", tmp_path / "legacy-json")
    monkeypatch.setattr(db, "_migration_done", False)
    monkeypatch.setattr(artifact_store, "ARTIFACT_ROOT", tmp_path / "artifacts")
    artifact_store.reset_connection_state()
    db.init_db()
    stem_uploads.init_uploads_table()
    yield tmp_path
    artifact_store.reset_connection_state()


def _ref_events(project_id: str) -> list[dict]:
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT * FROM domain_events WHERE event_type = 'reference.uploaded' AND aggregate_id = ?",
            (project_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def test_registers_artifact_and_emits_event(env):
    status, result = stem_uploads.store_reference("proj01", _wav_bytes(), "ref.wav")
    assert status == 200
    assert result["artifact"]["kind"] == "audio.source.reference"
    assert (stem_uploads.UPLOAD_ROOT / "proj01" / "reference" / "reference.wav").exists()
    assert len(_ref_events("proj01")) == 1


def test_second_upload_replaces_file_and_registers_new_artifact(env):
    stem_uploads.store_reference("proj01", _wav_bytes(64), "ref.wav")
    stem_uploads.store_reference("proj01", _wav_bytes(128), "ref.wav")
    ref_dir = stem_uploads.UPLOAD_ROOT / "proj01" / "reference"
    canonical = list(ref_dir.glob("reference.*"))
    assert len(canonical) == 1  # single canonical file survives
    assert len(_ref_events("proj01")) == 2  # each upload is a distinct artifact


def test_idempotent_replay_does_not_duplicate(env):
    wav = _wav_bytes()
    _, r1 = stem_uploads.store_reference("proj01", wav, "ref.wav", idempotency_key="k1")
    _, r2 = stem_uploads.store_reference("proj01", wav, "ref.wav", idempotency_key="k1")
    assert r2["artifact"]["artifact_id"] == r1["artifact"]["artifact_id"]
    assert len(_ref_events("proj01")) == 1


def test_invalid_reference_rejected(env):
    with pytest.raises(ValueError):
        stem_uploads.store_reference("proj01", b"", "ref.wav")  # empty
    with pytest.raises(ValueError):
        stem_uploads.store_reference("proj01", _wav_bytes(), "ref.txt")  # bad type
