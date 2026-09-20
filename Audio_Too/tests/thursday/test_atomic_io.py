"""atomic_write() was promoted from thursday/feedback.py to a shared
thursday/atomic_io.py and applied to 4 previously non-atomic JSON writers
(P4 fix, 2026-07-13) -- a crash mid-write must never leave a truncated
file that a loader's bare except silently treats as empty."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from thursday.atomic_io import atomic_write  # noqa: E402


def test_atomic_write_creates_parent_dirs_and_writes_content(tmp_path) -> None:
    target = tmp_path / "nested" / "dir" / "data.json"
    atomic_write(target, json.dumps({"ok": True}))
    assert target.exists()
    assert json.loads(target.read_text(encoding="utf-8")) == {"ok": True}


def test_atomic_write_leaves_no_temp_file_behind(tmp_path) -> None:
    target = tmp_path / "data.json"
    atomic_write(target, "{}")
    leftovers = list(tmp_path.glob(".tmp_*"))
    assert leftovers == []


def test_atomic_write_replaces_existing_file_atomically(tmp_path) -> None:
    target = tmp_path / "data.json"
    target.write_text("old content", encoding="utf-8")
    atomic_write(target, "new content")
    assert target.read_text(encoding="utf-8") == "new content"


def test_feedback_module_reexports_the_shared_atomic_write() -> None:
    import thursday.feedback as feedback

    assert feedback.atomic_write is atomic_write


def test_scheduling_monitor_diagnostics_watcher_use_the_shared_atomic_write() -> None:
    import thursday.scheduling as scheduling
    import thursday.monitor as monitor
    import thursday.diagnostics as diagnostics
    import thursday.watcher as watcher

    assert scheduling.atomic_write is atomic_write
    assert monitor.atomic_write is atomic_write
    assert diagnostics.atomic_write is atomic_write
    assert watcher.atomic_write is atomic_write


def test_save_reminders_uses_atomic_write(tmp_path, monkeypatch) -> None:
    import thursday.scheduling as scheduling

    reminders_file = tmp_path / "calendar" / "reminders.json"
    monkeypatch.setattr(scheduling, "CALENDAR_DIR", tmp_path / "calendar")
    monkeypatch.setattr(scheduling, "REMINDERS_FILE", reminders_file)

    scheduling._save_reminders([{"id": "r1", "text": "call client"}])

    assert json.loads(reminders_file.read_text(encoding="utf-8")) == [{"id": "r1", "text": "call client"}]


def test_save_alerts_uses_atomic_write(tmp_path, monkeypatch) -> None:
    import thursday.monitor as monitor

    alerts_file = tmp_path / "alerts.json"
    monkeypatch.setattr(monitor, "_alert_path", lambda: alerts_file)

    monitor._save_alerts([{"kind": "stale_lead"}])

    assert json.loads(alerts_file.read_text(encoding="utf-8")) == [{"kind": "stale_lead"}]


def test_save_analytics_uses_atomic_write(tmp_path, monkeypatch) -> None:
    import thursday.diagnostics as diagnostics

    monkeypatch.setattr(diagnostics, "ANALYTICS_DIR", tmp_path)

    diagnostics._save_analytics({"total_requests": 5})

    assert json.loads((tmp_path / "usage.json").read_text(encoding="utf-8")) == {"total_requests": 5}


def test_save_seen_uses_atomic_write(tmp_path, monkeypatch) -> None:
    import thursday.watcher as watcher

    seen_file = tmp_path / "nested" / ".watcher_seen.txt"
    monkeypatch.setattr(watcher, "SEEN_CACHE_FILE", seen_file)

    watcher._save_seen({"a.wav", "b.wav"})

    assert seen_file.read_text(encoding="utf-8") == "a.wav\nb.wav"


def test_save_seen_does_not_raise_when_write_fails(tmp_path, monkeypatch) -> None:
    import thursday.watcher as watcher

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(watcher, "atomic_write", boom)
    monkeypatch.setattr(watcher, "SEEN_CACHE_FILE", tmp_path / ".watcher_seen.txt")

    watcher._save_seen({"a.wav"})  # must not raise
