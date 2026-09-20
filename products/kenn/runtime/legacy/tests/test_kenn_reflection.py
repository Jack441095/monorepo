import tempfile
import sqlite3
import pytest
from pathlib import Path

from kenn.knowledge.reasoning import init_db
from kenn.knowledge.trust_scores import (
    get_source_trust,
    record_citation,
    record_correction,
)
from kenn.knowledge.reflection import (
    post_answer_critique,
    ingest_correction,
    list_lessons,
    list_corrections,
    propose_maintenance,
)

@pytest.fixture
def temp_db_env(monkeypatch):
    """Fixture to isolate reflection DB in a temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "kenn.db"
        monkeypatch.setenv("KENN_DB_PATH", str(db_path))
        monkeypatch.setenv("KENN_CHATS_DIR", tmpdir)
        yield db_path

def test_reflection_db_initialization(temp_db_env):
    """Verify reflection/trust tables are initialized in SQLite."""
    init_db()
    assert temp_db_env.exists()
    
    conn = sqlite3.connect(str(temp_db_env))
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    assert "knowledge_lessons" in tables
    assert "source_trust" in tables

def test_source_trust_lifecycle(temp_db_env):
    """Verify default trust, citation boosts, and corrections penalties."""
    # Default trust resolution
    manual_trust = get_source_trust("user-manual-ableton.pdf")
    note_trust = get_source_trust("compression-note.md")
    web_trust = get_source_trust("random-web-forum.html")
    
    assert manual_trust == 1.0
    assert note_trust == 0.9
    assert web_trust == 0.5
    
    # Verify citations boost trust
    record_citation("compression-note.md")
    assert get_source_trust("compression-note.md") == 0.91
    
    # Verify corrections penalize trust
    record_correction("compression-note.md")
    assert get_source_trust("compression-note.md") == 0.81

def test_critique_citations_check(temp_db_env):
    """Verify critique flags cited sources that were not retrieved."""
    # Chunk result mapping
    results = [
        (0.8, {"source": "compression-note.md", "title": "Mix Bus Compression", "page": 1}),
    ]
    
    # Valid answer citing active sources
    valid_answer = (
        "Make sure to use Glue Compressor.\n\n"
        "Sources:\n"
        "- Mix Bus Compression (compression-note.md)"
    )
    critique = post_answer_critique("How to compress?", valid_answer, results, [])
    assert critique["passed"] is True
    assert not critique["warnings"]
    
    # Invalid answer citing hallucinated source
    invalid_answer = (
        "Make sure to use Glue Compressor.\n\n"
        "Sources:\n"
        "- Hallucinated Note (fake-note.md)"
    )
    critique = post_answer_critique("How to compress?", invalid_answer, results, [])
    assert critique["passed"] is False
    assert any("fake-note.md" in w for w in critique["warnings"])

def test_critique_contradictions_check(temp_db_env):
    """Verify critique flags measurements that contradict past reasoning traces."""
    # Past trace that recommends -4 dB threshold
    past_traces = [
        {
            "trace_id": "trace-1",
            "query": "What threshold should I use?",
            "conclusion": "Set threshold to -4 dB with a fast attack.",
        }
    ]
    
    # Non-contradicting answer (recommends -4 dB or no measurements)
    answer_ok = "For good control, set threshold to -4 dB."
    critique = post_answer_critique("What threshold?", answer_ok, [], past_traces)
    assert critique["passed"] is True
    
    # Contradicting answer (recommends -8 dB threshold, mismatch on dB unit)
    answer_fail = "For good control, set threshold to -8 dB."
    critique = post_answer_critique("What threshold?", answer_fail, [], past_traces)
    assert critique["passed"] is False
    assert any("Contradiction warning" in w for w in critique["warnings"])

def test_ingest_correction(temp_db_env, monkeypatch):
    """Verify ingesting a user correction logs a lesson and penalizes source trust."""
    # Mock chunks list for get_chunk_id source resolution
    mock_chunk = {"source": "compression-note.md", "page": 1, "text": "chunk data"}
    from kenn.knowledge.reasoning import get_chunk_id
    chunk_id = get_chunk_id(mock_chunk)
    
    def mock_load_chunks():
        return [mock_chunk]
    
    monkeypatch.setattr("kenn.core.chat_retrieval.load_chunks", mock_load_chunks)
    
    # Pre-populate reasoning trace
    from kenn.knowledge.reasoning import save_reasoning_trace
    trace_id = save_reasoning_trace(
        query="What threshold for vocal compressor?",
        route="production",
        evidence_ids=[chunk_id],
        conclusion="Use a -6 dB threshold.",
        confidence="high",
        tags=["vocals", "compression"],
        trace_id="test-trace-id",
    )
    assert trace_id == "test-trace-id"
    
    # Initial source trust
    assert get_source_trust("compression-note.md") == 0.9
    
    # Ingest user correction
    res = ingest_correction("test-trace-id", "Use a -3 dB threshold instead to keep vocals dynamic.")
    assert res is not None
    assert "lesson" in res
    assert len(res["penalized_sources"]) == 1
    assert res["penalized_sources"][0]["source"] == "compression-note.md"
    assert res["penalized_sources"][0]["new_trust"] == 0.8
    
    # Verify trace is updated
    conn = sqlite3.connect(str(temp_db_env))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM knowledge_reasoning WHERE trace_id = ?", (trace_id,)).fetchone()
    assert row["outcome"] == "user_corrected"
    assert row["correction"] == "Use a -3 dB threshold instead to keep vocals dynamic."
    
    # Verify lesson is registered
    lessons = list_lessons()
    assert len(lessons) == 1
    assert lessons[0]["source_trace_id"] == "test-trace-id"
    assert "User corrected conclusion" in lessons[0]["lesson"]
    
    # Verify corrections listing
    corrs = list_corrections()
    assert len(corrs) == 1
    assert corrs[0]["trace_id"] == "test-trace-id"


def test_propose_maintenance(temp_db_env):
    """Verify propose_maintenance correctly flags low trust, contradictions, and coverage gaps."""
    init_db()
    
    # 1. Low Trust Note
    # Record multiple corrections to bring trust score below 0.7
    record_correction("stale-note.md")
    record_correction("stale-note.md")
    record_correction("stale-note.md")
    assert get_source_trust("stale-note.md") < 0.7
    
    # 2. Contradiction
    from kenn.knowledge.contradictions import save_contradiction
    save_contradiction(
        "measurement_mismatch",
        "note_a.md",
        "note_b.md",
        "Conflicting thresholds",
        {"unit": "db", "values_a": [-6], "values_b": [-12]}
    )
    
    # 3. Coverage Gap
    # Create two user lessons with the same topic 'vocals'
    import uuid
    import datetime
    from kenn.knowledge.reasoning import _get_conn
    created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO knowledge_lessons VALUES (?, ?, 'vocals', 'Lesson 1', 'trace-a')",
            (str(uuid.uuid4()), created_at)
        )
        conn.execute(
            "INSERT INTO knowledge_lessons VALUES (?, ?, 'vocals', 'Lesson 2', 'trace-b')",
            (str(uuid.uuid4()), created_at)
        )
        
    proposals = propose_maintenance()
    types = [p["type"] for p in proposals]
    
    assert "low_trust" in types
    assert "contradiction" in types
    assert "coverage_gap" in types
    
    # Check low trust specifics
    low_trust_prop = next(p for p in proposals if p["type"] == "low_trust")
    assert low_trust_prop["source"] == "stale-note.md"
    assert "stale-note.md" in low_trust_prop["description"]
    
    # Check contradiction specifics
    contradiction_prop = next(p for p in proposals if p["type"] == "contradiction")
    assert "Conflicting thresholds" in contradiction_prop["description"]
    
    # Check coverage gap specifics
    gap_prop = next(p for p in proposals if p["type"] == "coverage_gap")
    assert gap_prop["source"] == "vocals"
    assert "consistent answering difficulty" in gap_prop["description"]

