"""ensure_repo_paths_on_sys_path() -- a shared resolver for the ~200
near-duplicate sys.path.insert() call sites docs/codebase_scan_12_07.md
§4.2 found across ~150 files (P3, 2026-07-13). Available for incremental
adoption; not a full migration."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import repo_python  # noqa: E402


def test_ensure_repo_paths_adds_the_standard_pythonpath_dirs(monkeypatch):
    monkeypatch.setattr(sys, "path", [])

    repo_python.ensure_repo_paths_on_sys_path()

    assert str(repo_python.REPO_ROOT) in sys.path
    assert str((repo_python.REPO_ROOT / "scripts").resolve()) in sys.path
    assert str((repo_python.REPO_ROOT / "studio" / "kenn").resolve()) in sys.path
    assert str((repo_python.REPO_ROOT / "business" / "agents").resolve()) in sys.path


def test_ensure_repo_paths_is_idempotent(monkeypatch):
    monkeypatch.setattr(sys, "path", [])

    repo_python.ensure_repo_paths_on_sys_path()
    length_after_first = len(sys.path)
    repo_python.ensure_repo_paths_on_sys_path()

    assert len(sys.path) == length_after_first


def test_ensure_repo_paths_accepts_extra_dirs(monkeypatch):
    monkeypatch.setattr(sys, "path", [])

    repo_python.ensure_repo_paths_on_sys_path("studio/kenn/kenn")

    assert str((repo_python.REPO_ROOT / "studio" / "kenn" / "kenn").resolve()) in sys.path


def test_ensure_repo_paths_does_not_duplicate_existing_entries(monkeypatch):
    existing = str(repo_python.REPO_ROOT)
    monkeypatch.setattr(sys, "path", [existing])

    repo_python.ensure_repo_paths_on_sys_path()

    assert sys.path.count(existing) == 1


def test_python_executable_still_resolves_to_something_real(monkeypatch):
    # Regression guard: adding ensure_repo_paths_on_sys_path() must not
    # touch python_executable()'s existing, already-relied-upon behavior.
    result = repo_python.python_executable()
    assert result  # non-empty
    assert Path(result).name.startswith("python") or result == sys.executable
