import json
import sqlite3
import pytest
from pathlib import Path
from kenn.core.session_memory import save_session_feedback
from kenn.core.chat import search
from kenn.adaptive.calibrator import train_calibrator


def test_session_feedback_and_calibrator(tmp_path, monkeypatch):
    # Set up temp chats database path
    temp_db_dir = tmp_path / "chats"
    temp_db_dir.mkdir()
    temp_db_path = temp_db_dir / "kenn.db"
    
    # Patch session_memory and calibrator DB_PATH to use the temp DB
    from kenn.core import session_memory
    monkeypatch.setattr(session_memory, "DB_PATH", temp_db_path)
    import kenn.adaptive.calibrator as calibrator
    monkeypatch.setattr(calibrator, "DB_PATH", temp_db_path)
    
    # Path for output calibrated JSON
    temp_output_path = tmp_path / "calibrated_confidence_multipliers.json"
    monkeypatch.setattr(calibrator, "OUTPUT_PATH", temp_output_path)
    
    # Test DB creation and feedback saving
    save_session_feedback(
        turn_id="turn1",
        explicit_rating=1,
        dwell_seconds=15.0,
        has_followup=False,
        followup_interval_seconds=0.0,
        route="ableton",
        topics=["vocals", "EQ"]
    )
    
    save_session_feedback(
        turn_id="turn2",
        explicit_rating=-1,
        dwell_seconds=3.0,
        has_followup=True,
        followup_interval_seconds=4.0,
        route="production",
        topics=["mixing"]
    )

    # Verify rows in DB
    conn = sqlite3.connect(str(temp_db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM session_feedback").fetchall()
    assert len(rows) == 2
    assert rows[0]["turn_id"] == "turn1"
    assert rows[0]["explicit_rating"] == 1
    assert rows[1]["turn_id"] == "turn2"
    assert rows[1]["explicit_rating"] == -1
    conn.close()

    # Run calibrator with fallback frequency heuristic
    multipliers = train_calibrator()
    assert multipliers != {}
    assert "routes" in multipliers
    assert "topics" in multipliers
    assert multipliers["routes"]["ableton"] == 1.2
    assert multipliers["routes"]["production"] == 0.8
    assert multipliers["topics"]["vocals"] == 1.2

    # Add more samples to fit LogisticRegression
    for i in range(3, 8):
        save_session_feedback(
            turn_id=f"turn{i}",
            explicit_rating=1 if i % 2 == 0 else -1,
            dwell_seconds=20.0 if i % 2 == 0 else 2.0,
            has_followup=False if i % 2 == 0 else True,
            followup_interval_seconds=0.0 if i % 2 == 0 else 3.0,
            route="ableton" if i % 2 == 0 else "production",
            topics=["vocals"] if i % 2 == 0 else ["mixing"]
        )

    # Fit Logistic Regression model
    multipliers_lr = train_calibrator()
    assert multipliers_lr != {}
    assert multipliers_lr["routes"]["ableton"] > 1.0
    assert multipliers_lr["routes"]["production"] < 1.0


def test_search_uses_multipliers(monkeypatch):
    from kenn.core import chat_routing
    kenn_artifacts = Path(__file__).resolve().parent.parent / "studio" / "kenn" / "kenn" / "artifacts"
    orig_path = kenn_artifacts / "calibrated_confidence_multipliers.json"
    backup_path = kenn_artifacts / "calibrated_confidence_multipliers.json.bak"
    had_orig = orig_path.exists()
    if had_orig:
        if backup_path.exists():
            backup_path.unlink()
        orig_path.rename(backup_path)
        
    try:
        # Write test multipliers
        test_mult = {
            "routes": {"ableton": 1.2, "production": 0.8},
            "topics": {"vocals": 1.3, "mixing": 0.7}
        }
        orig_path.parent.mkdir(parents=True, exist_ok=True)
        with orig_path.open("w") as f:
            json.dump(test_mult, f)
            
        dummy_chunks = [
            {"text": "vocal advice", "topics": ["vocals"], "source": "note1", "kind": "note"},
            {"text": "mixing advice", "topics": ["mixing"], "source": "note2", "kind": "note"}
        ]
        from kenn.retrieval import retrieval
        monkeypatch.setattr(retrieval, "bm25_search", lambda query, chunks, terms, limit: [(10.0, dummy_chunks[0]), (10.0, dummy_chunks[1])])
        monkeypatch.setattr(retrieval, "load_embedding_index", lambda: None)
        monkeypatch.setattr(chat_routing, "route_query", lambda query, history: "ableton")
        
        results = search("vocal compress", dummy_chunks, {}, limit=2)
        assert len(results) == 2
        # First chunk gets score: 10.0 * 1.2 (ableton route) * 1.3 (vocals topic) = 15.6
        # Second chunk gets score: 10.0 * 1.2 (ableton route) * 0.7 (mixing topic) = 8.4
        assert results[0][1]["topics"] == ["vocals"]
        assert pytest.approx(results[0][0]) == 15.6
        assert pytest.approx(results[1][0]) == 8.4
        
    finally:
        # Restore backup
        if orig_path.exists():
            orig_path.unlink()
        if had_orig:
            backup_path.rename(orig_path)
