# tests/test_composition_audio_import_boundary.py
"""
Guardrail: the `composition` package must not import the `audio` package.

Symbol generation (`composition/`) and rendering (`audio/`) stay separate so the
graph stays testable and you can swap backends without import cycles.
"""

from __future__ import annotations

import ast
from pathlib import Path


def _ast_imports_audio(tree: ast.AST) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name or ""
                if name == "audio" or name.startswith("audio."):
                    out.append((node.lineno, f"import {name}"))
        elif isinstance(node, ast.ImportFrom):
            mod = node.module
            if mod is not None and (mod == "audio" or mod.startswith("audio.")):
                out.append((node.lineno, f"from {mod} import ..."))
    return out


def _composition_py_files(root: Path) -> list[Path]:
    comp = root / "composition"
    return sorted(p for p in comp.rglob("*.py") if p.is_file())


def test_composition_tree_does_not_import_audio() -> None:
    repo = Path(__file__).resolve().parent.parent
    violations: list[str] = []
    for path in _composition_py_files(repo):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            violations.append(f"{path}: could not read ({e})")
            continue
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as e:
            violations.append(f"{path}:{e.lineno or 0}: syntax error ({e})")
            continue
        for lineno, desc in _ast_imports_audio(tree):
            rel = path.relative_to(repo)
            violations.append(f"{rel}:{lineno}: forbidden import of `audio` package: {desc}")
    assert not violations, "composition/ must not import `audio`:\n" + "\n".join(violations)
