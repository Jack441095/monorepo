from __future__ import annotations

import re


from kenn.core.suggestions import starter_questions
from kenn.retrieval.retrieval import (
    TOPIC_SYNONYMS,
    best_sentence,
    chunk_topics,
    query_topics,
    tokenize,
)

from kenn.core.chat_constants import (
    MIN_RELEVANT_SCORE,
    NOTES_DIR,
    NOTE_SCORE_BONUS,
    SOURCE_QUALITY_ORDER,
)

from kenn.core.chat_retrieval import (
    chunk_is_catalog_boilerplate,
    detect_intent,
    display_results,
    intent_guard_failed,
    note_query_affinity,
    note_rank_key,
    query_is_out_of_scope,
    results_are_weak,
)
from kenn.core.chat_routing import (
    normalize_history,
)


def section_lines(text: str, heading: str) -> list[str]:
    lines = text.splitlines()
    found = False
    values: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if found and values:
                break
            continue
        # Live-tested 2026-08-03: automix-reverb-and-delay-sends.md's real
        # "Try this" section is headed "Try this -- default reverb sends by
        # instrument:", not bare "Try this:" -- the exact-match check below
        # never recognized it as a heading at all, silently discarding all
        # 14 of its instrument-by-instrument values. The "stop collecting"
        # check just below already tolerates a decorated heading via
        # re.match() (a prefix match); this "start collecting" check was
        # inconsistently stricter. Loosened to the same prefix-match
        # standard so a heading followed by extra descriptive text is still
        # recognized.
        if re.match(rf"^{re.escape(heading.lower().rstrip(':'))}\b", stripped.lower()):
            found = True
            continue
        if found and re.match(
            r"^(short answer|try this|why it matters|related questions|tags|type):", stripped, re.I
        ):
            break
        if found:
            values.append(stripped)
    return values


def clean_step(line: str) -> str:
    return re.sub(r"^[-* ]*\d*[.)]?\s*", "", line).strip()


def load_note_text(chunk: dict) -> str:
    source = str(chunk.get("source", ""))
    if source:
        path = NOTES_DIR / source
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
    return str(chunk.get("text", ""))


def note_sections(query: str, results: list[tuple[float, dict]]) -> dict[str, list[str] | str]:
    topics = query_topics(query)
    note_items = [(score, chunk) for score, chunk in results if chunk.get("kind") == "note"]
    if topics:
        note_items.sort(key=lambda item: note_rank_key(query, topics, item), reverse=True)
    note_chunks = [chunk for _score, chunk in note_items]
    top_affinity = note_query_affinity(query, note_chunks[0]) if note_chunks else 0
    top_source = str(note_chunks[0].get("source", "")) if note_chunks else ""

    short_parts: list[str] = []
    steps: list[str] = []
    why_parts: list[str] = []
    related: list[str] = []
    common_mistakes: list[str] = []
    scope_limits: list[str] = []
    seen_steps: set[str] = set()
    seen_mistakes: set[str] = set()
    seen_scope_limits: set[str] = set()

    for chunk in note_chunks[:3]:
        if top_affinity > 0 and top_source and str(chunk.get("source", "")) != top_source:
            continue
        if top_affinity > 0 and note_query_affinity(query, chunk) < top_affinity:
            continue
        if topics and not (chunk_topics(chunk) & set(topics)) and len(note_chunks) > 1:
            continue
        text = load_note_text(chunk)
        short = " ".join(section_lines(text, "Short answer"))
        if short and short not in short_parts:
            short_parts.append(short)
        if len(short_parts) >= 2 and len(" ".join(short_parts)) > 320:
            break
        for line in section_lines(text, "Try this"):
            step = clean_step(line)
            if step and step not in seen_steps:
                seen_steps.add(step)
                steps.append(step)
        why = " ".join(section_lines(text, "Why it matters"))
        if why and why not in why_parts:
            why_parts.append(why)
        for line in section_lines(text, "Related questions"):
            item = clean_step(line)
            if item and item not in related:
                related.append(item)
        for line in section_lines(text, "Common mistakes"):
            mistake = clean_step(line)
            if mistake and mistake not in seen_mistakes:
                seen_mistakes.add(mistake)
                common_mistakes.append(mistake)
        for line in section_lines(text, "When this does not apply"):
            limit = clean_step(line)
            if limit and limit not in seen_scope_limits:
                seen_scope_limits.add(limit)
                scope_limits.append(limit)

    if short_parts or steps or why_parts:
        return {
            "short": " ".join(short_parts),
            "steps": steps[:8],
            "why": " ".join(why_parts),
            "related": related[:5],
            "common_mistakes": common_mistakes[:3],
            "scope_limits": scope_limits[:3],
        }

    if note_chunks:
        text = load_note_text(note_chunks[0])
        return {
            "short": best_sentence(text, topics, tokenize(query)),
            "steps": [],
            "why": "",
            "related": related,
            "common_mistakes": [],
            "scope_limits": [],
        }
    return {
        "short": "", "steps": [], "why": "", "related": [],
        "common_mistakes": [], "scope_limits": [],
    }


def confidence_level(query: str, results: list[tuple[float, dict]]) -> str:
    if not results or results_are_weak(query, results):
        return "low"
    if intent_guard_failed(query, results):
        return "low"
    top_score, top_chunk = results[0]
    topics = query_topics(query)
    if top_chunk.get("kind") == "note" and top_score >= MIN_RELEVANT_SCORE * NOTE_SCORE_BONUS:
        if not topics or chunk_topics(top_chunk) & set(topics):
            return "high"
    if top_score >= MIN_RELEVANT_SCORE + 2:
        return "high"
    if top_score >= MIN_RELEVANT_SCORE:
        return "medium"
    return "low"


def source_quality_level(query: str, results: list[tuple[float, dict]]) -> str:
    if not results or results_are_weak(query, results):
        return "low"
    if intent_guard_failed(query, results):
        return "low"

    topics = set(query_topics(query))
    displayed = display_results(query, results, 3)
    if not displayed:
        return "low"

    best_quality = "low"
    for score, chunk in displayed:
        topic_match = not topics or bool(chunk_topics(chunk) & topics)
        if chunk.get("kind") == "note" and topic_match and score >= MIN_RELEVANT_SCORE:
            best_quality = "high"
            break
        if (
            score >= MIN_RELEVANT_SCORE
            and SOURCE_QUALITY_ORDER[best_quality] < SOURCE_QUALITY_ORDER["medium"]
        ):
            best_quality = "medium"
    return best_quality


def first_sentence(text: str) -> str:
    cleaned = " ".join(text.replace("\n", " ").split())
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    return parts[0] if parts else cleaned


def strip_catalog_metadata(text: str) -> str:
    cleaned = str(text)
    for label in ("Category", "Title", "Tags", "Topics"):
        cleaned = re.sub(rf"\b{label}:\s*[^.\n]+", " ", cleaned, flags=re.I)
    return " ".join(cleaned.split())


def fallback_short(query: str, results: list[tuple[float, dict]]) -> str:
    if not results:
        return "I could not find a useful match in the indexed Ableton notes."
    topics = query_topics(query)
    focus = tokenize(query)
    for _, chunk in results:
        if chunk_is_catalog_boilerplate(chunk):
            continue
        sentence = best_sentence(strip_catalog_metadata(chunk["text"]), topics, focus)
        if not sentence:
            continue
        lowered = sentence.lower()
        if "category:" in lowered and "title:" in lowered:
            continue
        if not topics or any(term in lowered for topic in topics for term in TOPIC_SYNONYMS[topic]):
            return sentence
    for _, chunk in results:
        if chunk.get("kind") == "note":
            sentence = best_sentence(strip_catalog_metadata(chunk["text"]), topics, focus)
            if sentence:
                return sentence
    return first_sentence(strip_catalog_metadata(results[0][1]["text"]))


def route_answer_plan(route: str, intent: str, topics: list[str]) -> dict:
    """Small deterministic answer rubric by route, before any optional LLM rewrite."""
    if route in {"mix_review", "mix_review_followup"}:
        return {
            "opener": "Here is the mix-review path I would use.",
            "check_label": "Listening check:",
            "check": "Compare the change at matched loudness, then check mono, small speakers, and headphones before committing.",
            "avoid": "Avoid fixing the loudest-looking band first if the actual problem is balance, arrangement, or masking.",
        }
    if route == "game_audio":
        return {
            "opener": "Here is the implementation-minded version.",
            "check_label": "Implementation check:",
            "check": "Test the result in context with repeated triggers, state changes, and realistic playback levels.",
            "avoid": "Avoid judging the sound only in the DAW; game audio decisions need middleware or engine context.",
        }
    if route == "ableton":
        return {
            "opener": {
                "steps": "Do it in Ableton like this.",
                "explain": "Here is the Ableton version in plain English.",
                "why": "Here is why it works in Live.",
                "troubleshooting": "I would troubleshoot the Ableton setup in this order.",
                "general": "Here is the practical Ableton version.",
            }.get(intent, "Here is the practical Ableton version."),
            "check_label": "Live check:",
            "check": "Try it on a duplicate track or blank Live Set first, then A/B the result with the device or routing bypassed.",
            "avoid": "Avoid changing several devices at once; make one change, listen, then move to the next.",
        }
    if route == "production":
        if "mastering" in topics or "loudness" in topics:
            return {
                "opener": "Here is the mastering-safe version.",
                "check_label": "Quality check:",
                "check": "Level-match the before/after, check true peak and loudness, then listen quietly and on a small speaker.",
                "avoid": "Avoid chasing loudness before the mix balance, low end, and harshness are under control.",
            }
        return {
            "opener": {
                "steps": "I would approach the session like this.",
                "explain": "Here is the plain-English production version.",
                "why": "The useful way to think about it is this.",
                "troubleshooting": "I would troubleshoot the sound in this order.",
                "general": "Here is the practical production version.",
            }.get(intent, "Here is the practical production version."),
            "check_label": "Listening check:",
            "check": "Bypass the change and compare at matched level; it should solve the symptom without making another range worse.",
            "avoid": "Avoid adding processing just because the source mentions it; fix balance, gain, and arrangement problems first.",
        }
    return {
        "opener": {
            "steps": "I would approach it like this.",
            "explain": "Here is the plain-English version.",
            "why": "The useful way to think about it is this.",
            "troubleshooting": "I would troubleshoot it in this order.",
            "general": "Here is the practical version.",
        }.get(intent, "Here is the practical version."),
        "check_label": "Check:",
        "check": "Test the answer against the source references and compare before/after at the same loudness.",
        "avoid": "Avoid treating this as a rule; use it as a starting point and verify it in the session.",
    }


def fallback_steps(
    intent: str, query: str, results: list[tuple[float, dict]], route: str = "unknown"
) -> list[str]:
    if intent == "explain":
        return [
            "Start with the short answer above.",
            "Check the source pages for the exact Ableton wording.",
            "Try the concept in a blank Live Set before using it in an important project.",
        ]
    if intent == "troubleshooting":
        return [
            "Recreate the issue in a simple Live Set so you know what is causing it.",
            "Try the most relevant source suggestion below.",
            "Change one setting at a time, then listen before making the next change.",
        ]
    if route == "production":
        return [
            "Set a rough balance first so you are not using processing to hide level problems.",
            "Apply the smallest change that addresses the symptom.",
            "Bypass and compare at matched loudness before adding another processor.",
        ]
    if route == "game_audio":
        return [
            "Define the playback context: event, state, trigger rate, and target platform.",
            "Build the simplest working version in the middleware or engine.",
            "Stress-test repeated playback, transitions, and loudness in context.",
        ]
    return [
        "Open the relevant Ableton view or device mentioned in the sources.",
        "Try the action on a duplicate clip or track first.",
        "Use the source pages below to verify the exact command or setting name.",
    ]


def _append_followup(out: list[str], seen: set[str], text: str, *, query: str = "") -> None:
    cleaned = str(text).strip()
    if not cleaned:
        return
    key = cleaned.lower()
    if key in seen:
        return
    if query and cleaned.lower().rstrip("?.!") == query.strip().lower().rstrip("?.!"):
        return
    seen.add(key)
    out.append(cleaned)


def related_from_results(
    query: str,
    results: list[tuple[float, dict]],
    *,
    limit: int = 6,
) -> list[str]:
    """Pull Related questions and cross-note prompts from retrieval hits."""
    seen: set[str] = set()
    out: list[str] = []
    query_lower = query.lower()
    topics = query_topics(query)

    for _score, chunk in results:
        if chunk.get("kind") != "note":
            continue
        text = load_note_text(chunk)
        for line in section_lines(text, "Related questions"):
            item = clean_step(line)
            if item and not any(
                term in item.lower() for term in query_lower.split() if len(term) > 4
            ):
                _append_followup(out, seen, item, query=query)
        if len(out) >= limit:
            break

    for _score, chunk in results:
        if chunk.get("kind") != "note" or len(out) >= limit:
            continue
        title = str(chunk.get("title", "")).strip()
        if not title or title.lower() in query_lower:
            continue
        chunk_topic_set = chunk_topics(chunk)
        if topics and not (chunk_topic_set & set(topics)):
            continue
        _append_followup(out, seen, f"What should I know about {title}?", query=query)

    return out[:limit]


def suggested_followups(
    query: str,
    related: list[str],
    topics: list[str],
    history: list | None = None,
    results: list[tuple[float, dict]] | None = None,
) -> list[str]:
    """Follow-up prompts for the UI — matched notes first, then retrieval/topic/history."""
    seen: set[str] = set()
    out: list[str] = []
    for item in related:
        _append_followup(out, seen, str(item), query=query)
    if results:
        for item in related_from_results(query, results):
            _append_followup(out, seen, item, query=query)
    topic_hints: dict[str, list[str]] = {
        "revision": [
            "How many mix revisions should I include in a quote?",
            "What should I ask before starting mix revisions?",
        ],
        "export": [
            "How should a client send stems for mixing?",
            "How do I deliver the final mix to a client?",
        ],
        "mastering": [
            "What LUFS target should I use for streaming?",
            "How much headroom should I leave before mastering?",
        ],
        "wwise": [
            "How do Wwise Events differ from playing raw files?",
            "How do I build SoundBanks for a level?",
        ],
        "game_audio": [
            "How does Wwise handle game audio events?",
            "How do I limit loudness for mobile games?",
        ],
        "bass": [
            "How do I sidechain bass to the kick?",
            "How do I fix muddy low mids in a mix?",
        ],
        "mixing": [
            "What order should I mix in?",
            "How do I use glue compression on the mix bus?",
        ],
        "vocals": [
            "What are tips for recording vocals at home?",
            "How do I set up a vocal compression chain?",
        ],
        "compression": [
            "How do I sidechain bass to the kick?",
            "How do I use glue compression on the mix bus?",
        ],
        "saturation": [
            "How do I saturate sub bass without distortion?",
            "How do I process bass in a mix?",
        ],
        "automation": [
            "How do clip envelopes work in Session View?",
            "How do I automate send levels on a track?",
        ],
        "cpu": [
            "What does freezing a track do?",
            "Should I increase buffer size while mixing?",
        ],
    }
    intent_hints: dict[str, list[str]] = {
        "steps": [
            "Which Ableton device or rack should I start with for this?",
            "What order should I try these steps in a blank Live Set?",
        ],
        "troubleshooting": [
            "What is the most likely cause if this still sounds wrong?",
            "What should I bypass first to isolate the problem?",
        ],
        "explain": [
            "Can you give me a shorter step-by-step version?",
            "What is a common mistake with this technique?",
        ],
        "why": [
            "When should I not use this approach?",
            "What should I listen for to know it is working?",
        ],
    }
    for hint in intent_hints.get(detect_intent(query), []):
        _append_followup(out, seen, hint, query=query)

    retrieved_topics = set()
    if results:
        for _score, chunk in results:
            retrieved_topics.update(chunk_topics(chunk))

    for topic in topics:
        if results is None or topic in retrieved_topics:
            for hint in topic_hints.get(topic, []):
                if len(out) < 6:
                    _append_followup(out, seen, hint, query=query)
    if normalize_history(history) and len(out) < 4:
        for hint in (
            "Can you break that down step by step?",
            "What should I do next in Ableton for this?",
            "What mistakes should I avoid here?",
        ):
            _append_followup(out, seen, hint, query=query)
    if len(out) < 2:
        topic_label = ", ".join(topics) if topics else query.rstrip("?")
        _append_followup(out, seen, f"What else should I know about {topic_label}?", query=query)
    return out[:2]


def weak_match_answer(query: str, answer_mode: str = "") -> str:
    topics = query_topics(query)
    out_of_scope = query_is_out_of_scope(query)
    examples = starter_questions(limit=3)

    if out_of_scope:
        if answer_mode == "voice":
            return (
                "I specialize in audio engineering, studio production, mixing, mastering, and Ableton Live. "
                '<break time="400ms"/> '
                "While I'm focused on helping with your session, let me know what audio problem or "
                "workflow we should work on next."
            )
        lines = [
            "I specialize in audio engineering, studio production, mixing, mastering, and Ableton Live workflows.",
            "Since I'm not going to guess at topics outside my expertise, let me know what audio problem or workflow you'd like to work on next!",
            "",
            "Here are a few things we can do together:",
            "• Fix mixing or frequency balance issues (e.g. vocal harshness, muddy low-end)",
            "• Troubleshoot Ableton Live routing or plugin setups",
            "• Audit track stems, manage project invoices, or review a mixdown",
        ]
        return "\n".join(lines)

    if topics:
        topic_hint = ", ".join(topic.replace("_", " ") for topic in topics[:3])
        if answer_mode == "voice":
            return (
                f"I see you're asking about {topic_hint}. "
                '<break time="400ms"/> '
                "To help you best with your mix, could you tell me "
                "a bit more? For example, what instrument are you working on, and what's the symptom you're hearing?"
            )
        lines = [
            f"I see you're asking about {topic_hint}. To give you the most accurate advice for your mix, could you share a bit more context?",
            "",
            "For example:",
            "1. What specific track or instrument are you working on?",
            "2. What's the symptom you're hearing (e.g. harshness, mud, phase cancellation)?",
            "3. What plugin or DAW tool are you using?",
        ]
        if examples:
            lines.extend(["", "Or pick one of these popular studio questions:"])
            lines.extend(f"• {item}" for item in examples[:3])
        return "\n".join(lines)

    llm_res = None
    try:
        from kenn.llm.llm_rewrite import generate_conversational_llm_response, llm_enabled
        if llm_enabled():
            llm_res = generate_conversational_llm_response(query)
    except Exception:
        pass
    if llm_res:
        return llm_res

    h = abs(hash(query)) % 4
    banter_responses = [
        "Haha, got it! Ready whenever you want to dive back into the session, mix decisions, or Ableton routing.",
        "Noted! Let me know what track, mix issue, or studio task we should solve next.",
        "Sounds good! Ready to assist with whatever you need for your audio session today.",
        "I'm here! Ask me about mixing, mastering, stems, client deliverables, or track setups whenever you're ready.",
    ]
    return banter_responses[h]


def get_conversational_headers(route: str, topics: list[str]) -> dict[str, str]:
    headers = {
        "short": "Short answer:",
        "steps": "Try this:",
        "why": "Why it matters:",
        "avoid": "Avoid this:",
    }
    if route in {"mix_review", "mix_review_followup"}:
        headers["short"] = "Based on the review criteria, here is the main recommendation:"
        headers["steps"] = "Follow these correction steps in your session:"
        headers["why"] = "Why this balance matters for translation:"
        headers["avoid"] = "Common pitfalls to avoid in this mix stage:"
    elif route == "ableton":
        headers["short"] = "In Ableton Live, the direct solution is:"
        headers["steps"] = "Here is the step-by-step setup in Live:"
        headers["why"] = "Why this workflow works in Ableton:"
        headers["avoid"] = "What to avoid while routing this device:"
    elif route == "production":
        if any(t in topics for t in ("mastering", "loudness")):
            headers["short"] = "For the final master, here is the direct advice:"
            headers["steps"] = "Follow these checks before exporting your file:"
            headers["why"] = "The technical reasoning behind these mastering levels:"
            headers["avoid"] = "Avoid doing this during the final stage:"
        else:
            headers["short"] = "Here is the recommended production technique:"
            headers["steps"] = "Try this workflow in your next session:"
            headers["why"] = "Why this makes a difference in your mix:"
            headers["avoid"] = "Avoid these common production mistakes:"
    else:
        headers["short"] = "To address your query directly:"
        headers["steps"] = "Here are the concrete steps to follow:"
        headers["why"] = "Here is the technical reasoning behind this:"
        headers["avoid"] = "Keep this in mind to avoid issues:"
    return headers
