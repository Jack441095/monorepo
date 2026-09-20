"""reminders.json grew unboundedly forever -- acknowledging a reminder only
flipped a flag, never removed it (P4 fix, 2026-07-13, matching monitor.py's
alerts [-50:] cap and diagnostics.py's analytics [-1000]/[-100] caps)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import thursday.scheduling as scheduling  # noqa: E402


def _reminder(reminder_id: str, *, acknowledged: bool, days_old: int) -> dict:
    created_at = datetime.now() - timedelta(days=days_old)
    return {
        "id": reminder_id,
        "text": "test reminder",
        "created_at": created_at.isoformat(),
        "acknowledged": acknowledged,
    }


def test_unacknowledged_reminders_are_never_pruned_regardless_of_age():
    old_unacked = _reminder("r1", acknowledged=False, days_old=365)
    kept = scheduling._prune_old_acknowledged_reminders([old_unacked])
    assert kept == [old_unacked]


def test_recently_acknowledged_reminders_are_kept():
    recent = _reminder("r2", acknowledged=True, days_old=1)
    kept = scheduling._prune_old_acknowledged_reminders([recent])
    assert kept == [recent]


def test_old_acknowledged_reminders_are_pruned():
    old = _reminder("r3", acknowledged=True, days_old=scheduling.ACKNOWLEDGED_REMINDER_RETENTION_DAYS + 5)
    kept = scheduling._prune_old_acknowledged_reminders([old])
    assert kept == []


def test_reminder_with_unparseable_timestamp_is_kept_not_dropped():
    malformed = {"id": "r4", "text": "x", "created_at": "not-a-date", "acknowledged": True}
    kept = scheduling._prune_old_acknowledged_reminders([malformed])
    assert kept == [malformed]


def test_save_reminders_prunes_before_writing(tmp_path, monkeypatch):
    reminders_file = tmp_path / "reminders.json"
    monkeypatch.setattr(scheduling, "CALENDAR_DIR", tmp_path)
    monkeypatch.setattr(scheduling, "REMINDERS_FILE", reminders_file)

    old_acked = _reminder("r5", acknowledged=True, days_old=scheduling.ACKNOWLEDGED_REMINDER_RETENTION_DAYS + 1)
    recent_unacked = _reminder("r6", acknowledged=False, days_old=0)

    scheduling._save_reminders([old_acked, recent_unacked])

    saved = json.loads(reminders_file.read_text(encoding="utf-8"))
    assert [r["id"] for r in saved] == ["r6"]
