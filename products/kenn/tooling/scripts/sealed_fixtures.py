"""Sealed retrieval fixtures: questions nobody tunes a change against.

A fixture carrying ``"sealed": true`` is a holdout. Its only worth is that no tuning
loop has yet seen the answer to "does this change help?", so the rule has to be
mechanical rather than a convention somebody remembers. A tuning entry point reads its
fixtures through :func:`tunable_cases`, which refuses a sealed file before reading a
case, so pointing one at a holdout raises instead of quietly printing a number that
must not be used.

The marker lives in the file's contents rather than in its name on purpose: renaming a
holdout must not unseal it, and a new holdout under an unremarkable name must arrive
already sealed. :func:`sealed_fixtures` in the eval policy is the one place a fixture
gets declared; nothing here guesses from a path.

Scoring a sealed fixture is the point of it, so
``tooling/scripts/evaluate_retrieval_modes.py`` deliberately does not come through
here. So does ``build_brain_style_corpus.py``: it reads every eval question in order to
drop near-copies out of training material, and a question we score on has no business
in a fine-tune set either way.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SEALED_MARKER = "sealed"
REPO_ROOT = Path(__file__).resolve().parents[2]
EVALS = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "evals"


class SealedFixtureError(RuntimeError):
    """Raised when a tuning path is pointed at a holdout."""


def is_sealed(path: Path) -> bool:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return isinstance(data, dict) and data.get(SEALED_MARKER) is True


def refuse_sealed_fixture(path: Path) -> None:
    """Raise if this fixture is a holdout. A missing file raises FileNotFoundError here."""
    if is_sealed(path):
        raise SealedFixtureError(
            f"{Path(path).name} is sealed: it is the holdout, so tuning a change against it destroys the one "
            f"measurement that says whether the change was worth making. Score it once at gate time with "
            f"evaluate_retrieval_modes.py, or add a fresh untuned question set instead."
        )


def tunable_cases(path: Path) -> list[dict[str, Any]]:
    """Read a fixture for a tuning loop, refusing one that is sealed.

    The refusal belongs to the read rather than to each caller's bookkeeping: a caller
    that forgets to check is exactly the accident this is meant to stop.
    """
    refuse_sealed_fixture(path)
    cases = json.loads(Path(path).read_text(encoding="utf-8")).get("cases", [])
    return [case for case in cases if isinstance(case, dict)]


def sealed_fixtures() -> list[Path]:
    return sorted(path for path in EVALS.glob("*.json") if is_sealed(path))
