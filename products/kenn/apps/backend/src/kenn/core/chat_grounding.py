from __future__ import annotations

import re


from kenn.retrieval.retrieval import (
    chunk_topics,
    query_topics,
    source_trust_score,
)

from kenn.core.chat_constants import (
    ANSWER_QUALITY_MIN_SCORE,
    ANSWER_MODES,
)

from kenn.core.chat_retrieval import (
    detect_intent,
    display_results,
    normalized_terms,
    query_intent_terms,
    source_label,
)


def answer_self_check(
    query: str,
    results: list[tuple[float, dict]],
    answer: str,
    *,
    route: str,
    confidence: str = "",
    timeline_context: str | None = None,
) -> dict:
    if timeline_context:
        return {
            "passed": True,
            "warnings": [],
            "sections": {"short_answer": True, "try_this": True, "check": True, "sources": True},
            "source_topic_match": True,
            "answered_intent": True,
        }
    topics = query_topics(query)
    displayed = display_results(query, results, 3)
    source_backed = bool(displayed)
    source_topic_match = not topics or any(
        chunk_topics(chunk) & set(topics) for _score, chunk in displayed
    )
    answer_terms = normalized_terms(answer)
    intent_terms = query_intent_terms(query) or {
        term for term in normalized_terms(query) if len(term) >= 4
    }
    answered_intent = not intent_terms or bool(answer_terms & intent_terms)
    sections_present = {
        "short_answer": "short answer:" in answer.lower(),
        "try_this": "try this:" in answer.lower(),
        "check": bool(
            re.search(r"\b(listening|live|quality|implementation)?\s*check:", answer.lower())
        ),
        "sources": "sources:" in answer.lower(),
    }
    warnings: list[str] = []
    if not source_backed:
        warnings.append("no displayed sources")
    if not source_topic_match:
        warnings.append("source topics do not match query topics")
    if confidence == "low":
        warnings.append("low confidence")
    if not answered_intent:
        warnings.append("answer may miss exact query terms")
    if route == "unknown":
        warnings.append("unknown route")
    return {
        "passed": not warnings,
        "warnings": warnings,
        "sections": sections_present,
        "source_topic_match": source_topic_match,
        "answered_intent": answered_intent,
    }


def grounding_report(
    query: str,
    results: list[tuple[float, dict]],
    answer: str,
    *,
    route: str,
    confidence: str,
    timeline_context: str | None = None,
) -> dict:
    if timeline_context:
        return {
            "score": 100,
            "top_source_trust": 1.0,
            "approved_note": True,
            "source_topic_match": True,
            "answered_intent": True,
            "route_known": True,
            "warnings": [],
        }
    displayed = display_results(query, results, 3)
    topics = set(query_topics(query))
    top = displayed[0][1] if displayed else {}
    top_trust = source_trust_score(top) if top else 0.0
    source_topic_match = not topics or any(
        chunk_topics(chunk) & topics for _score, chunk in displayed
    )
    approved_note = any(
        chunk.get("kind") == "note" and source_trust_score(chunk) >= 0.95
        for _score, chunk in displayed
    )
    answer_terms = normalized_terms(answer)
    intent_terms = query_intent_terms(query) or {
        term for term in normalized_terms(query) if len(term) >= 4
    }
    answered_intent = not intent_terms or bool(answer_terms & intent_terms)
    route_known = route not in {"", "unknown", "clarify"}
    score = 0
    score += int(top_trust * 30)
    score += 25 if source_topic_match else 0
    score += 15 if answered_intent else 0
    score += 10 if approved_note else 0
    score += 10 if route_known else 0
    if confidence == "low":
        score -= 20
    warnings: list[str] = []
    if top_trust and top_trust < 0.7:
        warnings.append("low source trust")
    if not source_topic_match:
        warnings.append("source topic mismatch")
    if not answered_intent:
        warnings.append("answer may miss intent")
    if not route_known:
        warnings.append("uncertain route")
    return {
        "score": max(0, min(100, score)),
        "top_source_trust": round(top_trust, 3),
        "approved_note": approved_note,
        "source_topic_match": source_topic_match,
        "answered_intent": answered_intent,
        "route_known": route_known,
        "warnings": warnings,
    }


def grounding_mode(report: dict) -> str:
    score = int(report.get("score", 0) or 0)
    if score >= 75:
        return "strong"
    if score >= 55:
        return "medium"
    return "weak"


_MEASUREMENT_RE = re.compile(
    r"\b-?\d+(?:\.\d+)?\s*(?:hz|khz|db(?:fs|tp)?|ms|%|lufs?|bpm|bits?)\b",
    re.IGNORECASE,
)
_STRUCTURE_TERMS = {
    "short", "answer", "try", "this", "check", "sources", "source", "step",
    "steps", "first", "then", "use", "using", "based", "notes", "note",
}
_CITED_SOURCE_FILENAME_RE = re.compile(r"\(([\w\-]+\.md)\)")


def _cited_source_filenames(answer: str) -> set[str]:
    """Filenames cited in the answer's own "Sources:" bullet list.

    llm_rewrite.py's system prompt tells the model to reproduce the exact
    "Title (filename.md)" labels it was given (source_label()'s format), but
    a small local model doesn't reliably copy them -- it can invent
    plausible-looking filenames instead. Scoped to the Sources: section only
    (not the whole answer) so a legitimate filename mention elsewhere isn't
    misread as a citation.
    """
    lowered = answer.lower()
    start = lowered.find("sources:")
    if start == -1:
        return set()
    end = lowered.find("you could also ask", start)
    section = answer[start:end] if end != -1 else answer[start:]
    return {m.lower() for m in _CITED_SOURCE_FILENAME_RE.findall(section)}


_SOURCE_PUNT_RE = re.compile(
    r"\b(mentioned in the sources?|source pages? below|sources? below to verify|"
    r"see the sources? (?:for|below)|check the sources? (?:for|below))\b",
    re.IGNORECASE,
)


def _punts_to_sources(answer: str) -> bool:
    """True if the answer tells the user to go consult "the sources"
    themselves instead of actually synthesizing them.

    Live-tested 2026-08-03: asked "how do i set up a send reverb". The real
    top source (reverb-send-workflow.md) has concrete steps (create a return
    track, 100% wet, high-pass 200-400 Hz, send 10-20%), but the generated
    "Try this:" section was "Open the relevant Ableton view or device
    mentioned in the sources... Use the source pages below to verify the
    exact command or setting name" -- content-free filler that punts the
    actual work back to the user, who can't act on it (the chat UI only
    shows source titles, not their full text). This slipped past the
    evidence-overlap check because other sections of the same answer drew
    real content from a different one of the 3 retrieved sources, keeping
    the aggregate overlap score high enough to pass.
    """
    return bool(_SOURCE_PUNT_RE.search(answer))


# Literal instructional fragments from llm_rewrite.py's SYSTEM_PROMPT_TEMPLATE
# answer-structure spec, e.g. "Short answer: (one punchy paragraph — your
# verdict first, then the reason)". These parenthesized descriptions tell the
# model what to WRITE in each section; they must never appear as the actual
# generated content.
_PROMPT_INSTRUCTION_ECHO_PHRASES = (
    "one punchy paragraph",
    "your verdict first, then the reason",
    "every step must be something jack can do right now in the daw",
    "one paragraph of the underlying engineering principle",
    "bullet list matching the provided source labels",
    "up to 3 short follow-up question bullets",
)


def _echoes_prompt_instructions(answer: str) -> bool:
    """True if the answer echoes its own system-prompt instructions back as
    if they were content.

    Live-tested 2026-08-03: asked "how do i set up a send reverb". The
    generated answer opened with "Short answer: (one punchy paragraph — your
    verdict first, then the reason)" -- qwen2.5:1.5b copied the literal
    parenthesized instruction describing what to write, instead of writing
    it, the same failure already fixed once in the weekly-review admin
    agent (business/agents/Admin/local_agent.py), now showing up in KENN's
    own rewrite path. Slipped past every other check because the rest of
    the same answer (Try this: steps, Why it matters) had strong evidence
    overlap with real note content.
    """
    lowered = answer.lower()
    return any(phrase in lowered for phrase in _PROMPT_INSTRUCTION_ECHO_PHRASES)


# A chat answer is advice; only the Live command path changes the set, and only after Apply. A model that writes
# "I've turned the bass down 2 dB" is handing the user a receipt for something that never happened, so that answer
# is thrown away and the template is used. Checked against 122 Qwen answers from the Stage 1 comparison: no false
# hits ("I'd cut", "you'll want to set" are advice and don't match).
_LIVE_CHANGE_CLAIM_RE = re.compile(
    r"\bI(?:'ve|\u2019ve| have| just)\s+(?:just\s+|now\s+|gone ahead and\s+)?"
    r"(?:turned|set|muted|unmuted|soloed|unsoloed|panned|lowered|raised|boosted|cut|added|inserted|loaded|applied|"
    r"changed|adjusted|renamed|created|removed|deleted|moved|made)\b"
    r"|^\s*done[.!,:\u2014-]",
    re.I | re.M,
)


def claims_live_change(answer: str) -> bool:
    return bool(_LIVE_CHANGE_CLAIM_RE.search(answer))


def generated_answer_validation(
    query: str,
    results: list[tuple[float, dict]],
    answer: str,
    *,
    route: str,
    confidence: str,
    answer_mode: str,
    timeline_context: str | None = None,
    additional_evidence_text: str | None = None,
) -> dict:
    """Gate generated prose against the same evidence used for retrieval.

    This is deliberately deterministic and provider-independent, so local,
    remote, sync, streaming, and voice generation cannot select different
    standards. Failed generated text is discarded before it reaches a caller.
    """
    trusted_inline_context = query.lower().startswith(
        ("[stems masking analysis context]", "[audio characterization:")
    )
    effective_answer_mode = "mix_diagnosis" if trusted_inline_context else answer_mode
    grounding = grounding_report(
        query,
        results,
        answer,
        route=route,
        confidence=confidence,
        timeline_context=timeline_context,
    )
    if trusted_inline_context:
        grounding = {
            "score": 90,
            "top_source_trust": 1.0,
            "approved_note": True,
            "source_topic_match": True,
            "answered_intent": True,
            "route_known": True,
            "warnings": [],
        }
    quality = answer_quality_report(
        query,
        results,
        answer,
        route=route,
        confidence="high" if trusted_inline_context else confidence,
        answer_mode=effective_answer_mode,
        grounding=grounding,
        timeline_context=timeline_context,
    )
    evidence_text = query + " " + " ".join(
        " ".join(
            (
                str(chunk.get("title") or ""),
                str(chunk.get("source") or ""),
                str(chunk.get("text") or ""),
            )
        )
        for _score, chunk in display_results(query, results, 3)
    )
    if timeline_context:
        evidence_text = f"{evidence_text} {timeline_context}"
    if additional_evidence_text:
        evidence_text = f"{evidence_text} {additional_evidence_text}"
    evidence_terms = normalized_terms(f"{query} {evidence_text}")
    answer_terms = normalized_terms(answer) - _STRUCTURE_TERMS
    overlap = (
        len(answer_terms & evidence_terms) / len(answer_terms)
        if answer_terms
        else 0.0
    )
    evidence_measurements = {
        " ".join(match.lower().split())
        for match in _MEASUREMENT_RE.findall(evidence_text)
    }
    answer_measurements = {
        " ".join(match.lower().split())
        for match in _MEASUREMENT_RE.findall(answer)
    }
    unsupported_measurements = sorted(answer_measurements - evidence_measurements)
    displayed_filenames = {
        str(chunk.get("source") or "").lower()
        for _score, chunk in display_results(query, results, 3)
        if chunk.get("source")
    }
    cited_filenames = _cited_source_filenames(answer)
    fabricated_sources = sorted(cited_filenames - displayed_filenames)
    punts_to_sources = _punts_to_sources(answer)
    echoes_prompt = _echoes_prompt_instructions(answer)
    claims_change = claims_live_change(answer)
    warnings = []
    if claims_change:
        warnings.append("generated answer claims it changed the Live set")
    if unsupported_measurements:
        warnings.append("generated answer introduced unsupported measurements")
    if fabricated_sources:
        warnings.append("generated answer cites sources not in the retrieved evidence")
    if punts_to_sources:
        warnings.append("generated answer punts to the sources instead of synthesizing them")
    if echoes_prompt:
        warnings.append("generated answer echoes its own system prompt instructions")
    minimum_overlap = 0.10 if trusted_inline_context else 0.16
    if len(answer_terms) >= 8 and overlap < minimum_overlap:
        warnings.append("generated answer has insufficient evidence overlap")
    if grounding_mode(grounding) == "weak":
        warnings.append("generated answer has weak grounding")
    if int(quality.get("score", 0) or 0) < ANSWER_QUALITY_MIN_SCORE:
        warnings.append("generated answer is below the quality threshold")
    return {
        "accepted": not warnings,
        "warnings": warnings,
        "unsupported_measurements": unsupported_measurements,
        "fabricated_sources": fabricated_sources,
        "punts_to_sources": punts_to_sources,
        "echoes_prompt_instructions": echoes_prompt,
        "claims_live_change": claims_change,
        "evidence_overlap": round(overlap, 3),
        "grounding": grounding,
        "quality": quality,
    }


MODE_BOUNDARY_REQUIREMENTS = {
    "ableton_steps": {
        "marker": "in live:",
        "terms": ("ableton", "live"),
        "match": "any",
        "warning": "ableton mode lacks Live safety boundary",
    },
    "client_delivery": {
        "marker": "scope boundary:",
        "terms": ("quote", "delivery", "client"),
        "match": "any",
        "warning": "client-delivery mode lacks scope boundary",
    },
    "dialogue_cleanup": {
        "marker": "dialogue check:",
        "terms": ("artifact", "intelligibility", "room tone", "noise"),
        "match": "any",
        "warning": "dialogue-cleanup mode lacks artifact boundary",
    },
    "game_audio_implementation": {
        "marker": "implementation check:",
        "terms": ("memory", "voice", "streaming", "sync", "state"),
        "match": "any",
        "warning": "game-audio mode lacks runtime tradeoff",
    },
    "mastering_safety": {
        "marker": "mastering boundary:",
        "terms": ("loudness", "balance", "true peak"),
        "match": "all",
        "warning": "mastering mode lacks loudness boundary",
    },
    "mix_diagnosis": {
        "marker": ("symptom and likely cause:", "diagnosis first:"),
        "terms": ("matched loudness",),
        "match": "any",
        "warning": "mix-diagnosis mode lacks symptom-first structure",
    },
}


def mode_boundary_requirement_met(answer_mode: str, lowered_answer: str) -> tuple[bool, str]:
    requirement = MODE_BOUNDARY_REQUIREMENTS.get(answer_mode)
    if not requirement:
        return True, ""
    terms = tuple(requirement["terms"])
    markers = requirement["marker"]
    if isinstance(markers, str):
        markers = (markers,)
    if not any(str(marker) in lowered_answer for marker in markers):
        return False, str(requirement["warning"])
    if requirement.get("match") == "all":
        ok = all(term in lowered_answer for term in terms)
    else:
        ok = any(term in lowered_answer for term in terms)
    return ok, "" if ok else str(requirement["warning"])


def answer_quality_report(
    query: str,
    results: list[tuple[float, dict]],
    answer: str,
    *,
    route: str,
    confidence: str,
    answer_mode: str,
    grounding: dict,
    timeline_context: str | None = None,
) -> dict:
    """Cheap deterministic judge for answer shape and grounding."""
    lowered = answer.lower()
    displayed = display_results(query, results, 3)
    numbered_steps = len(re.findall(r"(?m)^\s*\d+\.\s+\S+", answer))
    sections = {
        "short_answer": any(
            marker in lowered
            for marker in (
                "short answer:",
                "direct solution is:",
                "main recommendation:",
                "recommended production technique:",
                "direct advice:",
                "to address your query directly:",
                "symptom and likely cause:",
                "the concept:",
                "the reasoning:",
                "why this works:",
                "diagnosis first:",
            )
        ),
        "try_this": (
            "try this:" in lowered
            or "try this in your session:" in lowered
            or "try it:" in lowered
            or "to apply this:" in lowered
            or "step-by-step" in lowered
            or "correction steps" in lowered
            or "try this workflow" in lowered
            or "concrete steps" in lowered
            or numbered_steps >= 2
        ),
        "sources": "sources:" in lowered,
        "check": bool(
            re.search(
                r"\b(listening|live|quality|implementation|delivery|dialogue|mastering|revision|understanding|verification)?\s*check:|\bverification:",
                lowered,
            )
        ),
    }
    warnings: list[str] = []
    score = int(grounding.get("score", 0) or 0)
    score = min(score, 82)
    if timeline_context:
        score = 95
    if answer_mode == "studio_dialogue" or route in {"conversation", "production_dialogue"}:
        # Studio dialogue is measured by depth and coherence, not checklist headings
        if len(answer.split()) >= 20:
            score = max(score, 75)
    else:
        if not sections["short_answer"]:
            warnings.append("missing short answer section")
            score -= 10
        if not sections["try_this"]:
            warnings.append("missing steps section")
            score -= 12
        if numbered_steps < 2:
            warnings.append("fewer than two actionable steps")
            score -= 12
        else:
            score += min(numbered_steps, 5) * 2

    # The Sources: section is intentionally hidden unless the user asks for
    # it (chat_answer.py's asks_for_sources() gate, 2026-08-05) -- don't
    # penalize an ordinary answer for correctly omitting it. Duplicated
    # here rather than imported to avoid a circular import (chat_answer.py
    # already imports from this module); keep the term set in sync with
    # chat_answer.asks_for_sources().
    query_asks_for_sources = any(
        term in query.lower()
        for term in (
            "source", "sources", "reference", "references", "citation",
            "citations", "link", "links", "where is this from", "prove", "origin",
        )
    )
    if query_asks_for_sources and not sections["sources"]:
        warnings.append("missing sources section")
        score -= 10
    if not sections["check"]:
        warnings.append("missing verification check")
        score -= 8
    first_move_markers = (
        "first move:",
        "first move in live:",
        "first implementation move:",
        "first mastering move:",
        "first revision move:",
        "first cleanup move:",
        "symptom and likely cause:",
        "here are the steps:",
        "try this in your session:",
    )
    if any(marker in lowered for marker in first_move_markers):
        score += 4
    boundary_ok, boundary_warning = mode_boundary_requirement_met(answer_mode, lowered)
    if boundary_ok and answer_mode in MODE_BOUNDARY_REQUIREMENTS:
        score += 4
    elif boundary_warning:
        warnings.append(boundary_warning)
        score -= 6
    if not displayed and not timeline_context:
        if answer_mode != "studio_dialogue" and route not in {"conversation", "production_dialogue"}:
            warnings.append("no displayed sources")
            score -= 20
    if confidence == "low":

        warnings.append("low confidence")
        score -= 20
    if answer_mode not in ANSWER_MODES:
        warnings.append("unknown answer mode")
        score -= 8
    source_labels = " ".join(source_label(chunk).lower() for _score, chunk in displayed)
    if (
        answer_mode == "ableton_steps"
        and "ableton" not in lowered
        and "live" not in lowered
        and "ableton" not in source_labels
    ):
        warnings.append("ableton mode lacks Ableton/Live grounding")
        score -= 8
    if (
        answer_mode == "mix_review_followup"
        and "mix review" not in lowered
        and not timeline_context
    ):
        warnings.append("mix review mode lacks review context")
        score -= 8
    if answer_mode == "game_audio_implementation" and not any(
        term in lowered for term in ("wwise", "game", "middleware", "engine")
    ):
        warnings.append("game-audio mode lacks implementation context")
        score -= 8
    return {
        "score": max(0, min(100, score)),
        "mode": answer_mode,
        "warnings": warnings,
        "sections": sections,
        "actionable_steps": numbered_steps,
    }


def should_use_llm_rewrite(
    query: str,
    route: str,
    confidence: str,
    grounding: dict,
    quality: dict,
    answer_mode: str,
) -> bool:
    if "[stems masking" in query.lower() or "[audio characterization" in query.lower():
        return True
    if confidence not in {"high", "medium"}:
        return False
    if route in {"out_of_scope", "clarify", "conversation", "audiogen"}:
        return False
    if grounding_mode(grounding) == "weak":
        return False
    # Lowered threshold: LLM can improve even medium-quality drafts (was 62)
    if int(quality.get("score", 0) or 0) < 50:
        return False
    intent = detect_intent(query)
    # Always rewrite for these modes — they benefit most from polished prose
    if answer_mode in {
        "deep_explanation",
        "mix_review_followup",
        "client_delivery",
        "mix_diagnosis",
        "ableton_steps",
        "studio_dialogue",
    }:
        return True
    if intent in {"why", "explain"}:
        return True
    # Removed the 90-character length gate — short queries also benefit
    return True



def calibrate_answer_for_grounding(answer: str, report: dict) -> str:
    mode = grounding_mode(report)
    if mode == "medium":
        prefix = "Based on the closest local notes, treat this as a practical starting point rather than a final verdict."
        if answer.startswith(prefix):
            return answer
        return f"{prefix}\n\n{answer}"
    return answer


def mode_signature(mode: str, confidence: str = "medium") -> dict[str, str]:
    """Return the opener, tone markers, and distinctive phrasing for each answer mode.

    Each mode has its own 'signature' — the opener label, the kind of language it uses,
    and its distinctive framing. This gives the user a sense of a consistent personality
    that approaches different topics differently.
    """
    signatures = {
        "mix_diagnosis": {
            "opener": "→ Let's trace the symptom.",
            "section_tag": " Diagnosis:",
            "closing": "→ Try that change, then tell me if the symptom shifted or stayed. That tells us what to try next.",
            "confidence_high": "Here is what I would check first:",
            "confidence_medium": "Based on the notes, start here:",
            "confidence_low": "I am matching a few sources — treat this as a starting point:",
        },
        "ableton_steps": {
            "opener": "→ Hands-on. Live workflow:",
            "section_tag": " In Live:",
            "closing": "→ Try it on a duplicate track, then A/B. If this is not what you needed, I can walk through the routing or device setup.",
            "confidence_high": "Here is the exact Ableton setup:",
            "confidence_medium": "The notes suggest this workflow in Live:",
            "confidence_low": "This is what I found in the indexed sources for Live:",
        },
        "client_delivery": {
            "opener": "→ Before you send that file:",
            "section_tag": " Delivery:",
            "closing": "→ Confirm the details with the client before exporting. If they need stems or a specific format, I can help set that up.",
            "confidence_high": "Here is what I would send:",
            "confidence_medium": "Based on the references, check these before sending:",
            "confidence_low": "The sources are thin — verify these with the client:",
        },
        "deep_explanation": {
            "opener": "→ Here is the reasoning behind this.",
            "section_tag": " Why:",
            "closing": "→ Apply the idea to one small element in your session — that will turn the theory into a listening decision.",
            "confidence_high": "The concept works like this:",
            "confidence_medium": "Here is how the technique fits into the session:",
            "confidence_low": "This is what the sources suggest, but test it before depending on it:",
        },
        "dialogue_cleanup": {
            "opener": "→ Cleanup path for dialogue:",
            "section_tag": " Dialogue:",
            "closing": "→ Listen at normal speech level on headphones. The edit should disappear into the track.",
            "confidence_high": "Here is the dialogue chain I would build:",
            "confidence_medium": "Start with these steps for the dialogue:",
            "confidence_low": "Approach this conservatively — the sources are limited:",
        },
        "game_audio_implementation": {
            "opener": "→ Implementation path in middleware:",
            "section_tag": " Implementation:",
            "closing": "→ Test in engine context with repeated triggers and realistic playback levels.",
            "confidence_high": "Here is the implementation route:",
            "confidence_medium": "Based on the notes, start with:",
            "confidence_low": "The indexed sources are limited — verify against engine docs:",
        },
        "mastering_safety": {
            "opener": "→ Mastering checks:",
            "section_tag": " Mastering:",
            "closing": "→ Level-match before/after, check true peak, then listen quietly and on a small speaker.",
            "confidence_high": "Here is the mastering path I would follow:",
            "confidence_medium": "The standards suggest this approach:",
            "confidence_low": "Approach with caution — the sources are limited:",
        },
        "mix_review_followup": {
            "opener": "→ Revision check:",
            "section_tag": " Revision:",
            "closing": "→ Make one focused change, export, and compare against the previous version.",
            "confidence_high": "Based on the review data:",
            "confidence_medium": "The review suggests starting here:",
            "confidence_low": "The review data is limited — trust your ears first:",
        },
        "quick_fix": {
            "opener": "→ Quick move:",
            "section_tag": "",
            "closing": "→ Compare before/after at the same loudness. If this does not help, I can walk through a deeper approach.",
            "confidence_high": "Try this:",
            "confidence_medium": "Based on the notes, try:",
            "confidence_low": "Quick suggestion from the indexed sources — verify it:",
        },
        "studio_dialogue": {
            "opener": "→ In the studio:",
            "section_tag": " Studio Insight:",
            "closing": "→ Trust what your monitors and meters tell you, and let me know if you want to audition a specific move in the session.",
            "confidence_high": "Here is the engineering reality:",
            "confidence_medium": "Based on standard studio practice:",
            "confidence_low": "Here is how to think about this in the session:",
        },
    }
    return signatures.get(mode, signatures["quick_fix"])
