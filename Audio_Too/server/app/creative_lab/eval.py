"""Creative Lab: eval functions.

Split out of creative_lab.py (was 1,261 lines) — see docs/BACKLOG.md.
"""

from __future__ import annotations

import json
from pathlib import Path


from .constants import (
    CREATIVE_DRAFT_EVAL_PATH,
)


def _draft_eval_suite() -> dict:
    if CREATIVE_DRAFT_EVAL_PATH.exists():
        try:
            data = json.loads(CREATIVE_DRAFT_EVAL_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    else:
        data = {}
    cases = data.get("cases")
    if not isinstance(cases, list):
        cases = []
    return {
        "version": int(data.get("version", 1) or 1),
        "description": data.get(
            "description",
            "Reviewable eval cases drafted from Creative Lab repair feedback. Promote selected cases into questions.json.",
        ),
        "cases": cases,
    }


def _save_draft_eval_suite(suite: dict) -> None:
    CREATIVE_DRAFT_EVAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    CREATIVE_DRAFT_EVAL_PATH.write_text(json.dumps(suite, indent=2) + "\n", encoding="utf-8")


def _load_eval_suite(path: Path, description: str) -> dict:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    else:
        data = {}
    cases = data.get("cases")
    if not isinstance(cases, list):
        cases = []
    return {
        "version": int(data.get("version", 1) or 1),
        "description": data.get("description", description),
        "cases": cases,
    }


def _save_eval_suite(path: Path, suite: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(suite, indent=2) + "\n", encoding="utf-8")


def _draft_eval_case(case_id: str) -> dict | None:
    clean_id = str(case_id or "").strip()
    suite = _draft_eval_suite()
    return next((case for case in suite["cases"] if case.get("id") == clean_id), None)
