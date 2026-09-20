"""Registry of "structured commands" — fixed-prefix commands whose tail is
free-form user text that must NOT be subject to thursday.registry's fuzzy
trigger-substring scoring.

Why this exists: thursday.registry.score_by_triggers scans the *entire*
input for trigger substrings, with no concept of "this part is a free-text
argument, not a routing signal." A command like "create task marketing:
draft this week's post" embeds free text (the task's own objective) that
can legitimately contain words belonging to a totally unrelated service
("marketing", "draft post" are both real triggers of the marketing_agent
service) -- found live 2026-09-02 when that exact command silently routed
to the Marketing Agent instead of creating a task.

thursday.macros already solves this correctly for macro invocations by
being checked before the fuzzy scoring loop in orchestrator.handle(); this
module generalizes that same pre-check pattern so each new structured
command (task creation, marketing plans, ad campaign plans, ...) doesn't
need its own hand-rolled interception block in orchestrator.py.

A command's ``parse`` returns None for "this text isn't this command at
all" (the dispatcher tries the next one / falls through to normal
routing), or raises on "this text matched the command's shape but is
invalid" (still handled here, so the founder gets a real error message
instead of a routing miss). ``handle`` is expected to re-parse internally
and turn a raised error into a plain-language response -- see
thursday.registry.handlers._handle_create_task for the pattern.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class StructuredCommand:
    name: str
    parse: Callable[[str], Any]
    handle: Callable[[str], str]


def _task_creation_command() -> StructuredCommand:
    from thursday.ops import task_ledger
    from thursday.registry.handlers import _handle_create_task

    def parse(text: str):
        try:
            return task_ledger.parse_create_task_command(text)
        except (task_ledger.UnrecognizedWorkstream, ValueError):
            return "matched_but_invalid"

    return StructuredCommand("create_task", parse, _handle_create_task)


def _marketing_plan_command() -> StructuredCommand:
    from thursday.ops import marketing_ops
    from thursday.registry.handlers import _handle_create_marketing_plan

    def parse(text: str):
        try:
            return marketing_ops.parse_create_marketing_plan_command(text)
        except ValueError:
            return "matched_but_invalid"

    return StructuredCommand("create_marketing_plan", parse, _handle_create_marketing_plan)


def _ad_campaign_plan_command() -> StructuredCommand:
    from thursday.ops import advertising_ops
    from thursday.registry.handlers import _handle_create_campaign_plan

    def parse(text: str):
        try:
            return advertising_ops.parse_create_campaign_plan_command(text)
        except ValueError:
            return "matched_but_invalid"

    return StructuredCommand("create_campaign_plan", parse, _handle_create_campaign_plan)


def _brief_agent_command() -> StructuredCommand:
    from thursday.ops import agent_briefing
    from thursday.registry.handlers import _handle_brief_agent

    # parse_brief_agent_command never raises (an empty topic is a valid
    # "general briefing" request), so there's no "matched_but_invalid"
    # sentinel needed here -- it's just None or a real (possibly empty)
    # topic string, and an empty string is falsy in Python, so the
    # dispatcher's `if parsed is not None` check (not a truthiness check)
    # is what makes an empty-topic match still count as a real match.
    return StructuredCommand(
        "brief_agent", agent_briefing.parse_brief_agent_command, _handle_brief_agent,
    )


def _faq_command() -> StructuredCommand:
    from thursday.ops import support_ops
    from thursday.registry.handlers import _handle_faq

    return StructuredCommand("faq", support_ops.parse_faq_command, _handle_faq)


def _draft_beta_invite_command() -> StructuredCommand:
    from thursday.ops import beta_invite_ops
    from thursday.registry.handlers import _handle_draft_beta_invite

    def parse(text: str):
        try:
            return beta_invite_ops.parse_draft_beta_invite_command(text)
        except ValueError:
            return "matched_but_invalid"

    return StructuredCommand("draft_beta_invite", parse, _handle_draft_beta_invite)


def _find_customers_command() -> StructuredCommand:
    from thursday.ops import research_ops
    from thursday.registry.handlers import _handle_find_customers

    # parse_find_customers_command never raises (an empty query tail
    # falls back to the documented target audience, see
    # find_potential_customers()), so -- like brief_agent -- there's no
    # "matched_but_invalid" sentinel needed; an empty string is still a
    # real match, not a routing miss.
    return StructuredCommand(
        "find_customers", research_ops.parse_find_customers_command, _handle_find_customers,
    )


def _web_search_command() -> StructuredCommand:
    from thursday.ops import research_ops
    from thursday.registry.handlers import _handle_web_search

    return StructuredCommand(
        "web_search", research_ops.parse_web_search_command, _handle_web_search,
    )


def _reindex_docs_command() -> StructuredCommand:
    from thursday.ops import doc_search_ops
    from thursday.registry.handlers import _handle_reindex_docs

    return StructuredCommand(
        "reindex_docs", doc_search_ops.parse_reindex_docs_command, _handle_reindex_docs,
    )


def _search_docs_command() -> StructuredCommand:
    from thursday.ops import doc_search_ops
    from thursday.registry.handlers import _handle_search_docs

    return StructuredCommand(
        "search_docs", doc_search_ops.parse_search_docs_command, _handle_search_docs,
    )


def _notify_me_command() -> StructuredCommand:
    from thursday.ops import notify_ops
    from thursday.registry.handlers import _handle_notify_me

    return StructuredCommand(
        "notify_me", notify_ops.parse_notify_me_command, _handle_notify_me,
    )


def _registry() -> list[StructuredCommand]:
    # Built lazily (not at module import time) so importing this module
    # never eagerly imports task_ledger/marketing_ops/advertising_ops and
    # their transitive dependencies -- matches the lazy-import discipline
    # the rest of thursday/registry/ uses.
    return [
        _task_creation_command(),
        _marketing_plan_command(),
        _ad_campaign_plan_command(),
        _brief_agent_command(),
        _faq_command(),
        _draft_beta_invite_command(),
        _find_customers_command(),
        _web_search_command(),
        _reindex_docs_command(),
        _search_docs_command(),
        _notify_me_command(),
    ]


def try_dispatch(text: str) -> tuple[str, str] | None:
    """Return (command_name, response_text) for the first structured
    command whose parse() recognizes ``text`` (matched-valid or
    matched-but-invalid), or None if none of them claim it.
    """
    for cmd in _registry():
        parsed = cmd.parse(text)
        if parsed is not None:
            return cmd.name, cmd.handle(text)
    return None
