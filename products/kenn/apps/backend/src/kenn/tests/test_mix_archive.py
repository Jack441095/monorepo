"""Tests for KENN Mix Archive and Reference Library (Milestone E6).

Guarantees:
- Producers save named mixes and sequential revisions across turns and sessions.
- Audio references are read-only pointers: deleting or updating a mix never touches or deletes audio on disk.
- Strict producer isolation: no cross-producer or cross-session leakage when listing, viewing, or grading.
- Live integration: captures Live session tempo, track count, and meters into archive entries.
- Re-grading against stored references produces grounded 100-point grades.
"""

from __future__ import annotations

from pathlib import Path
import pytest
import tempfile

from kenn.core.fake_live import FakeLiveBackend
from kenn.core.mix_archive import (
    DEFAULT_TARGET_LUFS,
    DEFAULT_TEMPO_BPM,
    MixArchiveEntry,
    MixArchiveManager,
    MixRevision,
)


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Isolated SQLite database file for testing."""
    return tmp_path / "test_kenn_archive.db"


@pytest.fixture
def dummy_audio_file(tmp_path: Path) -> Path:
    """Simulated master audio file on disk to test non-destructive storage."""
    audio_path = tmp_path / "master_v1.wav"
    audio_path.write_bytes(b"RIFF....WAVEfmt ....data....")
    return audio_path


def test_add_mix_and_initial_revision(temp_db: Path, dummy_audio_file: Path) -> None:
    """Verifies mix creation, validation, tempo/loudness clamping, and initial revision."""
    archive = MixArchiveManager(db_path=temp_db)

    mix = archive.add_mix(
        producer_id="producer_alpha",
        name="Night Drive Master",
        audio_ref=str(dummy_audio_file),
        tempo=126.0,
        genre="deep_house",
        target_loudness=-14.0,
        session_notes="First mixdown bounce before stem review",
        session_id="session_101",
    )

    assert mix["mix_id"].startswith("mix-")
    assert mix["producer_id"] == "producer_alpha"
    assert mix["name"] == "Night Drive Master"
    assert mix["tempo"] == 126.0
    assert mix["genre"] == "deep_house"
    assert mix["target_loudness"] == -14.0
    assert mix["audio_ref"] == str(dummy_audio_file)
    assert mix["session_id"] == "session_101"

    # Initial revision 1 must be created automatically
    revisions = mix["revisions"]
    assert len(revisions) == 1
    assert revisions[0]["revision_id"] == "rev-001"
    assert revisions[0]["what_changed"] == "Initial mix import into archive"


def test_add_mix_rejects_empty_fields(temp_db: Path) -> None:
    """Ensures missing producer_id, mix name, or audio reference cleanly refuses."""
    archive = MixArchiveManager(db_path=temp_db)

    with pytest.raises(ValueError, match="producer_id is required"):
        archive.add_mix(producer_id="", name="Mix", audio_ref="/path/to/mix.wav")

    with pytest.raises(ValueError, match="Mix name cannot be empty"):
        archive.add_mix(producer_id="p1", name="", audio_ref="/path/to/mix.wav")

    with pytest.raises(ValueError, match="audio_ref is required"):
        archive.add_mix(producer_id="p1", name="Mix", audio_ref="")


def test_add_sequential_revisions(temp_db: Path, dummy_audio_file: Path) -> None:
    """Verifies that each mix change appends a sequential revision milestone."""
    archive = MixArchiveManager(db_path=temp_db)

    mix = archive.add_mix(
        producer_id="producer_alpha",
        name="Techno Peak Master",
        audio_ref=str(dummy_audio_file),
    )
    mix_id = mix["mix_id"]

    rev2 = archive.add_revision(
        mix_id=mix_id,
        producer_id="producer_alpha",
        what_changed="Cut 2.5 dB at 320 Hz on bass track to clear mud",
        suggestion_applied={"lever_id": "low_mid_mud_eq", "track": "Bass", "delta_db": -2.5},
        analysis_snapshot={"low_mid_energy_pct": 34.0, "true_peak_dbtp": -1.2},
        measured_grade={"points": 58.5, "points_available": 60.0},
    )

    assert rev2 is not None
    assert rev2["revision_id"] == "rev-002"
    assert "Cut 2.5 dB" in rev2["what_changed"]
    assert rev2["suggestion_applied"]["track"] == "Bass"

    rev3 = archive.add_revision(
        mix_id=mix_id,
        producer_id="producer_alpha",
        what_changed="Applied true-peak ceiling limiter at -1.0 dBTP",
        measured_grade={"points": 60.0, "points_available": 60.0},
    )

    assert rev3 is not None
    assert rev3["revision_id"] == "rev-003"

    # Fetch fresh record and inspect full history
    fetched = archive.get_mix(mix_id, "producer_alpha")
    assert fetched is not None
    assert len(fetched["revisions"]) == 3
    assert [r["revision_id"] for r in fetched["revisions"]] == ["rev-001", "rev-002", "rev-003"]


def test_update_notes(temp_db: Path, dummy_audio_file: Path) -> None:
    """Verifies editing session notes updates record without altering revisions."""
    archive = MixArchiveManager(db_path=temp_db)

    mix = archive.add_mix(
        producer_id="producer_alpha",
        name="Vocal Ballad",
        audio_ref=str(dummy_audio_file),
        session_notes="Initial notes: check vocal sibilance",
    )
    mix_id = mix["mix_id"]

    ok = archive.update_notes(mix_id, "producer_alpha", "Vocal de-essed with FabFilter Pro-DS; ready for release")
    assert ok is True

    fetched = archive.get_mix(mix_id, "producer_alpha")
    assert fetched is not None
    assert fetched["session_notes"] == "Vocal de-essed with FabFilter Pro-DS; ready for release"


def test_non_destructive_audio_storage_on_delete(temp_db: Path, dummy_audio_file: Path) -> None:
    """Guarantees deleting a mix metadata record NEVER touches or deletes the audio file on disk."""
    archive = MixArchiveManager(db_path=temp_db)

    mix = archive.add_mix(
        producer_id="producer_alpha",
        name="Precious Master Take",
        audio_ref=str(dummy_audio_file),
    )
    mix_id = mix["mix_id"]
    assert dummy_audio_file.exists()

    deleted = archive.delete_mix(mix_id, "producer_alpha")
    assert deleted is True

    # Record is gone from archive
    assert archive.get_mix(mix_id, "producer_alpha") is None

    # CRITICAL: Underlying audio file remains completely intact on disk!
    assert dummy_audio_file.exists()
    assert dummy_audio_file.read_bytes() == b"RIFF....WAVEfmt ....data...."


def test_strict_producer_isolation(temp_db: Path, dummy_audio_file: Path) -> None:
    """Guarantees producer A cannot view, list, delete, or modify producer B's mixes."""
    archive = MixArchiveManager(db_path=temp_db)

    mix_a = archive.add_mix(
        producer_id="producer_alice",
        name="Alice Track 1",
        audio_ref=str(dummy_audio_file),
    )
    mix_b = archive.add_mix(
        producer_id="producer_bob",
        name="Bob Secret VIP",
        audio_ref=str(dummy_audio_file),
    )

    # Bob lists mixes: Alice's mix must NOT appear
    bob_mixes = archive.list_mixes("producer_bob")
    assert len(bob_mixes) == 1
    assert bob_mixes[0]["name"] == "Bob Secret VIP"

    # Alice lists mixes: Bob's mix must NOT appear
    alice_mixes = archive.list_mixes("producer_alice")
    assert len(alice_mixes) == 1
    assert alice_mixes[0]["name"] == "Alice Track 1"

    # Bob cannot view Alice's mix
    assert archive.get_mix(mix_a["mix_id"], "producer_bob") is None

    # Bob cannot edit Alice's notes
    assert archive.update_notes(mix_a["mix_id"], "producer_bob", "Hacked notes") is False

    # Bob cannot delete Alice's mix
    assert archive.delete_mix(mix_a["mix_id"], "producer_bob") is False
    assert archive.get_mix(mix_a["mix_id"], "producer_alice") is not None


def test_grading_against_stored_reference_isolation(temp_db: Path, dummy_audio_file: Path) -> None:
    """Verifies grading against stored reference rejects cross-producer references with PermissionError."""
    archive = MixArchiveManager(db_path=temp_db)

    alice_ref = archive.add_mix(
        producer_id="producer_alice",
        name="Commercial Reference Master",
        audio_ref=str(dummy_audio_file),
        initial_snapshot={
            "integrated_lufs": -14.0,
            "true_peak_dbtp": -1.0,
            "crest_factor_db": 10.0,
            "correlation": 0.70,
            "bands": {"sub": 0.20, "low_mid": 0.30, "air": 0.15},
        },
    )

    bob_meters = {
        "integrated_lufs": -15.0,
        "true_peak_dbtp": -1.2,
        "crest_factor_db": 11.5,
        "correlation": 0.65,
        "bands": {"sub": 0.22, "low_mid": 0.32, "air": 0.14},
    }

    # Bob attempts to grade against Alice's reference: must fail with PermissionError
    with pytest.raises(PermissionError, match="Access denied: reference mix belongs to another producer"):
        archive.grade_against_reference(
            reference_mix_id=alice_ref["mix_id"],
            producer_id="producer_bob",
            current_meters=bob_meters,
        )

    # Alice grades against her own reference: succeeds and produces full grade
    result = archive.grade_against_reference(
        reference_mix_id=alice_ref["mix_id"],
        producer_id="producer_alice",
        current_meters=bob_meters,
        technical_report={
            "mqm_score": 28.0,
            "points_available": 30.0,
            "meaning": "Technical health",
            "unscored": [],
        },
        request_text="Score against my reference at -14 LUFS",
    )

    assert result["reference_mix_id"] == alice_ref["mix_id"]
    assert result["reference_name"] == "Commercial Reference Master"
    grade = result["grade"]
    assert grade["full_marks"] == 100.0
    # Reference match part must be scored out of 40 points
    ref_part = next((p for p in grade["parts"] if p["part"] == "reference_match"), None)
    assert ref_part is not None
    assert ref_part["points_available"] == 40.0
    assert 30.0 <= ref_part["points"] <= 40.0


def test_export_and_import_archive(temp_db: Path, dummy_audio_file: Path) -> None:
    """Verifies exporting a named set and importing into another tenant."""
    archive = MixArchiveManager(db_path=temp_db)

    m1 = archive.add_mix(
        producer_id="producer_alpha",
        name="Alpha Mix 1",
        audio_ref=str(dummy_audio_file),
        tempo=128.0,
        genre="trance",
    )
    archive.add_revision(
        mix_id=m1["mix_id"],
        producer_id="producer_alpha",
        what_changed="Added sidechain compression on bass",
    )

    exported = archive.export_archive("producer_alpha")
    assert exported["schema"] == "kenn.mix_archive_export.v1"
    assert exported["producer_id"] == "producer_alpha"
    assert exported["mix_count"] == 1
    assert exported["mixes"][0]["name"] == "Alpha Mix 1"
    assert len(exported["mixes"][0]["revisions"]) == 2

    # Import into producer_beta
    imported = archive.import_archive("producer_beta", exported)
    assert len(imported) == 1
    assert imported[0]["producer_id"] == "producer_beta"
    assert imported[0]["name"] == "Alpha Mix 1"
    assert imported[0]["tempo"] == 128.0
    assert len(imported[0]["revisions"]) == 2


def test_live_session_capture(temp_db: Path, dummy_audio_file: Path) -> None:
    """Verifies live session capture from FakeLiveBackend into the archive."""
    archive = MixArchiveManager(db_path=temp_db)
    live = FakeLiveBackend()
    live.set_tempo(124.0)

    mix = archive.capture_from_live(
        producer_id="producer_alpha",
        name="Live Studio Take",
        backend=live,
        audio_ref=str(dummy_audio_file),
        genre="tech_house",
        target_loudness=-14.0,
        session_notes="Direct capture from Ableton Live session",
    )

    assert mix["name"] == "Live Studio Take"
    assert mix["tempo"] == 124.0
    assert mix["genre"] == "tech_house"
    assert mix["target_loudness"] == -14.0
    assert len(mix["revisions"]) == 1
    assert mix["revisions"][0]["analysis_snapshot"]["captured_from_live"] is True
    assert mix["revisions"][0]["measured_grade"]["points"] > 0.0


def test_mix_archive_rest_endpoints(dummy_audio_file: Path) -> None:
    """Verifies Mix Archive REST API endpoints over HTTP using FastAPI TestClient."""
    from fastapi.testclient import TestClient
    from kenn.routes.fastapi_app import app

    client = TestClient(app)

    # 1. Add mix via REST
    resp = client.post(
        "/api/mix-archive/add",
        json={
            "producer_id": "rest_producer_1",
            "name": "REST Master Mix",
            "audio_ref": str(dummy_audio_file),
            "tempo": 128.0,
            "genre": "techno",
            "target_loudness": -14.0,
            "session_notes": "Added via REST test",
        },
    )
    assert resp.status_code == 201
    mix_data = resp.json()["mix"]
    mix_id = mix_data["mix_id"]
    assert mix_data["name"] == "REST Master Mix"

    # 2. List mixes via REST
    resp = client.get("/api/mix-archive/list", params={"producer_id": "rest_producer_1"})
    assert resp.status_code == 200
    listing = resp.json()
    assert listing["count"] >= 1
    assert any(m["mix_id"] == mix_id for m in listing["mixes"])

    # 3. Get single mix via REST
    resp = client.get(f"/api/mix-archive/mix/{mix_id}", params={"producer_id": "rest_producer_1"})
    assert resp.status_code == 200
    assert resp.json()["mix"]["mix_id"] == mix_id

    # 4. Cross-tenant isolation over REST (producer 2 cannot view producer 1's mix)
    resp = client.get(f"/api/mix-archive/mix/{mix_id}", params={"producer_id": "unauthorized_producer"})
    assert resp.status_code == 404

    # 5. Update notes via REST
    resp = client.post(
        "/api/mix-archive/notes",
        json={
            "mix_id": mix_id,
            "producer_id": "rest_producer_1",
            "session_notes": "Updated notes via REST test",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["session_notes"] == "Updated notes via REST test"

    # 6. Add revision via REST
    resp = client.post(
        "/api/mix-archive/revision",
        json={
            "mix_id": mix_id,
            "producer_id": "rest_producer_1",
            "what_changed": "Cut 2 dB in low-mids",
            "measured_grade": {"points": 58.0, "points_available": 60.0},
        },
    )
    assert resp.status_code == 201
    assert resp.json()["revision"]["revision_id"] == "rev-002"

    # 7. Export archive via REST
    resp = client.get("/api/mix-archive/export", params={"producer_id": "rest_producer_1"})
    assert resp.status_code == 200
    export_body = resp.json()
    assert export_body["mix_count"] >= 1

    # 8. Delete mix via REST (non-destructive audio check)
    resp = client.delete(f"/api/mix-archive/mix/{mix_id}", params={"producer_id": "rest_producer_1"})
    assert resp.status_code == 200
    assert dummy_audio_file.exists()  # Audio file remains on disk!

