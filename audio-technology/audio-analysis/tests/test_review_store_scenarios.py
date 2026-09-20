"""Tests for review_store.py — review persistence, feature caching, feedback.

Covers:
- metric_float()                     — 2 tests
- normalize_title()                  — 2 tests
- cache_feature_vector()             — 2 tests
- cache_feedback_feature_vector()    — 2 tests
- load_feature_history()             — 2 tests
- load_feedback_training_data()      — 1 test
- delete_feature_history()           — 1 test
- numeric_delta()                    — 2 tests
- review_history()                   — 2 tests
- read_report()                      — 2 tests
"""

from __future__ import annotations

import json
import tempfile
import sqlite3
from pathlib import Path

from audio_analysis.mix_review.review_store import (
    metric_float,
    normalize_title,
    cache_feature_vector,
    cache_feedback_feature_vector,
    load_feature_history,
    load_feedback_training_data,
    delete_feature_history,
    numeric_delta,
    review_history,
    read_report,
)


# ==============================================================================
#  metric_float
# ==============================================================================

class TestMetricFloat:
    def test_none(self):
        assert metric_float(None) == 0.0

    def test_float_string(self):
        assert metric_float("3.5") == 3.5


# ==============================================================================
#  normalize_title
# ==============================================================================

class TestNormalizeTitle:
    def test_basic(self):
        assert normalize_title("  My Mix  ") == "my mix"

    def test_empty(self):
        assert normalize_title("") == ""


# ==============================================================================
#  SQLite helpers for remaining tests
# ==============================================================================

def _init_db(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mix_feature_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            review_id TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            filename TEXT DEFAULT '',
            title TEXT DEFAULT '',
            version_label TEXT DEFAULT '',
            mix_goal_key TEXT DEFAULT '',
            feature_json TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mix_feedback_features (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            feedback_id TEXT NOT NULL UNIQUE,
            review_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            decision TEXT NOT NULL,
            note TEXT DEFAULT '',
            feature_json TEXT NOT NULL
        )
    """)
    conn.commit()


def _make_report(overrides=None):
    base = {
        "id": "test-review-1",
        "created_at": "2025-01-01T00:00:00",
        "title": "Test Mix",
        "version_label": "v1",
        "metrics": {
            "filename": "test.wav",
            "technical_score": 78,
            "peak_dbfs": -3.0,
            "crest_factor_db": 14.0,
            "rms_dbfs_estimate": -18.0,
            "mix_goal": {"key": "premaster"},
        },
    }
    if overrides:
        base.update(overrides)
    return base


# ==============================================================================
#  cache_feature_vector
# ==============================================================================

class TestCacheFeatureVector:

    def test_caches_vector(self):
        """Feature vector stored in DB."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        def connect():
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            _init_db(conn)
            return conn

        try:
            report = _make_report({"id": "r1"})
            cache_feature_vector(report, connect_func=connect)
            history = load_feature_history(connect_func=connect)
            assert len(history) == 1
            assert history[0]["review_id"] == "r1"
            assert "peak_dbfs" in history[0]["features"]
        finally:
            db_path.unlink(missing_ok=True)

    def test_skips_without_review_id(self):
        """No review_id → no-op."""
        called = []

        def connect():
            called.append(True)
            return sqlite3.connect(":memory:")

        cache_feature_vector(_make_report({"id": ""}), connect_func=connect)
        assert len(called) == 0


# ==============================================================================
#  cache_feedback_feature_vector
# ==============================================================================

class TestCacheFeedbackFeatureVector:

    def test_caches_feedback(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        def connect():
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            _init_db(conn)
            return conn

        try:
            cache_feedback_feature_vector("fb1", "r1", "yes", "Great", _make_report(), connect_func=connect)
            data = load_feedback_training_data(connect_func=connect)
            assert len(data) == 1
            assert data[0]["decision"] == "yes"
        finally:
            db_path.unlink(missing_ok=True)


# ==============================================================================
#  load_feature_history
# ==============================================================================

class TestLoadFeatureHistory:

    def test_empty(self):
        def connect():
            conn = sqlite3.connect(":memory:")
            conn.row_factory = sqlite3.Row
            _init_db(conn)
            return conn

        assert load_feature_history(connect_func=connect) == []


# ==============================================================================
#  delete_feature_history
# ==============================================================================

class TestDeleteFeatureHistory:

    def test_deletes_by_review_id(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        def connect():
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            _init_db(conn)
            return conn

        try:
            cache_feature_vector(_make_report({"id": "r1"}), connect_func=connect)
            delete_feature_history("r1", connect_func=connect)
            assert load_feature_history(connect_func=connect) == []
        finally:
            db_path.unlink(missing_ok=True)


# ==============================================================================
#  numeric_delta
# ==============================================================================

class TestNumericDelta:

    def test_valid(self):
        assert numeric_delta(10.0, 7.5) == 2.5

    def test_invalid(self):
        assert numeric_delta("abc", 5) is None


# ==============================================================================
#  review_history
# ==============================================================================

class TestReviewHistory:

    def test_compact_format(self):
        """review_history returns compact dicts."""
        items = [
            {"id": "r1", "title": "Mix A", "version_label": "v1", "created_at": "2025-01-01",
             "metrics": {"technical_score": 80, "technical_rating": "Good", "perceptual_summary": {"dominant_band": "mids"}},
             "summary": "A good mix", "flags": [{"label": "low_dynamics"}], "previous_version": None},
        ]
        history = review_history(lambda limit, *a, **kw: items, 10)
        assert len(history) == 1
        assert history[0]["score"] == 80
        assert history[0]["dominant_band"] == "mids"

    def test_title_filtering(self):
        items = [
            {"id": "r1", "title": "My Mix", "metrics": {}, "flags": [], "previous_version": None},
            {"id": "r2", "title": "Other Track", "metrics": {}, "flags": [], "previous_version": None},
        ]
        history = review_history(lambda limit, *a, **kw: items, 10, title="my mix")
        assert len(history) == 1
        assert history[0]["id"] == "r1"


# ==============================================================================
#  read_report
# ==============================================================================

class TestReadReport:

    def test_missing_file(self):
        assert read_report(Path("/nonexistent"), "report.json") == {}

    def test_valid_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"metrics": {"score": 80}}, f)
            path = Path(f.name)

        try:
            report = read_report(path.parent, path.name)
            assert report["metrics"]["score"] == 80
        finally:
            path.unlink(missing_ok=True)
