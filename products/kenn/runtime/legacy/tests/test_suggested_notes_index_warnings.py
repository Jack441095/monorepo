"""approve_suggested_note() must surface index-rebuild/hot-reload failures
instead of silently swallowing them behind ok=True (P0 fix, 2026-07-12)."""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import pytest

CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent.parent
WEBSITE_DIR = ROOT_DIR / "business" / "app"
KENN_DIR = ROOT_DIR / "studio" / "kenn"

for p in [str(ROOT_DIR), str(WEBSITE_DIR), str(KENN_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import db
import suggested_notes_ops
from db import now, upsert_record


@pytest.fixture
def canonical_setup(monkeypatch):
    """Point both NOTES_DIR and CANONICAL_NOTES_DIR at the same temp dir so
    approve_suggested_note() takes its canonical-index-rebuild branch."""
    temp_dir = tempfile.mkdtemp()
    temp_path = Path(temp_dir)
    notes_dir = temp_path / "Training_Data_Notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    db_path = temp_path / "audio_too.db"

    monkeypatch.setattr(db, "DB_PATH", db_path)
    monkeypatch.setattr(suggested_notes_ops, "NOTES_DIR", notes_dir)
    monkeypatch.setattr(suggested_notes_ops, "CANONICAL_NOTES_DIR", notes_dir)
    db.init_db()

    draft_id = "d1"
    upsert_record(
        "suggested_notes",
        {
            "id": draft_id,
            "title": "Test Note",
            "content": (
                "# Test Note\n\n"
                "Type: Mixing workflow\n"
                "Tags: compression, release, timing\n"
                "Source: Audio_Too studio practice\n"
                "Reviewed: 2026-07-12\n\n"
                "Short answer:\n"
                "Match release timing to the groove.\n\n"
                "Try this:\n"
                "1. Set release so gain recovers just before the next hit.\n\n"
                "Why it matters:\n"
                "It keeps pumping musical instead of distracting.\n\n"
                "Related questions:\n"
                "- How fast should attack be?\n"
                "- What ratio for drum bus glue?\n"
            ),
            "source_cluster_queries": "[]",
            "status": "pending",
            "created_at": now(),
            "updated_at": now(),
        },
    )

    yield draft_id

    shutil.rmtree(temp_dir, ignore_errors=True)


def test_approve_surfaces_index_rebuild_failure(monkeypatch, canonical_setup):
    draft_id = canonical_setup

    def boom(*args, **kwargs):
        raise RuntimeError("index build exploded")

    fake_module = type(sys)("kenn.retrieval.build_index")
    fake_module.build_index = boom
    monkeypatch.setitem(sys.modules, "kenn.retrieval.build_index", fake_module)

    result = suggested_notes_ops.approve_suggested_note(draft_id)

    assert result["ok"] is True
    assert result["index_ok"] is False
    assert any("index build exploded" in w for w in result["warnings"])
    assert "Warning:" in result["message"]


def test_approve_surfaces_hot_reload_failure(monkeypatch, canonical_setup):
    draft_id = canonical_setup

    fake_module = type(sys)("kenn.retrieval.build_index")
    fake_module.build_index = lambda *a, **k: None
    monkeypatch.setitem(sys.modules, "kenn.retrieval.build_index", fake_module)

    def boom_urlopen(*args, **kwargs):
        raise OSError("connection refused")

    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", boom_urlopen)

    result = suggested_notes_ops.approve_suggested_note(draft_id)

    assert result["ok"] is True
    assert result["index_ok"] is False
    assert any("hot-reload" in w for w in result["warnings"])


def test_approve_reports_index_ok_when_both_steps_succeed(monkeypatch, canonical_setup):
    draft_id = canonical_setup

    fake_module = type(sys)("kenn.retrieval.build_index")
    fake_module.build_index = lambda *a, **k: None
    monkeypatch.setitem(sys.modules, "kenn.retrieval.build_index", fake_module)

    import urllib.request

    class _FakeCtx:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _FakeCtx())

    result = suggested_notes_ops.approve_suggested_note(draft_id)

    assert result["ok"] is True
    assert result["index_ok"] is True
    assert result["warnings"] == []
    assert "Warning:" not in result["message"]
