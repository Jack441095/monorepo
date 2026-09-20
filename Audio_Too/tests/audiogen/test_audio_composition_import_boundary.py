# tests/test_audio_composition_import_boundary.py
"""
Guardrail: the `audio` package should not grow arbitrary imports of `composition`.

Rendering (`audio/`) ideally consumes events/config surfaces without pulling symbol-generation
internals everywhere. Today one realtime adapter imports composition helpers; keep imports
contained there unless you intentionally extend the allowlist below.
"""

from __future__ import annotations

import ast
from pathlib import Path

# Repo-relative POSIX paths. Only these files may contain static `import composition` /
# `from composition...` (AST-detected). Add entries deliberately when introducing a new adapter.
_ALLOWED_AUDIO_FILES_IMPORTING_COMPOSITION = frozenset(
    {
        "audio/RT_player/section_scheduler.py",
    }
)


def _ast_imports_composition(tree: ast.AST) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name or ""
                if name == "composition" or name.startswith("composition."):
                    out.append((node.lineno, f"import {name}"))
        elif isinstance(node, ast.ImportFrom):
            mod = node.module
            if mod is not None and (mod == "composition" or mod.startswith("composition.")):
                out.append((node.lineno, f"from {mod} import ..."))
    return out


def _audio_py_files(root: Path) -> list[Path]:
    audio = root / "audio"
    return sorted(p for p in audio.rglob("*.py") if p.is_file())


def test_audio_tree_composition_imports_are_allowlisted() -> None:
    repo = Path(__file__).resolve().parent.parent
    violations: list[str] = []
    for path in _audio_py_files(repo):
        rel = path.relative_to(repo)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            violations.append(f"{rel}: could not read ({e})")
            continue
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as e:
            violations.append(f"{rel}:{e.lineno or 0}: syntax error ({e})")
            continue
        hits = _ast_imports_composition(tree)
        if not hits:
            continue
        if rel.as_posix() not in _ALLOWED_AUDIO_FILES_IMPORTING_COMPOSITION:
            for lineno, desc in hits:
                violations.append(f"{rel}:{lineno}: forbidden import of `composition`: {desc}")
    assert not violations, (
        "audio/ must not import `composition` except in allowlisted adapter files "
        f"{sorted(_ALLOWED_AUDIO_FILES_IMPORTING_COMPOSITION)!r}.\n" + "\n".join(violations)
    )
