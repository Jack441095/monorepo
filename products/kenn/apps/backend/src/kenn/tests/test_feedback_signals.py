from __future__ import annotations

import json
import sqlite3

from kenn.core import feedback_signals
from kenn.retrieval import retrieval


def _make_db(path, rows: list[tuple[int, list[str]]]) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE session_feedback (topics TEXT, explicit_rating INTEGER)")
    conn.executemany(
        "INSERT INTO session_feedback(topics, explicit_rating) VALUES (?, ?)",
        [(json.dumps(topics), rating) for rating, topics in rows],
    )
    conn.commit()
    conn.close()


def test_feedback_reads_canonical_session_db_and_boosts_topics(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "kenn.db"
    _make_db(db_path, [(5, ["vocals"]), (1, ["vocals"]), (5, ["drums"])])
    monkeypatch.setattr(feedback_signals, "DB_PATH", db_path)
    feedback_signals.reset_cache()

    multipliers = feedback_signals.get_feedback_multipliers()
    assert multipliers["drums"] > multipliers["vocals"]
    assert 0.90 <= multipliers["vocals"] <= 1.10

    results = feedback_signals.apply_feedback_boost([
        (1.0, {"id": "drum", "topics": ["drums"]}),
        (1.0, {"id": "vocal", "topics": ["vocals"]}),
        (1.0, {"id": "untagged", "topics": []}),
    ])
    assert [chunk["id"] for _score, chunk in results] == ["drum", "vocal", "untagged"]
    assert results[-1][0] == 1.0


def test_feedback_is_bounded_and_ignores_malformed_topics(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "kenn.db"
    _make_db(db_path, [(5, ["same"])] * 100 + [(1, ["same"])] * 100)
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO session_feedback(topics, explicit_rating) VALUES (?, ?)", ("not-json", 5))
    conn.commit()
    conn.close()
    monkeypatch.setattr(feedback_signals, "DB_PATH", db_path)
    feedback_signals.reset_cache()

    multipliers = feedback_signals.get_feedback_multipliers()
    assert multipliers["same"] == 1.0
    assert all(0.90 <= value <= 1.10 for value in multipliers.values())


def test_feedback_is_applied_inside_shared_reranker_before_truncation(monkeypatch) -> None:
    monkeypatch.setattr(retrieval, "load_source_feedback_scores", lambda: {})
    monkeypatch.setattr(
        feedback_signals,
        "get_feedback_multipliers",
        lambda: {"preferred": 1.10},
    )
    chunks = [
        {"id": "ordinary", "title": "Advice", "source": "note", "text": "audio advice", "topics": ["ordinary"]},
        {"id": "preferred", "title": "Advice", "source": "note", "text": "audio advice", "topics": ["preferred"]},
    ]

    ranked = retrieval.rerank_results("audio", [(1.0, chunks[0]), (0.99, chunks[1])])

    assert ranked[0][1]["id"] == "preferred"
