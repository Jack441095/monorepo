"""Question suggestions: typeahead, dynamic starters, LLM follow-up parsing."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOTES_DIR = ROOT / "Training_Data_Notes"

DEFAULT_STARTERS = [
    "How do I sidechain bass to the kick?",
    "How should I export stems for mixing?",
    "How do I saturate sub bass without distortion?",
    "What does freezing a track do?",
    "How do I fix muddy low mids?",
    "What LUFS target should I use for streaming?",
    "How do clip envelopes work in Session View?",
    "How do I make space for the kick in drum and bass?",
]

_POOL_CACHE: list[tuple[str, int]] | None = None


def _note_status(path: Path) -> str:
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[:20]:
        if line.lower().startswith("status:"):
            return line.split(":", 1)[1].strip() or "Draft"
    return "Unmarked"


def _section_bullets(text: str, heading: str) -> list[str]:
    lines = text.splitlines()
    found = False
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if found and out:
                break
            continue
        if stripped.lower().rstrip(":") == heading.lower().rstrip(":"):
            found = True
            continue
        if found and re.match(
            r"^(short answer|try this|why it matters|related questions|tags|type|key ideas):",
            stripped,
            re.I,
        ):
            break
        if found:
            item = re.sub(r"^[-* ]*\d*[.)]?\s*", "", stripped).strip()
            if item:
                out.append(item)
    return out


def _note_title(text: str, path: Path) -> str:
    for line in text.splitlines()[:8]:
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem.replace("-", " ").title()


def _build_pool() -> list[tuple[str, int]]:
    global _POOL_CACHE
    if _POOL_CACHE is not None:
        return _POOL_CACHE
    pool: list[tuple[str, int]] = []
    seen: set[str] = set()
    if NOTES_DIR.exists():
        for path in sorted(NOTES_DIR.glob("*.md")):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            approved = _note_status(path).lower() == "approved"
            priority = 30 if approved else 10
            for item in _section_bullets(text, "Related questions"):
                key = item.lower()
                if key not in seen:
                    seen.add(key)
                    pool.append((item, priority + 5))
            if approved:
                title = _note_title(text, path)
                prompt = f"How do I apply {title.lower()} in Ableton?"
                key = prompt.lower()
                if key not in seen:
                    seen.add(key)
                    pool.append((prompt, priority))
    for item in DEFAULT_STARTERS:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            pool.append((item, 20))
    _POOL_CACHE = pool
    return pool


def reset_pool_cache() -> None:
    global _POOL_CACHE
    _POOL_CACHE = None


def _dedupe_ordered(items: list[str], *, limit: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def parse_followups_from_answer(text: str) -> list[str]:
    """Extract bullets under 'You could also ask:' from an LLM answer."""
    lines = str(text or "").splitlines()
    found = False
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if found and out:
                break
            continue
        if stripped.lower().rstrip(":") == "you could also ask":
            found = True
            continue
        if found and re.match(r"^(short answer|try this|why it matters|sources):", stripped, re.I):
            break
        if found:
            item = re.sub(r"^[-* ]*\d*[.)]?\s*", "", stripped).strip()
            if item.endswith("?"):
                out.append(item)
            elif item:
                out.append(item if item.endswith("?") else f"{item}?")
    return out[:5]


def score_match(query: str, candidate: str, priority: int) -> int:
    q = query.lower().strip()
    c = candidate.lower()
    if not q:
        return priority
    if c == q:
        return 1000 + priority
    if c.startswith(q):
        return 500 + priority + max(0, 40 - len(q))
    if q in c:
        return 200 + priority
    words = [w for w in q.split() if len(w) > 2]
    if words and all(w in c for w in words):
        return 120 + priority
    return 0


def typeahead(query: str, *, limit: int = 8) -> list[str]:
    q = str(query or "").strip()
    if len(q) < 2:
        return starter_questions(limit=limit)
    pool = _build_pool()
    scored: list[tuple[int, str]] = []
    for text, priority in pool:
        score = score_match(q, text, priority)
        if score > 0:
            scored.append((score, text))
    scored.sort(key=lambda item: (-item[0], item[1].lower()))
    return [text for _, text in scored[: max(1, min(12, limit))]]


def starter_questions(*, limit: int = 10, extra: list[str] | None = None) -> list[str]:
    """Homepage chips: defaults, approved-note related lines, plus optional extras (e.g. recent queries)."""
    pool = _build_pool()
    ranked = sorted(pool, key=lambda item: (-item[1], item[0].lower()))
    items = [text for text, _ in ranked]
    if extra:
        items = [*extra, *items]
    items.extend(DEFAULT_STARTERS)
    return _dedupe_ordered(items, limit=limit)


def catalog_payload(*, extra: list[str] | None = None, limit: int = 10) -> dict:
    """Shared by KENN's own /api/catalog (wants a short, tidy sidebar list --
    called with limit=2) and business/app/studio_tips.py's public FAQ-style
    catalog (wants the fuller default -- calls with no override, so this
    default must stay >= 4, the real assertion `test_public_catalog` makes).
    Don't change the default here again without checking both callers."""
    return {
        "ok": True,
        "starters": starter_questions(limit=limit, extra=extra),
    }


def merge_followups(primary: list[str], secondary: list[str], *, limit: int = 2) -> list[str]:
    return _dedupe_ordered([*primary, *secondary], limit=limit)
