"""Integration tests for Thursday Commercial Dispatcher Engine."""

from __future__ import annotations

import json
from pathlib import Path

from thursday.autonomous_dispatcher import ThursdayCommercialDispatcher
from app.routes.thursday_routes import handle_thursday_post


class DummyHTTPHandler:
    def __init__(self, body_data: dict | None = None):
        self.response_status = 0
        self.response_json = {}
        self.headers = {}
        if body_data is not None:
            raw_bytes = json.dumps(body_data).encode("utf-8")
            self.headers["Content-Length"] = str(len(raw_bytes))
            self.rfile = DummyRFile(raw_bytes)
        else:
            self.rfile = DummyRFile(b"")

    def send_json(self, status: int, data: dict):
        self.response_status = status
        self.response_json = data


class DummyRFile:
    def __init__(self, data: bytes):
        self.data = data

    def read(self, length: int) -> bytes:
        return self.data[:length]


def test_thursday_commercial_dispatcher_engine_fails_closed():
    """Phase-0 P0-8 (docs/audits/2026-08-20-thursday-nitedsp-forensic-audit.md):
    execute_commercial_job() previously reported every stage as "completed"
    unconditionally -- four fixed stem filenames never written to disk, a
    hardcoded $450.00 invoice, a hardcoded -1.0 dBTP true-peak, and
    master_lufs that merely echoed the input parameter. None of it reflected
    real audio work; if ever surfaced to a client as "your job was
    processed," the output was fictional.

    This is a deliberate behavioural change, not a regression: the method
    must now fail closed (NOT_IMPLEMENTED/PROTOTYPE_ONLY) rather than
    fabricate a completed commercial job. It must not write a delivery
    manifest file, must not report ok=True, and must not claim any
    invoice/LUFS/stem/delivery detail actually occurred."""
    from thursday.autonomous_dispatcher import DELIVERY_DIR

    # NOTE: DELIVERY_DIR already contains hundreds of manifest files written
    # by the prototype pipeline before this fix (real, pre-existing artifacts
    # -- left alone per repository-safety rules, not deleted by this test).
    # The assertion below checks no *new* file was added by this call, not
    # that the directory is empty.
    before = set(DELIVERY_DIR.glob("*_manifest.json")) if DELIVERY_DIR.exists() else set()

    dispatcher = ThursdayCommercialDispatcher()
    res = dispatcher.execute_commercial_job(
        client_name="Apex Music Group",
        project_title="Midnight Drive",
        genre="pop",
        bpm=120,
        target_lufs=-14.0,
    )

    assert res["ok"] is False
    assert res["status"] == "NOT_IMPLEMENTED"
    assert res["reason"] == "PROTOTYPE_ONLY"
    assert res["owner_review_required"] is True
    assert res["client_name"] == "Apex Music Group"
    assert res["project_title"] == "Midnight Drive"
    # No fabricated commerce/audio claims anywhere in the response.
    assert "job_id" not in res
    assert "invoice_id" not in res
    assert "manifest_file" not in res
    assert "job_package" not in res

    after = set(DELIVERY_DIR.glob("*_manifest.json")) if DELIVERY_DIR.exists() else set()
    assert after == before, "execute_commercial_job() wrote a new delivery manifest despite failing closed"


def test_thursday_commercial_dispatch_api_route_fails_closed():
    payload = {
        "client_name": "Horizon Records",
        "project_title": "Neon Skyline",
        "genre": "edm",
        "bpm": 128,
        "target_lufs": -14.0,
    }
    handler = DummyHTTPHandler(body_data=payload)
    handled = handle_thursday_post(handler, "/api/thursday/commercial-dispatch")

    assert handled is True
    assert handler.response_status == 200
    assert handler.response_json.get("ok") is False
    assert handler.response_json.get("status") == "NOT_IMPLEMENTED"
    assert "job_id" not in handler.response_json
    assert "invoice_id" not in handler.response_json


def test_prototype_pipeline_is_preserved_but_not_reachable(tmp_path, monkeypatch):
    """The original fabricated-output implementation is kept for owner
    inspection / a future real rebuild, but must not be reachable from the
    public method."""
    import thursday.autonomous_dispatcher as dispatcher_module

    # Isolate the prototype's (still-fabricated) manifest write to a temp
    # dir -- this test deliberately exercises the old fake-output path for
    # preservation-proof purposes only, and must not touch the real repo's
    # data/commercial_deliveries/ directory.
    monkeypatch.setattr(dispatcher_module, "DELIVERY_DIR", tmp_path)

    dispatcher = ThursdayCommercialDispatcher()
    assert hasattr(dispatcher, "_execute_commercial_job_prototype")
    prototype_res = dispatcher._execute_commercial_job_prototype(
        client_name="Internal QA", project_title="Prototype Inspection Only"
    )
    public_res = dispatcher.execute_commercial_job(
        client_name="Internal QA", project_title="Prototype Inspection Only"
    )
    # The prototype method itself is unchanged (still fabricates output) --
    # proving it is deliberately preserved, not deleted -- but it is a
    # differently-named method the public API and HTTP route never call.
    assert prototype_res["ok"] is True
    assert "job_id" in prototype_res
    assert public_res["ok"] is False
    assert "job_id" not in public_res
