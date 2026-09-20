from __future__ import annotations

import logging
import re
import time
import uuid
from typing import Generator

from kenn.orchestrator import get_orchestrator

from kenn.llm.llm_rewrite import (  # noqa: E402
    get_public_usage_stats as _get_llm_usage_stats,
)

from kenn.llm.llm_rewrite import enhance as llm_enhance_answer, enhance_stream as llm_enhance_answer_stream
from kenn.llm.llm_rewrite import is_enabled as llm_enabled
from kenn.core.session_memory import (
    build_session_context as _build_session_context,
    session_info as _session_info,
    update_session as _update_session,
    load_session as _load_session,
    skill_level_for_session as _skill_level_for_session,
    infer_preferences as _infer_preferences,
)
from kenn.core.branches import branches_payload as _branches_payload
from kenn.core.suggestions import merge_followups, parse_followups_from_answer, starter_questions
from kenn.retrieval.retrieval import (
    query_topics,
    tokenize,
)

from kenn.core.chat_constants import (
    ANSWER_QUALITY_MIN_SCORE,
    GAME_ROUTE_TOPICS,
    MIX_REVIEW_FOLLOWUP_TERMS,
)

from kenn.core.chat_retrieval import (
    chunk_search_terms,
    detect_intent,
    diagnostic_reason,
    display_results,
    intent_guard_failed,
    intent_guard_status,
    load_chunks,
    load_terms,
    normalized_terms,
    query_is_out_of_scope,
    result_payload,
    results_are_weak,
    search,
    evidence_label,
    source_label,
)
from kenn.core.chat_grounding import (
    answer_quality_report,
    answer_self_check,
    calibrate_answer_for_grounding,
    generated_answer_validation,
    grounding_mode,
    grounding_report,
    mode_signature,
    should_use_llm_rewrite,
)
from kenn.core.chat_routing import (
    audio_generation_payload,
    clarification_payload,
    classify_answer_mode,
    constrain_results_for_query,
    conversational_payload,
    format_timeline_report,
    format_track_memory,
    history_context_line,
    impossible_promise_payload,
    impossible_promise_query,
    is_followup_query,
    latest_mix_review_context,
    latest_track_memory_lookup,
    mix_review_followup_payload,
    mix_review_timeline_lookup,
    mode_profile,
    normalize_history,
    route_query,
    search_query_with_history,
    should_use_history,
)
from kenn.core.chat_formatting import (
    confidence_level,
    fallback_short,
    fallback_steps,
    get_conversational_headers,
    note_sections,
    route_answer_plan,
    source_quality_level,
    suggested_followups,
    weak_match_answer,
)
from kenn.core.diagnostic_framework import plan_for as diagnostic_plan_for, rank_with_evidence, render as render_diagnostic_plan
from kenn.core.evidence import current_for_diagnosis, packets_from_history, relevant_observations
from kenn.core.diagnostic_state import confirmed_findings as diagnostic_confirmed_findings, failed_techniques as diagnostic_failed_techniques, followup_query as diagnostic_followup_query, reported_findings as diagnostic_reported_findings


def _diagnostic_skill_level(query: str, session_id: str = "") -> str:
    """Use an explicit current-turn skill cue before stored session context.

    Session memory is saved after the answer is generated, so consulting only
    the session made a first-turn “I'm a beginner” ineffective.  This retains
    the deliberately conservative preference extractor: no level is inferred
    from jargon or topic alone.
    """
    current = str(_infer_preferences(query).get("skill_level") or "")
    return current or _skill_level_for_session(session_id)


def _adapt_production_answer_for_skill(answer: str, query: str, session_id: str = "") -> str:
    """Add one relevant lens to retrieved production guidance.

    Notes remain the authoritative technical content.  This small layer makes
    the same grounded note usable at two stated experience levels without
    inventing settings or rewriting its recommendation.  It deliberately
    reacts only to explicit/current-turn or saved preferences, never jargon.
    """
    level = _diagnostic_skill_level(query, session_id)
    if not level:
        return answer
    text = query.lower()
    if any(term in text for term in ("compress", "limiter", "dynamics")):
        beginner = "Plain-language note: compression automatically turns down louder moments. `Clip gain` means manually turning individual words or notes up/down before the compressor, so it has less work to do."
        advanced = "Advanced lens: compare candidates at matched output across sparse and dense sections; judge gain-reduction timing, transient retention, and breath/consonant exaggeration rather than meter movement alone."
    elif any(term in text for term in ("reverb", "delay", "plate", "hall")):
        beginner = "Plain-language note: reverb is the sense of a room or tail; delay is a repeat. A `send` lets the dry vocal stay clear while you control the effect separately."
        advanced = "Advanced lens: evaluate return masking in the densest section, pre-delay against consonant onset, and whether return filtering/ducking preserves the dry lead's depth cue."
    elif any(term in text for term in ("kick", "bass", "sub", "low end")):
        beginner = "Plain-language note: the `sub` is the very low weight you mostly feel; `mono` means the left and right sides are combined, which exposes low-end conflicts."
        advanced = "Advanced lens: compare fundamental ownership, envelope overlap, and mono-summed low-end stability at matched level before committing spectral or sidechain moves."
    else:
        beginner = "Plain-language note: make one small change at a time, compare at the same volume, and keep only the change that improves the full song—not just the sound in solo."
        advanced = "Advanced lens: isolate one causal variable, level-match the comparison, and verify the result in the densest relevant section before committing it."
    label = "Plain-language note:" if level == "beginner" else "Advanced lens:"
    guidance = beginner if level == "beginner" else advanced
    # The selected sentence already contains its label. Insert after the
    # opening paragraph so it is seen before the retrieved workflow.
    first_break = answer.find("\n\n")
    if first_break < 0:
        return f"{guidance}\n\n{answer}"
    if label.lower() in answer.lower():
        return answer
    return f"{answer[:first_break]}\n\n{guidance}{answer[first_break:]}"


def _specialist_evidence_context(query: str, history: list | None) -> str:
    """Provide bounded typed specialist observations to answer validation.

    Classifier and stem-scan results are carried in typed history rather than
    retrieval chunks. The answer builder already renders the relevant
    observations; mirror that same text into generated-answer validation so a
    valid rewrite is not rejected merely because its measurements came from a
    specialist tool.
    """
    packets = current_for_diagnosis(packets_from_history(history))
    specialist_packets = [
        packet for packet in packets
        if packet.source in {"audio_classification", "stem_masking_analysis"}
    ]
    return " ".join(relevant_observations(query, specialist_packets))


def asks_for_sources(query: str) -> bool:
    if not query:
        return False
    terms = {"source", "sources", "reference", "references", "citation", "citations", "link", "links", "where is this from", "prove", "origin"}
    query_lower = query.lower()
    return any(term in query_lower for term in terms)


def format_source_as_link(chunk: dict) -> str:
    provenance = evidence_label(chunk)
    if chunk.get("kind") == "note":
        title = chunk.get("title") or chunk.get("source")
        filename = chunk.get("source")
        if title.lower().endswith(".md"):
            title = title[:-3]
        return f"[{title}](/api/ableton/note?name={filename}) — {provenance}"
    return f"{chunk['source']}, page {chunk['page']} — {provenance}"


_MIX_HELP_RE = re.compile(
    r"\bhelp\b\s+(?:me\s+)?(?:out\s+)?(?:with\s+)?(?:my\s+|the\s+|this\s+)?mix\b"
)


def is_mix_help_request(query: str) -> bool:
    """True only for an actual request-shaped phrase like "help me with my
    mix" or "help with the mix" -- the original "help" in text and "mix" in
    text (regardless of distance or context) matched any technical question
    that happened to use both words, e.g. "can you help me understand
    parallel compression on my mix bus", hijacking it into a canned
    "upload your file" response instead of answering it (2026-08-04).
    """
    if not query:
        return False
    return bool(_MIX_HELP_RE.search(query.lower()))


def _is_diagnostic_result_report(query: str, session_id: str) -> bool:
    """Whether this turn explicitly reports the active plan's test result."""
    if not session_id:
        return False
    try:
        state = _load_session(session_id=session_id).get("diagnostic_state")
    except Exception:
        logging.getLogger("kenn.core.chat_answer").warning(
            "Session state load failed in _is_diagnostic_result_report; "
            "treating as not a result report", exc_info=True,
        )
        return False
    return bool(diagnostic_reported_findings(state, query))



def build_intent_answer(
    intent: str,
    short: str,
    steps: list[str],
    why: str,
    mode: str,
    route: str,
    profile: dict,
    plan: dict,
    followups: list[str],
    query: str,
    results: list[tuple[float, dict]],
    answer_mode: str,
    confidence: str = "medium",
    context: str = "",
    timeline_context: str | None = None,
    session_context: str = "",
    common_mistakes: list[str] | None = None,
    scope_limits: list[str] | None = None,
) -> list[str]:
    """Build an answer shaped by the user's intent.

    Each intent produces a different answer structure:
    - troubleshooting: Symptom → Likely cause → Fix steps → Check
    - steps: Just numbered steps, no explanation preamble
    - why: Explanation first, then application
    - explain: Concept → How it applies → Try it
    - compare: Side-by-side tradeoffs
    - general: Standard KENN structure with mode signature
    """
    sig = mode_signature(answer_mode, confidence)
    hdrs = get_conversational_headers(route, query_topics(query))
    common_mistakes = common_mistakes or []
    scope_limits = scope_limits or []
    lines: list[str] = []

    # --- Opener ---
    opener = str(plan.get("opener", ""))
    if opener:
        lines.append(opener)

    if context:
        lines.extend(["", context])

    # Session memory hook: if we have prior context, inject it right after the opener
    if session_context:
        lines.extend(["", "[Session Summary]:", session_context])

    conf_line = sig.get("opener", "")
    if conf_line:
        lines.append(conf_line)

    # --- Intent-shaped body ---
    if intent == "troubleshooting":
        # Symptom → Likely cause → Fix steps
        if short:
            lines.extend(["", "Symptom and likely cause:", short])
        if steps:
            lines.extend(["", "Try this in your session:"])
            for index, step in enumerate(steps[:5], start=1):
                lines.append(f"{index}. {step}")
        if profile.get("check_label") and profile.get("check"):
            lines.extend(["", str(profile["check_label"]), str(profile["check"])])

    elif intent == "steps":
        # Just the numbered steps, no explanation preamble
        if steps:
            lines.extend(["", "Here are the steps:"])
            for index, step in enumerate(steps[:6], start=1):
                lines.append(f"{index}. {step}")
        if why:
            lines.extend(["", "Why this works:", why])
        if profile.get("check_label") and profile.get("check"):
            lines.extend(["", str(profile["check_label"]), str(profile["check"])])

    elif intent == "why":
        # Explanation first, then application
        if why:
            lines.extend(["", "The reasoning:", why])
        if short:
            lines.extend(["", "In practice:", short])
        if steps:
            lines.extend(["", "To apply this:"])
            for index, step in enumerate(steps[:4], start=1):
                lines.append(f"{index}. {step}")

    elif intent == "explain":
        # Concept → How it applies → Try it
        if short:
            lines.extend(["", "The concept:", short])
        if why:
            lines.extend(["", "Why it works:", why])
        if steps:
            lines.extend(["", "Try it:"])
            for index, step in enumerate(steps[:4], start=1):
                lines.append(f"{index}. {step}")

    else:
        # General / default — standard KENN structure
        if short:
            lines.extend(["", hdrs["short"], short])
        if steps:
            lines.extend(["", hdrs["steps"]])
            for index, step in enumerate(steps[:6], start=1):
                lines.append(f"{index}. {step}")
        if profile.get("boundary_label") and profile.get("boundary"):
            lines.extend(["", str(profile["boundary_label"]), str(profile["boundary"])])
        if profile.get("tradeoff_label") and profile.get("tradeoff"):
            lines.extend(["", str(profile["tradeoff_label"]), str(profile["tradeoff"])])
        # Prefer the retrieved note's own "Common mistakes" bullets (real,
        # topic-specific pitfalls the note's author actually wrote) over the
        # generic per-mode/per-route "avoid" boilerplate -- found live-testing
        # 2026-08-03 that 122 notes have this content and none of it was ever
        # surfaced anywhere; every answer showed the same handful of generic
        # mode-level strings regardless of topic.
        avoid_text = (
            "\n".join(f"- {mistake}" for mistake in common_mistakes)
            if common_mistakes
            else str(profile.get("avoid") or plan["avoid"])
        )
        lines.extend(
            [
                "",
                str(profile.get("check_label") or plan["check_label"]),
                str(profile.get("check") or plan["check"]),
                "",
                hdrs["avoid"],
                avoid_text,
                "",
                hdrs["why"],
                why,
            ]
        )
        # Same "computed but never wired up" pattern as common_mistakes above:
        # 74 notes have a "When this does not apply" scope boundary (e.g.
        # "use Glue Compressor instead" for vintage bus coloration) that was
        # never surfaced. Only shown when the retrieved note actually has it.
        if scope_limits:
            lines.extend(
                [
                    "",
                    "This doesn't apply if:",
                    "\n".join(f"- {limit}" for limit in scope_limits),
                ]
            )

    # Intent-specific layouts used to omit the mode's safety boundary and
    # verification check. Keep those invariants across every answer shape.
    rendered_lower = "\n".join(lines).lower()
    for label_key, value_key in (
        ("boundary_label", "boundary"),
        ("tradeoff_label", "tradeoff"),
        ("check_label", "check"),
    ):
        label = str(profile.get(label_key) or "").strip()
        value = str(profile.get(value_key) or "").strip()
        if label and value and label.lower() not in rendered_lower:
            lines.extend(["", label, value])
            rendered_lower += f"\n{label.lower()}\n{value.lower()}"
    if common_mistakes:
        mistakes_block = "\n".join(f"- {mistake}" for mistake in common_mistakes)
        if mistakes_block.lower() not in rendered_lower:
            lines.extend(["", hdrs["avoid"], mistakes_block])
    else:
        avoid = str(profile.get("avoid") or "").strip()
        if avoid and avoid.lower() not in rendered_lower:
            lines.extend(["", hdrs["avoid"], avoid])
    if scope_limits:
        limits_block = "\n".join(f"- {limit}" for limit in scope_limits)
        if limits_block.lower() not in rendered_lower:
            lines.extend(["", "This doesn't apply if:", limits_block])
            rendered_lower += f"\nthis doesn't apply if:\n{limits_block.lower()}"

    # Mono-compatible width requires an explicit phase check.  Keep this
    # source-grounded invariant even when the concise "steps" layout omits the
    # note's short-answer section.
    query_terms = normalized_terms(query)
    displayed_chunks = [chunk for _score, chunk in display_results(query, results, 3)]
    if (
        "mono" in query_terms
        and ({"width", "wider"} & query_terms or "stereo_width" in query_topics(query))
        and any("phase" in chunk_search_terms(chunk) for chunk in displayed_chunks)
        and "phase" not in "\n".join(lines).lower()
    ):
        lines.extend(
            [
                "",
                "Phase check:",
                "Collapse to mono and watch correlation; if an element loses level or vanishes, reduce the phase-dependent widening.",
            ]
        )

    # --- Closing signature ---
    closing = sig.get("closing", "")
    if closing:
        lines.extend(["", closing])

    # --- Sources ---
    # Gated behind asks_for_sources() by explicit preference (2026-08-05,
    # reverted from always-on) -- keeps the answer body uncluttered by
    # default; the underlying retrieval/citations are still fully present
    # in the structured `sources` payload field regardless of whether this
    # text section renders, so benchmark/quality checks should assert
    # against that field, not require the citation text to be visible.
    if asks_for_sources(query):
        lines.extend(["", "Sources:"])
        for _, chunk in display_results(query, results, 3):
            lines.append(f"- {format_source_as_link(chunk)}")

    # --- Follow-ups ---
    if followups:
        lines.extend(["", "You could also ask:"])
        lines.extend(f"- {q}" for q in followups[:2])

    return lines


# Live-tested 2026-08-03: a 5-turn troubleshooting conversation ("my mix
# sounds muddy" -> "its mostly in the low mids" -> "i already tried eq
# cuts" -> ... -> "ok i did sidechain, still muddy") kept suggesting
# techniques the user had just said didn't work -- "i already tried eq
# cuts" got another EQ-focused answer, and "i did sidechain, still muddy"
# got a generic Multiband Dynamics explanation, neither acknowledging what
# had already been ruled out. mix_diagnosis mode was built for single-shot
# "symptom -> fix" answers, not a stateful troubleshooting conversation.
# This is a narrow, scoped piece of that: detect "already tried X, it
# didn't work" phrasing, deprioritize retrieval results primarily about
# that same technique, and frame the answer as "let's rule out something
# else" instead of silently repeating the same suggestion.
_ALREADY_TRIED_RE = re.compile(
    r"\b(already tried|tried that|tried it|still (?:not|doesn't|didn't|isn't|sounds|muddy|"
    r"harsh|boxy|thin|weak|quiet)|doesn't work|didn't work|not working|no luck|no change|"
    r"no difference)\b",
    re.IGNORECASE,
)
_ALREADY_TRIED_TECHNIQUE_TERMS = {
    "eq": "EQ", "equalization": "EQ", "equalizer": "EQ",
    "sidechain": "sidechaining", "side chain": "sidechaining", "side-chain": "sidechaining",
    "compression": "compression", "compressor": "compression",
    "saturation": "saturation", "clipping": "clipping", "limiting": "limiting",
    "gating": "gating", "gate": "gating",
    "parallel compression": "parallel compression",
    "mid-side": "mid-side processing", "mid side": "mid-side processing",
    "reverb": "reverb", "delay": "delay",
    "high-pass": "high-pass filtering", "high pass": "high-pass filtering",
    "low-pass": "low-pass filtering", "low pass": "low-pass filtering",
}


def _already_tried_technique(query: str) -> str:
    """The technique the user says they already tried without success, or
    "" if the query doesn't signal this."""
    if not _ALREADY_TRIED_RE.search(query):
        return ""
    lowered = query.lower()
    for term, label in _ALREADY_TRIED_TECHNIQUE_TERMS.items():
        if term in lowered:
            return label
    return ""


def _deprioritize_already_tried(
    results: list[tuple[float, dict]], already_tried: str
) -> list[tuple[float, dict]]:
    """Drop retrieved chunks primarily ABOUT the already-tried technique, so
    a different technique surfaces. Matched via title only, not tags --
    tags are a broad set of related keywords (nearly every mixing note
    tags itself "eq" since it's used almost everywhere, which would
    exclude the entire result set for any EQ-adjacent query), while a
    note's title is a precise signal of its actual subject ("EQ Eight
    Mixing Basics" is about EQ; "Fix Muddy Low-Mids In A Mix" merely uses
    EQ as part of its answer and should still be allowed to surface). Uses
    whole-word matching -- a bare substring check on a short term like "eq"
    would also match "frequency" or "sequence". Never filters to nothing.
    """
    term_re = re.compile(rf"\b{re.escape(already_tried.lower())}\b")
    filtered = [
        (score, chunk) for score, chunk in results
        if not term_re.search(str(chunk.get("title", "")).lower())
    ]
    return filtered if filtered else results


def build_template_answer(
    query: str,
    results: list[tuple[float, dict]],
    *,
    history: list | None = None,
    route: str = "unknown",
    timeline_context: str | None = None,
    answer_mode: str = "",
    session_id: str = "",
) -> str:
    if not timeline_context:
        # A clear symptom plan (or an explicit result from its active test)
        # is deterministic, bounded reasoning and must not be hidden merely
        # because retrieval has no matching prose note.  Retrieval remains
        # the fallback for questions without either signal.
        diagnostic_hint = diagnostic_plan_for(query)
        state_finding_hint = []
        if not diagnostic_hint and session_id:
            try:
                state_finding_hint = diagnostic_reported_findings(
                    _load_session(session_id=session_id).get("diagnostic_state"), query
                )
            except Exception:
                logging.getLogger("kenn.core.chat_answer").warning(
                    "Session state load failed while checking for a reported "
                    "diagnostic finding; treating as none found", exc_info=True,
                )
                state_finding_hint = []
        if (not results or results_are_weak(query, results) or intent_guard_failed(query, results)) and not diagnostic_hint and not state_finding_hint:
            return weak_match_answer(query, answer_mode=answer_mode)

    already_tried = _already_tried_technique(query)
    if already_tried:
        results = _deprioritize_already_tried(results, already_tried)
    results = _prefer_general_framework_for_uncovered_hardware(query, results)

    intent = detect_intent(query)
    topics = query_topics(query)
    plan = route_answer_plan(route, intent, topics)
    mode = answer_mode or classify_answer_mode(query, route, history=history)
    profile = mode_profile(mode)
    sections = note_sections(query, results)
    short = str(sections.get("short") or fallback_short(query, results))
    steps = list(sections.get("steps") or fallback_steps(intent, query, results, route))
    why = str(
        sections.get("why")
        or "The best next move is to test this inside Ableton and compare it against the source references."
    )
    related = list(sections.get("related") or [])
    common_mistakes = list(sections.get("common_mistakes") or [])
    scope_limits = list(sections.get("scope_limits") or [])
    followup_history = history if should_use_history(query, history) else None
    followups = suggested_followups(query, related, topics, followup_history, results=results)

    context = history_context_line(query, history)
    confidence = confidence_level(query, results)

    session_context = (
        _build_session_context(session_id=session_id)
        if _session_context_is_relevant(query, session_id)
        else ""
    )

    # Retrieval supplies topic-specific evidence, but its note-shaped
    # template used to jump from an ambiguous symptom straight to the first
    # technique mentioned in the best note.  For symptom-driven mix diagnosis
    # use a small causal plan first: rank plausible causes, give a cheap test
    # that separates them, and only then state the conditional intervention.
    # Keep this deterministic so the quality is available when the optional
    # LLM rewrite is disabled or unavailable.  Uploaded Mix Review context is
    # already evidence about the actual file and must remain its own path.
    diagnostic_state = None
    if session_id:
        try:
            diagnostic_state = _load_session(session_id=session_id).get("diagnostic_state")
        except Exception:
            logging.getLogger("kenn.core.chat_answer").warning(
                "Session state load failed while fetching diagnostic_state; "
                "continuing with no active diagnostic plan", exc_info=True,
            )
            diagnostic_state = None
    # A saved Mix Review timeline describes an actual uploaded render.  It
    # must enrich a symptom diagnosis with typed evidence, not suppress the
    # causal layer and force the user back to a generic report summary.
    # Keep the old timeline-only behaviour only when no structured evidence
    # was supplied with it (for example a legacy text summary).
    history_evidence = current_for_diagnosis(packets_from_history(history))
    diagnostic_plan = diagnostic_plan_for(query) if (not timeline_context or history_evidence) else None
    # An elliptical turn such as "still muddy" needs the active symptom from
    # this session, but only after the normal query itself produced no plan.
    reported_findings = diagnostic_reported_findings(diagnostic_state, query)
    diagnosis_continuation = is_followup_query(query) or bool(reported_findings) or bool(
        re.search(r"\b(still|no (?:change|difference|luck)|didn'?t work|doesn'?t work)\b", query, re.I)
    )
    if not diagnostic_plan and (not timeline_context or history_evidence) and diagnosis_continuation:
        canonical = diagnostic_followup_query(diagnostic_state)
        if canonical:
            diagnostic_plan = diagnostic_plan_for(canonical)
    # A symptom-shaped mastering question ("too loud and distorted") needs
    # diagnosis as much as a mix question does.  `mastering_safety` remains
    # the right mode for a direct export/loudness workflow, but must not
    # suppress measured clipping evidence when the user is troubleshooting.
    if diagnostic_plan:
        diagnostic_plan, ranking_rationale = rank_with_evidence(diagnostic_plan, history_evidence)
        lines = render_diagnostic_plan(diagnostic_plan, skill_level=_diagnostic_skill_level(query, session_id))
        findings = [*diagnostic_confirmed_findings(diagnostic_state), *reported_findings]
        findings = list(dict.fromkeys(findings))
        if findings:
            insert_at = lines.index("Most useful hypotheses to test:") if "Most useful hypotheses to test:" in lines else 0
            lines[insert_at:insert_at] = ["", "What your test result supports:", *findings, ""]
        failed = diagnostic_failed_techniques(diagnostic_state)
        if failed:
            insert_at = lines.index("Most useful hypotheses to test:") if "Most useful hypotheses to test:" in lines else 0
            lines[insert_at:insert_at] = [
                "",
                "Already tested:",
                f"You reported that {', '.join(failed)} did not resolve this symptom. Do not repeat it as the next move; start with an untested discriminator below.",
                "",
            ]
        measured = relevant_observations(query, history_evidence)
        if measured:
            insert_at = lines.index("Most useful hypotheses to test:") if "Most useful hypotheses to test:" in lines else 0
            priority = ["", "Evidence-informed priority:", ranking_rationale, ""] if ranking_rationale else []
            lines[insert_at:insert_at] = ["", "Measured evidence:", *measured, *priority]
        if asks_for_sources(query):
            lines.extend(["", "Sources:"])
            for _, chunk in display_results(query, results, 3):
                lines.append(f"- {format_source_as_link(chunk)}")
        if followups:
            lines.extend(["", "You could also ask:"])
            lines.extend(f"- {item}" for item in followups[:2])
        ans = "\n".join(lines).strip()
        query_specific_note = _query_specific_grounding_note(query)
        if query_specific_note:
            ans = f"{query_specific_note}\n\n{ans}"
        caveat = _uncovered_hardware_caveat(query, results)
        if caveat:
            ans = f"{caveat}\n\n{ans}"
        no_audio = _no_audio_caveat(query, timeline_context)
        if no_audio:
            ans = f"{no_audio}\n\n{ans}"
        from kenn.llm.linter import lint_response
        return lint_response(ans, mode)

    lines = build_intent_answer(
        intent=intent,
        short=short,
        steps=steps,
        why=why,
        mode=mode,
        route=route,
        profile=profile,
        plan=plan,
        followups=followups,
        query=query,
        results=results,
        answer_mode=mode,
        confidence=confidence,
        context=context,
        timeline_context=timeline_context,
        session_context=session_context,
        common_mistakes=common_mistakes,
        scope_limits=scope_limits,
    )

    # Standalone specialist results arrive as typed history rather than as
    # retrieval documents.  Surface their bounded observations in ordinary
    # advice too; otherwise they would only affect the diagnostic branch (or
    # remain hidden in metadata) even when the producer explicitly asks to
    # identify a sample or interpret a stem scan.
    specialist_packets = [
        packet for packet in history_evidence
        if packet.source in {"audio_classification", "stem_masking_analysis"}
    ]
    specialist_observations = relevant_observations(query, specialist_packets)
    if specialist_observations:
        lines.extend(["", "Evidence from your supplied analysis:", *specialist_observations])

    ans = "\n".join(lines).strip()
    ans = _adapt_production_answer_for_skill(ans, query, session_id)
    query_specific_note = _query_specific_grounding_note(query)
    if query_specific_note:
        ans = f"{query_specific_note}\n\n{ans}"
    if already_tried:
        ans = (
            f"Since {already_tried} already didn't fully fix it, let's rule out "
            f"something else.\n\n{ans}"
        )
    caveat = _uncovered_hardware_caveat(query, results)
    if caveat:
        ans = f"{caveat}\n\n{ans}"
    no_audio = _no_audio_caveat(query, timeline_context)
    if no_audio:
        ans = f"{no_audio}\n\n{ans}"
    from kenn.llm.linter import lint_response
    return lint_response(ans, mode)


# Well-known classic hardware/plugin names -- live-tested 2026-08-03: asked
# "how do I use the SSL 4000 console EQ curve on my vocal" and got a fully
# confident (grounding score 90, "strong"), complete answer about de-essing
# and sibilance -- nothing to do with the SSL 4000 at all. Retrieval scored
# high purely on generic "EQ"/"vocal" keyword overlap; the KB simply has no
# note on classic analog hardware curves/behaviour, and nothing flagged
# that gap. Same result for the 1176, Pultec EQP-1A, and LA-2A. Kept
# deliberately small and high-confidence (well-known iconic units only) to
# avoid false positives on ordinary text.
_KNOWN_HARDWARE_TERMS = {
    "ssl 4000": "SSL 4000", "ssl 9000": "SSL 9000", "ssl g-series": "SSL G-Series",
    "1176": "1176", "la-2a": "LA-2A", "la2a": "LA-2A", "pultec": "Pultec",
    "eqp-1a": "EQP-1A", "fairchild 670": "Fairchild 670", "fairchild": "Fairchild",
    "neve 1073": "Neve 1073", "neve 33609": "Neve 33609", "api 2500": "API 2500",
    "distressor": "Distressor", "dbx 160": "dbx 160",
    "manley massive passive": "Manley Massive Passive", "tube-tech": "Tube-Tech",
}

_KNOWN_DYNAMICS_HARDWARE_TERMS = {
    "1176", "la-2a", "la2a", "fairchild 670", "fairchild", "neve 33609",
    "api 2500", "distressor", "dbx 160", "tube-tech",
}


def _uncovered_hardware_caveat(query: str, results: list[tuple[float, dict]]) -> str:
    """A named piece of classic hardware the query asks about that none of
    the retrieved sources actually cover, as an honest caveat sentence --
    or "" if the query doesn't name any, or the sources do cover it."""
    lowered_query = query.lower()
    mentioned = next((term for term in _KNOWN_HARDWARE_TERMS if term in lowered_query), "")
    if not mentioned:
        return ""
    source_text = " ".join(
        str(chunk.get("text") or "").lower()
        for _score, chunk in display_results(query, results, 3)
    )
    if mentioned in source_text:
        return ""
    display_name = _KNOWN_HARDWARE_TERMS[mentioned]
    return (
        f"You'll want a note specifically on the {display_name} -- nothing in "
        "the knowledge base covers that unit's exact behaviour yet. Here's "
        "the closest general guidance I have:"
    )


def _prefer_general_framework_for_uncovered_hardware(
    query: str, results: list[tuple[float, dict]]
) -> list[tuple[float, dict]]:
    """Prevent an honest hardware caveat from preceding irrelevant advice.

    We intentionally do not infer an exact 1176/LA-2A/etc. control recipe
    without a source for that unit.  When a user asks about an uncovered
    dynamics processor on a vocal, the closest honest fallback is the vetted
    *general* vocal-compression decision framework—not a coincidental vocal
    note such as de-essing that happened to score highest on generic terms.
    """
    lowered = query.lower()
    has_uncovered_dynamics_unit = any(term in lowered for term in _KNOWN_DYNAMICS_HARDWARE_TERMS)
    if not has_uncovered_dynamics_unit or "vocal" not in lowered:
        return results
    if not _uncovered_hardware_caveat(query, results):
        return results
    preferred = [item for item in results if item[1].get("source") == "vocal-compressor-selection.md"]
    if not preferred:
        # The ordinary top-N retrieval result can be entirely occupied by
        # generic vocal terms (often de-essing). Pull the approved general
        # compressor note from the same local index, retaining an explicit
        # source rather than manufacturing an answer from a hard-coded recipe.
        preferred = [
            # Keep this finite: response metadata and JSON payloads must not
            # contain IEEE Infinity even though Python-only ranking accepts it.
            (1_000_000.0, chunk)
            for chunk in load_chunks()
            if chunk.get("source") == "vocal-compressor-selection.md"
        ]
    return preferred or results


# Live-tested 2026-08-10: "Listen to my vocal and tell me exactly what's
# wrong with it" fell through every existing gate (not question-shaped in
# the how-do-I sense, no literal "mix"/"master"/"track" noun for
# _MIX_REVIEW_PATTERNS to catch) and got answered as a generic vocal-comping
# question -- not literally claiming to have heard the audio, but not being
# upfront that it hadn't either. This closes that gap: a narrow match for
# phrasing that implies KENN already has the user's actual audio in hand
# (imperative "listen to"/"hear", or "tell me/what do you think" framed as
# if an analysis were possible), when no real analysis evidence
# (timeline_context from an actual Mix Review) exists for this session.
# Deliberately does NOT exclude question-shaped text the way
# orchestrator.py's dispatch guard does -- unlike that guard (which decides
# whether to hijack the whole answer with a tool-dispatch stub), this only
# prepends an honest disclaimer ahead of the same useful general answer, so
# a false positive costs one extra sentence rather than a wrong answer.
_CLAIMS_KENN_HEARD_AUDIO_RE = re.compile(
    r"\b(listen to|hear)\s+(my|this|the)\b.{0,40}\b(vocal|mix|master|track|song|beat|recording|take|file|stem)\b"
    r"|\btell me (exactly\s+)?what(?:'s|\s+is)?\s+wrong\s+with\s+(it|this|my)\b"
    r"|\bwhat\s+do\s+you\s+(think|hear)\s+(of|in)\s+(this|my)\b",
    re.I,
)


def _no_audio_caveat(query: str, timeline_context: str | None) -> str:
    """An honest disclaimer when the query implies KENN has already heard
    the user's actual audio and no real analysis evidence exists for this
    session -- or "" if the claim isn't made, or real evidence does exist."""
    if timeline_context:
        return ""
    if not _CLAIMS_KENN_HEARD_AUDIO_RE.search(query.lower()):
        return ""
    return (
        "I haven't actually heard your audio -- there's no file or Mix Review "
        "result attached to this chat yet, so what follows is general guidance "
        "based on the symptom you described, not an analysis of your track. "
        "Upload your file and I'll run it through Mix Review for real "
        "measurements:"
    )


def _query_specific_grounding_note(query: str) -> str:
    """Keep explicit user settings/measurements visible in grounded advice.

    Retrieval notes explain the general workflow, but a generic note can still
    bury a concrete value supplied by the user. These deterministic bridges
    make the answer useful while labelling the value as user-reported context,
    not as a measurement KENN made itself.
    """
    lowered = query.casefold()
    if (
        re.search(r"\b(?:eq\s*eight|eq8)\b", lowered)
        and re.search(r"\b(?:add|insert|put|place)\b", lowered)
        and re.search(r"\b(?:track|channel|ch)\s*(?:number\s*)?\d+\b", lowered)
    ):
        track_match = re.search(r"\b(?:track|channel|ch)\s*(?:number\s*)?(\d+)\b", lowered)
        track = track_match.group(1) if track_match else "the target"
        return (
            f"For the exact Ableton workflow: select track {track}, open Audio Effects, and drag EQ Eight "
            "onto that track's device chain. Make one measured EQ change at a time, then bypass it and "
            "compare at matched level before keeping the move."
        )
    if (
        "reverb" in lowered
        and re.search(r"\b(?:add|insert|put|place)\b", lowered)
        and re.search(r"\bdry\s*/?\s*wet\b|\bdry\s+wet\b", lowered)
    ):
        value_match = re.search(
            r"(\d+(?:\.\d+)?)\s*%\s*(?:dry\s*/?\s*wet|dry\s+wet)", lowered
        )
        value = value_match.group(1) if value_match else "the requested"
        return (
            f"For the exact insert you described: put Hybrid Reverb on the hi-hat/source track and set "
            f"Dry/Wet to {value}%. If you use a Return track instead, keep the return 100% wet and "
            "control the amount with the source track's send."
        )
    if (
        "pink" in lowered
        and "noise" in lowered
        and re.search(r"\b\d+(?:\.\d+)?\s*(?:hz|khz)\b", lowered)
    ):
        amount_match = re.search(r"([+-]?\d+(?:\.\d+)?)\s*db\s+(?:above|below)", lowered)
        frequency_match = re.search(r"(\d+(?:\.\d+)?)\s*(hz|khz)\b", lowered)
        amount = amount_match.group(1) if amount_match else "the stated"
        frequency = "that band"
        if frequency_match:
            unit = {"hz": "Hz", "khz": "kHz"}[frequency_match.group(2)]
            frequency = f"{frequency_match.group(1)} {unit}"
        direction = "above" if "above" in lowered else "below"
        interpretation = (
            "It could indicate extra low-mid/body energy there, sometimes heard as warmth, mud, or boxiness."
            if direction == "above"
            else "It could indicate a relative low-mid/body dip there, which may make the mix feel thinner."
        )
        return (
            f"Based on your stated measurement (not a measurement KENN made): {amount} dB {direction} "
            f"the pink-noise-style baseline around {frequency} suggests a broad tonal imbalance. {interpretation} "
            "Do not automatically cut or boost by the full measured amount: first level-match, use a long-term "
            "spectrum, compare a few same-style references, and confirm the change by ear. The baseline is a "
            "reference aid, not a universal EQ target."
        )
    return ""


_kenn_lm = None


def _session_context_is_relevant(query: str, session_id: str) -> bool:
    """Only inject a saved summary when its topic still matches this turn."""
    if not session_id or not is_followup_query(query):
        return False
    current_topics = set(query_topics(query))
    # A bare "is that too loud?" needs the preceding context.  A question
    # with its own named subject should not inherit an unrelated old one just
    # because it happens to contain a pronoun such as "that".
    if not current_topics:
        return True
    try:
        state = _load_session(session_id=session_id)
    except Exception:
        logging.getLogger("kenn.core.chat_answer").warning(
            "Session state load failed in _session_context_is_relevant; "
            "treating saved context as relevant (fail open)", exc_info=True,
        )
        return True
    previous_topics = set(query_topics(str(state.get("last_question", ""))))
    return not previous_topics or bool(current_topics & previous_topics)


def _get_kenn_lm():
    global _kenn_lm
    if _kenn_lm is None:
        try:
            from kenn.llm.kenn_lm import KennLM
            _kenn_lm = KennLM()
        except Exception as e:
            print(f"Warning importing KennLM: {e}")
    return _kenn_lm


def make_answer(
    query: str,
    results: list[tuple[float, dict]],
    *,
    history: list | None = None,
    allow_llm: bool = True,
    route: str = "unknown",
    timeline_context: str | None = None,
    answer_mode: str = "",
    session_id: str = "",
) -> tuple[str, bool]:
    import os, time as _time, sys as _sys
    _ma_t0 = _time.perf_counter()
    template = build_template_answer(
        query,
        results,
        history=history,
        route=route,
        timeline_context=timeline_context,
        answer_mode=answer_mode,
        session_id=session_id,
    )
    _ma_template_ms = (_time.perf_counter() - _ma_t0) * 1000
    if timeline_context:
        template = timeline_context + "\n\n" + template
    is_context_query = "[stems masking" in query.lower() or "[audio characterization" in query.lower()
    if (
        results_are_weak(query, results) or intent_guard_failed(query, results)
    ) and not timeline_context and not is_context_query:
        print(f"  make_answer: template={_ma_template_ms:.0f}ms (weak, early return)", file=_sys.stderr, flush=True)
        return template, False
    # Exact hardware behaviour is a source boundary, not a creative-writing
    # opportunity.  The deterministic response already states the gap and
    # uses the closest approved general framework; an optional rewrite can
    # only dilute that honesty and, with a slow local model, unnecessarily
    # delay a simple question.
    if _uncovered_hardware_caveat(query, results):
        return template, False
    # The current fine-tuned checkpoint was rejected by the 2026-07-14
    # context-adherence evaluation.  Keep it available for explicit experiments,
    # but do not let a stale KENN_LM_ENABLED setting activate it in production.
    local_lm_enabled = (
        os.environ.get("KENN_LM_ENABLED") == "1"
        and os.environ.get("KENN_LM_ALLOW_REJECTED") == "1"
    )
    if allow_llm and local_lm_enabled:
        kenn_lm = _get_kenn_lm()
        if kenn_lm and kenn_lm.available:
            chunks_texts = []
            for _score, chunk in results:
                text = chunk.get("text", "")
                if text:
                    chunks_texts.append(text.strip())
            context = "\n\n".join(chunks_texts)
            try:
                print("Generating answer using local fine-tuned KENN LM...")
                answer = kenn_lm.generate(query, context, history=history)
                if answer:
                    from kenn.llm.linter import lint_response
                    mode = answer_mode or classify_answer_mode(query, route, history=history)
                    answer = lint_response(answer, mode)
                    local_confidence = "high" if timeline_context else confidence_level(query, results)
                    local_validation = generated_answer_validation(
                        query,
                        results,
                        answer,
                        route=route,
                        confidence=local_confidence,
                        answer_mode=mode,
                        timeline_context=timeline_context,
                        additional_evidence_text=_specialist_evidence_context(query, history),
                    )
                    if local_validation["accepted"]:
                        return answer, True
            except Exception as e:
                print(f"Local KENN LM generation failed: {e}. Falling back...")
    if not allow_llm:
        print(f"  make_answer: template={_ma_template_ms:.0f}ms (llm disabled)", file=_sys.stderr, flush=True)
        return template, False
    _ma_t1 = _time.perf_counter()
    confidence = "high" if timeline_context else confidence_level(query, results)
    grounding = grounding_report(
        query,
        results,
        template,
        route=route,
        confidence=confidence,
        timeline_context=timeline_context,
    )
    quality = answer_quality_report(
        query,
        results,
        template,
        route=route,
        confidence=confidence,
        answer_mode=answer_mode or classify_answer_mode(query, route, history=history),
        grounding=grounding,
        timeline_context=timeline_context,
    )
    _ma_grounding_ms = (_time.perf_counter() - _ma_t1) * 1000
    if not should_use_llm_rewrite(
        query,
        route,
        confidence,
        grounding,
        quality,
        answer_mode or classify_answer_mode(query, route, history=history),
    ):
        print(f"  make_answer: template={_ma_template_ms:.0f}ms grounding={_ma_grounding_ms:.0f}ms (no rewrite)", file=_sys.stderr, flush=True)
        return template, False
    _ma_t2 = _time.perf_counter()
    enhanced = llm_enhance_answer(
        query,
        template,
        results,
        history,
        history_context_line(query, history),
        source_label,
        normalize_history,
        answer_mode=answer_mode,
        route=route,
        timeline_context=timeline_context,
        skill_level=_skill_level_for_session(session_id),
    )
    if enhanced:
        from kenn.llm.linter import lint_response
        mode = answer_mode or classify_answer_mode(query, route, history=history)
        enhanced = lint_response(enhanced, mode)
        validation = generated_answer_validation(
            query,
            results,
            enhanced,
            route=route,
            confidence=confidence,
            answer_mode=mode,
            timeline_context=timeline_context,
            additional_evidence_text=_specialist_evidence_context(query, history),
        )
        if validation["accepted"]:
            _ma_llm_ms = (_time.perf_counter() - _ma_t2) * 1000
            print(f"  make_answer: template={_ma_template_ms:.0f}ms grounding={_ma_grounding_ms:.0f}ms llm={_ma_llm_ms:.0f}ms (enhanced)", file=_sys.stderr, flush=True)
            return enhanced, True
    _ma_llm_ms = (_time.perf_counter() - _ma_t2) * 1000
    print(f"  make_answer: template={_ma_template_ms:.0f}ms grounding={_ma_grounding_ms:.0f}ms llm={_ma_llm_ms:.0f}ms (fallback)", file=_sys.stderr, flush=True)
    return template, False


def answer_payload_stream(
    query: str,
    limit: int = 4,
    history: list | None = None,
    *,
    allow_llm: bool = True,
    session_id: str = "",
    plugin_session_id: str = "",
    correlation_id: str = "",
):
    turn_id = str(uuid.uuid4())[:8]
    for event in _answer_payload_stream(
        query, limit, history, allow_llm=allow_llm, session_id=session_id, turn_id=turn_id,
        plugin_session_id=plugin_session_id, correlation_id=correlation_id,
    ):
        if event.get("event") == "metadata" and isinstance(event.get("data"), dict):
            event["data"]["turn_id"] = turn_id
        yield event


def _resolve_results_with_topic_lock(
    query: str,
    history: list | None,
    limit: int,
    chunks: list,
    terms: dict,
    session_id: str,
) -> tuple[list[tuple[float, dict]], bool, str, str, bool]:
    use_history = should_use_history(query, history)
    search_query = search_query_with_history(query, history)
    relevance_query = search_query if use_history else query

    results = None
    reused = False
    if use_history and session_id:
        try:
            state = _load_session(session_id=session_id)
            cached_results = state.get("last_retrieved_results")
            if cached_results:
                results = []
                for item in cached_results:
                    if isinstance(item, (list, tuple)) and len(item) == 2:
                        results.append((float(item[0]), item[1]))
                reused = True
        except Exception:
            # Non-fatal: results stays None and a fresh search() runs below,
            # so this can't produce a wrong answer -- but a cache-read
            # failure here is still unexpected and worth surfacing.
            logging.getLogger("kenn.core.chat_answer").warning(
                "Cached retrieval-results reuse failed; falling back to a "
                "fresh search", exc_info=True,
            )

    if results is None:
        results = search(search_query, chunks, terms, limit=max(limit, 16))

    results = constrain_results_for_query(relevance_query, results)
    return results, use_history, relevance_query, search_query, reused


def compact_history(history: list | None, limit: int = 8) -> list | None:
    """Compact long conversation history list using the LLM to prevent prompt bloat.

    Older turns are summarized into a single technical context paragraph, which
    replaces them. The most recent turns remain untouched.
    """
    if not history or len(history) <= limit:
        return history

    try:
        older_turns = history[:-4]
        recent_turns = history[-4:]

        summary_prompt = (
            "Analyze the following conversation turns between a user (Jack) and an audio assistant (KENN).\n"
            "Create a single-paragraph summary of the technical context, mixing details, tracks mentioned, "
            "and active decisions made so far. Keep the summary under 80 words and focus purely on mixing/DAW facts:\n\n"
        )
        for turn in older_turns:
            role = "Jack" if turn.get("role") == "user" else "KENN"
            content = turn.get("content") or turn.get("text") or ""
            summary_prompt += f"{role}: {content}\n"

        from audio_too.model_runtime import DEFAULT_LLM
        res = DEFAULT_LLM.generate(
            [{"role": "user", "content": summary_prompt}],
            timeout=10,
            json_mode=False
        )
        summary = res.content.strip()

        compacted = [
            {"role": "user", "content": f"[Prior context summary: {summary}]"},
            *recent_turns
        ]
        return compacted
    except Exception as e:
        print(f"WARNING: compact_history failed: {e}")
        return history


def _answer_payload_stream_raw(
    query: str,
    limit: int = 4,
    history: list | None = None,
    *,
    allow_llm: bool = True,
    session_id: str = "",
    turn_id: str = "",
    plugin_session_id: str = "",
    correlation_id: str = "",
):
    history = compact_history(history)
    conversational = conversational_payload(query, history)
    if conversational:
        yield {"event": "metadata", "data": conversational}
        yield {"event": "token", "token": conversational["answer"]}
        return

    orchestration = get_orchestrator().dispatch(
        query, correlation_id=correlation_id, session_id=session_id,
        plugin_session_id=plugin_session_id,
    )
    if orchestration:
        ans = orchestration["message"]
        # Append action links if the sub-agent returned one
        if orchestration.get("action"):
            label = orchestration.get("action_label", "Go")
            ans += f"\n\n[{label}](action:{orchestration['action']})"
        yield {
            "event": "metadata",
            "data": {
                "question": query,
                "answer": ans,
                "sources": orchestration.get("sources") or [],
                "found": True,
                "confidence": "high",
                "source_quality": "high",
                "topics": [orchestration.get("agent_name", "orchestration")],
                "intent": "orchestration",
                "route": orchestration.get("agent_name", "orchestration"),
                "intent_guard": "passed",
                "weak_match": False,
                "search_query": query,
                "diagnostic_reason": f"Orchestrator dispatched to {orchestration.get('agent_name')}.",
                "answer_self_check": {"passed": True},
                "related_questions": [],
                "used_history": False,
                "llm_enhanced": False,
                "llm_available": False,
                "orchestration": orchestration,
                # G6 (docs/KENN_IMPROVEMENT_PLAN.md): the mix-review
                # ⚠️ badge only ever reached this key for mix-review-
                # followup answers -- an orchestrated result (e.g. an
                # arrangement suggestion) had no path to set it at all,
                # even when the sub-agent's own dispatch_fn flagged
                # itself as an unvalidated suggestion (see
                # _dispatch_arrangement's return dict).
                "contains_unvalidated_suggestions": bool(
                    orchestration.get("contains_unvalidated_suggestions")
                ),
            }
        }
        yield {"event": "token", "token": ans}
        return

    if query_is_out_of_scope(query):
        out = {
            "question": query,
            "answer": weak_match_answer(query),
            "sources": [],
            "found": False,
            "confidence": "low",
            "source_quality": "low",
            "topics": [],
            "intent": "out_of_scope",
            "route": "out_of_scope",
            "intent_guard": "not_needed",
            "weak_match": True,
            "search_query": query,
            "diagnostic_reason": "Query contains an out-of-scope term, so retrieval was skipped.",
            "answer_self_check": {
                "passed": True,
                "warnings": ["retrieval skipped by route"],
                "sections": {
                    "short_answer": True,
                    "try_this": True,
                    "check": False,
                    "sources": True,
                },
                "source_topic_match": False,
                "answered_intent": True,
            },
            "grounding": {
                "score": 0,
                "top_source_trust": 0.0,
                "approved_note": False,
                "source_topic_match": False,
                "answered_intent": True,
                "route_known": True,
                "warnings": ["retrieval skipped by route"],
            },
            "grounding_mode": "weak",
            "answer_quality": {
                "score": 0,
                "mode": "quick_fix",
                "warnings": [],
                "sections": {
                    "short_answer": True,
                    "try_this": True,
                    "sources": True,
                    "check": False,
                },
                "actionable_steps": 3,
            },
            "related_questions": [],
            "used_history": False,
            "llm_enhanced": False,
            "llm_available": False,
            "conversation_only": True,
            "branches": [],
            "session": None,
        }
        yield {"event": "metadata", "data": out}
        yield {"event": "token", "token": out["answer"]}
        return

    explicit_game_audio = bool(set(query_topics(query)) & GAME_ROUTE_TOPICS)
    generation = None if explicit_game_audio else audio_generation_payload(query, session_id=session_id)
    if generation:
        yield {"event": "metadata", "data": generation}
        yield {"event": "token", "token": generation["answer"]}
        return
    guarded = (
        impossible_promise_payload(query, history, answer_mode=answer_mode) if impossible_promise_query(query) else None
    )
    if guarded:
        yield {"event": "metadata", "data": guarded}
        yield {"event": "token", "token": guarded["answer"]}
        return

    explicit_timeline_terms = {"timeline", "history", "evolution", "evolved"}
    skip_timeline_for_active_review = latest_mix_review_context(history) and not (
        set(tokenize(query.lower())) & explicit_timeline_terms
    )
    timeline_res = (
        None
        if (explicit_game_audio or skip_timeline_for_active_review)
        else mix_review_timeline_lookup(query)
    )
    if timeline_res:
        title, timeline = timeline_res
        timeline_context = format_timeline_report(title, timeline)
        route = "mix_review"
    else:
        timeline_context = None
        route = route_query(query, history)
    if route != "game_audio" and not timeline_context and not latest_mix_review_context(history):
        track_memory = latest_track_memory_lookup(query)
        if track_memory:
            memory_context = format_track_memory(track_memory)
            history = [*(history or []), {"role": "user", "content": memory_context}]
            if route == "unknown" or normalized_terms(query) & MIX_REVIEW_FOLLOWUP_TERMS:
                route = "mix_review_followup"

    # A Mix Review follow-up is useful for report-navigation questions, but a
    # clear symptom still needs causal diagnosis.  Previously this early
    # return swallowed questions such as “why is my mix darker than my
    # reference?” before the typed-review evidence could be considered.
    if route == "mix_review_followup" and not timeline_context and diagnostic_plan_for(query) is None and not _is_diagnostic_result_report(query, session_id):
        followup = mix_review_followup_payload(query, history)
        if followup:
            yield {"event": "metadata", "data": followup}
            yield {"event": "token", "token": followup["answer"]}
            return

    # A clear symptom plan is already the clarification KENN needs: it
    # contains ranked hypotheses and asks one discriminating question.  Do
    # not replace it with the generic intake form merely because routing
    # lacks an exact topic keyword (e.g. "my drums lack punch").
    has_diagnostic_plan = diagnostic_plan_for(query) is not None or _is_diagnostic_result_report(query, session_id)
    if route == "clarify" and not timeline_context and not has_diagnostic_plan:
        clarify = clarification_payload(query, history, answer_mode=answer_mode)
        yield {"event": "metadata", "data": clarify}
        yield {"event": "token", "token": clarify["answer"]}
        return

    if (route == "out_of_scope" or query_is_out_of_scope(query)) and not timeline_context:
        out = {
            "question": query,
            "answer": weak_match_answer(query, answer_mode=answer_mode),
            "sources": [],
            "found": False,
            "confidence": "low",
            "source_quality": "low",
            "topics": [],
            "intent": "out_of_scope",
            "route": "out_of_scope",
            "intent_guard": "not_needed",
            "weak_match": True,
            "search_query": query,
            "diagnostic_reason": "Query contains an out-of-scope term, so retrieval was skipped.",
            "answer_self_check": {
                "passed": True,
                "warnings": ["retrieval skipped by route"],
                "sections": {
                    "short_answer": True,
                    "try_this": True,
                    "check": False,
                    "sources": True,
                },
                "source_topic_match": False,
                "answered_intent": True,
            },
            "grounding": {
                "score": 0,
                "top_source_trust": 0.0,
                "approved_note": False,
                "source_topic_match": False,
                "answered_intent": True,
                "route_known": True,
                "warnings": ["retrieval skipped by route"],
            },
            "grounding_mode": "weak",
            "related_questions": [],
            "used_history": False,
            "llm_enhanced": False,
            "llm_available": llm_enabled(),
            "conversation_only": False,
            "branches": [],
            "session": None,
        }
        yield {"event": "metadata", "data": out}
        yield {"event": "token", "token": out["answer"]}
        return

    chunks = load_chunks()
    terms = load_terms()
    results, use_history, relevance_query, search_query, reused = _resolve_results_with_topic_lock(
        query, history, limit, chunks, terms, session_id
    )
    results = _prefer_general_framework_for_uncovered_hardware(query, results)
    answer_mode = classify_answer_mode(relevance_query, route, history=history)

    if timeline_context:
        virtual_chunk = {
            "source": "mix_review_database",
            "page": 1,
            "kind": "note",
            "title": "Mix Review History",
            "text": "Status: Approved\n\nTags: mix_review\n\n" + timeline_context,
        }
        results = [(20.0, virtual_chunk)] + list(results)

    weak_match = (
        results_are_weak(relevance_query, results) or intent_guard_failed(relevance_query, results)
    ) and not timeline_context
    sections = note_sections(relevance_query, results)

    template = build_template_answer(
        relevance_query,
        results,
        history=history,
        route=route,
        timeline_context=timeline_context,
        answer_mode=answer_mode,
        session_id=session_id,
    )
    if timeline_context:
        template = timeline_context + "\n\n" + template

    confidence = "high" if timeline_context else confidence_level(relevance_query, results)
    grounding = grounding_report(
        relevance_query,
        results,
        template,
        route=route,
        confidence=confidence,
        timeline_context=timeline_context,
    )
    mode = grounding_mode(grounding)
    quality = answer_quality_report(
        relevance_query,
        results,
        template,
        route=route,
        confidence=confidence,
        answer_mode=answer_mode,
        grounding=grounding,
        timeline_context=timeline_context,
    )

    if (
        not weak_match
        and (mode == "weak" or quality["score"] < ANSWER_QUALITY_MIN_SCORE)
        and not timeline_context
        # A deterministic symptom plan is a deliberately grounded answer in
        # its own right: its hypotheses, tests, uncertainty boundary, and
        # verification do not depend on an accidentally weak retrieval hit.
        # Do not replace it with unrelated starter questions.
        and diagnostic_plan_for(query) is None
        and not _is_diagnostic_result_report(query, session_id)
    ):
        weak_match = True
        confidence = "low"
        grounding = {
            **grounding,
            "warnings": [
                *grounding.get("warnings", []),
                "grounding below answer threshold"
                if mode == "weak"
                else "answer quality below threshold",
            ],
        }
        quality = {
            **quality,
            "warnings": [*quality.get("warnings", []), "answer withheld by quality gate"],
        }

    if weak_match:
        answer = weak_match_answer(query)
        followups = starter_questions(limit=2)
        metadata = {
            "question": query,
            "answer": answer,
            "sources": [],
            "found": False,
            "confidence": confidence,
            "source_quality": "low",
            "topics": query_topics(relevance_query),
            "intent": detect_intent(query),
            "route": route,
            "answer_mode": answer_mode,
            "answer_quality": quality,
            "intent_guard": intent_guard_status(relevance_query, results),
            "weak_match": True,
            "search_query": search_query,
            "diagnostic_reason": (
                "Answer quality was below threshold, so KENN avoided showing a weak answer."
                if "answer quality below threshold" in grounding.get("warnings", [])
                else "Grounding score was too low, so KENN avoided answering from weak local evidence."
                if "grounding below answer threshold" in grounding.get("warnings", [])
                else diagnostic_reason(query, results, True)
            ),
            "answer_self_check": answer_self_check(
                relevance_query,
                results,
                answer,
                route=route,
                confidence=confidence,
                timeline_context=timeline_context,
            ),
            "grounding": grounding,
            "grounding_mode": grounding_mode(grounding),
            "related_questions": followups,
            "used_history": use_history,
            "llm_enhanced": False,
            "llm_available": llm_enabled(),
            "conversation_only": False,
            "branches": [],
            "session": None,
        }
        yield {"event": "metadata", "data": metadata}
        yield {"event": "token", "token": answer}
        return

    followups = suggested_followups(
        relevance_query,
        list(sections.get("related") or []),
        query_topics(relevance_query),
        history if use_history else None,
        results=results,
    )

    llm_active = (
        llm_enabled()
        and allow_llm
        and should_use_llm_rewrite(query, route, confidence, grounding, quality, answer_mode)
    )

    final_answer = template
    llm_usage = None
    generation_validation = {
        "attempted": False,
        "accepted": False,
        "warnings": [],
        "unsupported_measurements": [],
        "evidence_overlap": 0.0,
    }

    initial_metadata = {
        "question": query,
        "answer": "",
        "sources": result_payload(query, results),
        "found": True,
        "confidence": confidence,
        "source_quality": source_quality_level(relevance_query, results),
        "topics": query_topics(relevance_query),
        "intent": detect_intent(query),
        "route": route,
        "answer_mode": answer_mode,
        "answer_quality": quality,
        "intent_guard": intent_guard_status(relevance_query, results),
        "weak_match": False,
        "search_query": search_query,
        "diagnostic_reason": "Timeline report retrieved from Mix Review Lab database."
        if timeline_context
        else diagnostic_reason(query, results, False),
        "answer_self_check": answer_self_check(
            relevance_query,
            results,
            "",
            route=route,
            confidence=confidence,
            timeline_context=timeline_context,
        ),
        "grounding": grounding,
        "grounding_mode": mode,
        "related_questions": followups,
        "used_history": use_history,
        "llm_enhanced": llm_active,
        "llm_available": llm_enabled(),
        "llm_usage": None,
        "generation_validation": generation_validation,
        "conversation_only": False,
        "branches": _branches_payload(answer_mode, ""),
    }

    yield {"event": "metadata", "data": initial_metadata}

    if llm_active:
        generator = llm_enhance_answer_stream(
            query,
            template,
            results,
            history,
            history_context_line(query, history),
            source_label,
            normalize_history,
            answer_mode=answer_mode,
            route=route,
            timeline_context=timeline_context,
            skill_level=_skill_level_for_session(session_id),
        )
        generated_parts = []
        for event in generator:
            if event["event"] == "token":
                token = event.get("token") or ""
                generated_parts.append(token)
            elif event["event"] == "llm_usage":
                llm_usage = event.get("data")
        candidate = "".join(generated_parts).strip()
        if candidate:
            validation = generated_answer_validation(
                relevance_query,
                results,
                candidate,
                route=route,
                confidence=confidence,
                answer_mode=answer_mode,
                timeline_context=timeline_context,
                additional_evidence_text=_specialist_evidence_context(relevance_query, history),
            )
            generation_validation = {
                "attempted": True,
                "accepted": bool(validation["accepted"]),
                "warnings": list(validation["warnings"]),
                "unsupported_measurements": list(
                    validation["unsupported_measurements"]
                ),
                "evidence_overlap": validation["evidence_overlap"],
            }
            if validation["accepted"]:
                final_answer = calibrate_answer_for_grounding(
                    candidate, validation["grounding"]
                )
                grounding = validation["grounding"]
                quality = validation["quality"]
                mode = grounding_mode(grounding)
                for section_event in _progressive_token_yield(
                    final_answer, answer_mode, route
                ):
                    yield section_event
            else:
                final_answer = template
                for section_event in _progressive_token_yield(
                    template, answer_mode, route
                ):
                    yield section_event
                llm_active = False
        else:
            generation_validation = {
                **generation_validation,
                "attempted": True,
                "warnings": ["generation returned no answer"],
            }
            yield {"event": "token", "token": template}
            final_answer = template
            llm_active = False

        # Yield updated final metadata
        final_metadata = {
            **initial_metadata,
            "answer": final_answer,
            "llm_enhanced": llm_active,
            "llm_usage": llm_usage,
            "generation_validation": generation_validation,
            "grounding": grounding,
            "grounding_mode": mode,
            "answer_quality": quality,
            "branches": _branches_payload(answer_mode, final_answer),
        }
        confidence = _critique_and_save_trace(
            query=query,
            final_answer=final_answer,
            results=results,
            route=route,
            confidence=confidence,
            tags=query_topics(query),
            turn_id=turn_id,
            metadata_payload=final_metadata,
            weak_match=weak_match,
        )
        final_metadata["answer_self_check"] = answer_self_check(
            relevance_query,
            results,
            final_answer,
            route=route,
            confidence=confidence,
            timeline_context=timeline_context,
        )
        yield {"event": "metadata", "data": final_metadata}
        if llm_usage:
            yield {"event": "llm_usage", "data": llm_usage}
    else:
        for section_event in _progressive_token_yield(template, answer_mode, route):
            yield section_event
        final_answer = template
        final_metadata = {
            **initial_metadata,
            "answer": template,
            "branches": _branches_payload(answer_mode, template),
            "grounding": grounding,
            "answer_quality": quality,
        }
        confidence = _critique_and_save_trace(
            query=query,
            final_answer=template,
            results=results,
            route=route,
            confidence=confidence,
            tags=query_topics(query),
            turn_id=turn_id,
            metadata_payload=final_metadata,
            weak_match=weak_match,
        )
        final_metadata["answer_self_check"] = answer_self_check(
            relevance_query,
            results,
            template,
            route=route,
            confidence=confidence,
            timeline_context=timeline_context,
        )
        yield {"event": "metadata", "data": final_metadata}

    # Update session memory after streaming completes
    _update_session(
        query, final_answer,
        route=route,
        answer_mode=answer_mode,
        confidence=confidence,
        intent=detect_intent(query),
        session_id=session_id,
        retrieved_results=results,
    )

    yield {"event": "session", "data": _session_info(session_id=session_id)}


def _answer_payload_stream(
    query: str,
    limit: int = 4,
    history: list | None = None,
    *,
    allow_llm: bool = True,
    session_id: str = "",
    turn_id: str = "",
    plugin_session_id: str = "",
    correlation_id: str = "",
):
    # Cached answers are valid only for stateless turns.  A session can carry
    # measured evidence and reported troubleshooting outcomes, both of which
    # materially change the next answer and must never be bypassed by a
    # generic cached response.
    if allow_llm and not history and not session_id:
        try:
            from kenn.core.session_memory import get_semantic_cache_hit
            cached_events = get_semantic_cache_hit(query)
            if cached_events:
                for event in cached_events:
                    if event.get("event") == "metadata" and isinstance(event.get("data"), dict):
                        event["data"]["semantic_cache_hit"] = True
                    yield event
                return
        except Exception:
            # Non-fatal: falls through to a fresh generator run below, so
            # this can't produce a wrong answer -- logged for cache-hit-rate
            # visibility.
            logging.getLogger("kenn.core.chat_answer").warning(
                "Semantic cache lookup failed; generating a fresh answer",
                exc_info=True,
            )

    generator = _answer_payload_stream_raw(
        query, limit, history, allow_llm=allow_llm, session_id=session_id, turn_id=turn_id,
        plugin_session_id=plugin_session_id, correlation_id=correlation_id,
    )

    accumulated_events = []
    for event in generator:
        accumulated_events.append(event)
        yield event

    if allow_llm and not history and not session_id and accumulated_events:
        final_metadata = None
        for ev in reversed(accumulated_events):
            if ev.get("event") == "metadata":
                final_metadata = ev.get("data")
                break

        if final_metadata and (final_metadata.get("llm_enhanced") or final_metadata.get("confidence") == "high"):
            try:
                from kenn.core.session_memory import save_to_semantic_cache
                save_to_semantic_cache(query, accumulated_events)
            except Exception:
                logging.getLogger("kenn.core.chat_answer").warning(
                    "Semantic cache save failed; this answer won't be "
                    "served from cache next time", exc_info=True,
                )


def answer_payload(
    query: str,
    limit: int = 4,
    history: list | None = None,
    *,
    allow_llm: bool = True,
    profile: bool = False,
    session_id: str = "",
    plugin_session_id: str = "",
    answer_mode: str = "",
    correlation_id: str = "",
) -> dict:
    turn_id = str(uuid.uuid4())[:8]
    payload = _answer_payload(
        query,
        limit,
        history,
        allow_llm=allow_llm,
        profile=profile,
        session_id=session_id,
        plugin_session_id=plugin_session_id,
        turn_id=turn_id,
        answer_mode=answer_mode,
        correlation_id=correlation_id,
    )
    if isinstance(payload, dict):
        payload["turn_id"] = turn_id
    return payload


def _answer_payload_raw(
    query: str,
    limit: int = 4,
    history: list | None = None,
    *,
    allow_llm: bool = True,
    profile: bool = False,
    session_id: str = "",
    turn_id: str = "",
    plugin_session_id: str = "",
    answer_mode: str = "",
    correlation_id: str = "",
) -> dict:
    history = compact_history(history)
    conversational = conversational_payload(query, history)
    if conversational:
        return conversational

    import inspect

    # Matching bare function names ("handle", "dispatch") false-positived
    # on http.server.BaseHTTPRequestHandler.handle() -- a stdlib frame
    # named "handle" that's on the call stack of every single real HTTP
    # request through server.py, not just the intended re-entrant case.
    # That silently forced orchestration to None for virtually all
    # production traffic (KENN's action dispatch -- Ableton control,
    # arrangement suggestions, everything routed through the
    # orchestrator -- stopped firing) while every test still passed,
    # since tests call answer_payload() directly and never put a stdlib
    # "handle" frame on the stack. Scoped to the specific (module,
    # function) pairs this guard actually means to catch.
    _REENTRANT_ORCHESTRATOR_FRAMES = {
        ("kenn.orchestrator", "dispatch"),
        ("thursday.orchestrator", "handle"),
        ("thursday.registry.handlers", "_handle_client_info"),
    }
    in_orchestrator = any(
        (f.frame.f_globals.get("__name__"), f.function) in _REENTRANT_ORCHESTRATOR_FRAMES
        for f in inspect.stack()[:15]
    )
    orchestration = None if in_orchestrator else get_orchestrator().dispatch(
        query, correlation_id=correlation_id, session_id=session_id,
        plugin_session_id=plugin_session_id,
    )
    if orchestration:
        ans = orchestration["message"]
        if orchestration.get("action"):
            label = orchestration.get("action_label", "Go")
            ans += f"\n\n[{label}](action:{orchestration['action']})"
        ret_payload = {
            "question": query,
            "answer": ans,
            "sources": orchestration.get("sources") or [],
            "found": True,
            "confidence": "high",
            "source_quality": "high",
            "topics": [orchestration.get("agent_name", "orchestration")],
            "intent": "orchestration",
            "route": orchestration.get("agent_name", "orchestration"),
            "intent_guard": "passed",
            "weak_match": False,
            "search_query": query,
            "diagnostic_reason": f"Orchestrator dispatched to {orchestration.get('agent_name')}.",
            "answer_self_check": {"passed": True},
            "related_questions": [],
            "used_history": False,
            "llm_enhanced": False,
            "llm_available": False,
            "orchestration": orchestration,
            "contains_unvalidated_suggestions": bool(
                orchestration.get("contains_unvalidated_suggestions")
            ),
        }
        if orchestration.get("proposal"):
            ret_payload["proposal"] = orchestration["proposal"]
            ret_payload["confirmation_token"] = orchestration.get("confirmation_token", "")
            ret_payload["requires_confirmation"] = bool(orchestration.get("requires_confirmation", True))
            for k in ("is_rack_synthesis", "is_doctor_remediation", "is_midi_proposal", "variations", "predicted_metrics"):
                if k in orchestration:
                    ret_payload[k] = orchestration[k]
        return ret_payload

    explicit_game_audio = bool(set(query_topics(query)) & GAME_ROUTE_TOPICS)
    generation = (
        None
        if (explicit_game_audio or query_is_out_of_scope(query))
        else audio_generation_payload(query, session_id=session_id)
    )
    if generation:
        return generation

    # Pre-calculate mode for fallbacks/guards
    mode = answer_mode or classify_answer_mode(query, "unknown", history=history)
    guarded = (
        impossible_promise_payload(query, history, answer_mode=mode) if impossible_promise_query(query) else None
    )
    if guarded:
        return guarded

    explicit_timeline_terms = {"timeline", "history", "evolution", "evolved"}
    skip_timeline_for_active_review = latest_mix_review_context(history) and not (
        set(tokenize(query.lower())) & explicit_timeline_terms
    )
    timeline_res = (
        None
        if (explicit_game_audio or skip_timeline_for_active_review)
        else mix_review_timeline_lookup(query)
    )
    if timeline_res:
        title, timeline = timeline_res
        timeline_context = format_timeline_report(title, timeline)
        route = "mix_review"
    else:
        timeline_context = None
        route = route_query(query, history)
    if route != "game_audio" and not timeline_context and not latest_mix_review_context(history):
        track_memory = latest_track_memory_lookup(query)
        if track_memory:
            memory_context = format_track_memory(track_memory)
            history = [*(history or []), {"role": "user", "content": memory_context}]
            if route == "unknown" or normalized_terms(query) & MIX_REVIEW_FOLLOWUP_TERMS:
                route = "mix_review_followup"

    if route == "mix_review_followup" and not timeline_context and diagnostic_plan_for(query) is None and not _is_diagnostic_result_report(query, session_id):
        followup = mix_review_followup_payload(query, history)
        if followup:
            return followup

    effective_mode = answer_mode or classify_answer_mode(query, route, history=history)
    # Keep the non-streaming path behaviour identical to the streaming path.
    # See the equivalent guard above for why a symptom plan takes precedence.
    has_diagnostic_plan = diagnostic_plan_for(query) is not None or _is_diagnostic_result_report(query, session_id)
    if route == "clarify" and not timeline_context and not has_diagnostic_plan:
        return clarification_payload(query, history, answer_mode=effective_mode)

    if (route == "out_of_scope" or query_is_out_of_scope(query)) and not timeline_context:
        answer = weak_match_answer(query, answer_mode=effective_mode)
        return {
            "question": query,
            "answer": answer,
            "sources": [],
            "found": False,
            "confidence": "low",
            "source_quality": "low",
            "topics": [],
            "intent": "out_of_scope",
            "route": "out_of_scope",
            "intent_guard": "not_needed",
            "weak_match": True,
            "search_query": query,
            "diagnostic_reason": "Query contains an out-of-scope term, so retrieval was skipped.",
            "answer_self_check": {
                "passed": True,
                "warnings": ["retrieval skipped by route"],
                "sections": {
                    "short_answer": True,
                    "try_this": True,
                    "check": False,
                    "sources": True,
                },
                "source_topic_match": False,
                "answered_intent": True,
            },
            "grounding": {
                "score": 0,
                "top_source_trust": 0.0,
                "approved_note": False,
                "source_topic_match": False,
                "answered_intent": True,
                "route_known": True,
                "warnings": ["retrieval skipped by route"],
            },
            "grounding_mode": "weak",
            "related_questions": [],
            "used_history": False,
            "llm_enhanced": False,
            "llm_available": llm_enabled(),
            "conversation_only": False,
            "branches": [],
            **(
                {
                    "timings_ms": {
                        "load_index_ms": 0.0,
                        "search_ms": 0.0,
                        "section_ms": 0.0,
                        "answer_ms": 0.0,
                        "metadata_ms": 0.0,
                        "total_profiled_ms": 0.0,
                    },
                    "index_cache": {
                        "chunks": load_chunks.cache_info()._asdict(),
                        "terms": load_terms.cache_info()._asdict(),
                    },
                }
                if profile
                else {}
            ),
        }

    timings: dict[str, float] = {}
    started = time.perf_counter()
    chunks = load_chunks()
    terms = load_terms()
    timings["load_index_ms"] = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    results, use_history, relevance_query, search_query, reused = _resolve_results_with_topic_lock(
        query, history, limit, chunks, terms, session_id
    )
    results = _prefer_general_framework_for_uncovered_hardware(query, results)
    timings["search_ms"] = (time.perf_counter() - started) * 1000
    # Found live-testing 2026-08-02: this used to unconditionally recompute
    # answer_mode, discarding whatever the caller explicitly passed in (e.g.
    # answer_mode="voice") -- so an explicit mode request silently reverted
    # to auto-classification for any query with real search results (every
    # path except the early clarify/out_of_scope returns above, which
    # already correctly do `answer_mode or classify_answer_mode(...)` as
    # effective_mode). No current caller passes answer_mode through to this
    # function yet, but the parameter exists specifically so one can -- this
    # would have silently broken that the moment it was wired up.
    answer_mode = answer_mode or classify_answer_mode(relevance_query, route, history=history)

    if timeline_context:
        virtual_chunk = {
            "source": "mix_review_database",
            "page": 1,
            "kind": "note",
            "title": "Mix Review History",
            "text": "Status: Approved\n\nTags: mix_review\n\n" + timeline_context,
        }
        results = [(20.0, virtual_chunk)] + list(results)

    weak_match = (
        results_are_weak(relevance_query, results) or intent_guard_failed(relevance_query, results)
    ) and not timeline_context

    started = time.perf_counter()
    sections = note_sections(relevance_query, results)
    timings["section_ms"] = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    answer, llm_used = make_answer(
        relevance_query,
        results,
        history=history,
        allow_llm=allow_llm,
        route=route,
        timeline_context=timeline_context,
        answer_mode=answer_mode,
        session_id=session_id,
    )
    timings["answer_ms"] = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    confidence = "high" if timeline_context else confidence_level(relevance_query, results)
    grounding = grounding_report(
        relevance_query,
        results,
        answer,
        route=route,
        confidence=confidence,
        timeline_context=timeline_context,
    )
    mode = grounding_mode(grounding)
    quality = answer_quality_report(
        relevance_query,
        results,
        answer,
        route=route,
        confidence=confidence,
        answer_mode=answer_mode,
        grounding=grounding,
        timeline_context=timeline_context,
    )
    if (
        not weak_match
        and (mode == "weak" or quality["score"] < ANSWER_QUALITY_MIN_SCORE)
        and not timeline_context
        and diagnostic_plan_for(query) is None
        and not _is_diagnostic_result_report(query, session_id)
    ):
        # Found live-testing 2026-08-02, same day as the answer_mode-
        # discarding bug just above: this retroactive downgrade (a real
        # answer turned out poorly grounded/low quality after the fact) is a
        # third, separate call to weak_match_answer() that simply never
        # passed answer_mode through at all -- every other call site in this
        # file does. Silently reverted an explicit voice-mode request back
        # to the full written template for any answer that fails this
        # after-the-fact quality check.
        answer = weak_match_answer(query, answer_mode=answer_mode)
        weak_match = True
        confidence = "low"
        grounding = {
            **grounding,
            "warnings": [
                *grounding.get("warnings", []),
                "grounding below answer threshold"
                if mode == "weak"
                else "answer quality below threshold",
            ],
        }
        quality = {
            **quality,
            "warnings": [*quality.get("warnings", []), "answer withheld by quality gate"],
        }
    elif not weak_match and not timeline_context:
        answer = calibrate_answer_for_grounding(answer, grounding)
        quality = answer_quality_report(
            query,
            results,
            answer,
            route=route,
            confidence=confidence,
            answer_mode=answer_mode,
            grounding=grounding,
            timeline_context=timeline_context,
        )
    self_check = answer_self_check(
        relevance_query,
        results,
        answer,
        route=route,
        confidence=confidence,
        timeline_context=timeline_context,
    )
    if weak_match:
        followups = [] if query_is_out_of_scope(query) else starter_questions(limit=2)
    else:
        followups = suggested_followups(
            relevance_query,
            list(sections.get("related") or []),
            query_topics(relevance_query),
            history if use_history else None,
            results=results,
        )
    if llm_used and confidence in {"high", "medium"}:
        followups = merge_followups(parse_followups_from_answer(answer), followups)
    timings["metadata_ms"] = (time.perf_counter() - started) * 1000
    payload = {
        "question": query,
        "answer": answer,
        "sources": [] if weak_match else result_payload(query, results),
        "found": bool(results) and not weak_match,
        "confidence": confidence,
        "source_quality": "low" if weak_match else source_quality_level(relevance_query, results),
        "topics": query_topics(relevance_query),
        "intent": detect_intent(query),
        "route": route,
        "answer_mode": answer_mode,
        "answer_quality": quality,
        "intent_guard": intent_guard_status(relevance_query, results),
        "weak_match": weak_match,
        "search_query": search_query,
        "diagnostic_reason": (
            "Timeline report retrieved from Mix Review Lab database."
            if timeline_context
            else (
                "Grounding score was too low, so KENN avoided answering from weak local evidence."
                if "grounding below answer threshold" in grounding.get("warnings", [])
                else "Answer quality was below threshold, so KENN avoided showing a weak answer."
                if "answer quality below threshold" in grounding.get("warnings", [])
                else diagnostic_reason(query, results, weak_match)
            )
        ),
        "answer_self_check": self_check,
        "grounding": grounding,
        "grounding_mode": grounding_mode(grounding),
        "related_questions": followups,
        "used_history": use_history,
        "llm_enhanced": llm_used,
        "llm_available": llm_enabled(),
        "llm_usage": llm_used and _get_llm_usage_stats(),
        "session": None,
    }
    timings["total_profiled_ms"] = sum(timings.values())
    payload["timings_ms"] = {key: round(value, 2) for key, value in timings.items()}
    if profile:
        payload["index_cache"] = {
            "chunks": load_chunks.cache_info()._asdict(),
            "terms": load_terms.cache_info()._asdict(),
        }

    # Add branches after payload construction (payload needs answer_key)
    payload["branches"] = _branches_payload(payload.get("answer_mode", ""), payload.get("answer", ""))

    # Add knowledge graph cross-links for concept browsing
    try:
        from kenn.core.knowledge_graph import cross_links_for_results
        if not weak_match and results:
            cross_links = cross_links_for_results(results, chunks, limit=3)
            payload["cross_links"] = [
                {"source": cl["source"], "shared_tags": cl["shared_tags"]}
                for cl in cross_links
            ]
        else:
            payload["cross_links"] = []
    except Exception:
        logging.getLogger("kenn.core.chat_answer").warning(
            "Knowledge-graph cross-links lookup failed; omitting cross_links "
            "from this answer", exc_info=True,
        )
        payload["cross_links"] = []

    # Update session memory after generating the payload
    _update_session(
        query,
        payload.get("answer", ""),
        route=payload.get("route", ""),
        answer_mode=payload.get("answer_mode", ""),
        confidence=payload.get("confidence", "medium"),
        intent=payload.get("intent", "general"),
        session_id=session_id,
        retrieved_results=results,
    )
    payload["session"] = _session_info(session_id=session_id)

    # Run self-critique, record citations, and save reasoning trace
    _critique_and_save_trace(
        query=query,
        final_answer=payload.get("answer", ""),
        results=results,
        route=payload.get("route", "unknown"),
        confidence=payload.get("confidence", "medium"),
        tags=query_topics(query),
        turn_id=turn_id,
        metadata_payload=payload,
        weak_match=weak_match,
    )

    return payload


def _short_circuit_evaluator(query: str, history: list | None = None, session_id: str = "") -> dict | None:
    """Instant sub-millisecond evaluator for status, simple transport, and one-word intents."""
    cleaned = query.strip().lower()
    if not cleaned:
        return None

    # Greetings
    if cleaned in {"hello", "hi", "hey", "good morning", "good afternoon", "good evening"}:
        return {
            "answer": "Hey there! Got a specific audio problem or track to review?",
            "route": "conversation",
            "confidence": "high",
            "sources": [],
            "suggestions": [
                "How do I sidechain bass to the kick?",
                "Audit session for clipping",
                "How do I saturate sub bass without distortion?",
                "What does freezing a track do?",
            ],
            "requires_confirmation": False,
        }

    # Status check
    if cleaned in {"status", "ping", "are you connected", "model status", "connection status"}:
        active_mb = 0
        try:
            from kenn.llm.mlx_inference_engine import MLXInferenceEngine
            if MLXInferenceEngine._instance is not None and MLXInferenceEngine._instance._loaded:
                stats = MLXInferenceEngine._instance.get_memory_stats()
                active_mb = stats.get("active_mb", 0)
        except Exception:
            pass
        return {
            "answer": f"KENN is fully online and operational. Engine: Apple Silicon Metal MLX (active: {active_mb}MB). OSC Bridge: port 11000/11001.",
            "route": "conversation",
            "confidence": "high",
            "sources": [],
            "suggestions": ["Mute vocal track", "Audit session for clipping", "What is the current tempo?"],
            "requires_confirmation": False,
        }

    # Cancel / Abort
    if cleaned in {"no", "n", "cancel", "abort", "reject", "stop action"}:
        return {
            "answer": "Cancelled. No changes were made to your Ableton session.",
            "route": "ableton",
            "confidence": "high",
            "sources": [],
            "suggestions": ["What tracks are in the project?", "Audit the mix"],
            "requires_confirmation": False,
        }

    # Simple Transport Play
    if cleaned in {"play", "start transport", "play session", "start playback"}:
        from kenn.core.live_action_service import LiveActionService
        service = LiveActionService()
        prop = service.propose_transport_action("transport_play", session_id=session_id)
        if prop.get("ok"):
            return {
                "answer": "Ready to start Ableton playback. Confirm to proceed.",
                "route": "ableton",
                "confidence": "high",
                "proposal": prop.get("proposal"),
                "confirmation_token": prop.get("confirmation_token", ""),
                "requires_confirmation": True,
                "sources": [],
            }
        return {
            "answer": "Ableton Live is not currently reachable on OSC port 11000. Ensure Ableton Live is running with KENN Bridge enabled.",
            "route": "ableton",
            "confidence": "high",
            "sources": [],
            "suggestions": ["Check status", "How do I setup Ableton OSC?"],
            "requires_confirmation": False,
        }

    # Simple Transport Stop
    if cleaned in {"stop", "stop transport", "pause", "pause playback", "stop playback"}:
        from kenn.core.live_action_service import LiveActionService
        service = LiveActionService()
        prop = service.propose_transport_action("transport_stop", session_id=session_id)
        if prop.get("ok"):
            return {
                "answer": "Ready to stop Ableton playback. Confirm to proceed.",
                "route": "ableton",
                "confidence": "high",
                "proposal": prop.get("proposal"),
                "confirmation_token": prop.get("confirmation_token", ""),
                "requires_confirmation": True,
                "sources": [],
            }
        return {
            "answer": "Ableton Live is not currently reachable on OSC port 11000. Ensure Ableton Live is running with KENN Bridge enabled.",
            "route": "ableton",
            "confidence": "high",
            "sources": [],
            "suggestions": ["Check status", "How do I setup Ableton OSC?"],
            "requires_confirmation": False,
        }

    return None


def _answer_payload(
    query: str,
    limit: int = 4,
    history: list | None = None,
    *,
    allow_llm: bool = True,
    profile: bool = False,
    session_id: str = "",
    turn_id: str = "",
    plugin_session_id: str = "",
    answer_mode: str = "",
    correlation_id: str = "",
) -> dict:
    # Instant fast-path for conversational greetings, thanks, check-ins (< 0.1 ms)
    conversational = conversational_payload(query, compact_history(history))
    if conversational:
        return conversational

    # Instant short-circuit router for status, aborts, and direct transport (< 0.1 ms)
    short_circuit = _short_circuit_evaluator(query, history=history, session_id=session_id)
    if short_circuit:
        return short_circuit

    if allow_llm and not history and not session_id:
        try:
            from kenn.core.session_memory import get_semantic_cache_hit
            cached_events = get_semantic_cache_hit(query)
            if cached_events:
                final_metadata = None
                for ev in reversed(cached_events):
                    if ev.get("event") == "metadata":
                        final_metadata = ev.get("data")
                        break
                if final_metadata:
                    res = dict(final_metadata)
                    res["semantic_cache_hit"] = True
                    return res
        except Exception:
            logging.getLogger("kenn.core.chat_answer").warning(
                "Semantic cache lookup failed; generating a fresh answer",
                exc_info=True,
            )

    payload = _answer_payload_raw(
        query,
        limit,
        history,
        allow_llm=allow_llm,
        profile=profile,
        session_id=session_id,
        plugin_session_id=plugin_session_id,
        turn_id=turn_id,
        answer_mode=answer_mode,
        correlation_id=correlation_id,
    )

    if allow_llm and not history and not session_id and isinstance(payload, dict):
        if payload.get("llm_enhanced") or payload.get("confidence") == "high":
            events = [
                {"event": "metadata", "data": payload},
                {"event": "token", "token": payload.get("answer", "")}
            ]
            try:
                from kenn.core.session_memory import save_to_semantic_cache
                save_to_semantic_cache(query, events)
            except Exception:
                logging.getLogger("kenn.core.chat_answer").warning(
                    "Semantic cache save failed; this answer won't be "
                    "served from cache next time", exc_info=True,
                )

    return payload



def _progressive_token_yield(
    template: str,
    answer_mode: str = "",
    route: str = "",
) -> Generator[dict, None, None]:
    """Yield answer sections with micro-pauses for progressive disclosure.

    Instead of dumping the full answer at once, this splits it into logical
    sections (opener, short answer, steps, check/avoid, why, sources, follow-ups)
    and yields them with intentional pauses. This gives the *feeling* of an AI
    building the answer, without any LLM cost.

    The pause duration is randomised slightly to feel more natural.
    """
    import random
    import time

    # Define section boundaries by heading markers
    sections = _split_answer_sections(template)

    # Yield each section immediately with zero artificial delay for sub-100ms streaming
    first = True
    for section in sections:
        if not section.strip():
            continue
        if first:
            yield {"event": "token", "token": section}
            first = False
        else:
            yield {"event": "token", "token": "\n" + section}


def _split_answer_sections(template: str) -> list[str]:
    """Split a KENN answer into logical display sections.

    Each section is a visually coherent block: opener, short answer,
    try this steps, check/avoid, why it matters, sources, follow-ups.
    """
    lines = template.splitlines()
    sections: list[str] = []
    current: list[str] = []

    section_markers = {
        # Intent-specific headings
        "Symptom and likely cause:",
        "Try this in your session:",
        "Here are the steps:",
        "Why this works:",
        "The reasoning:",
        "In practice:",
        "To apply this:",
        "The concept:",
        "Why it works:",
        "Try it:",
        # General headings
        "Short answer:",
        "In Ableton Live, the direct solution is:",
        "Based on the review criteria, here is the main recommendation:",
        "Here is the recommended production technique:",
        "To address your query directly:",
        "Here is the practical Ableton version.",
        "Here is the practical production version.",
        "Here is the practical version.",
        "Try this:",
        "Here are the concrete steps to follow:",
        "Follow these correction steps in your session:",
        "Here is the step-by-step setup in Live:",
        "Try this workflow in your next session:",
        "Sources:",
        "You could also ask:",
        "Avoid this:",
        "Avoid these common production mistakes:",
        "What to avoid while routing this device:",
        "Common pitfalls to avoid in this mix stage:",
        "Keep this in mind to avoid issues:",
        "Why it matters:",
        "Why this workflow works in Ableton:",
        "Here is the technical reasoning behind this:",
        "Why this balance matters for translation:",
        "Why this makes a difference in your mix:",
        "The technical reasoning behind these mastering levels:",
        "For the final master, here is the direct advice:",
    }

    for line in lines:
        stripped = line.strip()
        if stripped in section_markers and current:
            sections.append("\n".join(current))
            current = [line]
        else:
            current.append(line)

    if current:
        sections.append("\n".join(current))

    return sections if sections else [template]


def extract_conclusion_from_answer(answer: str) -> str:
    """Extract a concise conclusion from KENN's structured or unstructured answer."""
    import re
    match = re.search(r'(?:Short answer:|Short answer)\s*:\s*(.*?)(?:\n\n|\n[A-Z]|$)', answer, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    lines = [line.strip() for line in answer.split('\n') if line.strip()]
    if lines:
        first_line = lines[0]
        if first_line.startswith(("Symptom", "Here are", "Past reasoning", "You could", "Sources:")):
            if len(lines) > 1:
                return lines[1][:300]
        return first_line[:300]
    return ""


def _critique_and_save_trace(
    query: str,
    final_answer: str,
    results: list[tuple[float, dict]],
    route: str,
    confidence: str,
    tags: list[str],
    turn_id: str,
    metadata_payload: dict,
    weak_match: bool,
) -> str:
    """Helper to run self-critique, record citations, and save reasoning trace."""
    try:
        from kenn.knowledge import query_reasoning_traces, post_answer_critique, record_citation
        past_reasoning_traces = query_reasoning_traces(query)
        critique_result = post_answer_critique(
            query,
            final_answer,
            results,
            past_reasoning_traces,
            metadata_payload.get("answer_mode", "")
        )
        metadata_payload["critique"] = critique_result
        if not critique_result["passed"]:
            confidence = "low"
            metadata_payload["confidence"] = "low"
            # If warning field exists, add warnings
            g = metadata_payload.setdefault("grounding", {})
            warnings = g.setdefault("warnings", [])
            for w in critique_result["warnings"]:
                if w not in warnings:
                    warnings.append(w)


        # Record source citations to update dynamic trust scores
        if not weak_match:
            for _, chunk in (results or []):
                if chunk.get("source"):
                    record_citation(chunk["source"])
    except Exception as e:
        import logging
        logging.getLogger("kenn.core.chat_answer").warning(f"Self-critique / trust score processing failed: {e}")

    try:
        from kenn.knowledge import save_reasoning_trace, get_chunk_id
        ev_ids = [get_chunk_id(chunk) for _, chunk in (results or [])]
        conclusion = extract_conclusion_from_answer(final_answer)
        save_reasoning_trace(
            query=query,
            route=route,
            evidence_ids=ev_ids,
            conclusion=conclusion,
            confidence=confidence,
            tags=tags,
            trace_id=turn_id,
        )
    except Exception as e:
        import logging
        logging.getLogger("kenn.core.chat_answer").warning(f"Failed to save reasoning trace: {e}")

    return confidence
