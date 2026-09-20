"""Tests for the Automix GET and POST API endpoints."""

from __future__ import annotations

import sys
import json
import importlib.util
import wave
from pathlib import Path
from io import BytesIO
import pytest

ROOT = Path(__file__).resolve().parent.parent.parent

# Dynamically import app's server.py
website_server_path = ROOT / "server" / "app" / "server.py"
spec = importlib.util.spec_from_file_location("website_server", str(website_server_path))
website_server = importlib.util.module_from_spec(spec)
sys.modules["website_server"] = website_server
spec.loader.exec_module(website_server)

# Ensure paths are set up
if str(ROOT / "server" / "app") not in sys.path:
    sys.path.insert(0, str(ROOT / "server" / "app"))
if str(ROOT / "studio" / "audio_analysis") not in sys.path:
    sys.path.insert(0, str(ROOT / "studio" / "audio_analysis"))

import db
import automix_jobs
import automix_worker
import session_auth
import stem_uploads

REAL_REQUIRE_SOURCE_READY = stem_uploads.require_source_ready


class MockHandler(website_server.Handler):
    def __init__(self, path: str, method: str = "GET", body: bytes = b"", is_authorized: bool = True):
        self.path = path
        self.command = method
        self.headers = {
            "Content-Length": str(len(body)),
            "Content-Type": "application/json"
        }
        self.rfile = BytesIO(body)
        self.is_authorized = is_authorized
        self.status = 0
        self.payload = {}
        self.response_bytes = b""
        self.content_type = ""
        self.filename = ""

    def content_length(self) -> int:
        return int(self.headers.get("Content-Length", "0"))

    def read_body_bytes(self) -> bytes:
        return self.rfile.read()

    def require_auth(self) -> bool:
        if self.is_authorized:
            return True
        self.send_json(401, {"error": "Dashboard password required."})
        return False

    def require_private_post(self) -> bool:
        return self.require_auth()

    def send_json(self, status: int, payload: dict) -> None:
        self.status = status
        self.payload = payload

    def send_bytes(self, status: int, body: bytes, content_type: str, *, filename: str = "") -> None:
        self.status = status
        self.response_bytes = body
        self.content_type = content_type
        self.filename = filename

    def send_file(self, path: Path, content_type: str, *, filename: str = "") -> None:
        self.send_bytes(200, path.read_bytes(), content_type, filename=filename)

    def read_json_body(self) -> dict:
        return json.loads(self.read_body_bytes().decode("utf-8"))


@pytest.fixture
def setup_db(monkeypatch, tmp_path):
    # Patch database path to temporary database
    db_file = tmp_path / "audio_too.db"
    monkeypatch.setattr(db, "DB_PATH", db_file)
    db.init_db()
    
    # Patch BUSINESS_ROOT and static paths if needed
    monkeypatch.setattr(website_server, "BUSINESS_ROOT", tmp_path)
    monkeypatch.setattr(
        stem_uploads,
        "require_source_ready",
        lambda project_id, **kwargs: {
            "ready": True,
            "project_id": project_id,
            "file_count": 1,
            "total_bytes": 1024,
        },
    )
    return tmp_path


def test_automix_start_and_status(setup_db) -> None:
    # 1. Post request to start automix job
    body = json.dumps({
        "project_id": "test_project_123",
        "genre": "edm",
        "style_prefs": {"bright_warm": 0.7, "compressed_dynamic": 0.8}
    }).encode("utf-8")
    
    handler = MockHandler("/api/automix/start", method="POST", body=body)
    website_server.Handler.do_POST(handler)
    
    assert handler.status == 200
    assert handler.payload["ok"] is True
    job_id = handler.payload["job_id"]
    assert job_id is not None
    assert handler.payload["status"] == "queued"

    # 2. Get request to poll status
    handler_status = MockHandler(f"/api/automix/status?id={job_id}", method="GET")
    website_server.Handler.do_GET(handler_status)
    
    assert handler_status.status == 200
    assert handler_status.payload["id"] == job_id
    assert handler_status.payload["project_id"] == "test_project_123"
    assert handler_status.payload["status"] == "queued"
    assert handler_status.payload["genre"] == "edm"
    assert handler_status.payload["iteration_count"] == 0
    assert handler_status.payload["history"] == [
        {"status": "queued", "message": "", "created_at": handler_status.payload["created_at"]}
    ]


def test_automix_start_derives_correlation_id_by_default(setup_db) -> None:
    """A job started without an explicit correlation_id gets the legacy
    job-derived id, matching pre-migration behavior for every existing caller."""
    body = json.dumps({"project_id": "test_project_corr1", "genre": "pop"}).encode("utf-8")
    handler = MockHandler("/api/automix/start", method="POST", body=body)
    website_server.Handler.do_POST(handler)
    assert handler.status == 200
    job_id = handler.payload["job_id"]

    with db.connect() as conn:
        row = conn.execute(
            "SELECT correlation_id FROM automix_jobs WHERE id = ?", (job_id,)
        ).fetchone()
    assert row["correlation_id"] == f"automix-job:{job_id}"
    assert automix_jobs.job_correlation_id(conn, job_id) == f"automix-job:{job_id}"


def test_automix_start_accepts_explicit_correlation_id(setup_db) -> None:
    """A caller (Thursday's command_gateway, or a direct HTTP client) that
    supplies its own trace id has it stored verbatim, so downstream worker/
    advisor/feedback domain events can be correlated back to it."""
    body = json.dumps({
        "project_id": "test_project_corr2",
        "genre": "pop",
        "correlation_id": "thursday-cmd:req-42",
    }).encode("utf-8")
    handler = MockHandler("/api/automix/start", method="POST", body=body)
    website_server.Handler.do_POST(handler)
    assert handler.status == 200
    job_id = handler.payload["job_id"]

    with db.connect() as conn:
        row = conn.execute(
            "SELECT correlation_id FROM automix_jobs WHERE id = ?", (job_id,)
        ).fetchone()
    assert row["correlation_id"] == "thursday-cmd:req-42"
    assert automix_jobs.job_correlation_id(conn, job_id) == "thursday-cmd:req-42"


def test_job_correlation_id_falls_back_for_unknown_job(setup_db) -> None:
    with db.connect() as conn:
        assert automix_jobs.job_correlation_id(conn, "no-such-job") == "automix-job:no-such-job"


def test_versioned_automix_job_alias_uses_same_contract(setup_db) -> None:
    body = json.dumps(
        {"project_id": "versioned-project", "genre": "pop", "style_prefs": {"warm": 0.5}}
    ).encode()
    create = MockHandler("/api/v1/automix/jobs", method="POST", body=body)

    website_server.Handler.do_POST(create)

    assert create.status == 200
    assert create.payload["status"] == "queued"
    status = MockHandler(f"/api/v1/automix/jobs?id={create.payload['job_id']}")
    website_server.Handler.do_GET(status)
    assert status.status == 200
    assert status.payload["project_id"] == "versioned-project"


def test_job_rejects_invalid_musical_role_correction_before_queue(setup_db) -> None:
    body = json.dumps({
        "project_id": "role-project",
        "style_prefs": {
            "musical_role_corrections": {
                "Lead.wav": {"role": "magic", "priority": "foreground"}
            }
        },
    }).encode()
    handler = MockHandler("/api/v1/automix/jobs", method="POST", body=body)

    website_server.Handler.do_POST(handler)

    assert handler.status == 400
    assert handler.payload["code"] == "invalid_musical_role_correction"
    with db.connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM automix_jobs WHERE project_id = 'role-project'"
        ).fetchone()[0] == 0


def test_job_rejects_invalid_arrangement_correction_before_queue(setup_db) -> None:
    body = json.dumps({
        "project_id": "arrangement-project",
        "style_prefs": {
            "arrangement_corrections": {
                "schema": "audio-too.arrangement-correction.v1",
                "sections": [
                    {"start_seconds": 0.0, "end_seconds": 1.0,
                     "active_stems": ["Kick.wav"]},
                    {"start_seconds": 1.2, "end_seconds": 2.0,
                     "active_stems": ["Kick.wav", "Bass.wav"]},
                ],
            }
        },
    }).encode()
    handler = MockHandler("/api/v1/automix/jobs", method="POST", body=body)

    website_server.Handler.do_POST(handler)

    assert handler.status == 400
    assert handler.payload["code"] == "invalid_arrangement_correction"
    with db.connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM automix_jobs WHERE project_id = 'arrangement-project'"
        ).fetchone()[0] == 0


def test_job_accepts_and_normalizes_complete_arrangement_correction(setup_db) -> None:
    correction = {
        "schema": "audio-too.arrangement-correction.v1",
        "sections": [
            {"start_seconds": 0, "end_seconds": 1,
             "active_stems": ["Vocal.wav", "Kick.wav"]},
            {"start_seconds": 1, "end_seconds": 2, "active_stems": ["Kick.wav"]},
        ],
    }
    handler = MockHandler(
        "/api/v1/automix/jobs",
        method="POST",
        body=json.dumps({
            "project_id": "arrangement-project",
            "style_prefs": {"arrangement_corrections": correction},
        }).encode(),
    )

    website_server.Handler.do_POST(handler)

    assert handler.status == 200
    with db.connect() as conn:
        stored = json.loads(conn.execute(
            "SELECT style_prefs FROM automix_jobs WHERE id = ?", (handler.payload["job_id"],)
        ).fetchone()[0])
    normalized = stored["arrangement_corrections"]
    assert normalized["sections"][0] == {
        "start_seconds": 0.0,
        "end_seconds": 1.0,
        "active_stems": ["Kick.wav", "Vocal.wav"],
    }


def test_versioned_role_correction_privacy_deletion_is_idempotent(setup_db) -> None:
    handler = MockHandler(
        "/api/v1/automix/musical-role-corrections/deletions",
        method="POST",
        body=json.dumps({"project_id": "role-project"}).encode(),
    )

    website_server.Handler.do_POST(handler)

    assert handler.status == 200
    assert handler.payload == {
        "ok": True,
        "project_id": "role-project",
        "deleted": 0,
    }


def test_queue_health_reports_blocked_and_ready_jobs_without_mutation(
    setup_db, monkeypatch
) -> None:
    upload_root = setup_db / "data" / "stem_uploads"
    ready_dir = upload_root / "ready-project"
    ready_dir.mkdir(parents=True)
    audio = BytesIO()
    with wave.open(audio, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8_000)
        wav.writeframes(b"\0\0" * 80)
    (ready_dir / "stem.wav").write_bytes(audio.getvalue())
    monkeypatch.setattr(stem_uploads, "UPLOAD_ROOT", upload_root)
    timestamp = db.now()
    with db.connect() as conn:
        for job_id, project_id in (("ready-job", "ready-project"), ("blocked-job", "empty-project")):
            conn.execute(
                """INSERT INTO automix_jobs
                   (id, project_id, status, genre, style_prefs, error_message, result_path,
                    created_at, updated_at) VALUES (?, ?, 'queued', 'pop', '{}', '', '', ?, ?)""",
                (job_id, project_id, timestamp, timestamp),
            )
        conn.commit()

    handler = MockHandler("/api/v1/automix/queue-health")
    website_server.Handler.do_GET(handler)

    assert handler.status == 200
    assert handler.payload["active_jobs"] == 2
    assert handler.payload["ready_jobs"] == 1
    assert handler.payload["blocked_jobs"] == 1
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM automix_jobs WHERE status = 'queued'").fetchone()[0] == 2


def test_automix_job_creation_is_idempotent(setup_db) -> None:
    body = json.dumps({"project_id": "retry-project", "genre": "pop"}).encode()
    first = MockHandler("/api/v1/automix/jobs", method="POST", body=body)
    first.headers["Idempotency-Key"] = "job-request-1"
    second = MockHandler("/api/v1/automix/jobs", method="POST", body=body)
    second.headers["Idempotency-Key"] = "job-request-1"

    website_server.Handler.do_POST(first)
    website_server.Handler.do_POST(second)

    assert first.status == second.status == 200
    assert first.payload == second.payload
    with db.connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM automix_jobs WHERE project_id = 'retry-project'"
        ).fetchone()[0] == 1


def test_idempotency_key_rejects_different_request(setup_db) -> None:
    first = MockHandler(
        "/api/v1/automix/jobs",
        method="POST",
        body=json.dumps({"project_id": "project-a"}).encode(),
    )
    first.headers["Idempotency-Key"] = "reused-key"
    conflict = MockHandler(
        "/api/v1/automix/jobs",
        method="POST",
        body=json.dumps({"project_id": "project-b"}).encode(),
    )
    conflict.headers["Idempotency-Key"] = "reused-key"

    website_server.Handler.do_POST(first)
    website_server.Handler.do_POST(conflict)

    assert first.status == 200
    assert conflict.status == 409
    assert conflict.payload["code"] == "idempotency_conflict"


def test_automix_revision_creation_is_idempotent(setup_db) -> None:
    timestamp = db.now()
    with db.connect() as conn:
        conn.execute(
            """INSERT INTO automix_jobs
               (id, project_id, status, genre, style_prefs, error_message, result_path,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "completed-job",
                "revision-project",
                "complete",
                "rock",
                "{}",
                "",
                "/tmp/result.zip",
                timestamp,
                timestamp,
            ),
        )
        conn.commit()

    body = json.dumps(
        {"project_id": "revision-project", "feedback": "Bring the vocal forward"}
    ).encode()
    first = MockHandler("/api/v1/automix/revisions", method="POST", body=body)
    first.headers["Idempotency-Key"] = "revision-request-1"
    replay = MockHandler("/api/v1/automix/revisions", method="POST", body=body)
    replay.headers["Idempotency-Key"] = "revision-request-1"

    website_server.Handler.do_POST(first)
    website_server.Handler.do_POST(replay)

    assert first.status == replay.status == 200
    assert first.payload == replay.payload
    with db.connect() as conn:
        assert conn.execute(
            """SELECT COUNT(*) FROM automix_jobs
               WHERE project_id = 'revision-project' AND status = 'queued'"""
        ).fetchone()[0] == 1


def test_openapi_discovery_requires_dashboard_auth() -> None:
    unauthorized = MockHandler("/api/v1/openapi.json", is_authorized=False)
    website_server.Handler.do_GET(unauthorized)
    assert unauthorized.status == 401

    authorized = MockHandler("/api/v1/openapi.json")
    website_server.Handler.do_GET(authorized)
    assert authorized.status == 200
    assert authorized.payload["openapi"] == "3.1.0"


def test_worker_timeout_terminates_process_and_fails_job(monkeypatch) -> None:
    updates = []

    class HungProcess:
        exitcode = None

        def __init__(self, **kwargs):
            self.terminated = False

        def start(self):
            pass

        def join(self, timeout=None):
            pass

        def is_alive(self):
            return not self.terminated

        def terminate(self):
            self.terminated = True

    monkeypatch.setattr(
        automix_worker,
        "_update_job_status",
        lambda job_id, status, **kwargs: updates.append((job_id, status, kwargs)),
    )

    completed = automix_worker._run_job_with_timeout(
        {"id": "hung-job"},
        timeout_seconds=0.01,
        process_factory=HungProcess,
    )

    assert completed is False
    assert updates[0][0:2] == ("hung-job", "failed")
    assert "processing limit" in updates[0][2]["error_message"]


def test_worker_status_transitions_are_persisted(setup_db, monkeypatch) -> None:
    monkeypatch.setattr(automix_worker, "connect", db.connect)
    monkeypatch.setattr(automix_worker, "now", db.now)
    timestamp = db.now()
    with db.connect() as conn:
        conn.execute(
            """INSERT INTO automix_jobs
               (id, project_id, status, genre, style_prefs, error_message, result_path, iteration_count, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("state-job", "project", "queued", "pop", "{}", "", "", 0, timestamp, timestamp),
        )
        conn.commit()

    expected_statuses = [
        "claimed",
        "classifying",
        "preparing",
        "analysing",
        "deciding",
        "processing",
        "packaging",
    ]
    for status in expected_statuses:
        automix_worker._update_job_status("state-job", status)
    automix_worker._update_job_status(
        "state-job", "complete", result_path="/tmp/mix.zip", iteration_count=2
    )

    with db.connect() as conn:
        job = dict(conn.execute("SELECT * FROM automix_jobs WHERE id = 'state-job'").fetchone())
        events = conn.execute(
            "SELECT status FROM automix_job_events WHERE job_id = 'state-job' ORDER BY rowid"
        ).fetchall()
    assert job["status"] == "complete"
    assert job["iteration_count"] == 2
    assert [event["status"] for event in events] == [*expected_statuses, "complete"]


def test_worker_rejects_invalid_status_transition(setup_db, monkeypatch) -> None:
    monkeypatch.setattr(automix_worker, "connect", db.connect)
    monkeypatch.setattr(automix_worker, "now", db.now)
    timestamp = db.now()
    with db.connect() as conn:
        conn.execute(
            """INSERT INTO automix_jobs
               (id, project_id, status, genre, style_prefs, error_message, result_path,
                iteration_count, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("invalid-state-job", "project", "queued", "pop", "{}", "", "", 0, timestamp, timestamp),
        )
        conn.commit()

    with pytest.raises(ValueError, match="queued -> complete"):
        automix_worker._update_job_status("invalid-state-job", "complete")

    with db.connect() as conn:
        job = conn.execute(
            "SELECT status FROM automix_jobs WHERE id = 'invalid-state-job'"
        ).fetchone()
        events = conn.execute(
            "SELECT COUNT(*) FROM automix_job_events WHERE job_id = 'invalid-state-job'"
        ).fetchone()[0]
    assert job["status"] == "queued"
    assert events == 0


def test_worker_claims_job_once_and_recovers_expired_lease(setup_db, monkeypatch) -> None:
    monkeypatch.setattr(automix_worker, "connect", db.connect)
    monkeypatch.setattr(automix_worker, "now", db.now)
    timestamp = db.now()
    with db.connect() as conn:
        conn.execute(
            """INSERT INTO automix_jobs
               (id, project_id, status, genre, style_prefs, error_message, result_path,
                iteration_count, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("claim-job", "project", "queued", "pop", "{}", "", "", 0, timestamp, timestamp),
        )
        conn.commit()

    claimed = automix_worker._claim_next_job("worker-a")
    assert claimed is not None
    assert claimed["id"] == "claim-job"
    assert claimed["status"] == "claimed"
    assert claimed["worker_id"] == "worker-a"
    assert automix_worker._claim_next_job("worker-b") is None

    with db.connect() as conn:
        conn.execute(
            "UPDATE automix_jobs SET lease_expiry_at = '2000-01-01 00:00:00' WHERE id = 'claim-job'"
        )
        conn.commit()
    automix_worker.recover_abandoned_jobs("worker-b")

    with db.connect() as conn:
        recovered = dict(
            conn.execute("SELECT * FROM automix_jobs WHERE id = 'claim-job'").fetchone()
        )
    assert recovered["status"] == "queued"
    assert recovered["iteration_count"] == 1
    assert recovered["worker_id"] is None


def test_worker_quality_gate_blocks_safety_failure_not_low_advisory_score() -> None:
    automix_worker._require_quality_gate(
        {"quality_gate": {"passed": True, "technical_score": 54, "minimum_score": 65,
                          "advisory_score_passed": False}}
    )

    with pytest.raises(RuntimeError, match="delivery safety gate: non-finite samples"):
        automix_worker._require_quality_gate(
            {"quality_gate": {"passed": False, "hard_failures": ["non-finite samples"]}}
        )


def test_automix_download_and_preview_endpoints(setup_db) -> None:
    project_id = "test_proj_456"
    
    # A. Verify 404 before file creation
    handler_dl_404 = MockHandler(f"/api/automix/download/{project_id}")
    website_server.Handler.do_GET(handler_dl_404)
    assert handler_dl_404.status == 404

    # Create dummy output directory
    proj_dir = setup_db / "data" / "mix_outputs" / project_id
    proj_dir.mkdir(parents=True, exist_ok=True)
    
    # Write dummy files
    dummy_zip = proj_dir / "mix_package_v1.zip"
    dummy_zip.write_bytes(b"dummyzipcontent")
    
    dummy_wav = proj_dir / "mixdown_v1.wav"
    dummy_wav.write_bytes(b"dummywavcontent")
    
    dummy_html = proj_dir / "mix_report_v1.html"
    dummy_html.write_bytes(b"dummyhtmlcontent")
    
    dummy_json = proj_dir / "mix_decisions_v1.json"
    dummy_json.write_bytes(b'{"key": "val"}')

    # B. Test download route
    handler_dl = MockHandler(f"/api/automix/download/{project_id}")
    website_server.Handler.do_GET(handler_dl)
    assert handler_dl.status == 200
    assert handler_dl.response_bytes == b"dummyzipcontent"
    assert handler_dl.content_type == "application/zip"

    # C. Test play route
    handler_play = MockHandler(f"/api/automix/play/{project_id}")
    website_server.Handler.do_GET(handler_play)
    assert handler_play.status == 200
    assert handler_play.response_bytes == b"dummywavcontent"
    assert handler_play.content_type == "audio/wav"

    # D. Test report route
    handler_report = MockHandler(f"/api/automix/report/{project_id}")
    website_server.Handler.do_GET(handler_report)
    assert handler_report.status == 200
    assert handler_report.response_bytes == b"dummyhtmlcontent"
    assert handler_report.content_type == "text/html"

    # E. Test manifest route
    handler_manifest = MockHandler(f"/api/automix/manifest/{project_id}")
    website_server.Handler.do_GET(handler_manifest)
    assert handler_manifest.status == 200
    assert handler_manifest.response_bytes == b'{"key": "val"}'
    assert handler_manifest.content_type == "application/json"


def test_before_after_route_does_not_collide_with_manifest_route(setup_db) -> None:
    """Both files live in the same project dir with the same .json extension
    -- the manifest route must not accidentally serve the before/after
    comparison (or vice versa) just because it's the newer file."""
    project_id = "test_proj_before_after"
    proj_dir = setup_db / "data" / "mix_outputs" / project_id
    proj_dir.mkdir(parents=True, exist_ok=True)

    (proj_dir / "mix_decisions_v1.json").write_bytes(b'{"kind": "manifest"}')
    # Written after the manifest, so it has a newer mtime -- the exact
    # ordering that would previously have broken the shared "*.json" glob.
    (proj_dir / "source_vs_delivery_v1.json").write_bytes(b'{"kind": "before_after"}')

    handler_manifest = MockHandler(f"/api/automix/manifest/{project_id}")
    website_server.Handler.do_GET(handler_manifest)
    assert handler_manifest.status == 200
    assert handler_manifest.response_bytes == b'{"kind": "manifest"}'

    handler_before_after = MockHandler(f"/api/automix/before-after/{project_id}")
    website_server.Handler.do_GET(handler_before_after)
    assert handler_before_after.status == 200
    assert handler_before_after.response_bytes == b'{"kind": "before_after"}'
    assert handler_before_after.content_type == "application/json"


def test_before_after_route_404s_before_any_render_has_completed(setup_db) -> None:
    handler = MockHandler("/api/automix/before-after/no-such-project")
    website_server.Handler.do_GET(handler)
    assert handler.status == 404


def _write_mono_wav(path: Path, *, frequency_hz: float = 440.0, sample_rate: int = 44100, seconds: float = 1.0) -> None:
    import math
    import struct

    frame_count = int(sample_rate * seconds)
    frames = bytearray()
    for i in range(frame_count):
        sample = int(0.3 * 32767 * math.sin(2 * math.pi * frequency_hz * i / sample_rate))
        frames += struct.pack("<h", sample)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(bytes(frames))


def test_spectrum_match_404s_before_any_render_has_completed(setup_db) -> None:
    handler = MockHandler("/api/automix/spectrum-match?genre=pop&project_id=no-such-project")
    website_server.Handler.do_GET(handler)
    assert handler.status == 404


def test_spectrum_match_computes_real_bands_from_the_delivered_mixdown(setup_db) -> None:
    project_id = "spectrum_project"
    proj_dir = setup_db / "data" / "mix_outputs" / project_id
    proj_dir.mkdir(parents=True, exist_ok=True)
    _write_mono_wav(proj_dir / "mixdown_v1.wav")

    handler = MockHandler(f"/api/automix/spectrum-match?genre=house&project_id={project_id}")
    website_server.Handler.do_GET(handler)

    assert handler.status == 200
    assert handler.payload["ok"] is True
    # "house" is an alias resolved to "edm" (mix_decision_engine.resolve_genre) --
    # the response must reflect the resolved genre, not the raw alias.
    assert handler.payload["genre"] == "edm"
    assert len(handler.payload["mix_40_bands"]) == 40
    assert len(handler.payload["ref_40_bands"]) == 40
    assert isinstance(handler.payload["eq_recommendations"], list)
    # Must not be the old hardcoded placeholder formula's exact fingerprint.
    assert handler.payload["mix_40_bands"][0] != pytest.approx(-18.0)


def test_spectrum_match_uses_real_curated_reference_tracks_when_available(setup_db) -> None:
    """pop has a curated reference_tracks/pop/ folder (automix_worker's
    _GENRE_REFERENCE_FOLDER) -- the response must say so honestly rather
    than silently presenting the hand-tuned genre-profile estimate as a
    measurement."""
    project_id = "spectrum_project_real_ref"
    proj_dir = setup_db / "data" / "mix_outputs" / project_id
    proj_dir.mkdir(parents=True, exist_ok=True)
    _write_mono_wav(proj_dir / "mixdown_v1.wav")

    handler = MockHandler(f"/api/automix/spectrum-match?genre=pop&project_id={project_id}")
    website_server.Handler.do_GET(handler)

    assert handler.status == 200
    assert handler.payload["reference_source"] == "curated_reference_tracks"


def test_spectrum_match_falls_back_to_genre_estimate_without_a_curated_folder(setup_db) -> None:
    """rock/jazz/podcast have no entry in _GENRE_REFERENCE_FOLDER -- must
    still work, but must say honestly that it's an estimate, not a
    measurement."""
    project_id = "spectrum_project_no_curated_ref"
    proj_dir = setup_db / "data" / "mix_outputs" / project_id
    proj_dir.mkdir(parents=True, exist_ok=True)
    _write_mono_wav(proj_dir / "mixdown_v1.wav")

    handler = MockHandler(f"/api/automix/spectrum-match?genre=jazz&project_id={project_id}")
    website_server.Handler.do_GET(handler)

    assert handler.status == 200
    assert handler.payload["reference_source"] == "genre_profile_estimate"
    assert len(handler.payload["ref_40_bands"]) == 40


def test_spectrum_match_serves_the_newest_delivered_mixdown(setup_db) -> None:
    project_id = "spectrum_project_v2"
    proj_dir = setup_db / "data" / "mix_outputs" / project_id
    proj_dir.mkdir(parents=True, exist_ok=True)
    _write_mono_wav(proj_dir / "mixdown_v1.wav", frequency_hz=110.0)
    _write_mono_wav(proj_dir / "mixdown_v2.wav", frequency_hz=6000.0)

    handler = MockHandler(f"/api/automix/spectrum-match?genre=pop&project_id={project_id}")
    website_server.Handler.do_GET(handler)

    assert handler.status == 200
    # A 6kHz tone should register energy far up in the band array; a 110Hz
    # tone would not -- this proves it read v2 (the newer file), not v1.
    assert max(handler.payload["mix_40_bands"][30:]) > max(handler.payload["mix_40_bands"][:10])


def test_waveform_route_404s_before_any_render_has_completed(setup_db) -> None:
    handler = MockHandler("/api/automix/waveform/no-such-project")
    website_server.Handler.do_GET(handler)
    assert handler.status == 404


def test_waveform_route_returns_downsampled_peaks_for_the_delivered_mixdown(setup_db) -> None:
    project_id = "waveform_project"
    proj_dir = setup_db / "data" / "mix_outputs" / project_id
    proj_dir.mkdir(parents=True, exist_ok=True)
    _write_mono_wav(proj_dir / "mixdown_v1.wav")

    handler = MockHandler(f"/api/automix/waveform/{project_id}?points=200")
    website_server.Handler.do_GET(handler)

    assert handler.status == 200
    assert handler.payload["ok"] is True
    assert handler.payload["points"] == 200
    assert len(handler.payload["peaks"]) == 200
    assert handler.payload["sample_rate"] == 44100


def test_default_reference_dir_maps_known_genres_to_curated_folders(monkeypatch, tmp_path) -> None:
    refs_root = tmp_path / "reference_tracks"
    (refs_root / "pop").mkdir(parents=True)
    (refs_root / "pop" / "a.wav").write_bytes(b"x")
    monkeypatch.setattr(automix_worker, "REFERENCE_TRACKS_ROOT", refs_root)

    assert automix_worker.default_reference_dir("pop") == refs_root / "pop"


def test_default_reference_dir_returns_none_for_unmapped_genre(monkeypatch, tmp_path) -> None:
    refs_root = tmp_path / "reference_tracks"
    refs_root.mkdir()
    monkeypatch.setattr(automix_worker, "REFERENCE_TRACKS_ROOT", refs_root)

    # "rock"/"jazz"/"podcast" have no curated folder (see reference_tracks/README.md)
    assert automix_worker.default_reference_dir("rock") is None
    assert automix_worker.default_reference_dir("podcast") is None


def test_default_reference_dir_returns_none_for_empty_or_missing_folder(monkeypatch, tmp_path) -> None:
    refs_root = tmp_path / "reference_tracks"
    (refs_root / "pop").mkdir(parents=True)  # folder exists but has no audio yet
    monkeypatch.setattr(automix_worker, "REFERENCE_TRACKS_ROOT", refs_root)
    assert automix_worker.default_reference_dir("pop") is None

    # "hip_hop" maps to hiphop_rnb, which doesn't exist under this tmp root at all
    assert automix_worker.default_reference_dir("hip_hop") is None


def test_genre_aliases_resolve_before_the_curated_reference_lookup() -> None:
    """default_reference_dir keys on the canonical genre ("edm", "pop", ...),
    but a caller (e.g. Thursday voice/chat) can submit an alias mix_decision_
    engine.resolve_genre understands ("house", "techno", "trap", ...). Found
    2026-07-30: the worker used to call default_reference_dir(genre) with
    the raw, unresolved string, so an alias silently got no curated reference
    even though generate_mix_plan resolves the exact same alias to a genre
    that DOES have a curated folder. This proves the fix against the real
    reference_tracks/ directory, not a synthetic one."""
    from audio_analysis.mixdown.mix_decision_engine import resolve_genre

    for alias, expected_folder in (
        ("house", "electronic"), ("techno", "electronic"), ("trance", "electronic"),
        ("trap", "hiphop_rnb"), ("rap", "hiphop_rnb"),
        ("classical", "cinematic"), ("film", "cinematic"),
        ("folk", "acoustic"),
    ):
        resolved, _note = resolve_genre(alias)
        default_ref = automix_worker.default_reference_dir(resolved)
        assert default_ref is not None, (
            f"genre alias {alias!r} resolved to {resolved!r}, which should have "
            f"a curated reference_tracks/{expected_folder}/ folder"
        )
        assert default_ref.name == expected_folder

    # the bug this guards against: looking the RAW alias up directly finds nothing
    assert automix_worker.default_reference_dir("house") is None
    assert automix_worker.default_reference_dir("trap") is None


def test_automix_match_report_endpoint_is_distinct_from_the_mix_report(setup_db) -> None:
    """The reference-match evidence report (match_report.html, an exact
    filename) must be served by its own route and never collide with the
    versioned mix_report_v<N>.html glob served by /api/automix/report/."""
    project_id = "test_proj_match_789"

    # 404 before either report exists
    handler_404 = MockHandler(f"/api/automix/match-report/{project_id}")
    website_server.Handler.do_GET(handler_404)
    assert handler_404.status == 404

    proj_dir = setup_db / "data" / "mix_outputs" / project_id
    proj_dir.mkdir(parents=True, exist_ok=True)
    # Same order the worker writes them in (match_report.html, Stage 5.5, then
    # mix_report_v<N>.html, Stage 6/packaging) -- the "*.html" glob behind
    # /api/automix/report/ picks the newest file, so this order is what keeps
    # the two routes from colliding; write it the same way here.
    (proj_dir / "match_report.html").write_bytes(b"match report content")
    (proj_dir / "mix_report_v1.html").write_bytes(b"mix report content")

    handler_match = MockHandler(f"/api/automix/match-report/{project_id}")
    website_server.Handler.do_GET(handler_match)
    assert handler_match.status == 200
    assert handler_match.response_bytes == b"match report content"
    assert handler_match.content_type == "text/html"

    # the pre-existing /report/ route must still resolve to the mix report,
    # not accidentally pick up match_report.html via its "*.html" glob
    handler_report = MockHandler(f"/api/automix/report/{project_id}")
    website_server.Handler.do_GET(handler_report)
    assert handler_report.status == 200
    assert handler_report.response_bytes == b"mix report content"


def test_automix_match_evidence_endpoint_serves_the_raw_json(setup_db) -> None:
    """D2.3 (docs/KENN_FUTURE_PLAN.md Phase 2): the raw evidence dict
    behind match_report.html (score_before/after, band deltas) is served
    as its own JSON route -- exact filename, same collision-avoidance
    reasoning as match_report.html's own route."""
    project_id = "test_proj_match_evidence_123"

    handler_404 = MockHandler(f"/api/automix/match-evidence/{project_id}")
    website_server.Handler.do_GET(handler_404)
    assert handler_404.status == 404

    proj_dir = setup_db / "data" / "mix_outputs" / project_id
    proj_dir.mkdir(parents=True, exist_ok=True)
    evidence = {"score_before": 61.2, "score_after": 78.4, "score_delta": 17.2}
    (proj_dir / "match_evidence.json").write_text(json.dumps(evidence), encoding="utf-8")

    handler = MockHandler(f"/api/automix/match-evidence/{project_id}")
    website_server.Handler.do_GET(handler)
    assert handler.status == 200
    assert handler.content_type == "application/json"
    assert json.loads(handler.response_bytes) == evidence


def test_automix_revision_flow(setup_db) -> None:
    # 1. Try to revise a project that does not exist -> 400 Bad Request
    body = json.dumps({
        "project_id": "non_existent_project",
        "feedback": "make vocals louder"
    }).encode("utf-8")
    handler_fail = MockHandler("/api/automix/revise", method="POST", body=body)
    website_server.Handler.do_POST(handler_fail)
    assert handler_fail.status == 400
    assert "error" in handler_fail.payload

    # 2. Seed a completed job in the database
    from db import connect, now
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO automix_jobs (id, project_id, status, genre, style_prefs, error_message, result_path, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("prev_job", "proj_rev_123", "complete", "rock", '{"bright_warm": 0.5}', "", "/path/to/result", now(), now())
        )
        conn.commit()

    # 3. Post a valid revision request
    body_ok = json.dumps({
        "project_id": "proj_rev_123",
        "feedback": "more bass and less snare"
    }).encode("utf-8")
    handler_ok = MockHandler("/api/automix/revise", method="POST", body=body_ok)
    website_server.Handler.do_POST(handler_ok)
    
    assert handler_ok.status == 200
    assert handler_ok.payload["ok"] is True
    rev_job_id = handler_ok.payload["job_id"]
    assert rev_job_id != "prev_job"

    # 4. Check new database record
    with connect() as conn:
        row = conn.execute("SELECT * FROM automix_jobs WHERE id = ?", (rev_job_id,)).fetchone()
    assert row is not None
    job = dict(row)
    assert job["status"] == "queued"
    assert job["genre"] == "rock"
    
    prefs = json.loads(job["style_prefs"])
    assert prefs["feedback"] == "more bass and less snare"
    assert prefs["bright_warm"] == 0.5


def test_automix_revision_accumulates_feedback_across_requests(setup_db) -> None:
    """A second revision used to overwrite the first revision's feedback
    string entirely (preferences["feedback"] = request.feedback, a plain
    assignment) -- since every revision regenerates the plan from scratch,
    that meant the first request's instruction was silently discarded the
    moment a second one was submitted. feedback_history must accumulate."""
    from db import connect, now

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO automix_jobs (id, project_id, status, genre, style_prefs, error_message, result_path, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("prev_job_2", "proj_rev_history", "complete", "pop", "{}", "", "/path/to/result", now(), now())
        )
        conn.commit()

    body_1 = json.dumps({"project_id": "proj_rev_history", "feedback": "brighter"}).encode("utf-8")
    handler_1 = MockHandler("/api/automix/revise", method="POST", body=body_1)
    website_server.Handler.do_POST(handler_1)
    assert handler_1.status == 200
    job_id_1 = handler_1.payload["job_id"]

    with connect() as conn:
        conn.execute("UPDATE automix_jobs SET status = 'complete' WHERE id = ?", (job_id_1,))
        conn.commit()

    body_2 = json.dumps({"project_id": "proj_rev_history", "feedback": "more reverb"}).encode("utf-8")
    handler_2 = MockHandler("/api/automix/revise", method="POST", body=body_2)
    website_server.Handler.do_POST(handler_2)
    assert handler_2.status == 200
    job_id_2 = handler_2.payload["job_id"]

    with connect() as conn:
        row = conn.execute("SELECT style_prefs FROM automix_jobs WHERE id = ?", (job_id_2,)).fetchone()
    prefs = json.loads(dict(row)["style_prefs"])
    assert prefs["feedback_history"] == ["brighter", "more reverb"]
    assert prefs["feedback"] == "more reverb"


def test_handler_authorized_requires_valid_signed_cookie(monkeypatch) -> None:
    monkeypatch.setenv("AUDIO_TOO_SESSION_SECRET", "automix-session-secret")
    handler = MockHandler("/api/automix/status?id=job_123")

    assert website_server.Handler.authorized(handler) is False

    token = session_auth.make_session_token(ttl_seconds=60)
    handler.headers["Cookie"] = f"{session_auth.SESSION_COOKIE}={token}"
    assert website_server.Handler.authorized(handler) is True

    handler.headers["Cookie"] = f"{session_auth.SESSION_COOKIE}=tampered"
    assert website_server.Handler.authorized(handler) is False


def test_private_post_requires_session_bound_csrf_and_same_origin(monkeypatch) -> None:
    monkeypatch.setenv("AUDIO_TOO_SESSION_SECRET", "csrf-test-secret")
    token = session_auth.make_session_token(ttl_seconds=60)
    csrf_token = session_auth.make_csrf_token(token)
    handler = MockHandler("/api/automix/start", method="POST", body=b"{}")
    handler.headers.update(
        {
            "Cookie": f"{session_auth.SESSION_COOKIE}={token}",
            "Host": "127.0.0.1:8080",
            "Origin": "http://127.0.0.1:8080",
            "X-CSRF-Token": csrf_token,
        }
    )

    assert website_server.Handler.require_private_post(handler) is True

    handler.headers["X-CSRF-Token"] = "tampered"
    assert website_server.Handler.require_private_post(handler) is False
    assert handler.status == 403

    handler.headers["X-CSRF-Token"] = csrf_token
    handler.headers["Origin"] = "https://attacker.example"
    assert website_server.Handler.require_private_post(handler) is False
    assert handler.payload == {"error": "Cross-origin request rejected."}


@pytest.mark.parametrize("path", ["/api/public/ask", "/api/enquiry", "/api/demo/ask"])
def test_public_and_demo_posts_reject_cross_origin_before_dispatch(path) -> None:
    handler = MockHandler(path, method="POST", body=b"{}")
    handler.headers.update(
        {
            "Host": "127.0.0.1:8080",
            "Origin": "https://attacker.example",
            "Sec-Fetch-Site": "cross-site",
        }
    )

    website_server.Handler.do_POST(handler)

    assert handler.status == 403
    assert handler.payload == {"error": "Cross-origin request rejected."}


def test_authenticated_posts_are_rate_limited_before_dispatch(monkeypatch) -> None:
    monkeypatch.setattr(
        website_server.request_security.enquiry_guard,
        "is_rate_limited",
        lambda *_a, **_kw: True,
    )
    handler = MockHandler("/api/automix/start", method="POST", body=b"{}")

    website_server.Handler.do_POST(handler)

    assert handler.status == 429
    assert handler.payload == {"error": "Too many dashboard changes. Try again shortly."}

@pytest.mark.parametrize(
    "path",
    [
        "/api/automix/status?id=job_123",
        "/api/automix/download/project_123",
        "/api/automix/play/project_123",
        "/api/automix/report/project_123",
        "/api/automix/manifest/project_123",
    ],
)
def test_automix_get_routes_require_dashboard_auth(path) -> None:
    handler = MockHandler(path, is_authorized=False)

    website_server.Handler.do_GET(handler)

    assert handler.status == 401
    assert handler.payload == {"error": "Dashboard password required."}


@pytest.mark.parametrize(
    "path",
    [
        "/api/automix/upload",
        "/api/automix/reference/upload",
        "/api/automix/start",
        "/api/automix/revise",
    ],
)
def test_automix_post_routes_require_dashboard_auth(path) -> None:
    handler = MockHandler(path, method="POST", body=b"{}", is_authorized=False)

    website_server.Handler.do_POST(handler)

    assert handler.status == 401
    assert handler.payload == {"error": "Dashboard password required."}


@pytest.mark.parametrize(
    "path",
    [
        "/api/automix/download/..",
        "/api/automix/play/%2e%2e",
        "/api/automix/report/project/child",
        "/api/automix/manifest/.hidden",
    ],
)
def test_automix_file_routes_reject_unsafe_project_ids(path) -> None:
    handler = MockHandler(path)

    website_server.Handler.do_GET(handler)

    assert handler.status == 400
    assert "Invalid project ID" in handler.payload["error"]


def test_automix_start_rejects_unsafe_project_id(setup_db) -> None:
    body = json.dumps({"project_id": "../escape", "genre": "pop"}).encode("utf-8")
    handler = MockHandler("/api/automix/start", method="POST", body=body)

    website_server.Handler.do_POST(handler)

    assert handler.status == 400
    assert "Invalid project ID" in handler.payload["error"]
    with db.connect() as conn:
        count = conn.execute("SELECT COUNT(*) FROM automix_jobs").fetchone()[0]
    assert count == 0


def test_automix_start_rejects_project_without_uploaded_stems(
    setup_db, monkeypatch
) -> None:
    monkeypatch.setattr(stem_uploads, "require_source_ready", REAL_REQUIRE_SOURCE_READY)
    monkeypatch.setattr(stem_uploads, "UPLOAD_ROOT", setup_db / "data" / "stem_uploads")
    body = json.dumps({"project_id": "empty-project", "genre": "pop"}).encode("utf-8")
    handler = MockHandler("/api/v1/automix/jobs", method="POST", body=body)

    website_server.Handler.do_POST(handler)

    assert handler.status == 409
    assert handler.payload["code"] == "automix_source_not_ready"
    assert "Upload a ZIP or supported audio stem" in handler.payload["error"]
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM automix_jobs").fetchone()[0] == 0
