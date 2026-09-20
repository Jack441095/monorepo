from __future__ import annotations

import json
import sqlite3
import threading
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

import kenn.server as server_module


def _cache(tmp_path):
    path = tmp_path / "sample_cache.sqlite3"
    db = sqlite3.connect(path)
    db.execute(
        """CREATE TABLE sample_cache (
        path TEXT PRIMARY KEY, category TEXT, subcategory TEXT,
        secondary_tags TEXT, tag_confidence REAL, tag_source TEXT,
        tag_user_overridden INTEGER, winning_evidence TEXT,
        classification_model_version INTEGER, taxonomy_version INTEGER)"""
    )
    db.execute(
        "INSERT INTO sample_cache VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("/private/library/kick.wav", "Drums", "Kick", "Punchy", 0.91, "ml_v3", 0, "DSP", 6, 5),
    )
    db.commit()
    db.close()
    return path


@pytest.fixture
def slo_server():
    httpd = server_module.ThreadingHTTPServer(("127.0.0.1", 0), server_module.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        thread.join(timeout=2)
        httpd.server_close()


def test_list_and_detail_routes_are_read_only_and_path_safe(tmp_path, monkeypatch, slo_server):
    monkeypatch.setenv("SLO_CLASSIFICATION_DB", str(_cache(tmp_path)))
    with urlopen(f"{slo_server}/api/slo/classifications", timeout=2) as response:
        payload = json.load(response)
    assert payload["status"] == "ready"
    item = payload["items"][0]
    assert item["display_name"] == "kick.wav"
    assert "path" not in item

    with urlopen(f"{slo_server}/kenn/api/slo/classifications/{item['id']}", timeout=2) as response:
        detail = json.load(response)
    assert detail["item"]["id"] == item["id"]


def test_unavailable_route_has_structured_state(tmp_path, monkeypatch, slo_server):
    monkeypatch.setenv("SLO_CLASSIFICATION_DB", str(tmp_path / "missing.sqlite3"))
    with pytest.raises(HTTPError) as captured:
        urlopen(f"{slo_server}/api/slo/classifications", timeout=2)
    assert captured.value.code == 503
    payload = json.load(captured.value)
    assert payload["status"] == "unavailable"
    assert payload["items"] == []
