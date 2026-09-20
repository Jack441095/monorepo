"""Phase-0 P0-E regression: real filesystem containment for
`thursday/registry/codebase.py`'s `safe_resolve_path()`.

docs/audits/2026-08-20-thursday-nitedsp-forensic-audit.md and the companion
platform master report found that `safe_resolve_path()` used a string-prefix
containment test (``str(resolved).startswith(str(WORKSPACE_ROOT))``) rather
than real path containment. A sibling directory whose name happens to share
``WORKSPACE_ROOT`` as a string prefix -- e.g. ``thursday_backup`` next to
``thursday``, or ``Audio_Too_backup`` next to ``Audio_Too`` -- would satisfy
that string check while being a completely different directory outside the
intended workspace. This mattered specifically for `codebase_edit`, already
flagged HIGH destructive potential (arbitrary file write) elsewhere in the
audit.

These tests prove the fix (`Path.is_relative_to()`) against every case the
audit called out: ``../`` traversal, absolute paths, symlink escape,
prefix-collision siblings, nested valid paths, and the workspace root itself.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from thursday.registry.codebase import safe_resolve_path


@pytest.fixture(autouse=True)
def workspace_root(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir).resolve() / "thursday"
        root.mkdir()
        (root / "src").mkdir()
        monkeypatch.setattr("thursday.registry.codebase.WORKSPACE_ROOT", root)
        yield root


def test_nested_valid_path_is_allowed(workspace_root):
    resolved = safe_resolve_path("src/main.py")
    assert resolved == workspace_root / "src" / "main.py"


def test_workspace_root_itself_is_allowed(workspace_root):
    resolved = safe_resolve_path(".")
    assert resolved == workspace_root


def test_dotdot_traversal_is_rejected(workspace_root):
    with pytest.raises(ValueError, match="escapes the workspace root"):
        safe_resolve_path("../../../etc/passwd")


def test_dotdot_traversal_to_a_specific_sibling_is_rejected(workspace_root):
    with pytest.raises(ValueError, match="escapes the workspace root"):
        safe_resolve_path("../thursday_backup/secrets.env")


def test_absolute_path_outside_workspace_is_rejected(workspace_root):
    with pytest.raises(ValueError, match="escapes the workspace root"):
        safe_resolve_path("/etc/passwd")


def test_prefix_collision_sibling_directory_is_rejected(workspace_root):
    """The exact bug: a sibling directory name that shares WORKSPACE_ROOT as
    a *string* prefix (but is not a path descendant of it) must not pass."""
    sibling = workspace_root.parent / (workspace_root.name + "_backup")
    sibling.mkdir()
    (sibling / "secret.txt").write_text("do not touch")

    # String-prefix would have wrongly allowed this: str(sibling / "secret.txt")
    # literally starts with str(workspace_root).
    assert str(sibling).startswith(str(workspace_root))

    with pytest.raises(ValueError, match="escapes the workspace root"):
        safe_resolve_path(f"../{sibling.name}/secret.txt")


def test_prefix_collision_via_relative_dotdot_construction_is_rejected(workspace_root):
    """Same collision, reached the way a real traversal payload would try
    it: workspace_root joined with a `..`-based relative path that resolves
    onto the colliding sibling."""
    sibling = workspace_root.parent / (workspace_root.name + "-evil")
    sibling.mkdir()
    with pytest.raises(ValueError, match="escapes the workspace root"):
        safe_resolve_path(f"../{sibling.name}")


@pytest.mark.skipif(os.name == "nt", reason="symlink semantics differ on Windows")
def test_symlink_escape_is_rejected(workspace_root, tmp_path):
    """A symlink physically located inside the workspace, but pointing
    outside it, must be judged by where it actually resolves on disk."""
    outside_dir = tmp_path / "outside_workspace"
    outside_dir.mkdir()
    (outside_dir / "secret.txt").write_text("outside data")

    link = workspace_root / "escape_link"
    link.symlink_to(outside_dir)

    with pytest.raises(ValueError, match="escapes the workspace root"):
        safe_resolve_path("escape_link/secret.txt")


@pytest.mark.skipif(os.name == "nt", reason="symlink semantics differ on Windows")
def test_symlink_pointing_inside_workspace_is_allowed(workspace_root):
    real_file = workspace_root / "src" / "real.py"
    real_file.write_text("x = 1")
    link = workspace_root / "alias.py"
    link.symlink_to(real_file)

    resolved = safe_resolve_path("alias.py")
    assert resolved == real_file


def test_unicode_path_component_within_workspace_is_allowed(workspace_root):
    unicode_dir = workspace_root / "música"
    unicode_dir.mkdir()
    resolved = safe_resolve_path("música/notas.txt")
    assert resolved == unicode_dir / "notas.txt"


def test_codebase_edit_honors_the_same_confinement(workspace_root):
    """Apply the confinement consistently to the actual mutating tool, not
    just the helper in isolation."""
    from thursday.registry.codebase import _handle_codebase_edit

    sibling = workspace_root.parent / (workspace_root.name + "_backup")
    sibling.mkdir()

    result = _handle_codebase_edit(
        {"path": f"../{sibling.name}/pwned.py", "content": "x = 1"}, None, ""
    )
    assert "escapes the workspace root" in result or "Access denied" in result
    assert not (sibling / "pwned.py").exists()
