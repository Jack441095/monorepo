"""Tests for reference_store.py — reference management.

Covers:
- ReferenceStoreContext dataclass      — 1 test
- save_reference()                     — 2 tests
- list_references()                    — 2 tests
- reference_by_id()                    — 2 tests
- handle_multipart_reference()         — 2 tests
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
import pytest

from audio_analysis.integration.reference_store import (
    ReferenceStoreContext,
    save_reference,
    list_references,
    reference_by_id,
    reference_envelope_for_genre,
    handle_multipart_reference,
)


# ==============================================================================
#  Helpers
# ==============================================================================

def _sample_context(**overrides) -> ReferenceStoreContext:
    ctx = ReferenceStoreContext(
        analyze_wav=lambda fb, fn: {"ok": True, "metrics": {"technical_score": 78, "filename": fn, "peak_dbfs": -3.0}},
        connect=lambda: _connect_func(),
        init_reviews_table=lambda: None,
        now=lambda: "2025-01-01T00:00:00",
        reference_root=Path(tempfile.mkdtemp()),
        validate_wav_upload=lambda fb, fn, **kw: {"ok": True, "safe_name": fn},
    )
    if overrides:
        for k, v in overrides.items():
            object.__setattr__(ctx, k, v)
    return ctx


_db_path = None

def _connect_func():
    global _db_path
    conn = sqlite3.connect(str(_db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mix_references (
            id TEXT PRIMARY KEY,
            name TEXT,
            style TEXT,
            original_name TEXT,
            stored_name TEXT,
            metrics_json TEXT,
            genre_key TEXT DEFAULT '',
            genre_confidence REAL DEFAULT 0,
            profile_json TEXT DEFAULT '[]',
            crest_factor_db REAL,
            integrated_lufs REAL,
            loudness_range_lu REAL,
            stereo_correlation REAL,
            stereo_width_ratio REAL,
            size_bytes INTEGER,
            created_at TEXT
        )
    """)
    conn.commit()
    return conn


@pytest.fixture(autouse=True)
def _setup_db():
    global _db_path
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        _db_path = Path(f.name)
    yield
    try:
        _db_path.unlink(missing_ok=True)
    except OSError:
        pass


# ==============================================================================
#  ReferenceStoreContext
# ==============================================================================

class TestReferenceStoreContext:

    def test_default_creation(self):
        ctx = _sample_context()
        assert callable(ctx.analyze_wav)
        assert callable(ctx.connect)
        assert callable(ctx.init_reviews_table)
        assert callable(ctx.now)
        assert isinstance(ctx.reference_root, Path)
        assert callable(ctx.validate_wav_upload)


# ==============================================================================
#  save_reference
# ==============================================================================

class TestSaveReference:

    def test_saves_reference(self):
        ctx = _sample_context()
        result = save_reference(file_bytes=b"WAV", filename="ref.wav", name="My Ref", context=ctx)
        assert result["ok"] is True
        assert result["reference"]["name"] == "My Ref"
        assert result["reference"]["original_name"] == "ref.wav"

    def test_validation_failure(self):
        ctx = _sample_context(validate_wav_upload=lambda fb, fn, **kw: {"ok": False, "error": "Bad file"})
        result = save_reference(file_bytes=b"bad", filename="bad.wav", context=ctx)
        assert result["ok"] is False

    def test_auto_categorises_and_stores_explicit_profile_metrics(self):
        from audio_analysis.analysis_core.genre_profiles import GENRE_SEED_PROFILES

        profile = GENRE_SEED_PROFILES["jazz"]["profile"]
        metrics = {
            "log_bands_40": profile,
            "crest_factor_db": 11.0,
            "integrated_lufs": -14.0,
            "loudness_range_lu": 8.0,
            "stereo_correlation": 0.8,
            "stereo_width_ratio": 0.6,
        }
        ctx = _sample_context(analyze_wav=lambda fb, fn: {"ok": True, "metrics": metrics})
        result = save_reference(file_bytes=b"WAV", filename="jazz.wav", context=ctx)

        assert result["reference"]["genre_key"] == "jazz"
        assert result["reference"]["style"] == "Jazz / Blues"
        stored = reference_by_id(
            result["reference"]["id"], init_reviews_table=lambda: None, connect=_connect_func
        )
        assert stored["profile"] == profile
        assert stored["crest_factor_db"] == 11.0

        envelope = reference_envelope_for_genre(
            "jazz", init_reviews_table=lambda: None, connect=_connect_func
        )
        assert envelope["sample_count"] == 1


# ==============================================================================
#  list_references
# ==============================================================================

class TestListReferences:

    def test_empty(self):
        refs = list_references(init_reviews_table=lambda: None, connect=_connect_func)
        assert refs == []

    def test_lists_references(self):
        ctx = _sample_context()
        save_reference(file_bytes=b"WAV", filename="ref1.wav", name="Ref 1", context=ctx)
        save_reference(file_bytes=b"WAV", filename="ref2.wav", name="Ref 2", context=ctx)
        refs = list_references(init_reviews_table=lambda: None, connect=_connect_func)
        assert len(refs) >= 2


# ==============================================================================
#  reference_by_id
# ==============================================================================

class TestReferenceById:

    def test_none_for_invalid(self):
        assert reference_by_id("", init_reviews_table=lambda: None, connect=_connect_func) is None

    def test_finds_saved(self):
        ctx = _sample_context()
        result = save_reference(file_bytes=b"WAV", filename="ref.wav", name="My Ref", context=ctx)
        ref_id = result["reference"]["id"]
        found = reference_by_id(ref_id, init_reviews_table=lambda: None, connect=_connect_func)
        assert found is not None
        assert found["name"] == "My Ref"


# ==============================================================================
#  handle_multipart_reference
# ==============================================================================

class TestHandleMultipartReference:

    def test_missing_file(self):
        result = handle_multipart_reference(
            "multipart/form-data; boundary=x",
            b"--x\r\n\r\n--x--\r\n",
            parse_multipart_form=lambda ct, b: {},
            save_reference=lambda **kw: {"ok": False, "error": "Missing file"},
        )
        assert result["ok"] is False

    def test_with_file(self):
        def parse(ct, b):
            return {"file": b"WAV", "file__filename": "test.wav", "name": "Test Ref"}

        def save(**kw):
            return {"ok": True, "reference": {"id": "abc123", "name": kw.get("name", "")}}

        result = handle_multipart_reference(
            "multipart/form-data; boundary=x",
            b"fake",
            parse_multipart_form=parse,
            save_reference=save,
        )
        assert result["ok"] is True
        assert result["reference"]["name"] == "Test Ref"
