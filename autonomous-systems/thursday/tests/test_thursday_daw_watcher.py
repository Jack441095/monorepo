"""Tests for Thursday DAW Project File Watcher."""

import os

from thursday.daw_watcher import DAWProjectWatcher, DAWSessionInfo


def test_daw_project_watcher_scan(tmp_path):
    session_file = tmp_path / "MyProject.als"
    session_file.write_text("mock ableton project data")

    watcher = DAWProjectWatcher(watch_dir=tmp_path)
    sessions = watcher.scan_once()

    assert len(sessions) == 1
    info = sessions[0]
    assert isinstance(info, DAWSessionInfo)
    assert info.daw_type == "Ableton Live"
    assert info.session_name == "MyProject"
    assert info.metadata["extension"] == ".als"


def test_daw_project_watcher_empty_dir(tmp_path):
    watcher = DAWProjectWatcher(watch_dir=tmp_path / "nonexistent")
    sessions = watcher.scan_once()
    assert sessions == []


# ── Debounce (D2.4: rapid successive saves should collapse into one event) ──


def _touch_with_mtime(path, mtime: float) -> None:
    path.write_text("mock project data")
    os.utime(path, (mtime, mtime))


def test_rapid_resaves_within_debounce_window_emit_one_event(tmp_path):
    session_file = tmp_path / "MyProject.als"
    watcher = DAWProjectWatcher(watch_dir=tmp_path, debounce_seconds=30.0)

    _touch_with_mtime(session_file, 1000.0)
    first = watcher.scan_once(now=1000.0)
    assert len(first) == 1

    # Ableton autosaves again 5s later -- well inside the 30s debounce window.
    _touch_with_mtime(session_file, 1005.0)
    second = watcher.scan_once(now=1005.0)
    assert second == []

    # A third autosave 10s after the first event, still inside the window.
    _touch_with_mtime(session_file, 1010.0)
    third = watcher.scan_once(now=1010.0)
    assert third == []


def test_resave_after_debounce_window_emits_a_new_event(tmp_path):
    session_file = tmp_path / "MyProject.als"
    watcher = DAWProjectWatcher(watch_dir=tmp_path, debounce_seconds=30.0)

    _touch_with_mtime(session_file, 1000.0)
    first = watcher.scan_once(now=1000.0)
    assert len(first) == 1

    # Next save is 31s after the *event*, past the debounce window.
    _touch_with_mtime(session_file, 1031.0)
    second = watcher.scan_once(now=1031.0)
    assert len(second) == 1
    assert second[0].last_modified == 1031.0


def test_debounced_write_still_updates_tracked_mtime_no_lost_or_duplicate_events(tmp_path):
    # A save inside the debounce window must not be silently forgotten: the
    # next scan (even one still inside the window relative to the *event*)
    # should not re-fire for the same mtime it already saw.
    session_file = tmp_path / "MyProject.als"
    watcher = DAWProjectWatcher(watch_dir=tmp_path, debounce_seconds=30.0)

    _touch_with_mtime(session_file, 1000.0)
    watcher.scan_once(now=1000.0)

    _touch_with_mtime(session_file, 1005.0)
    watcher.scan_once(now=1005.0)  # collapsed, but mtime tracked as seen

    # No further writes -- re-scanning at the same mtime must emit nothing.
    again = watcher.scan_once(now=1010.0)
    assert again == []


def test_default_debounce_is_thirty_seconds(tmp_path):
    watcher = DAWProjectWatcher(watch_dir=tmp_path)
    assert watcher.debounce_seconds == 30.0


def test_zero_debounce_preserves_original_every_change_fires_behavior(tmp_path):
    session_file = tmp_path / "MyProject.als"
    watcher = DAWProjectWatcher(watch_dir=tmp_path, debounce_seconds=0.0)

    _touch_with_mtime(session_file, 1000.0)
    assert len(watcher.scan_once(now=1000.0)) == 1

    _touch_with_mtime(session_file, 1001.0)
    assert len(watcher.scan_once(now=1001.0)) == 1
