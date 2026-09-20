from __future__ import annotations

import sqlite3

import pytest

from kenn.core.slo_classification_adapter import (
    SloClassificationUnavailable,
    get_classification,
    list_classifications,
)


def _cache(tmp_path):
    path = tmp_path / "sample_cache.sqlite3"
    db = sqlite3.connect(path)
    db.execute(
        """CREATE TABLE sample_cache (
        path TEXT PRIMARY KEY, category TEXT, subcategory TEXT,
        secondary_tags TEXT, tag_confidence REAL, tag_source TEXT,
        tag_user_overridden INTEGER, winning_evidence TEXT,
        classification_model_version INTEGER, taxonomy_version INTEGER)"""
    )
    db.executemany(
        "INSERT INTO sample_cache VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("/private/library/kick.wav", "Drums", "Kick", "Punchy|Short", 1.7, "ml_v3", 0, "DSP", 6, 5),
            ("/private/library/odd.wav", "", "", "", -0.4, "ml_ood", 0, "DSP", 6, 5),
            ("/private/library/vocal.wav", "Vocals", "Vocal Phrase", "Loop", 0.6, "user", 1, "USER_OVERRIDE", 6, 3),
            ("/private/library/todo.wav", "", "", "", None, "unclassified", 0, "UNKNOWN", 0, 0),
        ],
    )
    db.commit()
    db.close()
    return path


def test_normalizes_clamps_and_hides_paths(tmp_path):
    result = list_classifications(cache_path=_cache(tmp_path))
    kick = result["items"][0]
    assert kick["confidence"] == 1.0
    assert kick["display_name"] == "kick.wav"
    assert "path" not in kick
    assert kick["tags"] == ["Punchy", "Short"]
    assert result["summary"] == {"total": 4, "returned": 4, "needs_review": 2, "stale": 0}


def test_ood_is_neutral_and_user_override_is_preserved(tmp_path):
    items = list_classifications(cache_path=_cache(tmp_path))["items"]
    odd = next(item for item in items if item["display_name"] == "odd.wav")
    vocal = next(item for item in items if item["display_name"] == "vocal.wav")
    assert odd["primary_label"] == "Needs review"
    assert odd["review_required"] is True
    assert odd["uncertainty_reason"] == "outside the known audio domain"
    assert odd["confidence"] == 0.0
    assert vocal["user_overridden"] is True
    assert vocal["classification_state"] == "ready"
    assert vocal["uncertainty_reason"] is None


def test_filters_and_detail_lookup(tmp_path):
    path = _cache(tmp_path)
    filtered = list_classifications(cache_path=path, query="kick", category="Drums")
    assert filtered["summary"]["total"] == 1
    sample_id = filtered["items"][0]["id"]
    detail = get_classification(sample_id, cache_path=path)
    assert detail and detail["item"]["display_name"] == "kick.wav"
    assert get_classification("bad-id", cache_path=path) is None


def test_missing_or_malformed_cache_is_unavailable(tmp_path):
    with pytest.raises(SloClassificationUnavailable):
        list_classifications(cache_path=tmp_path / "missing.sqlite3")
    malformed = tmp_path / "malformed.sqlite3"
    sqlite3.connect(malformed).close()
    with pytest.raises(SloClassificationUnavailable):
        list_classifications(cache_path=malformed)
