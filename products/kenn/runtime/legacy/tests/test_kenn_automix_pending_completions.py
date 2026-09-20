"""Tests for KENN server.py's /api/kenn/automix/pending-completions (D2.3,
docs/KENN_FUTURE_PLAN.md Phase 2) -- the proactive completion-surfacing
half. Mirrors test_kenn_automix_upload.py's MockHandler pattern (call the
real Handler method directly rather than spinning up a real socket
server)."""

from __future__ import annotations

import io
import json

import pytest
from kenn import server
from kenn.core import session_memory


class MockHandler(server.Handler):
    def __init__(self, *, headers: dict | None = None, body: bytes = b""):
        self.headers = headers or {}
        self.client_address = ("127.0.0.1", 0)
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.status = 0
        self.sent_json: dict = {}

    def send_response(self, status: int, message=None) -> None:
        self.status = status

    def send_header(self, name: str, value: str) -> None:
        pass

    def end_headers(self) -> None:
        pass

    def send_json(self, status: int, payload: dict) -> None:
        self.status = status
        self.sent_json = payload

    def request_id(self) -> str:
        return "test-req"

    def structured_log(self, *a, **k) -> None:
        pass

    def enforce_rate_limit(self, scope: str) -> bool:
        return True


@pytest.fixture(autouse=True)
def isolated_session_db(tmp_path, monkeypatch):
    monkeypatch.setattr(session_memory, "DB_PATH", tmp_path / "kenn.db")
    yield


def test_pending_completions_returns_empty_for_a_session_with_none():
    handler = MockHandler()
    handler.path = "/api/kenn/automix/pending-completions?session_id=s1"
    server.Handler.do_GET(handler)

    assert handler.status == 200
    assert handler.sent_json["completions"] == []


def test_pending_completions_reports_and_clears_a_completed_job(monkeypatch):
    session_memory.remember_pending_automix_job("s1", "job-1")
    monkeypatch.setattr(
        server, "automix_jobs",
        type("M", (), {"get_job_status": staticmethod(
            lambda job_id: {"id": job_id, "project_id": "proj-1", "status": "complete"}
        )}),
    )
    monkeypatch.setattr(server, "_read_match_evidence", lambda project_id: None)

    handler = MockHandler()
    handler.path = "/api/kenn/automix/pending-completions?session_id=s1"
    server.Handler.do_GET(handler)

    assert handler.status == 200
    completions = handler.sent_json["completions"]
    assert len(completions) == 1
    assert completions[0]["status"] == "complete"
    assert completions[0]["project_id"] == "proj-1"

    # One-shot: the job must be cleared, not surfaced again next poll.
    assert session_memory.get_pending_automix_jobs("s1") == []


def test_pending_completions_reports_a_failed_job_with_its_error(monkeypatch):
    session_memory.remember_pending_automix_job("s1", "job-1")
    monkeypatch.setattr(
        server, "automix_jobs",
        type("M", (), {"get_job_status": staticmethod(
            lambda job_id: {"id": job_id, "project_id": "proj-1", "status": "failed", "error_message": "boom"}
        )}),
    )

    handler = MockHandler()
    handler.path = "/api/kenn/automix/pending-completions?session_id=s1"
    server.Handler.do_GET(handler)

    completions = handler.sent_json["completions"]
    assert completions[0]["status"] == "failed"
    assert completions[0]["error"] == "boom"


def test_pending_completions_leaves_still_processing_jobs_pending(monkeypatch):
    session_memory.remember_pending_automix_job("s1", "job-1")
    monkeypatch.setattr(
        server, "automix_jobs",
        type("M", (), {"get_job_status": staticmethod(
            lambda job_id: {"id": job_id, "project_id": "proj-1", "status": "processing"}
        )}),
    )

    handler = MockHandler()
    handler.path = "/api/kenn/automix/pending-completions?session_id=s1"
    server.Handler.do_GET(handler)

    assert handler.sent_json["completions"] == []
    assert session_memory.get_pending_automix_jobs("s1") == ["job-1"]


def test_pending_completions_includes_match_evidence_when_present(monkeypatch):
    session_memory.remember_pending_automix_job("s1", "job-1")
    monkeypatch.setattr(
        server, "automix_jobs",
        type("M", (), {"get_job_status": staticmethod(
            lambda job_id: {"id": job_id, "project_id": "proj-1", "status": "complete"}
        )}),
    )
    monkeypatch.setattr(
        server, "_read_match_evidence",
        lambda project_id: {"score_before": 62.0, "score_after": 81.5},
    )

    handler = MockHandler()
    handler.path = "/api/kenn/automix/pending-completions?session_id=s1"
    server.Handler.do_GET(handler)

    assert handler.sent_json["completions"][0]["match_evidence"] == {"score_before": 62.0, "score_after": 81.5}


def test_pending_completions_503s_when_automix_unavailable(monkeypatch):
    monkeypatch.setattr(server, "automix_jobs", None)
    handler = MockHandler()
    handler.path = "/api/kenn/automix/pending-completions?session_id=s1"
    server.Handler.do_GET(handler)

    assert handler.status == 503


def test_read_match_evidence_returns_none_for_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "WEBSITE_ROOT", tmp_path / "business" / "app")
    assert server._read_match_evidence("no-such-project") is None


def test_read_match_evidence_reads_a_real_file(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "WEBSITE_ROOT", tmp_path / "business" / "app")
    proj_dir = tmp_path / "business" / "data" / "mix_outputs" / "proj-1"
    proj_dir.mkdir(parents=True)
    (proj_dir / "match_evidence.json").write_text(json.dumps({"score_before": 50.0}), encoding="utf-8")

    assert server._read_match_evidence("proj-1") == {"score_before": 50.0}
