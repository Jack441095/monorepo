"""Rolling back only works if the previous build is still there and you know which one you are on.

E3 asks for three things: the last two DMGs kept, a note on how to go back, and the version shown in the app. Two of
those are code paths that can silently do nothing -- retention that keeps nothing, and a version line that reads
"unknown" forever because nobody tested the manifest path -- so both are pinned here.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from scripts import build_kenn_app, kenn_tray


def _dmg(output: Path, commit: str, age_seconds: float) -> Path:
    path = output / f"KENN-beta-{commit}.dmg"
    path.write_bytes(b"x")
    when = time.time() - age_seconds
    os.utime(path, (when, when))
    return path


def test_two_dmgs_survive_a_build_so_the_previous_one_is_still_installable(tmp_path) -> None:
    _dmg(tmp_path, "aaaaaaa", 300)
    _dmg(tmp_path, "bbbbbbb", 200)
    _dmg(tmp_path, "ccccccc", 100)      # the newest, i.e. what we just built
    removed = build_kenn_app.retain_recent_dmgs(tmp_path, keep=2)
    assert sorted(p.name for p in tmp_path.glob("*.dmg")) == ["KENN-beta-bbbbbbb.dmg", "KENN-beta-ccccccc.dmg"]
    assert removed == ["KENN-beta-aaaaaaa.dmg"]


def test_retention_is_by_time_not_by_the_commit_in_the_name(tmp_path) -> None:
    """A rebuilt commit produces the same filename; the pair actually installed still has to survive."""
    old = _dmg(tmp_path, "aaaaaaa", 500)
    new = _dmg(tmp_path, "aaaaaaa", 10)
    assert old == new
    build_kenn_app.retain_recent_dmgs(tmp_path, keep=2)
    assert new.exists(), "the same filename twice must not be pruned twice into nothing"


def test_retention_leaves_nothing_to_remove_when_there_are_fewer_dmgs_than_the_budget(tmp_path) -> None:
    _dmg(tmp_path, "aaaaaaa", 10)
    assert build_kenn_app.retain_recent_dmgs(tmp_path, keep=2) == []
    assert len(list(tmp_path.glob("*.dmg"))) == 1


def test_the_version_line_names_the_commit_the_build_recorded(tmp_path) -> None:
    resources = tmp_path / "Contents" / "Resources"
    resources.mkdir(parents=True)
    (resources / "build_manifest.json").write_text(json.dumps({
        "source_git_commit": "65496cae9bb3f0c1a2b3c4d5e6f7a8b9c0d1e2f3",
        "built_at": "2026-09-30T22:14:03+00:00",
        "index_version": "v-db8c6334cf63",
    }), encoding="utf-8")
    info = kenn_tray.build_info(app_bundle=tmp_path)
    assert info["source_git_commit"].startswith("65496ca")
    # Call the real function rather than rebuilding the string here: an earlier version of this test formatted the
    # line itself and so passed while the function truncated the index version to a value that does not exist.
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(kenn_tray, "build_info", lambda *a, **k: info)
    try:
        assert kenn_tray.installed_build_info() == "Build: 65496ca  (2026-09-30, index v-db8c6334cf63)"
    finally:
        monkeypatch.undo()


def test_a_missing_or_unreadable_manifest_says_so_instead_of_claiming_a_version(tmp_path) -> None:
    assert kenn_tray.build_info(app_bundle=tmp_path) == {}
    resources = tmp_path / "Contents" / "Resources"
    resources.mkdir(parents=True)
    (resources / "build_manifest.json").write_text("{not json", encoding="utf-8")
    assert kenn_tray.build_info(app_bundle=tmp_path) == {}


def test_the_rollback_runbook_names_all_three_things(tmp_path) -> None:
    runbook = build_kenn_app.KENN_ROOT / "docs" / "runbooks" / "KENN_ROLLBACK_AND_UPDATE.md"
    text = runbook.read_text(encoding="utf-8")
    assert "Build:" in text, "the runbook must show how to read the version, not just that one exists"
    assert "two most recent" in text
    assert "What a rollback does **not** undo" in text