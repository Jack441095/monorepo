"""Shared configuration constants for the mix review system.

Extracted from :mod:`audio_analysis_tool.mix_review` so the module's
imports can be order-independent (no ``# noqa: E402`` debt).
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).parents[4]
ABLETON_ROOT = REPO_ROOT / "studio" / "kenn" / "kenn"
AGENTS_ROOT = REPO_ROOT / "studio" / "agents"
BUSINESS_ROOT = AGENTS_ROOT.parent
AUDIOGEN_ROOT = REPO_ROOT / "studio" / "audiogen" / "audiogen"
PORTFOLIO_ROOT = REPO_ROOT / "server" / "portfolio"
MIX_REVIEW_DATA_ROOT = Path(
    os.environ.get(
        "AUDIO_TOO_MIX_REVIEW_DATA_ROOT",
        str(AGENTS_ROOT / "MixReview" / "data" / "mix_reviews"),
    )
)
UPLOAD_ROOT = MIX_REVIEW_DATA_ROOT / "uploads"
REPORT_ROOT = MIX_REVIEW_DATA_ROOT / "reports"
REFERENCE_ROOT = MIX_REVIEW_DATA_ROOT / "references"
ANALYSIS_FEEDBACK_PATH = REPO_ROOT / "artifacts" / "analysis_feedback.jsonl"
TARGET_CONFIG_PATH = Path(
    os.environ.get(
        "AUDIO_TOO_MIX_TARGETS",
        str(Path(__file__).resolve().parent / "mix_review_targets.json"),
    )
)
MAX_UPLOAD_BYTES = 150 * 1024 * 1024
WAV_SUFFIXES = {".wav", ".wave"}
DECODABLE_SUFFIXES = WAV_SUFFIXES | {".aif", ".aiff", ".flac", ".m4a", ".mp3"}
MIN_LUFS_SAMPLE_RATE = 4000

# Frequency bands used throughout analysis
BANDS = [
    ("sub", 20, 60),
    ("bass", 60, 150),
    ("low_mids", 150, 400),
    ("mids", 400, 2000),
    ("presence", 2000, 6000),
    ("sibilance", 6000, 8000),
    ("air", 8000, 16000),
]
PRESENCE_BANDS = {"presence", "sibilance", "air"}

DEFAULT_MIX_GOAL = "premaster"

# SQL statements for review and reference tables
CREATE_REVIEWS_SQL = """
    CREATE TABLE IF NOT EXISTS mix_reviews (
        id TEXT PRIMARY KEY,
        title TEXT,
        original_name TEXT,
        stored_name TEXT,
        report_name TEXT,
        size_bytes INTEGER,
        created_at TEXT,
        status TEXT DEFAULT 'completed',
        error TEXT
    )
"""

CREATE_REFERENCES_SQL = """
    CREATE TABLE IF NOT EXISTS mix_references (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
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
"""
