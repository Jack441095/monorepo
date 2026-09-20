"""Shared constants and leaf utilities for the llm_improvement package.

No function here calls into any other llm_improvement submodule -- this is
the bottom of the dependency layering (constants/config -> _shared ->
training_records -> exports/draft_eval/queue -> repair -> __init__'s
snapshot()/run_command()), so it can be imported first with no risk of a
cycle.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = ROOT.parent
PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
ABLETON_ROOT = REPO_ROOT / "studio" / "kenn" / "kenn"
ARTIFACTS = ABLETON_ROOT / "artifacts"
MAIN_EVAL_PATH = ABLETON_ROOT / "evals" / "questions.json"
DRAFT_EVAL_PATH = ABLETON_ROOT / "evals" / "draft_feedback_cases.json"
TRAINING_REVIEW_PATH = ARTIFACTS / "training" / "kenn_review_labels.json"
REVIEWED_TRAINING_PATH = ARTIFACTS / "training" / "kenn_reviewed_answer_records.jsonl"
HARD_NEGATIVES_PATH = ARTIFACTS / "training" / "kenn_hard_negatives.jsonl"
ROUTE_MEMORY_PATH = ARTIFACTS / "training" / "kenn_route_memory.jsonl"
if str(ABLETON_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ABLETON_ROOT.parent))

EVAL_TERM_STOPWORDS = {
    "about",
    "after",
    "answer",
    "before",
    "could",
    "does",
    "from",
    "have",
    "into",
    "make",
    "should",
    "sound",
    "that",
    "this",
    "what",
    "when",
    "where",
    "with",
    "without",
}

FIXTURE_QUESTIONS = {
    "dedupe test question alpha",
    "test feedback question",
    "test weak question",
}


def normalize_question(question: str) -> str:
    return re.sub(r"\s+", " ", str(question or "").strip().lower())[:500]


def _pkg():
    """Lazy import of the llm_improvement package itself.

    Tests (and any future caller) monkeypatch mutable config like
    ``llm_improvement.ARTIFACTS`` on the *package* object -- that only
    takes effect for code that reads the value back off the package at
    call time, not code holding its own `from ._shared import ARTIFACTS`
    copy captured at module-import time (a real bug this decomposition
    introduced and then fixed, see the commit that added this function).
    Safe to import here despite being the dependency root: by the time any
    function actually runs, `llm_improvement` has already finished
    importing this very module, so there is no import-time cycle -- only
    call-time attribute lookups happen through this indirection.
    """
    import llm_improvement

    return llm_improvement


def covered_eval_questions(path: Path | None = None) -> set[str]:
    """Return normalized tracked eval questions so stale repair signals can be filtered."""
    eval_path = path or _pkg().MAIN_EVAL_PATH
    try:
        data = json.loads(eval_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    cases = data.get("cases")
    if not isinstance(cases, list):
        return set()
    covered: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            continue
        question = normalize_question(str(case.get("question", "")))
        if question:
            covered.add(question)
    return covered


def is_fixture_repair_signal(*, question: str, top_source: str = "") -> bool:
    """Suppress local test/demo residue without hiding real user repair candidates."""
    normalized = normalize_question(question)
    if normalized in FIXTURE_QUESTIONS:
        return True
    return str(top_source or "").strip().lower() == "test source"


def python_cmd() -> str:
    return str(PYTHON) if PYTHON.exists() else "python3"


def latest_json(directory: Path, pattern: str) -> dict | None:
    paths = sorted(directory.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        data["_path"] = str(path)
        return data
    return None


def _topic_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(decoded, list):
            return [str(item).strip() for item in decoded if str(item).strip()]
    return []


def _slug(value: str, fallback: str = "feedback-case") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
    return slug[:80] or fallback


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _clean_bool(value) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"true", "yes", "1", "correct"}:
        return True
    if text in {"false", "no", "0", "incorrect"}:
        return False
    return None


def _bump_counter(counter: dict[str, int], key: str) -> None:
    clean = str(key or "").strip() or "unknown"
    counter[clean] = counter.get(clean, 0) + 1


def _top_counts(counter: dict[str, int], limit: int = 8) -> list[dict]:
    return [
        {"label": label, "count": count}
        for label, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def _source_lines(sources: list) -> str:
    lines: list[str] = []
    for source in sources[:5]:
        if not isinstance(source, dict):
            continue
        label = source.get("label") or source.get("title") or source.get("source") or "source"
        score = source.get("score")
        kind = source.get("kind")
        meta = " · ".join(str(item) for item in (kind, f"score {score}" if score is not None else "") if item)
        lines.append(f"- {label}{f' ({meta})' if meta else ''}")
    return "\n".join(lines) or "- No source payload was captured."


def _source_texts(sources: list) -> list[str]:
    values: list[str] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        values.append(
            " ".join(
                str(source.get(key, ""))
                for key in ("label", "title", "source", "kind")
                if source.get(key)
            ).lower()
        )
    return values
