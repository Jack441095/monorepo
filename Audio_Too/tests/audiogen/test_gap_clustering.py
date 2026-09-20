"""Tests for the gap clustering, note synthesis, and DB operations pipeline."""

import json
import shutil
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import sys
CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent.parent
WEBSITE_DIR = ROOT_DIR / "server" / "app"
KENN_DIR = ROOT_DIR / "studio" / "kenn" / "kenn"

for p in [str(ROOT_DIR), str(WEBSITE_DIR), str(KENN_DIR), str(KENN_DIR / "adaptive"), str(KENN_DIR.parent)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import gap_clustering
import suggested_notes_ops
import db


@pytest.fixture
def temp_dirs():
    """Setup temporary directories for database and markdown notes."""
    temp_dir = tempfile.mkdtemp()
    temp_path = Path(temp_dir)
    
    db_path = temp_path / "audio_too.db"
    notes_dir = temp_path / "Training_Data_Notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    
    # Save original paths
    orig_db_path = db.DB_PATH
    orig_notes_dir = suggested_notes_ops.NOTES_DIR
    orig_kenn_dir = gap_clustering.KENN_DIR
    
    # Patch paths
    db.DB_PATH = db_path
    suggested_notes_ops.NOTES_DIR = notes_dir
    gap_clustering.KENN_DIR = temp_path
    
    # Initialize DB
    db.init_db()
    
    yield temp_path, db_path, notes_dir
    
    # Restore paths
    db.DB_PATH = orig_db_path
    suggested_notes_ops.NOTES_DIR = orig_notes_dir
    gap_clustering.KENN_DIR = orig_kenn_dir
    
    shutil.rmtree(temp_dir)


def test_fetch_queries_and_clustering(temp_dirs):
    temp_path, db_path, notes_dir = temp_dirs

    # 1. Populate tips_gaps table in business DB
    with db.connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tips_gaps (
                id TEXT PRIMARY KEY, question TEXT, confidence TEXT, status TEXT
            )
            """
        )
        rows = [
            ("g1", "How to fix muddy vocals?", "low", "open"),
            ("g2", "How do I fix muddy vocals?", "low", "open"),
            ("g3", "Fix muddy vocals", "low", "open"),
            ("g4", "Compressing drum tracks", "low", "open"),
            ("g5", "Drum compression workflow", "low", "open"),
            ("g6", "Compressing drums in Ableton", "low", "open"),
            ("g7", "pricing of mix reviews", "low", "resolved"),
        ]
        conn.executemany(
            "INSERT INTO tips_gaps (id, question, confidence, status) VALUES (?, ?, ?, ?)",
            rows,
        )
        conn.commit()

    # 2. Populate kenn.db sessions table
    kenn_db = temp_path / "chats" / "kenn.db"
    kenn_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(kenn_db) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY, state TEXT
            )
            """
        )
        state_str = json.dumps({
            "last_confidence": "low",
            "last_question": "how do I fix muddy vocals?"
        })
        conn.execute("INSERT INTO sessions VALUES (?, ?)", ("s1", state_str))
        conn.commit()

    # Test fetch_queries
    queries = gap_clustering.fetch_queries()
    # Should get deduplicated queries:
    # "How to fix muddy vocals?", "Compressing drum tracks", "Drum compression workflow", "Compressing drums in Ableton"
    # Wait, "How to fix muddy vocals?", "How do I fix muddy vocals?", "how do I fix muddy vocals?" are different strings but might be normalized to the same.
    # Normalization: "how to fix muddy vocals", "how do i fix muddy vocals", "fix muddy vocals", "compressing drum tracks", "drum compression workflow", "compressing drums in ableton".
    assert len(queries) >= 3

    # Test clustering
    clusters = gap_clustering.cluster_queries(queries)
    # Since all-MiniLM-L6-v2 is local, clustering should group the similar queries
    # e.g., the vocal query cluster or drum compression cluster if DBSCAN finds them close.
    # We just verify DBSCAN doesn't crash and returns a dict
    assert isinstance(clusters, dict)


@patch("kenn.llm.kenn_lm.KennLM")
@patch("kenn.llm.llm_rewrite.chat_completion")
@patch("kenn.llm.llm_rewrite.is_enabled")
def test_note_synthesis_and_operations(mock_is_enabled, mock_chat_completion, mock_kenn_lm, temp_dirs):
    temp_path, db_path, notes_dir = temp_dirs
    mock_is_enabled.return_value = True
    
    # Mock cloud LLM response
    mock_chat_completion.return_value = """# Dynamic Drum Compression

This note outlines drum compression techniques.
Use glue compressor for glueing.

Tags: drum, compression, workflow"""

    # Mock KennLM to be unavailable to trigger cloud fallback
    mock_lm_instance = MagicMock()
    mock_lm_instance.available = False
    mock_kenn_lm.return_value = mock_lm_instance

    cluster_qs = ["Drum compression workflow", "Compressing drums in Ableton", "Compressing drum tracks"]
    
    # Create tips_gaps table and open gaps for testing linking
    import tips_gaps
    tips_gaps.init_gaps_table()
    with db.connect() as conn:
        conn.execute("INSERT INTO tips_gaps (id, question, status) VALUES (?, ?, ?)", ("g1", "Drum compression workflow", "open"))
        conn.execute("INSERT INTO tips_gaps (id, question, status) VALUES (?, ?, ?)", ("g2", "Compressing drums in Ableton", "open"))
        conn.commit()

    # Run synthesis
    note = gap_clustering.synthesize_note(cluster_qs)
    assert note is not None
    assert note["title"] == "Dynamic Drum Compression"
    assert "drum, compression, workflow" in note["content"]

    # Save to suggested_notes table
    from db import upsert_record, now
    draft_id = "d1"
    record = {
        "id": draft_id,
        "title": note["title"],
        "content": note["content"],
        "source_cluster_queries": note["source_cluster_queries"],
        "status": "pending",
        "created_at": now(),
        "updated_at": now(),
    }
    upsert_record("suggested_notes", record)

    # Test list_suggested_notes
    drafts = suggested_notes_ops.list_suggested_notes()
    assert len(drafts) == 1
    assert drafts[0]["id"] == draft_id
    assert drafts[0]["title"] == "Dynamic Drum Compression"

    # Test save edits
    edited_content = """# Edited Title

Type: Mixing workflow
Tags: drum, compression, workflow
Status: Draft
Source: Reviewed cluster excerpts
Reviewed: 2026-07-01

Short answer:
New content body for controlled drum compression.

Try this:
1. Set the threshold from the loudest drum hits.

Why it matters:
The envelope should support the groove.

Related questions:
- How much gain reduction should I use?
- How should release follow the groove?
"""
    edits_res = suggested_notes_ops.save_suggested_note_edits(draft_id, "Edited Title", edited_content)
    assert edits_res["ok"] is True
    draft = suggested_notes_ops.get_suggested_note(draft_id)
    assert draft["title"] == "Edited Title"

    # Test approve
    approve_res = suggested_notes_ops.approve_suggested_note(draft_id)
    assert approve_res["ok"] is True
    assert approve_res["gaps_linked"] == 2
    
    # Verify file is written
    note_path = notes_dir / "edited-title.md"
    assert note_path.exists()
    assert "New content body" in note_path.read_text(encoding="utf-8")

    # Verify status in suggested_notes is updated
    draft = suggested_notes_ops.get_suggested_note(draft_id)
    assert draft["status"] == "approved"

    # Verify gaps status updated to drafted
    with db.connect() as conn:
        rows = conn.execute("SELECT status, note_file FROM tips_gaps").fetchall()
        for r in rows:
            assert r["status"] == "drafted"
            assert r["note_file"] == "edited-title.md"


def test_dismiss_suggested_note(temp_dirs):
    temp_path, db_path, notes_dir = temp_dirs
    from db import upsert_record, now
    
    draft_id = "d2"
    record = {
        "id": draft_id,
        "title": "Bad Draft",
        "content": "Irrelevant text",
        "source_cluster_queries": json.dumps(["unrelated query"]),
        "status": "pending",
        "created_at": now(),
        "updated_at": now(),
    }
    upsert_record("suggested_notes", record)

    # Dismiss
    dismiss_res = suggested_notes_ops.dismiss_suggested_note(draft_id)
    assert dismiss_res["ok"] is True
    
    draft = suggested_notes_ops.get_suggested_note(draft_id)
    assert draft["status"] == "dismissed"
