import tempfile
import sqlite3
import pytest
from pathlib import Path

from kenn.knowledge.reasoning import init_db
from kenn.knowledge.contradictions import (
    scan_for_contradictions,
    list_contradictions,
    resolve_contradiction,
)

@pytest.fixture
def temp_env(monkeypatch):
    """Fixture to isolate reasoning DB and training notes in a temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "kenn.db"
        notes_dir = Path(tmpdir) / "notes"
        notes_dir.mkdir()
        
        monkeypatch.setenv("KENN_DB_PATH", str(db_path))
        monkeypatch.setenv("KENN_CHATS_DIR", tmpdir)
        yield db_path, notes_dir

def test_contradictions_db_initialization(temp_env):
    """Verify contradictions table is initialized in SQLite."""
    init_db()
    db_path, _ = temp_env
    assert db_path.exists()
    
    conn = sqlite3.connect(str(db_path))
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    assert "knowledge_contradictions" in tables

def test_contradiction_detection_notes(temp_env):
    """Verify scan_for_contradictions detects conflicting measurements on shared tag."""
    _, notes_dir = temp_env
    
    # Create two conflicting notes
    note_a = (
        "# Mix Bus Glue\n\n"
        "Type: Note\n"
        "Tags: compression, glue\n"
        "Status: Approved\n\n"
        "Contradiction-Key: mix-bus-threshold\n\n"
        "Set the Glue Compressor threshold to -6 dB."
    )
    note_b = (
        "# Light Bus Comp\n\n"
        "Type: Note\n"
        "Tags: compression, glue\n"
        "Status: Approved\n\n"
        "Contradiction-Key: mix-bus-threshold\n\n"
        "Set the compressor threshold to -12 dB."
    )
    (notes_dir / "note_a.md").write_text(note_a, encoding="utf-8")
    (notes_dir / "note_b.md").write_text(note_b, encoding="utf-8")
    
    scan_for_contradictions(notes_dir)
    contradictions = list_contradictions()
    assert len(contradictions) == 1
    assert contradictions[0]["type"] == "measurement_mismatch"
    assert contradictions[0]["source_a"] == "note_a.md"
    assert contradictions[0]["source_b"] == "note_b.md"
    assert "compression" in contradictions[0]["conflicting_data"]["shared_tags"]

def test_contradiction_detection_transcript_vs_manual(temp_env):
    """Verify scan detects transcript note vs manual note conflicts."""
    _, notes_dir = temp_env
    
    # Create one manual note and one transcript note
    note_manual = (
        "# Glue Compressor Guide\n\n"
        "Type: Manual\n"
        "Tags: compression\n"
        "Status: Approved\n"
        "Contradiction-Key: compressor-threshold\n\n"
        "Set threshold to -4 dB."
    )
    note_transcript = (
        "# Virtual Riot Comp Lesson\n\n"
        "Type: Transcript\n"
        "Tags: compression\n"
        "Status: Approved\n"
        "Contradiction-Key: compressor-threshold\n\n"
        "Set threshold to -8 dB."
    )
    (notes_dir / "note_manual.md").write_text(note_manual, encoding="utf-8")
    (notes_dir / "note_transcript.md").write_text(note_transcript, encoding="utf-8")
    
    scan_for_contradictions(notes_dir)
    contradictions = list_contradictions()
    assert len(contradictions) == 1
    assert contradictions[0]["type"] == "transcript_vs_manual"


def test_different_parameters_with_same_unit_are_not_contradictions(temp_env):
    _, notes_dir = temp_env
    note_a = (
        "# Dynamic EQ\nType: Note\nTags: mastering, resonance\nStatus: Approved\n\n"
        "Cap the dynamic EQ boost at 6 dB."
    )
    note_b = (
        "# Master Prep\nType: Note\nTags: mastering, headroom\nStatus: Approved\n\n"
        "Leave -6 dB of headroom before mastering."
    )
    (notes_dir / "dynamic.md").write_text(note_a, encoding="utf-8")
    (notes_dir / "headroom.md").write_text(note_b, encoding="utf-8")

    assert scan_for_contradictions(notes_dir) == []
    assert list_contradictions() == []


def test_rescan_retires_stale_machine_detection(temp_env):
    _, notes_dir = temp_env
    first = "# A\nType: Note\nTags: glue\nStatus: Approved\nContradiction-Key: glue-threshold\n\nSet threshold to -6 dB."
    second = "# B\nType: Note\nTags: glue\nStatus: Approved\nContradiction-Key: glue-threshold\n\nSet threshold to -12 dB."
    path_a = notes_dir / "a.md"
    path_a.write_text(first, encoding="utf-8")
    (notes_dir / "b.md").write_text(second, encoding="utf-8")
    assert len(scan_for_contradictions(notes_dir)) == 1
    assert len(list_contradictions()) == 1

    path_a.write_text(
        "# A\nType: Note\nTags: glue\nStatus: Approved\nContradiction-Key: glue-threshold\n\nSet threshold to -12 dB.",
        encoding="utf-8",
    )
    assert scan_for_contradictions(notes_dir) == []
    assert list_contradictions() == []

def test_resolve_contradiction_primary_a(temp_env):
    """Verify resolve_contradiction updates deprecated note status to Draft."""
    _, notes_dir = temp_env
    
    note_a = (
        "# Mix Bus Glue\n\n"
        "Type: Note\n"
        "Tags: compression\n"
        "Status: Approved\n"
        "Contradiction-Key: mix-bus-threshold\n\n"
        "Set threshold to -6 dB."
    )
    note_b = (
        "# Light Bus Comp\n\n"
        "Type: Note\n"
        "Tags: compression\n"
        "Status: Approved\n"
        "Contradiction-Key: mix-bus-threshold\n\n"
        "Set threshold to -12 dB."
    )
    (notes_dir / "note_a.md").write_text(note_a, encoding="utf-8")
    (notes_dir / "note_b.md").write_text(note_b, encoding="utf-8")
    
    scan_for_contradictions(notes_dir)
    c_list = list_contradictions()
    cid = c_list[0]["contradiction_id"]
    
    # Resolve with primary_a (keeps note_a, deprecates note_b)
    success = resolve_contradiction(cid, "primary_a", notes_dir)
    assert success is True
    
    # Check note_b header is updated to Status: Draft
    content_b = (notes_dir / "note_b.md").read_text(encoding="utf-8")
    assert "Status: Draft" in content_b
    assert "Status: Approved" not in content_b
    
    # Check note_a header is still Status: Approved
    content_a = (notes_dir / "note_a.md").read_text(encoding="utf-8")
    assert "Status: Approved" in content_a

def test_build_index_contradictions_threshold(temp_env, monkeypatch):
    """Verify build_index aborts with SystemExit if open contradictions exceed limit."""
    _, notes_dir = temp_env
    
    # Create 2 conflicting notes to generate 1 contradiction
    note_a = "# Note A\nType: Note\nTags: eq\nStatus: Approved\nContradiction-Key: eq-cut\n\nCut at 200 Hz."
    note_b = "# Note B\nType: Note\nTags: eq\nStatus: Approved\nContradiction-Key: eq-cut\n\nCut at 300 Hz."
    (notes_dir / "note_a.md").write_text(note_a, encoding="utf-8")
    (notes_dir / "note_b.md").write_text(note_b, encoding="utf-8")
    
    # Set limit to 0 so 1 contradiction exceeds it
    monkeypatch.setenv("KENN_MAX_CONTRADICTIONS", "0")
    
    from kenn.retrieval.build_index import build_index
    with pytest.raises(SystemExit) as excinfo:
        build_index(pdf_dir=notes_dir, notes_dir=notes_dir)
        
    assert "Index rebuild blocked due to 1 open contradictions." in str(excinfo.value)
