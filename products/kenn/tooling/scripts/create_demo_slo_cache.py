#!/usr/bin/env python3
"""Create a sanitized local SLO cache for full-stack UX development."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

ROWS = [
    ("/demo/kick_tight_01.wav", "Drums", "Kick", "Punchy|Short", 0.94, "ml_v3", 0, "DSP", 6, 5),
    ("/demo/vocal_hook_02.wav", "Vocals", "Vocal Phrase", "Loop", 0.63, "user", 1, "USER_OVERRIDE", 6, 4),
    ("/demo/texture_unknown_03.wav", "", "", "Texture", 0.22, "ml_ood", 0, "DSP", 6, 5),
    ("/demo/new_recording_04.wav", "", "", "", 0.0, "unclassified", 0, "UNKNOWN", 0, 0),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default=".runtime/demo_slo.sqlite3")
    target = Path(parser.parse_args().path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    db = sqlite3.connect(target)
    try:
        db.execute(
            """CREATE TABLE sample_cache (
            path TEXT PRIMARY KEY, category TEXT, subcategory TEXT,
            secondary_tags TEXT, tag_confidence REAL, tag_source TEXT,
            tag_user_overridden INTEGER, winning_evidence TEXT,
            classification_model_version INTEGER, taxonomy_version INTEGER)"""
        )
        db.executemany("INSERT INTO sample_cache VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", ROWS)
        db.commit()
    finally:
        db.close()
    print(target.resolve())


if __name__ == "__main__":
    main()
