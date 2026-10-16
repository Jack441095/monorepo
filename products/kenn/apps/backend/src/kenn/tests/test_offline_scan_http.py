"""HTTP path for the FakeLive offline scan: propose, confirm-and-start, poll, cancel.

These cross the same three transports the cancellation route tests use, so a route
registered in only one server fails here. No Live UI action runs anywhere in this file.
"""
from __future__ import annotations

from collections import defaultdict, deque
import fcntl
import json
import os
import subprocess
import sys
import textwrap
import uuid
from threading import Event, Thread
import time
import urllib.error
import urllib.request

from fastapi.testclient import TestClient
import pytest

import kenn.server_rate_limit as rate_limit
from kenn.core import confirmation, live_action_service, offline_scan_runtime
from kenn.core.fake_live import FakeLiveBackend
from kenn.core.offline_scan import OfflineScanService

OWNER = "scan-owner"
SOURCE = {"source_kind": "arrangement_main", "fingerprint": offline_scan_runtime.FAKE_ARRANGEMENT_FINGERPRINT,
          "range_confirmed": True, "tail_policy": "within_range"}
EXPORT = {"live_pid": 12345, "expected_window_title": "Synthetic disposable set", "render_start": "1.1.1",
          "render_length": "1.0.0", "sample_rate": 48000, "timeout_seconds": 10}


@pytest.fixture(autouse=True)
def isolated_scan_state(monkeypatch, tmp_path):
    monkeypatch.setattr(confirmation, "_USED_TOKENS", set())
    monkeypatch.setattr(confirmation, "_ISSUED_TOKENS", {})
    monkeypatch.setattr(confirmation, "_REVOKED_TOKENS", set())
    monkeypatch.setattr(rate_limit, "RATE_BUCKETS", defaultdict(deque))
    monkeypatch.setenv("KENN_LIVE_BACKEND", "fake")
    monkeypatch.setenv("KENN_EXPERIMENTAL_LIVE_EXPORT", "1")
    monkeypatch.setenv("KENN_ALLOW_DAW_CONTROL", "1")
    monkeypatch.setenv("KENN_OFFLINE_SCAN_RUNTIME_DIR", str(tmp_path / "scan-runtime"))
    offline_scan_runtime.reset_offline_scan_service()
    yield
    offline_scan_runtime.reset_offline_scan_service()


@pytest.fixture(params=["http", "prefixed_http", "fastapi"])
def post(request, monkeypatch):
    from kenn import server
    from kenn.routes.fastapi_app import app

    monkeypatch.setattr(live_action_service, "live_client", FakeLiveBackend())
    if request.param == "fastapi":
        with TestClient(app) as client:
            def send(path, payload):
                response = client.post(path, json=payload)
                return response.status_code, response.json()
            yield send
        return

    httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    worker = Thread(target=lambda: httpd.serve_forever(poll_interval=0.01), daemon=True)
    worker.start()
    prefix = "/kenn" if request.param == "prefixed_http" else ""

    def send(path, payload):
        req = urllib.request.Request(
            f"http://127.0.0.1:{httpd.server_port}{prefix}{path}",
            data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            response = urllib.request.urlopen(req, timeout=5)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            return response.status, json.load(response)

    try:
        yield send
    finally:
        httpd.shutdown()
        httpd.server_close()
        worker.join(2)


def _propose(post):
    status, body = post("/api/ableton/offline-scan/proposal",
                        {"session_id": OWNER, "source": SOURCE, "export_request": EXPORT})
    assert status == 200 and body["status"] == "confirmation_required" and body["changed"] is False, body
    return body["proposal"]


def _start(post, proposal, key=None):
    # Idempotency keys live in a process-wide set, so each request needs a fresh one across parametrized runs.
    key = key or f"scan-request-{uuid.uuid4().hex}"
    return post("/api/ableton/offline-scan/start", {
        "session_id": OWNER, "proposal": proposal, "confirm_token": proposal["confirmation_token"], "idempotency_key": key,
    })


def _wait_for_terminal(post, job_id):
    deadline = time.monotonic() + 20  # 20 seconds bounds real local analysis of the one-second fixture tone.
    while time.monotonic() < deadline:
        status, receipt = post("/api/ableton/offline-scan/status", {"session_id": OWNER, "job_id": job_id})
        assert status == 200, receipt
        if receipt["state"] not in {"exporting", "analyzing"}:
            return receipt
        time.sleep(0.01)
    pytest.fail("Offline scan did not finish within 20 seconds.")


def test_button_press_reaches_a_retained_report_and_the_generated_wav_is_gone(post, tmp_path):
    proposal = _propose(post)
    status, started = _start(post, proposal)
    assert status == 202 and started["state"] == "exporting"

    receipt = _wait_for_terminal(post, started["job_id"])
    assert receipt["state"] == "completed", receipt
    assert receipt["audio_deleted"] is True
    assert receipt["review"]["metrics"] and receipt["review"]["action_plan"]
    assert receipt["review"]["audio_retained"] is False
    assert not list((tmp_path / "scan-runtime").rglob("*.wav"))
    # The confirmation was single-use: replaying the same start must not export again.
    assert _start(post, proposal)[0] == 409
    assert _start(post, proposal)[0] == 409


def test_another_conversation_cannot_read_or_cancel_the_job(post):
    started = _start(post, _propose(post))[1]
    for action in ("status", "cancel"):
        status, body = post(f"/api/ableton/offline-scan/{action}", {"session_id": "someone-else", "job_id": started["job_id"]})
        assert status == 404 and body["ok"] is False
    assert _wait_for_terminal(post, started["job_id"])["state"] == "completed"


def test_cancel_during_export_discards_the_late_report_and_the_wav(post, tmp_path):
    entered, release = Event(), Event()
    real_export = offline_scan_runtime.fake_tone_exporter

    def slow_export(request, cancelled):
        entered.set()
        assert release.wait(10)  # 10 seconds is only a hang guard; the test releases it after cancelling.
        return real_export(request, cancelled)

    # Replace the cached service with one whose exporter holds the job in "exporting".
    held = OfflineScanService(tmp_path / "held", exporter=slow_export,
                              read_source_fingerprint=offline_scan_runtime._fake_fingerprint)
    offline_scan_runtime._service = held

    started = _start(post, _propose(post))[1]
    assert entered.wait(5)
    status, cancelled = post("/api/ableton/offline-scan/cancel", {"session_id": OWNER, "job_id": started["job_id"]})
    assert status == 200 and cancelled["cancel_requested"] is True
    release.set()

    receipt = _wait_for_terminal(post, started["job_id"])
    assert receipt["state"] == "cancelled" and "review" not in receipt
    assert receipt["audio_deleted"] is True
    assert not list((tmp_path / "held").rglob("*.wav"))


def test_malformed_bodies_are_rejected_before_any_job_exists(post):
    assert post("/api/ableton/offline-scan/proposal", {"session_id": OWNER, "source": SOURCE})[0] == 400
    assert post("/api/ableton/offline-scan/start", {"session_id": OWNER, "proposal": {}, "confirm_token": 5, "idempotency_key": "k"})[0] == 400
    assert post("/api/ableton/offline-scan/status", {"session_id": OWNER, "job_id": ["x"]})[0] == 400
    assert post("/api/ableton/offline-scan/cancel", {"session_id": " ", "job_id": "scan-x"})[0] == 400


def test_real_live_gets_no_exporter_and_every_route_says_so(post, monkeypatch):
    monkeypatch.setenv("KENN_LIVE_BACKEND", "osc")
    offline_scan_runtime.reset_offline_scan_service()
    assert offline_scan_runtime.get_offline_scan_service() is None

    status, body = post("/api/ableton/offline-scan/proposal",
                        {"session_id": OWNER, "source": SOURCE, "export_request": EXPORT})
    assert status == 409 and "No qualified offline export candidate" in body["error"]
    status, body = post("/api/ableton/offline-scan/status", {"session_id": OWNER, "job_id": "scan-" + "0" * 32})
    assert status == 409 and "No qualified offline export candidate" in body["error"]
    # Start and cancel must refuse too; a route that forgot the None check would raise a 500 instead.
    proposal = {"confirmation_token": "x"}
    status, body = post("/api/ableton/offline-scan/start",
                        {"session_id": OWNER, "proposal": proposal, "confirm_token": "x", "idempotency_key": "k"})
    assert status == 409 and "No qualified offline export candidate" in body["error"]
    status, body = post("/api/ableton/offline-scan/cancel", {"session_id": OWNER, "job_id": "scan-" + "0" * 32})
    assert status == 409 and "No qualified offline export candidate" in body["error"]


def test_a_proposal_edited_after_confirmation_does_not_start_a_job(post, tmp_path):
    # The token confirms the preview the owner saw; swapping the render length afterwards must not ride on it.
    proposal = _propose(post)
    edited = json.loads(json.dumps(proposal))
    edited["export_request"]["render_length"] = "2.0.0"
    status, body = _start(post, edited)
    assert status == 409, body
    assert not list((tmp_path / "scan-runtime").glob("scan-*"))


def test_closed_experimental_gate_blocks_proposals(post, monkeypatch):
    monkeypatch.delenv("KENN_EXPERIMENTAL_LIVE_EXPORT")
    status, body = post("/api/ableton/offline-scan/proposal",
                        {"session_id": OWNER, "source": SOURCE, "export_request": EXPORT})
    assert status == 409 and "disabled" in body["error"]


def test_a_scan_killed_mid_export_is_disposed_when_the_runtime_restarts(tmp_path):
    runtime = tmp_path / "scan-runtime"
    # A child process starts a real job and dies inside the exporter after writing part of
    # the WAV, the way a backend crash or kill -9 would. os._exit skips every cleanup path.
    child = textwrap.dedent(f"""
        import os, sys, time
        from pathlib import Path
        from kenn.core.offline_scan import OfflineScanService

        def die_mid_export(request, cancelled):
            Path(request["output_path"]).write_bytes(b"RIFF" + bytes(64))  # Truncated, never closed.
            os._exit(1)

        jobs = OfflineScanService({str(runtime)!r}, exporter=die_mid_export, read_source_fingerprint=lambda: {SOURCE["fingerprint"]!r})
        print(jobs.start({OWNER!r}, {SOURCE!r}, {EXPORT!r})["job_id"], flush=True)
        time.sleep(30)  # Only reached if the exporter thread never runs; the parent kills nothing.
    """)
    done = subprocess.run([sys.executable, "-c", child], capture_output=True, text=True, timeout=30,
                          env={"PYTHONPATH": os.pathsep.join(sys.path), "PATH": os.environ["PATH"]})
    assert done.returncode == 1, done.stderr
    job_id = done.stdout.strip()
    assert list(runtime.rglob("kenn-analysis.wav")), "the child should have left its partial WAV behind"

    service = offline_scan_runtime.get_offline_scan_service()
    receipt = service.status(OWNER, job_id)
    assert receipt["state"] == "cancelled" and receipt["audio_deleted"] is True
    assert not list(runtime.rglob("kenn-analysis.wav"))


def test_a_busy_lease_at_startup_does_not_take_the_routes_down(tmp_path):
    # Two backends sharing one runtime directory: the second must still serve requests while the first
    # owns a job, and must finish recovery once the lease is free. Before this the RuntimeError from
    # the busy lease escaped get_offline_scan_service() and every route returned 500 until restart.
    runtime = tmp_path / "scan-runtime"
    runtime.mkdir()
    holder = os.open(runtime / ".scan.lock", os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        assert offline_scan_runtime.get_offline_scan_service() is not None
        assert offline_scan_runtime._recovered is False
    finally:
        os.close(holder)  # Closing the descriptor drops the flock.
    assert offline_scan_runtime.get_offline_scan_service() is not None
    assert offline_scan_runtime._recovered is True
