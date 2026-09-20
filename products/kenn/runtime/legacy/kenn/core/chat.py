#!/usr/bin/env python3
"""Terminal chatbot for the local Ableton tips knowledge base.

This module used to be one 4,298-line file; it's now a thin re-export shim over
kenn.core.chat_constants / chat_retrieval / chat_grounding / chat_routing /
chat_formatting / chat_answer / chat_cli, split by concern (see docs/BACKLOG.md
for the decomposition record). All public names below preserve the original
import surface for the ~20 external callers (server.py, business/app, scripts/,
thursday/voice.py, tests). Tests that monkeypatch an internal dependency (e.g.
grounding_report, mix_review, llm_enabled) must patch the submodule that owns the
real call site (chat_answer / chat_retrieval / chat_routing), not this shim —
patching the shim's copy of a name doesn't affect another module's own import of
that same name.
"""

from __future__ import annotations

from kenn.core.chat_constants import (  # noqa: F401
    ANALYSIS_TOOL_ROOT,
    ANSWER_MODES,
    ANSWER_QUALITY_MIN_SCORE,
    BUSINESS_PRICING_TERMS,
    CHAT_DIR,
    CHECK_IN_INPUTS,
    CHUNKS_PATH,
    FOLLOWUP_REFERENCES,
    FOLLOWUP_STARTERS,
    GAME_ROUTE_TOPICS,
    GENERIC_TRACK_TITLE_TERMS,
    GREETING_INPUTS,
    IMPOSSIBLE_PROMISE_TERMS,
    INDEX_DIR,
    INTENT_GUARD_TERMS,
    META_CHAT_PATTERNS,
    MIN_RELEVANT_SCORE,
    MIX_REVIEW_FOLLOWUP_TERMS,
    NOTES_DIR,
    NOTE_SCORE_BONUS,
    OUT_OF_SCOPE_TERMS,
    PRODUCTION_ROUTE_TOPICS,
    PROJECT_ROOT,
    REPO_ROOT,
    ROOT,
    ROUTE_MEMORY_PATH,
    SOURCE_QUALITY_ORDER,
    SYSTEM_NOTE,
    TERMS_PATH,
    TERM_ALIASES,
    THANKS_INPUTS,
    UNCLEAR_INPUTS,
    WEBSITE_ROOT,
)
from kenn.core.chat_retrieval import (  # noqa: F401
    _load_route_memory_cached,
    _multi_turn_boost,
    chunk_is_catalog_boilerplate,
    chunk_search_terms,
    detect_intent,
    diagnostic_reason,
    display_results,
    intent_guard_failed,
    intent_guard_status,
    load_chunks,
    load_route_memory,
    load_terms,
    normalized_terms,
    note_query_affinity,
    note_rank_key,
    prefer_note_over_manual,
    query_intent_terms,
    query_is_out_of_scope,
    result_payload,
    results_are_weak,
    route_memory_cache_key,
    route_memory_match,
    search,
    source_label,
    warm_index,
)
from kenn.core.chat_grounding import (  # noqa: F401
    MODE_BOUNDARY_REQUIREMENTS,
    answer_quality_report,
    answer_self_check,
    calibrate_answer_for_grounding,
    grounding_mode,
    grounding_report,
    mode_boundary_requirement_met,
    mode_signature,
    should_use_llm_rewrite,
)
from kenn.core.chat_routing import (  # noqa: F401
    _extract_mix_review_items,
    audio_generation_payload,
    business_pricing_payload,
    business_pricing_query,
    clarification_payload,
    classify_answer_mode,
    cleaned_query,
    client_delivery_query,
    constrain_results_for_query,
    conversational_intent,
    conversational_payload,
    dialogue_cleanup_query,
    first_move_line,
    format_timeline_report,
    format_track_memory,
    history_context_line,
    impossible_promise_payload,
    impossible_promise_query,
    is_followup_query,
    is_session_context_turn,
    is_unclear_query,
    latest_mix_review_context,
    latest_track_memory_lookup,
    mix_review_followup_payload,
    mix_review_timeline_lookup,
    mode_profile,
    normalize_history,
    route_query,
    search_query_with_history,
    session_context_matches_query,
    should_use_history,
    useful_history_user_turns,
)
from kenn.core.chat_formatting import (  # noqa: F401
    _append_followup,
    clean_step,
    confidence_level,
    fallback_short,
    fallback_steps,
    first_sentence,
    get_conversational_headers,
    load_note_text,
    note_sections,
    related_from_results,
    route_answer_plan,
    section_lines,
    source_quality_level,
    strip_catalog_metadata,
    suggested_followups,
    weak_match_answer,
)
from kenn.core.chat_answer import (  # noqa: F401
    _answer_payload,
    _answer_payload_stream,
    _get_kenn_lm,
    _progressive_token_yield,
    _split_answer_sections,
    answer_payload,
    answer_payload_stream,
    build_intent_answer,
    build_template_answer,
    make_answer,
)
from kenn.core.chat_cli import (  # noqa: F401
    ask_once,
    interactive,
    main,
    save_chat,
)
from kenn.knowledge import (  # noqa: F401
    save_reasoning_trace,
    query_reasoning_traces,
    get_reasoning_trace,
    list_reasoning_history,
    post_answer_critique,
    ingest_correction,
    list_lessons,
    list_corrections,
    propose_maintenance,
    get_source_trust,
    record_citation,
    record_correction,
    set_source_trust,
    list_source_trust,
    scan_for_contradictions,
    save_contradiction,
    list_contradictions,
    resolve_contradiction,
)


if __name__ == "__main__":
    raise SystemExit(main())
