"""Tests for KENN v0.4.0 HTTP Endpoints (Genre Curves, Audition Delta, Rack Builder)."""

import json
import os
import threading
import time
import urllib.request
import urllib.error
import pytest

import kenn.server as server_module


@pytest.fixture(scope="module")
def v040_test_server():
    os.environ["KENN_PORT"] = "8098"
    os.environ["KENN_HOST"] = "127.0.0.1"
    os.environ["AUDIO_TOO_LLM_ENABLED"] = "0"
    os.environ["KENN_LIVE_LLM_ENABLED"] = "0"

    httpd = server_module.ThreadingHTTPServer(("127.0.0.1", 8098), server_module.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.5)
    try:
        yield "http://127.0.0.1:8098"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_get_genre_curves(v040_test_server):
    url = f"{v040_test_server}/api/genre_curves"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=3.0) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["ok"] is True
        assert len(data["genres"]) == 6
        ids = {g["id"] for g in data["genres"]}
        assert "edm_club" in ids
        assert "modern_pop" in ids


def test_get_racks(v040_test_server):
    url = f"{v040_test_server}/api/racks"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=3.0) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["ok"] is True
        assert len(data["racks"]) >= 12
        ids = {r["id"] for r in data["racks"]}
        assert "neuro_bass_rack" in ids
        assert "nyc_drum_crush_rack" in ids
        assert "neuro_reese_saturator" in ids


def test_post_audition_delta(v040_test_server):
    url = f"{v040_test_server}/api/ableton/audition_delta"
    payload = json.dumps({"dry_lufs": -14.0, "wet_lufs": -10.5}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=3.0) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["ok"] is True
        assert data["gain_adjustment_db"] == -3.5
        assert data["compensated_wet_lufs"] == -14.0
        assert data["unbiased_audition_ready"] is True


def test_post_rack_build(v040_test_server):
    url = f"{v040_test_server}/api/rack/build"
    payload = json.dumps({
        "rack_id": "neuro_bass_rack",
        "track_index": 1,
        "track_name": "Main Bass",
        "session_id": "sess_123"
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=3.0) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["ok"] is True
        assert data["proposal"]["track_index"] == 1
        assert data["proposal"]["requires_confirmation"] is True
        assert data["proposal"]["confirmation_token"].startswith("rack_")

