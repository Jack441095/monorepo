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
    count_actionable_steps,
)

from kenn.core.chat_retrieval import (
    detect_intent,
    normalized_terms,
    query_intent_terms,
    source_label,
)

from kenn.llm.llm_rewrite import model_evidence, resolve_context_chars


# The evidence set the gate judges against is the set of chunks the model was actually shown, read out of the
# same list the prompt was assembled from. Deriving it here instead is how the gate ends up wider than the model
# in one direction and narrower in the other, and both have been measured on the streaming chat surface with
# kenn-brain-qwen3-8b and the cache off:
#
# Narrow, fixed 2 Oct 2026: the gate read the top 3 while the model read 12, so a figure in chunk #7 was quoted
# back and reported invented. Acceptance fell from 41% (12 of 29) to 27% (4 of 15) — 10 unsupported-measurement
# and 3 fabricated-source rejections, every one of them a chunk the gate had never opened.
#
# Wide, fixed 2 Oct 2026: the gate went back to reading every chunk's text in full while the prompt fitted 2-4
# excerpts into 1200 chars at 400 each. On index v-db8c6334cf63 at the ask path's limit of 16, "send reverb on a
# vocal bus" put 3 excerpts in front of the model and 10 chunks in front of the gate, with 22 measurements in the
# gate's text that the model was never shown. A "3 dB" from the model's training prior was waved through on
# chunk #9. model_evidence() is the one list both sides read, so the seam is gone rather than tested for.
#
# Note what leaving display_results() also fixed: it de-duplicates on (kind, source, page), and all 3204 note
# sections in that index carry page == 0, so every section of one note collapsed into a single slot. The old
# EVIDENCE_SCAN_WINDOW of 12 was a depth in name only — the real depth was 4 to 10. The list below is keyed by
# chunk, so a note's sections stay distinct exactly as they do in the prompt.
#
# The budget needed the same treatment as the list, and it took a second pass to see it. Taking model_evidence()'s
# max_chars default here looked right and was not: the prompt path reads KENN_LLM_CONTEXT_CHARS, so a run that
# pinned it built a shorter block than this list was read at. At 300 chars on index v-db8c6334cf63 the model saw
# 1 excerpt and this gate judged 3 — the same 1-vs-3 gap as the 41% to 27% measurement above with the roles
# reversed. Both sides now take the budget from llm_rewrite.resolve_context_chars(), so an override moves both
# readers or neither, and the threshold below is untouched either way.
def _evidence_chunks(results: list[tuple[float, dict]]) -> list[tuple[float, dict, str]]:
    """(score, chunk, body-as-shown) for every excerpt the model was given, in prompt order."""
    _block, shown = model_evidence(results, source_label, max_chars=resolve_context_chars())
    return shown


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
    displayed = _evidence_chunks(results)
    source_backed = bool(displayed)
    source_topic_match = not topics or any(
        chunk_topics(chunk) & set(topics) for _score, chunk, _body in displayed
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
    displayed = _evidence_chunks(results)
    topics = set(query_topics(query))
    top = displayed[0][1] if displayed else {}
    top_trust = source_trust_score(top) if top else 0.0
    source_topic_match = not topics or any(
        chunk_topics(chunk) & topics for _score, chunk, _body in displayed
    )
    approved_note = any(
        chunk.get("kind") == "note" and source_trust_score(chunk) >= 0.95
        for _score, chunk, _body in displayed
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


# Three defects this pattern carried, found by running real answers against real evidence. A hyphen
# between two numbers is a range, not a sign: "200-400 Hz" read as "-400 Hz", so quoting the range's
# own lower bound was rejected as invented, and "-18 dBFS" lost its sign and could be restated
# "+18 dBFS" and pass. Ranges are rewritten to their endpoints first, leaving the hyphen unambiguous.
# The trailing \b was the third: it cannot match after "%", so percentages escaped the gate entirely.
_RANGE_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)"
    r"(\s*(?:hz|khz|db(?:fs|tp)?|ms|%|lufs?|bpm|bits?))(?![a-z0-9])",
    re.IGNORECASE,
)
_MEASUREMENT_RE = re.compile(
    r"(?<![\d.])-?\d+(?:\.\d+)?\s*(?:hz|khz|db(?:fs|tp)?|ms|%|lufs?|bpm|bits?)"
    r"(?![a-z0-9])",
    re.IGNORECASE,
)


def _measurements(text: str) -> set[str]:
    """Each measurement in `text`, keyed so spacing never decides a match.

    The space between number and unit is dropped rather than collapsed: audio writing puts it both ways
    in the same breath ("120 Hz" in a note, "120Hz" from the model), and treating those as two different
    values rejected answers that quoted the note correctly.
    """
    return {
        "".join(m.lower().split())
        for m in _MEASUREMENT_RE.findall(_RANGE_RE.sub(r"\1\3 \2\3", text))
    }


_STRUCTURE_TERMS = {
    "short", "answer", "try", "this", "check", "sources", "source", "step",
    "steps", "first", "then", "use", "using", "based", "notes", "note",
}
_CITED_SOURCE_FILENAME_RE = re.compile(r"\(([\w\-]+\.md)\)")


def _sources_section(answer: str) -> tuple[int, int]:
    """Byte range of the answer's own "Sources:" list, or (-1, -1) when there isn't one."""
    lowered = answer.lower()
    start = lowered.find("sources:")
    if start == -1:
        return -1, -1
    end = lowered.find("you could also ask", start)
    return start, (end if end != -1 else len(answer))


def _cited_source_filenames(answer: str) -> set[str]:
    """Filenames cited in the answer's own "Sources:" bullet list.

    llm_rewrite.py's system prompt tells the model to reproduce the exact
    "Title (filename.md)" labels it was given (source_label()'s format), but
    a small local model doesn't reliably copy them -- it can invent
    plausible-looking filenames instead. Scoped to the Sources: section only
    (not the whole answer) so a legitimate filename mention elsewhere isn't
    misread as a citation.
    """
    start, end = _sources_section(answer)
    if start == -1:
        return set()
    return {m.lower() for m in _CITED_SOURCE_FILENAME_RE.findall(answer[start:end])}


def _prose_without_sources(answer: str) -> str:
    """The answer with its own citation list removed.

    The Sources: line is copied from the labels we handed the model, so its words are guaranteed to
    appear in the evidence. Counting them toward evidence overlap let an answer clear the floor on the
    strength of the citation alone, with nothing in the prose actually drawn from the note.
    """
    start, end = _sources_section(answer)
    if start == -1:
        return answer
    return (answer[:start] + answer[end:]).strip()


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
# "I've turned the bass down 2 dB" is handing the user a receipt for something never happened, so that answer is
# thrown away and the template is used. Checked against 122 Qwen answers from the Stage 1 comparison: no false hits
# on the auxiliary forms ("I'd cut", "you'll want to set" are advice and don't match).
#
# The auxiliary-only version missed the plainer past tense, which is what a small local model actually writes:
# "I lowered the bass by 2 dB" claims exactly as much as "I have lowered the bass by 2 dB" and slipped through on
# 25 of 29 realistic phrasings. Hence the second branch. Bare "I" takes the whole verb list, "set" and "cut"
# included, because the two errors are not symmetric: a missed claim shows the producer a receipt for a change
# that never happened, while a false positive only falls back to the template. The advice forms stay clean anyway,
# because no modal can reach either branch: "I'd set" is stopped by the apostrophe, and "I would set",
# "I will set" and "I'll set" are stopped by no modal being in the verb list.
_CHANGE_VERBS = (
    r"turned|set|muted|unmuted|soloed|unsoloed|panned|lowered|raised|boosted|cut|added|inserted|loaded|"
    r"applied|changed|adjusted|renamed|created|removed|deleted|moved|made|dropped|bypassed|armed|disarmed|"
    r"assigned|duplicated|copied|imported|exported|recorded|sent|wrote|replaced|swapped|nudged|faded|chopped|"
    r"routed|quantized|disabled|enabled|started|stopped|saved|cleared|reset|unlinked|grouped|ungrouped|"
    r"selected|deselected|automated|opened|closed"
)
_LIVE_CHANGE_CLAIM_RE = re.compile(
    # "I've turned", "I have set", "I just muted", "I now lowered", "I've gone ahead and set"
    rf"\bI(?:'ve|\u2019ve| have| just| now| already)\s+(?:just\s+|now\s+|gone ahead and\s+|already\s+)?"
    rf"(?:{_CHANGE_VERBS})\b"
    # Plain past tense with no auxiliary: "I lowered the bass by 2 dB", "I muted the kick", "I set the send to 15%"
    rf"|\bI\s+(?:then\s+|also\s+|went ahead and\s+)?(?:{_CHANGE_VERBS})\b"
    # "Done." and "Done - the send is set up." The delimiter used to be mandatory, so "Done - ..." missed.
    rf"|^\s*done\b",
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
    grounding = grounding_report(
        query,
        results,
        answer,
        route=route,
        confidence=confidence,
        timeline_context=timeline_context,
    )
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
    # Read the evidence list once and hand the same one to every check below, so the measurements, the overlap
    # score and the citation check cannot end up scored against different sets.
    shown = _evidence_chunks(results)
    evidence_text = " ".join(
        " ".join(
            (
                str(chunk.get("title") or ""),
                str(chunk.get("source") or ""),
                # The body the prompt carried, not chunk["text"]. Title and source are in the prompt too, inside
                # the label attribute of the same <source_excerpt>, so this set stays a subset of what the model
                # read. Reading the raw text instead is what let the gate vouch for numbers from chunks #7 to #10.
                body,
            )
        )
        for _score, chunk, body in shown
    )
    if timeline_context:
        evidence_text = f"{evidence_text} {timeline_context}"
    if additional_evidence_text:
        evidence_text = f"{evidence_text} {additional_evidence_text}"
    # The query is deliberately not part of the evidence set. This overlap check answers one question:
    # is the answer built out of the notes we retrieved? Folding the query in would let a model pass by
    # echoing the words of the question back, which is the one thing a synthesised answer always does.
    # Whether the answer engages the question is already covered by `answered_intent` in grounding_report.
    evidence_terms = normalized_terms(evidence_text)
    answer_terms = normalized_terms(_prose_without_sources(answer)) - _STRUCTURE_TERMS
    overlap = (
        len(answer_terms & evidence_terms) / len(answer_terms)
        if answer_terms
        else 0.0
    )
    unsupported_measurements = sorted(_measurements(answer) - _measurements(evidence_text))
    # The labels the model was actually given, so a citation is only fabricated if the filename was not on
    # screen. Derived from the same shown list, not from what retrieval could have supplied.
    displayed_filenames = {
        str(chunk.get("source") or "").lower()
        for _score, chunk, _body in shown
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
    if len(answer_terms) >= 8 and overlap < 0.16:
        warnings.append("generated answer has insufficient evidence overlap")
    if grounding_mode(grounding) == "weak":
        warnings.append("generated answer has weak grounding")
    if int(quality.get("score", 0) or 0) < ANSWER_QUALITY_MIN_SCORE:
        warnings.append("generated answer is below the quality threshold")
        # Aggregate first: route_latency_report.py groups on the first warning, so specifics ahead would split it.
        warnings.extend(str(w) for w in (quality.get("warnings") or []))
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
    displayed = _evidence_chunks(results)
    numbered_steps = count_actionable_steps(answer)
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
    source_labels = " ".join(source_label(chunk).lower() for _score, chunk, _body in displayed)
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
    # Deliberately no "trusted context" escape hatch keyed on the query text. A query is producer-supplied,
    # so a prefix in it is a producer-supplied bypass: typing the marker used to switch this on with a weak
    # template answer, before the confidence, grounding and quality checks below. Host-supplied context
    # arrives as `timeline_context`, which is a real argument and cannot be forged from the request body.
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
