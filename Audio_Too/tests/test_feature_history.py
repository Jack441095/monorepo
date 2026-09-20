"""Tests for ML feature history storage and feedback enrichment."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "studio" / "audio_analysis"))
sys.path.insert(0, str(ROOT / "studio"))

# We test the review_store functions directly, mocking connect.
from audio_analysis.mix_review import review_store


def _mock_connect(db_path: Path):
    """Return a context manager that gives an in-memory SQLite connection."""
    class _MockConn:
        def __enter__(self2):
            self2.conn = sqlite3.connect(str(db_path))
            self2.conn.row_factory = sqlite3.Row
            return self2.conn

        def __exit__(self2, *args):
            self2.conn.close()

        def execute(self2, *a, **kw):
            return self2.conn.execute(*a, **kw)

        def commit(self2):
            self2.conn.commit()

    return _MockConn()


def _init_tables(db_path: Path) -> None:
    """Ensure the feature history and feedback tables exist."""

    def _conn_func():
        return _mock_connect(db_path)
    review_store.init_feature_history(_conn_func)


def _make_minimal_report(review_id: str, score: int = 80) -> dict:
    """Return a minimal report dict with enough metrics for feature extraction."""
    return {
        "id": review_id,
        "title": "Test Track",
        "created_at": "2026-06-24T12:00:00",
        "version_label": "v1",
        "metrics": {
            "filename": "test.wav",
            "duration_seconds": 120.0,
            "sample_rate": 44100,
            "peak_dbfs": -3.21,
            "left_peak_dbfs": -3.5,
            "right_peak_dbfs": -4.1,
            "rms_dbfs_estimate": -18.5,
            "loudest_section_rms_dbfs": -12.3,
            "dynamic_range_estimate_db": 8.2,
            "crest_factor_db": 14.0,
            "true_peak_dbfs": -2.9,
            "integrated_lufs": -14.2,
            "leading_silence_seconds": 0.02,
            "trailing_silence_seconds": 0.15,
            "dc_offset": 0.0001,
            "stereo_balance": 0.02,
            "stereo_correlation": 0.85,
            "stereo_width_ratio": 0.35,
            "clipping_risk": False,
            "clipped_frames_estimate": 0,
            "bands": {"sub": 0.05, "bass": 0.10, "low_mids": 0.20, "mids": 0.35, "presence": 0.18, "sibilance": 0.08, "air": 0.04},
            "perceptual_bands": {"sub": 0.02, "bass": 0.06, "low_mids": 0.15, "mids": 0.30, "presence": 0.25, "sibilance": 0.12, "air": 0.10},
            "mid_bands": {"sub": 0.03, "bass": 0.08, "low_mids": 0.18, "mids": 0.32, "presence": 0.22, "sibilance": 0.10, "air": 0.07},
            "side_bands": {"sub": 0.01, "bass": 0.02, "low_mids": 0.05, "mids": 0.08, "presence": 0.10, "sibilance": 0.06, "air": 0.04},
            "correlation_bands": {"sub": 0.95, "bass": 0.90, "low_mids": 0.85, "mids": 0.80, "presence": 0.75, "sibilance": 0.70, "air": 0.65},
            "perceptual_summary": {"dominant_band": "mids", "presence_share": 0.47, "low_end_share": 0.08},
            "spectral_features": {"centroid_hz": 1200.5, "rolloff_85_hz": 8500.0, "high_frequency_share": 0.05},
            "tonal_balance": {"profile": "balanced", "low_end_share": 0.15, "body_share": 0.55, "clarity_share": 0.30, "perceived_clarity_share": 0.35},
            "dynamic_profile": {"profile": "controlled", "crest_factor_db": 14.0, "transient_margin_db": 3.2, "short_term_range_db": 6.5, "section_range_db": 8.1},
            "stereo_field": {"image": "stable", "low_side_share": 0.02, "low_band_correlation": 0.92},
            "section_analysis": {"sections": [{"label": "Intro", "rms_dbfs": -22.0}, {"label": "Verse", "rms_dbfs": -18.5}]},
            "chords": {"estimated_key": "C Major", "key_confidence_score": 0.85, "sanity": {"changes_per_minute": 8.0, "complex_chord_ratio": 0.1, "named_sections": 2}},
            "mix_goal": {"key": "premaster", "label": "Premaster"},
            "technical_score": score,
        },
    }


def test_cache_feature_vector_stores_vector(tmp_path) -> None:
    db_path = tmp_path / "test_features.db"


    def conn_func():
        return _mock_connect(db_path)
    _init_tables(db_path)

    report = _make_minimal_report("rev-1")
    review_store.cache_feature_vector(report, connect_func=conn_func)

    rows = review_store.load_feature_history(connect_func=conn_func)
    assert len(rows) == 1
    assert rows[0]["review_id"] == "rev-1"
    assert rows[0]["title"] == "Test Track"
    assert rows[0]["version_label"] == "v1"
    assert rows[0]["mix_goal_key"] == "premaster"

    features = rows[0]["features"]
    assert isinstance(features, dict)
    assert features["technical_score"] == 80
    assert features["peak_dbfs"] == -3.21


def test_cache_feature_vector_upserts_by_review_id(tmp_path) -> None:
    db_path = tmp_path / "test_upsert.db"


    def conn_func():
        return _mock_connect(db_path)
    _init_tables(db_path)

    report_v1 = _make_minimal_report("rev-2", score=75)
    review_store.cache_feature_vector(report_v1, connect_func=conn_func)

    report_v2 = _make_minimal_report("rev-2", score=82)
    report_v2["version_label"] = "v2"
    review_store.cache_feature_vector(report_v2, connect_func=conn_func)

    rows = review_store.load_feature_history(connect_func=conn_func)
    assert len(rows) == 1
    assert rows[0]["version_label"] == "v2"
    assert rows[0]["features"]["technical_score"] == 82


def test_cache_feature_vector_handles_missing_metrics(tmp_path) -> None:
    db_path = tmp_path / "test_no_metrics.db"


    def conn_func():
        return _mock_connect(db_path)
    _init_tables(db_path)

    review_store.cache_feature_vector({"id": "rev-3"}, connect_func=conn_func)

    rows = review_store.load_feature_history(connect_func=conn_func)
    assert len(rows) == 0


def test_load_feature_history_by_review_id(tmp_path) -> None:
    db_path = tmp_path / "test_filter.db"

    def conn_func():
        return _mock_connect(db_path)
    _init_tables(db_path)

    review_store.cache_feature_vector(_make_minimal_report("rev-a", score=70), connect_func=conn_func)
    review_store.cache_feature_vector(_make_minimal_report("rev-b", score=85), connect_func=conn_func)

    rows = review_store.load_feature_history(connect_func=conn_func, review_id="rev-a")
    assert len(rows) == 1
    assert rows[0]["review_id"] == "rev-a"


def test_cache_feedback_feature_vector_stores_labelled_data(tmp_path) -> None:
    db_path = tmp_path / "test_feedback.db"

    def conn_func():
        return _mock_connect(db_path)
    _init_tables(db_path)

    report = _make_minimal_report("rev-fb-1", score=65)
    review_store.cache_feedback_feature_vector(
        feedback_id="fb-1",
        review_id="rev-fb-1",
        decision="accepted",
        note="Good first fix suggestion.",
        report=report,
        connect_func=conn_func,
    )

    rows = review_store.load_feedback_training_data(connect_func=conn_func)
    assert len(rows) == 1
    assert rows[0]["feedback_id"] == "fb-1"
    assert rows[0]["decision"] == "accepted"
    assert rows[0]["note"] == "Good first fix suggestion."

    features = rows[0]["features"]
    assert isinstance(features, dict)
    assert features["technical_score"] == 65


def test_delete_feature_history_removes_all_records(tmp_path) -> None:
    db_path = tmp_path / "test_delete.db"

    def conn_func():
        return _mock_connect(db_path)
    _init_tables(db_path)

    report = _make_minimal_report("rev-del")
    review_store.cache_feature_vector(report, connect_func=conn_func)
    review_store.cache_feedback_feature_vector(
        feedback_id="fb-del", review_id="rev-del",
        decision="rejected", note="", report=report,
        connect_func=conn_func,
    )

    review_store.delete_feature_history("rev-del", connect_func=conn_func)

    assert len(review_store.load_feature_history(connect_func=conn_func)) == 0
    assert len(review_store.load_feedback_training_data(connect_func=conn_func)) == 0


def test_record_review_feedback_enriches_with_features(tmp_path, monkeypatch) -> None:
    """Verify that record_review_feedback stores a feature vector."""
    db_path = tmp_path / "test_record_feedback.db"

    def conn_func():
        return _mock_connect(db_path)
    _init_tables(db_path)

    # Mock the connect used by record_review_feedback
    monkeypatch.setattr(review_store, "connect", conn_func)

    feedback_path = tmp_path / "feedback.jsonl"
    report = _make_minimal_report("rev-fb-full", score=78)

    result = review_store.record_review_feedback(
        "rev-fb-full",
        "accepted",
        "Catchy hook.",
        path=feedback_path,
        review_lookup=lambda _rid: {"report_name": "rev-fb-full.json", "id": "rev-fb-full"},
        report_reader=lambda _name: report,
        connect_func=conn_func,
    )

    assert result["ok"] is True

    fb_rows = review_store.load_feedback_training_data(connect_func=conn_func)
    assert len(fb_rows) == 1
    assert fb_rows[0]["features"]["technical_score"] == 78
