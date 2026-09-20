"""CLI extras: corrupt undo logs, trash-log rotation."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sidecar import cli as CLI


def test_undo_corrupt_log_exits_2(tmp_path, capsys):
    bad = tmp_path / "undo.json"
    bad.write_text("{not json")
    with pytest.raises(SystemExit) as e:
        CLI.cmd_undo(str(bad))
    assert e.value.code == 2


def test_undo_nonlist_log_exits_2(tmp_path):
    bad = tmp_path / "undo.json"
    bad.write_text('{"a": 1}')
    with pytest.raises(SystemExit) as e:
        CLI.cmd_undo(str(bad))
    assert e.value.code == 2


def test_rotate_keeps_10(tmp_path, monkeypatch):
    import sidecar.cli as CLIM

    fake_home = tmp_path / "home"
    (fake_home / ".Trash" / "Disksweep").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(fake_home))
    base = fake_home / ".Trash" / "Disksweep"
    for i in range(13):
        (base / f"202609{i:02d}-000000").mkdir()
    # rotate_trash_logs expands ~ at call time
    CLIM.rotate_trash_logs(keep=10)
    assert len(list(base.iterdir())) == 10


def test_undo_roundtrip_ok(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    f = d / "x.txt"
    f.write_text("hi")
    log = tmp_path / "undo.json"
    log.write_text(json.dumps([{"src": str(f), "dst": str(tmp_path / "trashed.txt")}]))
    import shutil

    shutil.move(str(f), str(tmp_path / "trashed.txt"))
    CLI.cmd_undo(str(log))
    assert f.exists()
