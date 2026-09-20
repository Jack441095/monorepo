"""Resolve the Python executable and import path for Audio_Too launchers."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Kept in sync with pyproject.toml's [tool.pytest.ini_options] pythonpath --
# pytest gets this for free from that config; anything launched OUTSIDE
# pytest (main.py subcommands, thursday/server.py, scripts/*.py run
# directly, etc.) has always had to hand-roll its own subset of these as
# individual sys.path.insert() calls. docs/codebase_scan_12_07.md §4.2
# found ~200 near-duplicate instances of this across ~150 files, with
# genuine drift between them (different combinations of paths, different
# insertion order) -- exactly the kind of inconsistency that caused a real
# collection-order bug during the 2026-07-12 package reorg (see that
# commit's notes). New code should prefer ensure_repo_paths_on_sys_path()
# over hand-rolling its own list; existing call sites can be migrated
# opportunistically when touched for other reasons, rather than in one
# large, hard-to-fully-verify sweep.
REPO_PYTHONPATH_DIRS: tuple[str, ...] = (
    ".",
    "scripts",
    "business",
    "server/app",
    "studio",
    "studio/kenn",
    "studio/audio_analysis",
    "studio/audio_analysis/audio_analysis",
    "studio/audiogen/audiogen",
    "server/agents",
)


def ensure_repo_paths_on_sys_path(*extra: str) -> None:
    """Insert the standard repo import roots onto sys.path, in a fixed order.

    Idempotent (skips a directory already present) and safe to call
    multiple times/from multiple modules. ``extra`` accepts additional
    repo-relative paths a specific caller needs beyond the standard set
    (e.g. a package's own nested subdirectory), inserted after the
    standard set so a caller's specific needs still take priority via
    ``sys.path.insert(0, ...)`` ordering (later inserts end up earlier in
    the list).
    """
    for rel in (*REPO_PYTHONPATH_DIRS, *extra):
        path = str((REPO_ROOT / rel).resolve()) if rel != "." else str(REPO_ROOT)
        if path not in sys.path:
            sys.path.insert(0, path)


def python_executable() -> str:
    candidates = [
        REPO_ROOT / ".venv" / "bin" / "python",
        REPO_ROOT / "business" / "agents" / ".venv" / "bin" / "python",
        REPO_ROOT / "studio" / "kenn" / ".venv" / "bin" / "python",
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return sys.executable
