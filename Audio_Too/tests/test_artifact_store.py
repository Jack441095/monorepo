"""Content-addressing, idempotency, lineage, and integrity tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server" / "app"))

import artifact_store  # noqa: E402
import db  # noqa: E402


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "audio_too.db")
    monkeypatch.setattr(db, "AGENT_DATA", tmp_path / "legacy-json")
    monkeypatch.setattr(db, "_migration_done", False)
    monkeypatch.setattr(artifact_store, "ARTIFACT_ROOT", tmp_path / "artifacts")
    artifact_store.reset_connection_state()
    artifact_store.ensure_schema()
    yield tmp_path
    artifact_store.reset_connection_state()


def register(path: Path, **overrides) -> dict:
    values = {
        "kind": "audio.generated.loop",
        "media_type": "audio/wav",
        "producer": "audiogen",
        "producer_version": "1.0.0",
        "project_id": "project-1",
        "source_uri": "/portfolio/audio/example.wav",
        "metadata": {"emotion": "joy"},
    }
    values.update(overrides)
    return artifact_store.register_file(path, **values)


def test_registration_uses_content_addressed_private_blob(store: Path) -> None:
    source = store / "source.wav"
    source.write_bytes(b"RIFF-audio-data")

    item = register(source)
    managed = artifact_store.resolve_path(item["id"])

    assert managed.read_bytes() == source.read_bytes()
    assert managed.parent.parent.name == "sha256"
    assert managed.name == item["content_hash"].removeprefix("sha256:")[2:]
    assert managed.stat().st_mode & 0o777 == 0o600
    assert artifact_store.ARTIFACT_ROOT.stat().st_mode & 0o777 == 0o700
    assert managed.parent.stat().st_mode & 0o777 == 0o700
    assert artifact_store.verify(item["id"])["ok"] is True


def test_blob_bytes_deduplicate_without_merging_logical_artifacts(store: Path) -> None:
    first_path = store / "first.wav"
    second_path = store / "second.wav"
    first_path.write_bytes(b"same audio")
    second_path.write_bytes(b"same audio")

    first = register(first_path, external_key="render:one")
    second = register(second_path, external_key="render:two")

    assert first["id"] != second["id"]
    assert first["content_hash"] == second["content_hash"]
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM artifact_blobs").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0] == 2


def test_external_key_is_idempotent_but_rejects_changed_content(store: Path) -> None:
    source = store / "source.wav"
    source.write_bytes(b"version one")
    first = register(source, external_key="audiogen-job:abc")
    repeat = register(source, external_key="audiogen-job:abc")
    assert repeat["id"] == first["id"]

    source.write_bytes(b"version two")
    with pytest.raises(artifact_store.ArtifactError, match="different content"):
        register(source, external_key="audiogen-job:abc")


def test_lineage_requires_existing_parents_and_round_trips_as_contract(store: Path) -> None:
    source = store / "source.wav"
    child_path = store / "child.wav"
    source.write_bytes(b"source")
    child_path.write_bytes(b"derived")
    parent = register(source, kind="audio.source")

    child = register(child_path, parent_ids=(parent["id"],))
    public = artifact_store.public_record(child)

    assert child["parent_ids"] == (parent["id"],)
    assert public["parent_ids"] == [parent["id"]]
    assert public["uri"] == f"artifact://{child['id']}"
    assert "storage_path" not in public

    with pytest.raises(artifact_store.MissingParentArtifact):
        register(child_path, external_key="missing-parent", parent_ids=("art_missing",))


def test_integrity_check_detects_blob_tampering(store: Path) -> None:
    source = store / "source.wav"
    source.write_bytes(b"trusted bytes")
    item = register(source)
    artifact_store.resolve_path(item["id"]).write_bytes(b"tampered")

    report = artifact_store.verify(item["id"])
    assert report["ok"] is False
    assert "integrity" in report["error"].lower()


def test_project_listing_and_external_metadata_do_not_expose_storage_path(store: Path) -> None:
    source = store / "source.wav"
    source.write_bytes(b"audio")
    item = register(source)

    listed = artifact_store.list_for_project("project-1")
    assert [entry["id"] for entry in listed] == [item["id"]]
    assert artifact_store.public_record(listed[0])["project_id"] == "project-1"
    assert "storage_path" not in artifact_store.public_record(listed[0])


def test_symbolic_link_sources_are_rejected(store: Path) -> None:
    source = store / "source.wav"
    link = store / "link.wav"
    source.write_bytes(b"audio")
    link.symlink_to(source)

    with pytest.raises(artifact_store.ArtifactError, match="symbolic link"):
        register(link)


def test_prepared_blob_can_rollback_with_callers_transaction(store: Path) -> None:
    source = store / "source.wav"
    source.write_bytes(b"transactional audio")
    prepared = artifact_store.prepare_blob(source)

    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        artifact_store.register_prepared(
            conn,
            prepared,
            kind="audio.source.upload",
            media_type="audio/wav",
            producer="stem-upload",
            producer_version="1.0.0",
            external_key="stem-upload:rollback",
        )
        conn.rollback()

    assert artifact_store.discard_unreferenced_blob(prepared) is True
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM artifact_blobs").fetchone()[0] == 0
    assert not (artifact_store.ARTIFACT_ROOT / prepared.storage_path).exists()
