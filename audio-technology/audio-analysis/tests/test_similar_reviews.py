"""Tests for find_similar_reviews() — A7.1 Spectral Fingerprint Embedding."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

from audio_analysis.mix_review.review_store import find_similar_reviews


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_fv(**overrides) -> dict:
    """Base feature vector with all-zero values; override specific keys."""
    base = {f"bands_{b}": 0.0 for b in ("sub", "bass", "low_mids", "mids", "presence", "sibilance", "air")}
    base.update({
        "peak_dbfs": -6.0, "crest_factor_db": 14.0, "stereo_correlation": 0.85,
        "stereo_width_ratio": 0.45, "integrated_lufs": -18.0,
    })
    base.update(overrides)
    return base


def _make_history(entries: list[dict]) -> list[dict]:
    return [
        {
            "review_id": e["id"],
            "title": e.get("title", f"Mix {e['id']}"),
            "filename": f"{e['id']}.wav",
            "mix_goal_key": e.get("goal", "premaster"),
            "features": e["fv"],
        }
        for e in entries
    ]


@contextmanager
def _stub_connect(history: list[dict]):
    """Context manager stub that patches load_feature_history."""
    with patch(
        "audio_analysis.mix_review.review_store.load_feature_history",
        return_value=history,
    ):
        yield


def _noop_connect():
    pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFindSimilarReviews:

    def test_returns_nearest_match(self):
        """The most similar review (nearest cosine neighbour) is returned first."""
        query = _make_fv(bands_sub=0.10, bands_bass=0.20, peak_dbfs=-6.0)
        # r1 is nearly identical to query; r2 and r3 are very different
        r1 = _make_fv(bands_sub=0.10, bands_bass=0.21, peak_dbfs=-6.1)
        r2 = _make_fv(bands_sub=0.50, bands_bass=0.01, peak_dbfs=-20.0)
        r3 = _make_fv(bands_sub=0.01, bands_bass=0.50, peak_dbfs=-3.0)
        history = _make_history([
            {"id": "r1", "fv": r1, "title": "Close Mix"},
            {"id": "r2", "fv": r2, "title": "Different A"},
            {"id": "r3", "fv": r3, "title": "Different B"},
        ])
        with _stub_connect(history):
            results = find_similar_reviews(query, connect_func=_noop_connect, limit=1)
        assert len(results) == 1
        assert results[0]["review_id"] == "r1"

    def test_excludes_self_by_id(self):
        """A review matching exclude_review_id is never returned."""
        query = _make_fv(bands_sub=0.10)
        r_self = _make_fv(bands_sub=0.10)
        r_other = _make_fv(bands_sub=0.11, peak_dbfs=-7.0)
        history = _make_history([
            {"id": "self", "fv": r_self},
            {"id": "other", "fv": r_other},
            {"id": "other2", "fv": _make_fv(bands_sub=0.09)},
        ])
        with _stub_connect(history):
            results = find_similar_reviews(
                query, connect_func=_noop_connect, limit=2, exclude_review_id="self"
            )
        ids = [r["review_id"] for r in results]
        assert "self" not in ids

    def test_returns_empty_when_too_few_reviews(self):
        """Returns [] when history has fewer reviews than requested limit."""
        history = _make_history([{"id": "only", "fv": _make_fv()}])
        with _stub_connect(history):
            results = find_similar_reviews(_make_fv(), connect_func=_noop_connect, limit=3)
        assert results == []

    def test_result_shape(self):
        """Each result has the expected keys."""
        entries = [{"id": f"r{i}", "fv": _make_fv(peak_dbfs=float(-i))} for i in range(5)]
        history = _make_history(entries)
        with _stub_connect(history):
            results = find_similar_reviews(_make_fv(), connect_func=_noop_connect, limit=2)
        assert len(results) == 2
        for r in results:
            assert "review_id" in r
            assert "title" in r
            assert "filename" in r
            assert "mix_goal_key" in r
            assert "score" in r
            assert 0.0 <= r["score"] <= 1.0

    def test_sklearn_unavailable_returns_empty(self):
        """When sklearn cannot be imported, function returns [] without raising."""
        history = _make_history([
            {"id": f"r{i}", "fv": _make_fv(peak_dbfs=float(-i))} for i in range(5)
        ])
        with _stub_connect(history):
            with patch.dict("sys.modules", {"sklearn": None, "sklearn.neighbors": None, "sklearn.preprocessing": None}):
                results = find_similar_reviews(_make_fv(), connect_func=_noop_connect, limit=3)
        assert results == []
