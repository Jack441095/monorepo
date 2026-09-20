from __future__ import annotations

import json
import sqlite3

from kenn.adaptive import calibrator


def _make_db(path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE session_feedback (
            turn_id TEXT, explicit_rating INTEGER, dwell_seconds REAL,
            has_followup BOOLEAN, followup_interval_seconds REAL,
            route TEXT, topics TEXT
        )"""
    )
    conn.executemany(
        "INSERT INTO session_feedback VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("good-1", 5, None, None, None, "advice", json.dumps(["vocals"])),
            ("good-2", 4, None, None, None, "advice", json.dumps(["vocals"])),
            ("bad-1", 2, None, None, None, "search", json.dumps(["foley"])),
            ("bad-2", 1, None, None, None, "search", json.dumps(["foley"])),
            ("neutral", 3, None, None, None, "neutral", json.dumps(["neutral"])),
        ],
    )
    conn.commit()
    conn.close()


def test_calibrator_maps_live_five_point_ratings(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "kenn.db"
    output_path = tmp_path / "multipliers.json"
    _make_db(db_path)
    monkeypatch.setattr(calibrator, "DB_PATH", db_path)
    monkeypatch.setattr(calibrator, "OUTPUT_PATH", output_path)

    multipliers = calibrator.train_calibrator()

    assert multipliers["topics"]["vocals"] > 1.0
    assert multipliers["topics"]["foley"] < 1.0
    assert "neutral" not in multipliers["topics"]
    assert json.loads(output_path.read_text()) == multipliers


def test_calibrator_rejects_legacy_and_out_of_range_ratings() -> None:
    assert calibrator._explicit_rating_label(5) == 1
    assert calibrator._explicit_rating_label(1) == 0
    assert calibrator._explicit_rating_label(3) is None
    assert calibrator._explicit_rating_label(-1) is None
    assert calibrator._explicit_rating_label("not-a-rating") is None
