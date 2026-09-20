"""Tests for business/app/podcast_report_store.py (migration 016)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server" / "app"))

import db  # noqa: E402
import podcast_report_store  # noqa: E402


@pytest.fixture(autouse=True)
def _use_temp_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "audio_too.db")
    db.init_db()


def test_save_and_get_round_trip():
    report = {"target": "spotify", "target_label": "Spotify", "score": 91, "checks": []}
    report_id = podcast_report_store.save_podcast_report(
        title="My Episode", target="spotify", report=report, html_report="<html>hi</html>",
    )

    item = podcast_report_store.get_podcast_report(report_id)

    assert item is not None
    assert item["id"] == report_id
    assert item["title"] == "My Episode"
    assert item["target"] == "spotify"
    assert item["score"] == 91
    assert item["report"] == report
    assert item["html_report"] == "<html>hi</html>"


def test_get_returns_none_for_missing_id():
    assert podcast_report_store.get_podcast_report("does-not-exist") is None


def test_get_returns_none_for_empty_id():
    assert podcast_report_store.get_podcast_report("") is None


def test_title_is_truncated_to_160_chars():
    long_title = "x" * 500
    report_id = podcast_report_store.save_podcast_report(
        title=long_title, target="spotify", report={}, html_report="<html></html>",
    )
    item = podcast_report_store.get_podcast_report(report_id)
    assert len(item["title"]) == 160


def test_each_save_gets_a_distinct_id():
    id1 = podcast_report_store.save_podcast_report(title="A", target="spotify", report={}, html_report="")
    id2 = podcast_report_store.save_podcast_report(title="B", target="spotify", report={}, html_report="")
    assert id1 != id2
