"""Every Remote Script KENN ships must at least compile: Live logs a
RemoteScriptError at every start for one that does not (KENN_Bridge line 888/1045,
found 2026-09-24)."""

from __future__ import annotations

import py_compile
from pathlib import Path

import pytest

KENN_ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = sorted(
    p for folder in ("integrations/ableton-remote-script", "integrations/ableton-osc")
    for p in (KENN_ROOT / folder).rglob("*.py") if "__pycache__" not in p.parts
)


def test_remote_script_sources_are_found() -> None:
    assert len(SCRIPTS) > 5


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: str(p.relative_to(KENN_ROOT)))
def test_remote_script_compiles(path: Path, tmp_path: Path) -> None:
    py_compile.compile(str(path), cfile=str(tmp_path / "out.pyc"), doraise=True)
