from fastapi.testclient import TestClient
import pytest

from kenn.routes.fastapi_app import app

client = TestClient(app)


def test_fastapi_health():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "kenn"
    assert "Ableton Live" in data["daw"]
    retrieval = data["subsystems"]["retrieval"]
    assert retrieval["schema"] == "kenn.retrieval_status.v1"
    assert retrieval["active_mode"] in {"unavailable", "bm25_only", "hybrid"}


def test_fastapi_cors_allows_local_frontend_only():
    allowed = client.get("/api/health", headers={"Origin": "http://127.0.0.1:5173"})
    assert allowed.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"

    untrusted = client.get("/api/health", headers={"Origin": "https://untrusted.example"})
    assert "access-control-allow-origin" not in untrusted.headers
    assert "access-control-allow-credentials" not in untrusted.headers


def test_fastapi_openapi_spec():
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    data = resp.json()
    assert data["info"]["title"] == "KENN Audio Engineering Companion"
    assert "/api/ask" in data["paths"]
    assert "/api/ableton/command" in data["paths"]
    assert "/api/mix-review/reference-match" in data["paths"]


def test_fastapi_suggest():
    resp = client.get("/api/suggest?q=compr")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list) and len(data) > 0


def test_fastapi_session_card():
    resp = client.get("/api/ableton/session-card")
    assert resp.status_code == 200
    data = resp.json()
    assert "ok" in data
    assert "session" in data
