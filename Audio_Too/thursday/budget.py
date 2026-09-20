"""Token-budgeted context assembly for Thursday's LLM prompts.

No existing context-building code enforces a token budget:
`memory_manager.query_context()` concatenates entity-graph and episodic
memory with no length cap, and past-plan lessons are appended unconditionally
in `brain.py`'s prompt. This wraps those pieces with a simple, dependency-
free token estimate (~4 characters per token — a standard rough heuristic;
this is a budget guard, not exact billing) and drops whole lowest-priority
sections first when the assembled context would exceed budget, rather than
truncating mid-sentence.

Priority order (highest priority first, dropped last): the current turn/task
text is never part of this module at all — it's assembled separately and
always sent in full — followed by recent conversation turns, then semantic/
episodic memory, then past-plan lessons (lowest priority, dropped first).
"""

from __future__ import annotations

from dataclasses import dataclass, field

_CHARS_PER_TOKEN_ESTIMATE = 4


def estimate_tokens(text: str) -> int:
    """Rough token estimate for budgeting — not exact, good enough to decide
    what to drop when a section is oversized."""
    return max(1, len(text) // _CHARS_PER_TOKEN_ESTIMATE) if text else 0


@dataclass
class ContextSection:
    """One named, priority-ordered piece of prompt context."""

    name: str
    text: str
    priority: int  # lower number = higher priority = dropped last


@dataclass
class BudgetedContext:
    """Assembles context sections within a token budget.

    Sections are considered highest-priority (lowest `priority` number)
    first; once the running total would exceed `max_tokens`, every
    remaining section is dropped whole rather than truncated mid-sentence.
    The single highest-priority section is always kept even if it alone
    exceeds the budget — a section can't be silently emptied by its own
    size.
    """

    max_tokens: int
    sections: list[ContextSection] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    used_tokens: int = 0

    def add(self, name: str, text: str, priority: int) -> None:
        if text and text.strip():
            self.sections.append(ContextSection(name=name, text=text, priority=priority))

    def build(self) -> str:
        self.dropped = []
        ordered = sorted(self.sections, key=lambda s: s.priority)
        kept: list[ContextSection] = []
        used = 0
        for section in ordered:
            cost = estimate_tokens(section.text)
            if used + cost > self.max_tokens and kept:
                self.dropped.append(section.name)
                continue
            kept.append(section)
            used += cost
        self.used_tokens = used
        return "\n\n".join(s.text for s in kept)

    @property
    def kept_names(self) -> list[str]:
        return [s.name for s in sorted(self.sections, key=lambda s: s.priority) if s.name not in self.dropped]
