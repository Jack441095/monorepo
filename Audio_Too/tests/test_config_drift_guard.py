"""Guards against configuration drift that has bitten this repo before.

Ruff auto-discovers the *nearest* pyproject per file, so a nested
`[tool.ruff]` config silently diverges the lint ruleset per-directory. One under
`studio/audiogen/audiogen/` once added the `UP` ruleset and produced 5,739 errors,
turning the CI lint gate red without any code change. This locks the lint config
to the repo root so that can't recur.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _pyprojects() -> list[Path]:
    return [
        p
        for p in ROOT.rglob("pyproject.toml")
        if not any(part.startswith(".venv") for part in p.parts)
        and "node_modules" not in p.parts
        # .claude/worktrees/ is gitignored -- local-only leftover checkouts
        # from background agents, not tracked repo content. Scanning them
        # surfaces stale copies of already-merged files as false "drift."
        and ".claude" not in p.parts
    ]


def test_ruff_config_lives_only_at_repo_root() -> None:
    root_pyproject = ROOT / "pyproject.toml"
    offenders = []
    for path in _pyprojects():
        if path == root_pyproject:
            continue
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
        if "ruff" in data.get("tool", {}):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, (
        "Nested pyproject.toml files define their own [tool.ruff] config: "
        f"{offenders}. Ruff config must live only in the repo-root pyproject.toml "
        "so every file is linted with the same ruleset."
    )


def test_root_ruff_config_is_present_and_intact() -> None:
    with open(ROOT / "pyproject.toml", "rb") as fh:
        data = tomllib.load(fh)
    ruff = data.get("tool", {}).get("ruff", {})
    assert ruff, "Root pyproject.toml must define [tool.ruff]."
    select = ruff.get("lint", {}).get("select", [])
    for rule in ("E", "F", "I"):
        assert rule in select, f"Root ruff config unexpectedly dropped the '{rule}' rule set."
