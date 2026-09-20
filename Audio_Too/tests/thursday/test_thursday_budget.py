"""Tests for thursday.budget (priority-ordered, token-budgeted context
assembly) and its wiring into memory_manager.query_context /
brain.decide()'s prompt assembly."""

from __future__ import annotations

from thursday.budget import BudgetedContext, estimate_tokens


def test_estimate_tokens_roughly_scales_with_length():
    assert estimate_tokens("") == 0
    assert estimate_tokens("a") == 1
    assert estimate_tokens("a" * 400) == 100


def test_all_sections_kept_when_under_budget():
    ctx = BudgetedContext(max_tokens=1000)
    ctx.add("a", "short text", priority=0)
    ctx.add("b", "also short", priority=1)
    result = ctx.build()
    assert "short text" in result and "also short" in result
    assert ctx.dropped == []


def test_lowest_priority_section_dropped_first_when_over_budget():
    ctx = BudgetedContext(max_tokens=10)  # ~40 chars
    ctx.add("high_priority", "x" * 30, priority=0)
    ctx.add("low_priority", "y" * 30, priority=1)
    result = ctx.build()
    assert "x" * 30 in result
    assert "y" * 30 not in result
    assert ctx.dropped == ["low_priority"]


def test_highest_priority_section_kept_even_if_it_alone_exceeds_budget():
    ctx = BudgetedContext(max_tokens=1)  # ~4 chars, far smaller than the section
    ctx.add("only_section", "this is much longer than the budget allows", priority=0)
    result = ctx.build()
    assert "this is much longer" in result
    assert ctx.dropped == []


def test_priority_order_is_independent_of_add_order():
    ctx = BudgetedContext(max_tokens=1000)
    ctx.add("second", "SECOND", priority=1)
    ctx.add("first", "FIRST", priority=0)
    result = ctx.build()
    assert result.index("FIRST") < result.index("SECOND")


def test_empty_or_whitespace_sections_are_never_added():
    ctx = BudgetedContext(max_tokens=1000)
    ctx.add("empty", "", priority=0)
    ctx.add("whitespace", "   \n  ", priority=1)
    assert ctx.sections == []
    assert ctx.build() == ""


def test_used_tokens_reflects_only_kept_sections():
    ctx = BudgetedContext(max_tokens=10)
    ctx.add("kept", "x" * 30, priority=0)  # ~7 tokens, fits
    ctx.add("dropped", "y" * 40, priority=1)  # ~10 tokens, pushes over budget
    ctx.build()
    assert ctx.used_tokens == estimate_tokens("x" * 30)
    assert ctx.dropped == ["dropped"]


# ── memory_manager.query_context(max_tokens=...) ────────────────────────


def test_query_context_max_tokens_none_preserves_unbounded_behavior(tmp_path):
    from thursday.memory.memory_manager import MemoryManager

    mm = MemoryManager(storage_dir=tmp_path)
    for i in range(10):
        mm.episodic_memory.record_episode(
            session_id="s", user_text=f"tell me about widget {i}",
            assistant_response="ok " * 50, intent="test", service_used="",
            entities_extracted={},
        )
    unbounded = mm.query_context("widget", limit=10)
    assert len(unbounded) > 0

    budgeted = mm.query_context("widget", limit=10, max_tokens=5)
    assert len(budgeted) <= len(unbounded)


def test_query_context_returns_empty_string_when_nothing_matches(tmp_path):
    from thursday.memory.memory_manager import MemoryManager

    mm = MemoryManager(storage_dir=tmp_path)
    assert mm.query_context("nothing here", max_tokens=100) == ""


# ── brain.decide(): a huge memory match still produces a bounded prompt ──


def test_decide_caps_prompt_size_despite_a_huge_memory_match(monkeypatch, tmp_path):
    from nite_core.model_runtime import LLMResult
    from thursday.brain import decide
    from thursday.memory.memory_manager import MemoryManager

    mm = MemoryManager(storage_dir=tmp_path)
    # One entity ("widget", matched verbatim by the query text) with hundreds
    # of relationships -- entity-graph facts aren't truncated per-relation
    # the way episodic memory is, so this produces a genuinely huge single
    # mem_ctx block, unbounded from query_context()'s own perspective.
    for i in range(300):
        mm.entity_graph.add_relationship(
            source_name="widget", source_type="product",
            target_name=f"detail attribute number {i} with a fairly long descriptive value",
            target_type="attribute", relation_type="has_attribute",
        )
    monkeypatch.setattr("thursday.memory.get_memory_manager", lambda: mm)
    monkeypatch.setenv("THURSDAY_BRAIN_CONTEXT_TOKEN_BUDGET", "50")  # ~200 chars

    json_response = '{"type": "chat", "abstract": "ok", "steps": [], "confidence": "high"}'
    captured = {}

    class CapturingProvider:
        def generate(self, messages, timeout=10, response_schema=None):
            captured["messages"] = messages
            return LLMResult(content=json_response, model="mock-model", usage={})

    monkeypatch.setattr("thursday.brain.DEFAULT_LLM", CapturingProvider())

    session = {"turns": [{"role": "user", "text": "earlier turn about something else"}]}
    decide(session=session, services={}, subagents=[], user_text="tell me about the widget")

    system_messages = "\n".join(m["content"] for m in captured["messages"] if m["role"] == "system")
    # The recent-turns section (higher priority) survives; the huge
    # memory-context block (lower priority) is dropped whole rather than
    # blowing the prompt out to tens of thousands of characters.
    assert "earlier turn about something else" in system_messages
    assert "detail attribute number" not in system_messages
    # The fixed prompt boilerplate alone runs a couple thousand characters;
    # the unbounded 300-relation entity dump this budget avoided would add
    # well over 15,000 more on top of that.
    assert len(system_messages) < 5000
