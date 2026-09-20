"""Tests for KENN session history trends SQLite mining."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
LM = ROOT / "studio" / "kenn" / "kenn"
sys.path.insert(0, str(LM.parent))

from kenn.core import session_memory


def test_session_trends_aggregation(tmp_path, monkeypatch):
    # Mock database path to avoid messing with the production db
    db_file = tmp_path / "test_kenn.db"
    monkeypatch.setattr(session_memory, "DB_PATH", db_file)
    
    # 1. Initially trends should be empty
    trends = session_memory.get_cross_session_trends()
    assert trends["ok"] is True
    assert trends["total_sessions_analyzed"] == 0
    assert len(trends["topics"]) == 0
    assert len(trends["techniques"]) == 0
    
    # 2. Save mock session states to SQLite database
    session_memory._get_db().close()
    
    # Session 1: topics=["compression", "eq"], techniques=["saturation"]
    state1 = {
        "session_id": "session1",
        "topics_mentioned": ["compression", "eq"],
        "techniques_mentioned": ["saturation"],
        "updated_at": 1000,
        "created_at": 1000
    }
    session_memory.save_session_to_db(state1)
    
    # Session 2: topics=["eq"], techniques=["saturation", "limiting"]
    state2 = {
        "session_id": "session2",
        "topics_mentioned": ["eq"],
        "techniques_mentioned": ["saturation", "limiting"],
        "updated_at": 2000,
        "created_at": 2000
    }
    session_memory.save_session_to_db(state2)
    
    # 3. Aggregate trends and verify frequencies
    trends = session_memory.get_cross_session_trends()
    assert trends["ok"] is True
    assert trends["total_sessions_analyzed"] == 2
    
    # "eq" occurs in 2 sessions, "compression" in 1
    topics_map = {t["topic"]: t["count"] for t in trends["topics"]}
    assert topics_map["eq"] == 2
    assert topics_map["compression"] == 1
    
    # "saturation" occurs in 2 sessions, "limiting" in 1
    techs_map = {t["technique"]: t["count"] for t in trends["techniques"]}
    assert techs_map["saturation"] == 2
    assert techs_map["limiting"] == 1


def test_cmd_session_dump(tmp_path, monkeypatch, capsys):
    db_file = tmp_path / "test_kenn.db"
    monkeypatch.setattr(session_memory, "DB_PATH", db_file)
    
    import importlib.util
    spec = importlib.util.spec_from_file_location("root_main", str(ROOT / "main.py"))
    root_main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(root_main)
    
    # 1. Non-existent session
    code = root_main.cmd_session_dump(["nonexistent"])
    assert code == 1
    
    # 2. Existing session
    state = {
        "session_id": "session123",
        "topics_mentioned": ["eq"],
        "created_at": 12345,
        "last_updated": 12345
    }
    session_memory.save_session_to_db(state)
    
    capsys.readouterr()
    code = root_main.cmd_session_dump(["session123"])
    assert code == 0
    captured = capsys.readouterr()
    
    import json
    dumped = json.loads(captured.out)
    assert dumped["session_id"] == "session123"
    assert dumped["topics_mentioned"] == ["eq"]


def test_configured_retention_is_bounded(monkeypatch):
    monkeypatch.setenv("AUDIO_TOO_KENN_SESSION_RETENTION_HOURS", "48")
    assert session_memory.configured_retention_hours() == 48
    monkeypatch.setenv("AUDIO_TOO_KENN_SESSION_RETENTION_HOURS", "invalid")
    assert session_memory.configured_retention_hours() == 168
    monkeypatch.setenv("AUDIO_TOO_KENN_SESSION_RETENTION_HOURS", "999999")
    assert session_memory.configured_retention_hours() == 8760


def test_cmd_session_delete_requires_confirmation(tmp_path, monkeypatch):
    db_file = tmp_path / "delete_kenn.db"
    monkeypatch.setattr(session_memory, "DB_PATH", db_file)
    session_memory.save_session_to_db({"session_id": "delete-me", "created_at": 12345})

    import importlib.util

    spec = importlib.util.spec_from_file_location("root_main_delete", str(ROOT / "main.py"))
    root_main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(root_main)

    assert root_main.cmd_session_delete(["delete-me"]) == 2
    assert session_memory.load_session_from_db("delete-me") is not None
    assert root_main.cmd_session_delete(["delete-me", "--yes"]) == 0
    assert session_memory.load_session_from_db("delete-me") is None
