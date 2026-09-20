from __future__ import annotations

import json
import re
import sys


from kenn.core.lm_identity import APP_NAME
from kenn.llm.llm_rewrite import is_enabled as llm_enabled
from kenn.core.suggestions import starter_questions
from kenn.retrieval.retrieval import (
    query_topics,
    tokenize,
)

from kenn.core.chat_constants import (
    ABLETON_ROUTE_TOPICS,
    BUSINESS_PRICING_TERMS,
    CHECK_IN_INPUTS,
    FOLLOWUP_REFERENCES,
    FOLLOWUP_STARTERS,
    GAME_ROUTE_TOPICS,
    GENERIC_TRACK_TITLE_TERMS,
    GREETING_INPUTS,
    IMPOSSIBLE_PROMISE_TERMS,
    META_CHAT_PATTERNS,
    MIX_REVIEW_FOLLOWUP_TERMS,
    PRODUCTION_ROUTE_TOPICS,
    THANKS_INPUTS,
    UNCLEAR_INPUTS,
    WEBSITE_ROOT,
    mix_review,
)

from kenn.core.chat_retrieval import (
    chunk_search_terms,
    detect_intent,
    normalized_terms,
    query_is_out_of_scope,
    route_memory_match,
)


def clean_history_content(text: str, role: str) -> str:
    if role != "assistant":
        return text
    # Strip bullet lists under "Sources:" or "You could also ask:"
    lines = text.splitlines()
    clean_lines = []
    skip = False
    for line in lines:
        stripped = line.strip()
        if re.search(r"^(?:sources|you could also ask|you could ask)\b", stripped, re.IGNORECASE):
            skip = True
            continue
        if skip:
            if stripped.startswith(("-", "*", "•")) or re.match(r"^\d+[.)]", stripped) or not stripped:
                continue
            else:
                skip = False
        # Remove generated session summaries from assistant content
        if stripped.lower().startswith("[session summary]:") or stripped.lower().startswith("earlier, we were discussing"):
            continue
        clean_lines.append(line)
    return "\n".join(clean_lines).strip()


def normalize_history(history: list | None) -> list[dict]:
    clean: list[dict] = []
    for item in history or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).strip().lower() or "user"
        content = str(item.get("content") or item.get("question") or "").strip()
        if content:
            cleaned_content = clean_history_content(content, role)
            if cleaned_content:
                clean.append({"role": role, "content": cleaned_content})
    return clean[-4:]


def latest_mix_review_context(history: list | None) -> str:
    for turn in reversed(useful_history_user_turns(history)):
        lowered = turn.lower()
        if (
            lowered.startswith("mix review lab context")
            or lowered.startswith("track memory for ")
            or "structured uploaded-track analysis" in lowered
        ):
            return turn
    return ""


def _extract_mix_review_items(context: str, labels: tuple[str, ...], limit: int = 4) -> list[str]:
    items: list[str] = []
    for line in context.splitlines():
        stripped = line.strip()
        lowered = stripped.lower()
        for label in labels:
            prefix = f"{label.lower()}:"
            if not lowered.startswith(prefix):
                continue
            value = stripped[len(label) + 1 :].strip()
            # Older handoff summaries used semicolon-delimited numbered
            # priorities while the current structured handoff uses pipes.
            # Treat only a semicolon immediately introducing another numbered
            # item as a delimiter: ordinary explanatory prose may contain
            # semicolons and must remain intact.
            for part in re.split(r"\s+\|\s+|;\s*(?=#\d+\b)", value):
                clean = part.strip(" -")
                if clean and clean not in items:
                    items.append(clean)
            break
        if len(items) >= limit:
            break
    return items[:limit]


def _mix_review_measurement_facts(context: str) -> list[str]:
    """Return a short, explicitly measured fact list from the handoff.

    This prevents review follow-ups from presenting a priority as if it were
    a direct listening judgement. Only the server's objective-metrics JSON is
    read here; flags, recommendations, and score-like fields are deliberately
    not converted into measurements.
    """
    for line in context.splitlines():
        prefix = "Objective technical metrics:"
        if not line.strip().startswith(prefix):
            continue
        raw = line.strip()[len(prefix) :].strip()
        try:
            values = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
        if not isinstance(values, dict):
            return []
        facts: list[str] = []
        labels = (
            ("true_peak_dbfs", "True peak", "dBFS"),
            ("peak_dbfs", "Peak", "dBFS"),
            ("integrated_lufs", "Integrated loudness", "LUFS"),
            ("crest_factor_db", "Crest factor", "dB"),
            ("stereo_correlation", "Stereo correlation", ""),
        )
        for key, label, unit in labels:
            value = values.get(key)
            if not isinstance(value, (int, float)):
                continue
            suffix = f" {unit}" if unit else ""
            facts.append(f"{label}: {value:g}{suffix}")
        return facts[:4]
    return []


def mix_review_followup_payload(query: str, history: list | None) -> dict | None:
    context = latest_mix_review_context(history)
    if not context:
        return None
    terms = normalized_terms(query)
    is_relevant = (
        should_use_history(query, history)
        or is_unclear_query(query)
        or bool(terms & MIX_REVIEW_FOLLOWUP_TERMS)
    )
    if not is_relevant:
        return None

    # Prefer canonical structured labels before their legacy aliases. The
    # latter may appear in a prose context line ahead of current structured
    # data, which previously flattened several priorities into one sentence.
    priorities = _extract_mix_review_items(
        context,
        ("Structured priority actions",),
        limit=4,
    ) or _extract_mix_review_items(context, ("Priority actions", "Priority action", "Fix first"), limit=4)
    checklist = _extract_mix_review_items(
        context,
        ("Structured revision checklist", "Revision checklist", "Revision steps"),
        limit=4,
    )
    revision_plan_steps = _extract_mix_review_items(
        context,
        ("Structured next revision steps", "Next revision steps", "Fix next"),
        limit=4,
    )
    revision_plan_focus = _extract_mix_review_items(
        context,
        ("Structured next revision focus", "Next revision focus"),
        limit=1,
    )
    ableton_repairs = _extract_mix_review_items(
        context,
        (
            "Structured Ableton repairs",
            "Ableton repair templates",
            "Structured Ableton repair templates",
            "Ableton repair chain",
        ),
        limit=4,
    )
    flags = _extract_mix_review_items(context, ("Structured flags",), limit=4) or _extract_mix_review_items(
        context, ("Flags",), limit=4
    )
    metrics = _extract_mix_review_items(context, ("Structured metrics", "Metrics"), limit=2)
    measurement_facts = _mix_review_measurement_facts(context)
    leave_alone = _extract_mix_review_items(
        context,
        ("Structured leave alone", "Leave alone"),
        limit=4,
    )
    # Split so the payload can tell a UI/caller which specific items are
    # ungrounded suggestions vs. a grounded classification -- these two
    # used to be extracted into one merged bucket with no way to tell them
    # apart afterward (Known Gap #5, docs/KENN_FUTURE_PLAN.md §2): genre
    # classification is a real measured/classified fact, but reference-
    # track EQ moves are a suggested action, not something blind-A/B
    # tested yet (the blind-gate law, §1 Principle 4) -- both used to be
    # stamped with the same hardcoded "grounding_mode": "strong" below,
    # which overclaimed the EQ moves' evidence status.
    genre_items = _extract_mix_review_items(
        context,
        ("Structured genre classification", "Genre classification"),
        limit=4,
    )
    eq_move_items = _extract_mix_review_items(
        context,
        (
            "Structured reference EQ moves",
            "Reference EQ moves",
            "Structured reference comparison",
            "Reference comparison",
            "Reference advice",
        ),
        limit=4,
    )
    reference_notes = list(dict.fromkeys(genre_items + eq_move_items))[:4]
    context_source_label = (
        "saved Mix Review session report for this track"
        if context.lower().startswith("track memory for ")
        else "Mix Review Lab context from the latest uploaded review"
    )

    revision_terms = {
        "next",
        "revision",
        "version",
        "v2",
        "v3",
        "progress",
        "compare",
        "comparison",
        "improve",
        "improved",
    }
    leave_terms = {"leave", "alone", "ignore", "protect", "keep"}
    reference_terms = {"reference", "compare", "comparison", "against"}
    chain_terms = {"ableton", "chain", "rack", "device", "repair", "plugin", "plugins"}
    wants_revision_plan = bool(terms & revision_terms) or is_unclear_query(query)
    wants_leave_alone = bool(terms & leave_terms)
    wants_reference = bool(terms & reference_terms)
    wants_chain = bool(terms & chain_terms)
    if wants_leave_alone and leave_alone:
        steps = leave_alone
        short = f"Leave this alone for now: {steps[0]}"
        section_label = "Protect this:"
        why = "Protecting stable parts of the mix keeps the next revision focused, so you do not create new problems while fixing the main flag."
    elif wants_reference and reference_notes:
        steps = reference_notes
        short = f"Use the reference comparison first: {steps[0]}"
        section_label = "Reference checks:"
        why = "Reference notes are useful only when they guide a specific, level-matched comparison instead of encouraging broad copying."
        used_reference_notes = True
    elif wants_chain and ableton_repairs:
        steps = ableton_repairs
        short = f"Start with this Ableton repair move: {steps[0]}"
        section_label = "Ableton repair chain:"
        why = "A small device-chain move is easier to A/B than broad mix processing, especially after an objective review flag."
    elif wants_revision_plan and (revision_plan_steps or revision_plan_focus):
        steps = [
            *revision_plan_steps,
            *[item for item in priorities if item not in revision_plan_steps],
            *[
                item
                for item in ableton_repairs
                if item not in revision_plan_steps and item not in priorities
            ],
            *[
                item
                for item in checklist
                if item not in revision_plan_steps
                and item not in priorities
                and item not in ableton_repairs
            ],
        ]
        short = (
            f"Start with: {steps[0]}"
            if steps
            else "Start with one focused revision from the latest review."
        )
        section_label = "Try this:"
        why = "This is using the uploaded-track analysis from the latest review, so it should take priority over generic mixing notes."
    else:
        # A "what first?" request needs a short, ordered decision list. Do
        # not append device-chain templates until the user explicitly asks
        # for a repair chain; mixing those legacy templates into priorities
        # previously yielded one huge semicolon-delimited fifth step.
        steps = priorities or [
            *ableton_repairs,
            *[item for item in checklist if item not in ableton_repairs],
        ]
        short = (
            f"Start with: {steps[0]}"
            if steps
            else "Start with one focused revision from the latest review."
        )
        section_label = "Try this:"
        why = "This is using the uploaded-track analysis from the latest review, so it should take priority over generic mixing notes."
    if not steps and flags:
        steps = [f"Address this review flag first: {flags[0]}"]
    if not steps:
        steps = [
            "Re-open the latest review, make one focused revision, then upload the new export for comparison."
        ]
    short = short if "short" in locals() else f"Start with: {steps[0]}"
    section_label = section_label if "section_label" in locals() else "Try this:"
    why = (
        why
        if "why" in locals()
        else "This is using the uploaded-track analysis from the latest review, so it should take priority over generic mixing notes."
    )
    contains_unvalidated_eq_moves = (
        "used_reference_notes" in locals() and used_reference_notes and bool(eq_move_items)
    )

    answer_mode = classify_answer_mode(query, "mix_review_followup", history=history)
    lines = [
        f"Based on the {context_source_label}.",
        "",
        "Short answer:",
        short,
        "",
        section_label,
    ]
    # The chosen first priority is already stated in the short answer. Start
    # the ordered list after it so a review response does not echo its first
    # action twice before offering a next move.
    display_steps = steps[1:5] if short.startswith("Start with:") else steps[:5]
    for index, step in enumerate(display_steps, start=2 if short.startswith("Start with:") else 1):
        lines.append(f"{index}. {step}")
    if measurement_facts:
        lines.extend(["", "Measured evidence from the uploaded file:", *[f"- {fact}" for fact in measurement_facts]])
    if flags:
        lines.extend(["", "Review flags:", *[f"- {flag}" for flag in flags[:4]]])
    if metrics and not measurement_facts:
        lines.extend(["", "Useful metrics:", *[f"- {metric}" for metric in metrics[:2]]])
    if revision_plan_focus:
        lines.extend(["", "Next revision focus:", f"- {revision_plan_focus[0]}"])
    lines.extend(
        [
            "",
            "Why it matters:",
            why,
            "",
            "Sources:",
            f"- {context_source_label}",
        ]
    )
    answer = "\n".join(lines).strip()
    return {
        "question": query,
        "answer": answer,
        "sources": [
            {
                "label": context_source_label,
                "source": "mix_review_history",
                "page": 1,
                "kind": "note",
                "score": 20.0,
            }
        ],
        "found": True,
        "confidence": "high",
        "source_quality": "high",
        "topics": ["mix_review"],
        "intent": detect_intent(query),
        "route": "mix_review_followup",
        "answer_mode": answer_mode,
        "answer_quality": {
            "score": 100,
            "mode": answer_mode,
            "warnings": [],
            "sections": {"short_answer": True, "try_this": True, "sources": True},
            "actionable_steps": len(steps[:5]),
        },
        "intent_guard": "not_needed",
        "weak_match": False,
        "search_query": query,
        "diagnostic_reason": f"Answered from the {context_source_label} in conversation history.",
        "answer_self_check": {
            "passed": True,
            "warnings": [],
            "sections": {
                "short_answer": True,
                "try_this": True,
                "check": bool(flags or metrics),
                "sources": True,
            },
            "source_topic_match": True,
            "answered_intent": True,
        },
        "grounding": {
            "score": 100,
            "top_source_trust": 1.0,
            "approved_note": True,
            "source_topic_match": True,
            "answered_intent": True,
            "route_known": True,
            "warnings": [],
        },
        "grounding_mode": "strong",
        # NOT the same as grounding_mode above -- that stays "strong"
        # because the response is genuinely built from the user's own
        # completed review (not a hallucinated LLM guess). This flags a
        # narrower, more specific thing: whether the answer includes a
        # *suggested* EQ move that hasn't passed the blind-gate law yet
        # (§1 Principle 4), as opposed to a measured/classified fact like
        # genre. Known Gap #5's actual bug: this used to not exist at all,
        # so the UI had no way to tell the two apart.
        "contains_unvalidated_suggestions": contains_unvalidated_eq_moves,
        "related_questions": [
            "What should I change before the next export?",
            "How do I compare the next revision?",
            "Which review flag matters most?",
        ],
        "used_history": True,
        "llm_enhanced": False,
        "llm_available": llm_enabled(),
        "conversation_only": False,
        "branches": [],
        "session": None,
    }


def conversational_intent(query: str) -> str:
    cleaned = re.sub(r"[^\w\s]+", " ", str(query).lower()).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)

    if cleaned in GREETING_INPUTS:
        return "greeting"
    if cleaned in CHECK_IN_INPUTS:
        return "check_in"
    if cleaned in THANKS_INPUTS:
        return "thanks"
    if cleaned in {"help", "what can you do", "what can i ask", "show suggestions"}:
        return "help"

    # Substring / compound check for greetings, check-ins, and thanks
    for thanks in THANKS_INPUTS:
        if thanks in cleaned:
            return "thanks"
    for check_in in CHECK_IN_INPUTS:
        if check_in in cleaned:
            return "check_in"

    # Friendly greeting prefix with no specific technical audio domain topics
    words = cleaned.split()
    if words and words[0] in {"hello", "hey", "hi", "hiya", "yo", "good morning", "good afternoon", "good evening"}:
        if len(words) <= 7 and not query_topics(query):
            return "check_in" if any(w in cleaned for w in ("doing", "going", "you", "today", "right")) else "greeting"

    if any(w in cleaned for w in ("joke", "funny", "humour", "humor", "banter")):
        return "joke"

    if any(re.search(pattern, cleaned) for pattern in META_CHAT_PATTERNS):
        return "meta"

    # General knowledge / non-technical queries that don't match any KENN technical topics
    gk_patterns = [
        r"^(?:what\s+is|who\s+is|who\s+was|who\s+were|how\s+many|why\s+is|when\s+did|where\s+is|tell\s+me\s+about|what\s+does\s+the\s+word|explain\s+to\s+me)\b",
        r"\b(?:capital\s+of|population\s+of|definition\s+of)\b"
    ]
    if any(re.search(pattern, cleaned) for pattern in gk_patterns):
        if not query_topics(query):
            return "general_knowledge"

    return ""


def cleaned_query(query: str) -> str:
    cleaned = re.sub(r"[^\w\s]+", " ", str(query).lower()).strip()
    return re.sub(r"\s+", " ", cleaned)


def is_unclear_query(query: str) -> bool:
    cleaned = cleaned_query(query)
    if cleaned in UNCLEAR_INPUTS:
        return True
    raw_words = set(cleaned.split())
    if raw_words & FOLLOWUP_REFERENCES and len(raw_words) <= 9 and cleaned.startswith(
        ("should i", "do i", "can i", "would it", "what kind", "what relationship", "why is that", "why does that")
    ):
        return True
    terms = tokenize(query)
    return 0 < len(terms) <= 2 and not query_topics(query) and not conversational_intent(query)


def conversational_payload(query: str, history: list | None = None) -> dict | None:
    # Scope handling belongs to the main answer path, where it returns the
    # explicit low-confidence boundary response.  Do not let a friendly
    # conversational fallback override it with a high-confidence result.
    if query_is_out_of_scope(query):
        return None
    intent = conversational_intent(query)
    # General-knowledge questions are not a conversational answer KENN can
    # ground. Let retrieval's weak-match path abstain rather than presenting
    # a generic studio greeting as a confident answer.
    if intent == "general_knowledge":
        return None
    if not intent:
        return None
    history_used = bool(normalize_history(history))
    starters = starter_questions(limit=5)
    llm_res = None
    if llm_enabled():
        try:
            from kenn.llm.llm_rewrite import generate_conversational_llm_response
            llm_res = generate_conversational_llm_response(query, history=history)
        except Exception:
            pass

    if llm_res:
        answer = llm_res
    else:
        h = abs(hash(query)) % 4
        if intent == "thanks":
            responses = [
                "Anytime! Let me know if you want to test another move in the session.",
                "You got it! I'm right here whenever you want to work through the next track.",
                "Happy to help! Let's keep the momentum going on this project.",
                "Cheers! Let me know what track or mix problem we're tackling next.",
            ]
            answer = responses[h]
        elif intent == "check_in":
            responses = [
                "Doing great, thanks! Ready to dive into some audio. What are we working on today?",
                "All good on my end! The studio setup is warmed up—what track are we tuning or mixing?",
                "Feeling sharp! Ready to inspect stems, fix phase issues, or chat through mix decisions. What's on your mind?",
                "Everything's running smoothly! Let me know what session problem we should solve next.",
            ]
            answer = responses[h]
        elif intent == "meta":
            answer = (
                f"No worries! I am {APP_NAME} — your studio AI companion for Ableton, mixing, mastering, "
                "stems, client deliverables, and audio production workflow. Ask me anything!"
            )
        elif intent == "help":
            answer = (
                "Talk to me like an engineer in the control room. Ask about vocal sibilance, kick/bass phase, "
                "plugin routing, client invoices, or mix reviews—I'm here to help."
            )
        elif intent == "joke":
            jokes = [
                "Why do sound engineers only count to two? Because on three you have to lift! ...And on four, someone asks for more low end in their monitors.",
                "How many audio engineers does it take to change a lightbulb? Just one, but they'll spend 4 hours auditioning 12 different bulbs for 'analog warmth'.",
                "What's the difference between a recording engineer and a pizza? A pizza can feed a family of four!",
                "An engineer walks into a bar... and immediately tries to find the 2.5 kHz resonant frequency of the room reflections.",
            ]
            answer = jokes[h]
        elif intent == "general_knowledge":
            answer = "I'm focused on your audio sessions, but let me know what we're mixing or mastering today!"
        else:
            responses = [
                "Hey! Good to have you in the studio. What are we focusing on today?",
                "Yo! Ready when you are. What are we mixing, tweaking, or building next?",
                "Hey there! Got a specific audio problem or track to review?",
                "Good day! I'm set for session work or production chat. What's the plan?",
            ]
            answer = responses[h]

    return {
        "question": query,
        "answer": answer,
        "sources": [],
        "found": True,
        "confidence": "high",
        "source_quality": "not_needed",
        "topics": [],
        "related_questions": starters,
        "used_history": history_used,
        "llm_enhanced": bool(llm_res),
        "llm_available": llm_enabled(),
        "conversation_only": True,
        "intent": intent,
        "route": "conversation",
        "branches": [],
        "session": None,
    }


def clarification_payload(query: str, history: list | None = None, reason: str = "unclear", answer_mode: str = "") -> dict:
    history_used = bool(normalize_history(history))
    
    # Detect repeated failed clarification
    consecutive_clarifications = 0
    if history:
        for turn in reversed(normalize_history(history)):
            if turn.get("role") == "assistant":
                content = turn.get("content", "").lower()
                if "need one bit more direction" in content or "reset/rephrase" in content or "trouble matching your question" in content:
                    consecutive_clarifications += 1
                else:
                    break
                    
    if consecutive_clarifications >= 1:
        if answer_mode == "voice":
            answer = (
                "I'm still having trouble matching your question to my local audio engineering knowledge. "
                "Let's reset. You can ask a direct production question like 'how do I sidechain bass to the kick', "
                "ask about Ableton workflows, or ask about Wwise. Or you can clear this conversation's state by saying 'reset'."
            )
        else:
            answer = (
                "I'm still having trouble matching your question to my local audio engineering knowledge. "
                "Let's reset. Try asking your question in one of these clear formats:\n\n"
                "1. Ask a direct production question: 'How do I sidechain bass to the kick?'\n"
                "2. Ask about an Ableton Live workflow: 'How do I automate send levels on a track?'\n"
                "3. Ask about Wwise or game audio: 'How do I trigger an event in Wwise?'\n\n"
                "Or, you can clear this conversation's state entirely by typing 'reset'."
            )
    else:
        if answer_mode == "voice":
            answer = (
                "I can help, but I need a little more direction first. Are you asking about a mix problem, "
                "an Ableton workflow, mastering, arrangement, game audio, or a mix review?"
            )
        else:
            answer = (
                "I can help, but I need one bit more direction first. Are you asking about a mix problem, "
                "an Ableton workflow, mastering, arrangement, game audio, or an uploaded mix review?"
            )

    return {
        "question": query,
        "answer": answer,
        "sources": [],
        "found": False,
        "weak_match": True,
        "confidence": "low",
        "source_quality": "not_needed",
        "topics": [],
        "related_questions": [
            "How do I fix muddy low mids?",
            "What should I check first in this mix?",
            "How do I export stems from Ableton?",
            "How do I make vocals wider without mud?",
        ],
        "used_history": history_used,
        "llm_enhanced": False,
        "llm_available": llm_enabled(),
        "conversation_only": True,
        "intent": "clarify",
        "route": "clarify",
        "diagnostic_reason": f"KENN asked for clarification because the query was {reason}.",
        "branches": [],
        "session": None,
    }


def impossible_promise_query(query: str) -> bool:
    terms = normalized_terms(query)
    if not (terms & IMPOSSIBLE_PROMISE_TERMS):
        return False
    audio_terms = {"ableton", "mix", "master", "professional", "vocal", "vocals"}
    return bool(terms & audio_terms)


def impossible_promise_payload(query: str, history: list | None = None, answer_mode: str = "") -> dict:
    if answer_mode == "voice":
        answer = (
            "There is no single secret setting that instantly makes a vocal sound professional. "
            "A professional vocal requires a solid chain of good recording source quality, editing, corrective EQ, dynamics control, and send effects. "
            "Try starting with source cleanup and subtle, progressive moves instead of looking for shortcuts."
        )
    else:
        answer = (
            "There is no single secret setting that makes a vocal professional instantly.\n\n"
            "Short answer:\n"
            "Treat it as a chain of source quality, editing, tuning, EQ, dynamics, de-essing, level, and space. "
            "If the local notes do not support a shortcut claim, I will not invent one.\n\n"
            "Try this:\n"
            "1. Start with the source: comp the best take, clean obvious noise, and fix timing or tuning problems first.\n"
            "2. Use corrective EQ and de-essing only where the vocal actually has harshness, boxiness, or sibilance.\n"
            "3. Add compression, level automation, and send effects in small moves, then A/B at matched loudness.\n\n"
            "Listening check:\n"
            "The vocal should stay clear when the beat returns, not only when it is soloed.\n\n"
            "Sources:\n"
            "- No single-setting shortcut exists in the approved local notes."
        )
    return {
        "question": query,
        "answer": answer,
        "sources": [],
        "found": False,
        "confidence": "low",
        "source_quality": "low",
        "topics": query_topics(query),
        "related_questions": [
            "How do I use compressor on vocals?",
            "How do I fix harsh S sounds on vocals?",
            "How do I add body to a thin vocal without making it muddy?",
        ],
        "used_history": bool(normalize_history(history)),
        "llm_enhanced": False,
        "llm_available": llm_enabled(),
        "conversation_only": False,
        "intent": "out_of_scope",
        "route": "unsupported_claim",
        "answer_mode": answer_mode or "quick_fix",
        "answer_quality": {
            "score": 72,
            "mode": "quick_fix",
            "warnings": ["unsupported shortcut claim refused"],
            "sections": {"short_answer": True, "try_this": True, "sources": True, "check": True},
            "actionable_steps": 3,
        },
        "intent_guard": "not_needed",
        "weak_match": True,
        "search_query": query,
        "diagnostic_reason": "Question asked for an unsupported instant shortcut, so KENN refused the premise.",
        "answer_self_check": {
            "passed": True,
            "warnings": ["unsupported shortcut claim refused"],
            "sections": {"short_answer": True, "try_this": True, "check": True, "sources": True},
            "source_topic_match": False,
            "answered_intent": True,
        },
        "grounding": {
            "score": 45,
            "top_source_trust": 0.0,
            "approved_note": False,
            "source_topic_match": False,
            "answered_intent": True,
            "route_known": True,
            "warnings": ["unsupported shortcut claim refused"],
        },
        "grounding_mode": "weak",
        "branches": [],
        "session": None,
    }


def business_pricing_query(query: str) -> bool:
    terms = normalized_terms(query)
    if not (terms & BUSINESS_PRICING_TERMS):
        return False
    return bool(
        terms & {"mix", "mixing", "master", "mastering", "stem", "stems", "client", "revision"}
    )


def constrain_results_for_query(
    query: str, results: list[tuple[float, dict]]
) -> list[tuple[float, dict]]:
    """Remove clearly unrelated production notes from strict business answers."""
    if not business_pricing_query(query):
        return results
    pricing_terms = {"business", "price", "pricing", "quote", "quoting", "rate", "scope", "discount"}
    relevant = [
        item
        for item in results
        if chunk_search_terms(item[1]) & pricing_terms
    ]
    return relevant or results


def business_pricing_payload(query: str, history: list | None = None) -> dict:
    return {
        "question": query,
        "answer": (
            "I do not have a reliable local pricing policy for that yet, so I am not going to invent a rate.\n\n"
            "Short answer:\n"
            "Use the business/admin workflow for quotes, or add an approved pricing note before Kenn gives pricing advice.\n\n"
            "Try this:\n"
            "1. Gather the scope: song count, stem count, editing needs, deadline, revision allowance, and deliverables.\n"
            "2. Compare that scope against your actual service packages or admin quote template.\n"
            "3. If you want Kenn to answer pricing consistently, add an approved pricing note and an eval case.\n\n"
            "Check:\n"
            "Do not let a retrieval answer make up numbers for client-facing pricing.\n\n"
            "Sources:\n"
            "- No approved local pricing source found."
        ),
        "sources": [],
        "found": False,
        "confidence": "low",
        "source_quality": "low",
        "topics": query_topics(query),
        "related_questions": [
            "How many mix revisions should I include?",
            "How should a client send stems for mixing?",
            "How do I deliver the final mix to a client?",
        ],
        "used_history": bool(normalize_history(history)),
        "llm_enhanced": False,
        "llm_available": llm_enabled(),
        "conversation_only": False,
        "intent": "out_of_scope",
        "route": "business_pricing",
        "answer_mode": "client_delivery",
        "answer_quality": {
            "score": 72,
            "mode": "client_delivery",
            "warnings": ["pricing source missing"],
            "sections": {"short_answer": True, "try_this": True, "sources": True, "check": True},
            "actionable_steps": 3,
        },
        "intent_guard": "not_needed",
        "weak_match": True,
        "search_query": query,
        "diagnostic_reason": "Question needs client-pricing policy, but no approved local pricing source is indexed.",
        "answer_self_check": {
            "passed": True,
            "warnings": ["pricing source missing"],
            "sections": {"short_answer": True, "try_this": True, "check": True, "sources": True},
            "source_topic_match": False,
            "answered_intent": True,
        },
        "grounding": {
            "score": 45,
            "top_source_trust": 0.0,
            "approved_note": False,
            "source_topic_match": False,
            "answered_intent": True,
            "route_known": True,
            "warnings": ["pricing source missing"],
        },
        "grounding_mode": "weak",
        "branches": [],
        "session": None,
    }


def _resolve_or_create_automix_project(session_id: str) -> str:
    """Mirrors server.py::resolve_session_project()'s resolve-or-create
    logic -- can't import that directly (server.py imports this module,
    the reverse would be circular), so this is a small, self-contained
    duplicate for the one caller here that needs project continuity
    (D3.2's AudioGen->AutoMix chain, which needs a project_id for the
    stem upload + AutoMix job it queues)."""
    if not session_id:
        return ""
    try:
        from kenn.core.session_memory import get_remembered_automix_project, remember_automix_project
        existing = get_remembered_automix_project(session_id)
        if existing:
            return existing
        if str(WEBSITE_ROOT) not in sys.path:
            sys.path.insert(0, str(WEBSITE_ROOT))
        import song_projects
        project = song_projects.create_project()
        remember_automix_project(session_id, project["id"])
        return project["id"]
    except Exception:
        return ""


def audio_generation_payload(query: str, *, session_id: str = "") -> dict | None:
    if set(query_topics(query)) & GAME_ROUTE_TOPICS:
        return None
    if str(WEBSITE_ROOT) not in sys.path:
        sys.path.insert(0, str(WEBSITE_ROOT))
    try:
        import audiogen_bridge
    except Exception as exc:
        print(f"WARNING: audiogen_bridge import failed ({exc!r}) -- "
              f"audio-generation requests will silently fall through to normal chat routing")
        return None
    if not audiogen_bridge.prompt_requests_generation(query):
        return None
    kind = getattr(audiogen_bridge, "generation_request_kind", lambda value: "loop")(query)
    if kind == "clarify":
        emotion = getattr(audiogen_bridge, "infer_emotion", lambda value: "joy")(query)
        return {
            "question": query,
            "answer": (
                f"I can make that in the {emotion} emotion mode. Do you want a short loop/chorus idea, "
                "or a full-song render?\n\n"
                "Short answer:\n"
                "Say either `generate a loop` or `generate a full song`, and I will route it to AudioGen.\n\n"
                "Try this:\n"
                f"1. Generate a {emotion} loop.\n"
                f"2. Generate a full {emotion} song.\n"
                "3. After it renders, ask me how to arrange or mix it."
            ),
            "sources": [],
            "found": False,
            "confidence": "medium",
            "source_quality": "not_needed",
            "topics": ["audiogen", "composition"],
            "related_questions": [
                f"Generate a {emotion} loop",
                f"Generate a full {emotion} song",
                "How should I mix the generated idea?",
            ],
            "used_history": False,
            "llm_enhanced": False,
            "llm_available": False,
            "intent": "generate",
            "route": "audiogen",
            "weak_match": False,
            "grounding_mode": "strong",
            "grounding": {"score": 80, "warnings": ["AudioGen render type needs confirmation"]},
            "conversation_only": True,
            "audiogen": {"ok": True, "emotion": emotion, "kind": "clarify"},
            "branches": [],
            "session": None,
        }

    if kind == "full_song":
        # D3.2 (docs/KENN_FUTURE_PLAN.md Phase 3): "generate drums and
        # bassline, then render an AutoMix pass from these" -- the actual
        # stem-capture -> zip -> upload -> queue_job chain
        # (queue_automix_from_stem_files() in audiogen_bridge.py) already
        # existed and worked, but was only reachable via the authenticated
        # Creative Lab dashboard route, never from KENN's own chat. Same
        # class of reachability gap as the mix-revision one found earlier
        # this session -- checked for it specifically this time.
        chain_to_automix = audiogen_bridge.requests_automix_chain(query)
        chain_project_id = _resolve_or_create_automix_project(session_id) if chain_to_automix else ""
        job = audiogen_bridge.enqueue_full_song_render(
            emotion=audiogen_bridge.infer_emotion(query),
            bars=4,
            k=1,
            publish=True,
            project_id=chain_project_id,
            chain_to_automix=chain_to_automix,
        )
        if not job.get("ok"):
            return {
                "question": query,
                "answer": (
                    "I understood that as a full-song AudioGen request, but I could not queue it.\n\n"
                    "Short answer:\n"
                    f"{job.get('error', 'AudioGen did not return a usable queue response.')}\n\n"
                    "Try this:\n"
                    "1. Open the dashboard AudioGen tab.\n"
                    "2. Check the render queue.\n"
                    "3. Try a smaller bar setting if the renderer is under load."
                ),
                "sources": [],
                "found": False,
                "confidence": "low",
                "source_quality": "low",
                "topics": ["audiogen"],
                "related_questions": [],
                "used_history": False,
                "llm_enhanced": False,
                "llm_available": False,
                "intent": "generate",
                "route": "audiogen",
                "weak_match": True,
                "grounding_mode": "weak",
                "grounding": {"score": 0, "warnings": ["AudioGen queue failed"]},
                "audiogen": job,
            }
        queued = job.get("job") or {}
        emotion = queued.get("emotion", "joy")
        if chain_to_automix:
            answer = (
                f"Done. I queued a full AudioGen song with the {emotion} emotion profile, and it'll "
                "chain straight into an AutoMix render once the stems are captured.\n\n"
                "Short answer:\n"
                "The render is running in the background -- once AudioGen finishes, the captured stems "
                "get zipped, uploaded, and a real AutoMix job starts automatically.\n\n"
                "Try this:\n"
                "1. Open the dashboard AudioGen tab and watch the render queue.\n"
                "2. Once it completes, check the AutoMix dashboard for the mixdown.\n"
                "3. Ask me for a revision once you've heard it."
            )
        else:
            answer = (
                f"Done. I queued a full AudioGen song with the {emotion} emotion profile.\n\n"
                "Short answer:\n"
                "The render is running in the background, so the chat stays usable while AudioGen works.\n\n"
                "Try this:\n"
                "1. Open the dashboard AudioGen tab and watch the render queue.\n"
                "2. When the job completes, load it into the player or open the WAV from the portfolio audio list.\n"
                "3. Ask me to review the generated song structure or suggest mix changes."
            )
        return {
            "question": query,
            "answer": answer,
            "sources": [
                {
                    "label": "LLM_AudioGen render queue",
                    "source": queued.get("id", ""),
                    "kind": "audiogen_queue",
                    "score": 1.0,
                }
            ],
            "found": True,
            "confidence": "high",
            "source_quality": "generated",
            "topics": ["audiogen", "composition"],
            "related_questions": [
                "Check my latest AudioGen render",
                "How should I arrange this generated song?",
                "How should I mix the generated song?",
            ],
            "used_history": False,
            "llm_enhanced": False,
            "llm_available": False,
            "intent": "generate",
            "route": "audiogen",
            "weak_match": False,
            "grounding_mode": "strong",
            "grounding": {
                "score": 100,
                "top_source_trust": 1.0,
                "approved_note": False,
                "source_topic_match": True,
                "answered_intent": True,
                "route_known": True,
                "warnings": [],
            },
            "audiogen": job,
            "chained_to_automix": chain_to_automix,
        }

    generation = audiogen_bridge.generate_for_kenn(query)
    if not generation.get("ok"):
        return {
            "question": query,
            "answer": (
                "I understood that as an AudioGen request, but local generation failed.\n\n"
                "Short answer:\n"
                f"{generation.get('error', 'AudioGen did not return a usable result.')}\n\n"
                "Try this:\n"
                "1. Run `./audio-too audiogen status`.\n"
                "2. Run `./audio-too audiogen phrase --emotion joy --bars 8`.\n"
                "3. If that fails, run `./audio-too audiogen test`."
            ),
            "sources": [],
            "found": False,
            "confidence": "low",
            "source_quality": "low",
            "topics": ["audiogen"],
            "related_questions": [],
            "used_history": False,
            "llm_enhanced": False,
            "llm_available": False,
            "intent": "generate",
            "route": "audiogen",
            "weak_match": True,
            "grounding_mode": "weak",
            "grounding": {"score": 0, "warnings": ["AudioGen generation failed"]},
            "audiogen": generation,
        }

    entry = generation.get("portfolio_entry") or {}
    wav_path = str(generation.get("wav_path", ""))

    # "...and load it into track 2" -- send the rendered loop straight to
    # Ableton via OSC instead of making the user do it manually.
    load_message = ""
    load_success = False
    track_match = re.search(r"\btrack\s*(\d+)\b", query, re.I)
    if track_match and wav_path:
        target_track_idx = int(track_match.group(1)) - 1
        try:
            from kenn.ableton_osc_bridge import live_client

            if live_client.load_clip(target_track_idx, 0, wav_path):
                load_success = True
                load_message = (
                    f"\n- Loaded into Ableton track {target_track_idx + 1} via OSC."
                )
            else:
                load_message = (
                    "\n- Could not load into Ableton (OSC client offline)."
                )
        except Exception as exc:
            load_message = f"\n- Failed to dispatch clip to Ableton: {exc}"

    # D3.5 (docs/KENN_FUTURE_PLAN.md Phase 3): "my loop is too
    # repetitive, give me a variation" -- re-running generation already
    # naturally produces a different render (no fixed seed pinning), so
    # this is purely a framing difference in the reply, not new
    # generation logic.
    is_variation = audiogen_bridge.requests_variation(query)
    opening = (
        f"Here's a variation with the {generation.get('emotion', 'joy')} profile."
        if is_variation
        else f"Done. I generated an AudioGen chorus with the {generation.get('emotion', 'joy')} profile."
    )
    answer = (
        f"{opening}\n\n"
        "Short answer:\n"
        "The WAV has been rendered locally and added to the portfolio audio list.\n\n"
        "Try this:\n"
        "1. Open the portfolio and play the generated audio example.\n"
        "2. Ask for a different emotion, seed, or bar length if you want a variation.\n"
        "3. For a complete arrangement, run `./audio-too audiogen render --emotion "
        f"{generation.get('emotion', 'joy')}`.\n\n"
        "Sources:\n"
        f"- LLM_AudioGen local generator ({wav_path}){load_message}"
    )
    if entry.get("src"):
        answer += (
            f"\n- Portfolio entry: {entry.get('title', 'AudioGen render')} ({entry.get('src')})"
        )
    generation["load_success"] = load_success
    return {
        "question": query,
        "answer": answer,
        "is_variation": is_variation,
        "sources": [
            {
                "label": "LLM_AudioGen local generator",
                "source": wav_path,
                "kind": "audiogen",
                "score": 1.0,
            }
        ],
        "found": True,
        "confidence": "high",
        "source_quality": "generated",
        "topics": ["audiogen", "composition"],
        "related_questions": [
            "Generate a love chorus with a different seed",
            "Render a full AudioGen song",
            "How should I mix this generated chorus?",
        ],
        "used_history": False,
        "llm_enhanced": False,
        "llm_available": False,
        "intent": "generate",
        "route": "audiogen",
        "weak_match": False,
        "grounding_mode": "strong",
        "grounding": {
            "score": 100,
            "top_source_trust": 1.0,
            "approved_note": False,
            "source_topic_match": True,
            "answered_intent": True,
            "route_known": True,
            "warnings": [],
        },
        "audiogen": generation,
    }


def mix_review_timeline_lookup(query: str) -> tuple[str, list[dict]] | None:
    if not mix_review:
        return None

    query_lower = query.lower()
    timeline_keywords = {
        "timeline",
        "evolution",
        "evolved",
        "history",
        "progress",
        "version",
        "versions",
        "compare",
    }
    query_tokens = set(tokenize(query_lower))

    if not (query_tokens & timeline_keywords):
        return None

    reviews = mix_review.list_reviews(limit=200)
    if not reviews:
        return None

    # Group reviews by title
    tracks = {}
    for r in reviews:
        title = r.get("title", "")
        if not title:
            continue
        tracks.setdefault(title, []).append(r)

    best_title = None
    best_overlap = 0
    best_track_reviews = []

    for title, track_reviews in tracks.items():
        title_tokens = set(tokenize(title.lower()))
        if not title_tokens:
            continue
        overlap = len(query_tokens & title_tokens)
        if overlap > best_overlap:
            best_overlap = overlap
            best_title = title
            best_track_reviews = track_reviews

    if best_overlap > 0 and best_track_reviews:
        sorted_reviews = sorted(best_track_reviews, key=lambda x: x.get("created_at", ""))
        return best_title, sorted_reviews

    # Default to the most recent track if timeline keywords matched but no title overlap
    if reviews:
        sorted_reviews_by_date = sorted(
            reviews, key=lambda x: x.get("created_at", ""), reverse=True
        )
        best_title = sorted_reviews_by_date[0].get("title", "")
        best_track_reviews = tracks.get(best_title, [])
        sorted_reviews = sorted(best_track_reviews, key=lambda x: x.get("created_at", ""))
        return best_title, sorted_reviews

    return None


def latest_track_memory_lookup(query: str) -> dict | None:
    if not mix_review:
        return None
    normalized_query = " ".join(tokenize(query.lower()))
    query_tokens = set(tokenize(query.lower())) - GENERIC_TRACK_TITLE_TERMS
    if not query_tokens:
        return None
    try:
        reviews = mix_review.list_reviews(limit=200)
    except Exception as exc:
        print(f"WARNING: latest_track_memory_lookup: mix_review.list_reviews failed ({exc!r}) -- "
              f"treated identically to 'no matching track found'")
        return None
    best: tuple[int, dict] | None = None
    for review in reviews:
        title = str(review.get("title", "")).strip()
        if not title:
            continue
        normalized_title = " ".join(tokenize(title.lower()))
        title_tokens = set(tokenize(title.lower())) - GENERIC_TRACK_TITLE_TERMS
        if normalized_title and normalized_title in normalized_query:
            return review
        if not title_tokens:
            continue
        overlap = len(query_tokens & title_tokens)
        if overlap <= 0:
            continue
        if not best or overlap > best[0]:
            best = (overlap, review)
    if not best:
        return None
    return best[1]


def format_track_memory(review: dict) -> str:
    session_report = (
        review.get("session_report") if isinstance(review.get("session_report"), dict) else {}
    )
    handoff = review.get("kenn_handoff") if isinstance(review.get("kenn_handoff"), dict) else {}
    memory_lines = [
        str(line).strip()
        for line in session_report.get("kenn_memory_lines", [])
        if str(line).strip()
    ]
    if not memory_lines:
        memory_lines = [
            str(line).strip() for line in handoff.get("context_lines", []) if str(line).strip()
        ][:8]
    title = str(
        review.get("title") or session_report.get("title") or "latest reviewed track"
    ).strip()
    lines = [
        f"Track memory for {title}.",
        "Use this latest Mix Review session report when the user asks about this track, unless they ask for a different version.",
    ]
    lines.extend(memory_lines[:8])
    return "\n".join(line for line in lines if line)


def format_timeline_report(title: str, timeline: list[dict]) -> str:
    lines = []
    lines.append(f"# Mix Review Timeline: {title}")
    lines.append(f"Found {len(timeline)} review(s) for this track, showing evolution over time.\n")

    for i, review in enumerate(timeline, 1):
        version = review.get("version_label") or review.get("version") or f"v{i}"
        created = review.get("created_at") or "Unknown Date"
        metrics = review.get("metrics") or {}
        score = metrics.get("technical_score") or review.get("score")
        rating = metrics.get("technical_rating") or review.get("rating") or "N/A"
        summary = review.get("summary") or ""

        lines.append(f"### Version: {version} ({created})")
        if score is not None:
            lines.append(f"- **Technical Score**: {score}/100 ({rating})")
        else:
            lines.append(f"- **Technical Rating**: {rating}")

        peak = metrics.get("peak_dbfs") or review.get("peak_dbfs")
        rms = metrics.get("rms_dbfs_estimate") or review.get("rms_dbfs_estimate")
        crest = metrics.get("crest_factor_db") or review.get("crest_factor_db")

        metric_parts = []
        if peak is not None:
            metric_parts.append(
                f"Peak: {peak:.1f} dBFS" if isinstance(peak, (int, float)) else f"Peak: {peak}"
            )
        if rms is not None:
            metric_parts.append(
                f"RMS: {rms:.1f} dBFS" if isinstance(rms, (int, float)) else f"RMS: {rms}"
            )
        if crest is not None:
            metric_parts.append(
                f"Crest Factor: {crest:.1f} dB"
                if isinstance(crest, (int, float))
                else f"Crest Factor: {crest}"
            )

        if metric_parts:
            lines.append(f"- **Metrics**: {', '.join(metric_parts)}")

        if summary:
            lines.append(f"- **Summary**: {summary}")

        flags = review.get("flags") or []
        if flags:
            clean_flags = []
            for f in flags:
                if isinstance(f, dict):
                    clean_flags.append(f.get("label") or f.get("name") or str(f))
                else:
                    clean_flags.append(str(f))
            lines.append(f"- **Flags**: {', '.join(clean_flags)}")

        lines.append("")

    return "\n".join(lines).strip()


def route_query(query: str, history: list | None = None) -> str:
    """Route a query to the appropriate handler.

    Uses keyword-based routing first, then falls back to LLM-based classification
    when the keyword approach returns 'unknown'.
    """
    memory = route_memory_match(query)
    if memory:
        return str(memory.get("target_route") or "unknown")
    if conversational_intent(query):
        return "conversation"
    topics = set(query_topics(query))
    if topics & GAME_ROUTE_TOPICS:
        return "game_audio"
    if latest_mix_review_context(history) and (
        should_use_history(query, history) or is_unclear_query(query)
    ):
        return "mix_review_followup"
    if should_use_history(query, history):
        history_topics = set(query_topics(search_query_with_history(query, history)))
        if history_topics & {"mix_review"}:
            return "mix_review"
        if history_topics & GAME_ROUTE_TOPICS:
            return "game_audio"
        if history_topics & ABLETON_ROUTE_TOPICS:
            return "ableton"
        if history_topics & PRODUCTION_ROUTE_TOPICS:
            return "production"
    if is_unclear_query(query):
        return "clarify"
    if query_is_out_of_scope(query):
        return "out_of_scope"
    if topics & {"mix_review"}:
        return "mix_review"
    if topics & ABLETON_ROUTE_TOPICS:
        return "ableton"
    if topics & PRODUCTION_ROUTE_TOPICS:
        return "production"

    # LLM routing fallback: when keyword routing fails, ask the model
    try:
        from kenn.llm.llm_rewrite import llm_route_query as _llm_route
        llm_route = _llm_route(query)
        if llm_route:
            return llm_route
    except ImportError:
        pass
    except Exception as exc:
        print(f"WARNING: LLM routing fallback raised ({exc!r}) -- "
              f"falling through to 'unknown' route, indistinguishable from the LLM simply not being confident")

    return "unknown"


def classify_answer_mode(query: str, route: str, history: list | None = None) -> str:
    """Pick the answer shape before generation, without calling a model."""
    if route == "mix_review_followup" or latest_mix_review_context(history):
        return "mix_review_followup"
    topics = set(query_topics(query))
    intent = detect_intent(query)
    if route == "game_audio" or topics & GAME_ROUTE_TOPICS:
        return "game_audio_implementation"
    if business_pricing_query(query):
        return "client_delivery"
    if client_delivery_query(query, topics):
        return "client_delivery"
    if topics & {"mastering", "loudness"}:
        return "mastering_safety"
    if route == "ableton" or topics & ABLETON_ROUTE_TOPICS:
        return "ableton_steps"
    if dialogue_cleanup_query(query, topics):
        return "dialogue_cleanup"
    if intent == "troubleshooting" or topics & {
        "mixing",
        "vocals",
        "bass",
        "drums",
        "translation",
        "monitoring",
        "eq",
        "compression",
    }:
        return "mix_diagnosis"
    if intent in {"why", "explain"}:
        return "deep_explanation"
    return "quick_fix"


def client_delivery_query(query: str, topics: set[str] | None = None) -> bool:
    """Separate client/file-delivery intent from audio send/return routing."""
    lowered = query.lower()
    terms = normalized_terms(query)
    topic_set = topics if topics is not None else set(query_topics(query))
    explicit_terms = {
        "client",
        "deliver",
        "delivery",
        "file",
        "files",
        "handoff",
        "mp3",
        "preview",
        "revision",
        "revisions",
        "stem",
        "stems",
        "wav",
    }
    if terms & explicit_terms:
        return True
    if topic_set & {"export", "revision"}:
        return True
    if "final mix" in lowered or "send for a mix" in lowered or "sending for a mix" in lowered:
        return True
    return False


def dialogue_cleanup_query(query: str, topics: set[str] | None = None) -> bool:
    topic_set = topics if topics is not None else set(query_topics(query))
    terms = normalized_terms(query)
    if "podcast" in topic_set:
        return True
    return bool(terms & {"artifact", "artifacts", "dialogue", "podcast", "room", "tone"})


def mode_profile(answer_mode: str) -> dict[str, str]:
    profiles = {
        "ableton_steps": {
            "check_label": "Live check:",
            "check": "Try the move on a duplicate track or blank Live Set, then A/B with the device or routing bypassed.",
            "boundary_label": "Live safety:",
            "boundary": "Duplicate or save the track first, make one device or routing change at a time, then A/B in Live before committing.",
            "avoid": "Avoid changing several devices at once; make one move, listen, then continue.",
        },
        "client_delivery": {
            "check_label": "Delivery check:",
            "check": "Confirm file names, sample rate, bit depth, headroom, and what the client needs before sending.",
            "boundary_label": "Scope boundary:",
            "boundary": "Do not quote or promise turnaround from a vague brief; confirm stem count, editing, tuning, deliverables, deadline, revision rounds, and rush expectations first.",
            "avoid": "Avoid sending mystery exports; label versions and include notes when the file is for review.",
        },
        "deep_explanation": {
            "check_label": "Understanding check:",
            "check": "Apply the idea to one small example in the session so it becomes a listening decision, not just theory.",
            "avoid": "Avoid treating the explanation as a rule; verify it against the source material and the session.",
        },
        "dialogue_cleanup": {
            "check_label": "Dialogue check:",
            "check": "Listen at normal speech level and on headphones; the cleanup should reduce distractions without chopping words or sounding processed.",
            "boundary_label": "Cleanup boundary:",
            "boundary": "Preserve intelligibility and natural room tone before chasing silence; remove noise in small passes so artifacts do not become worse than the noise.",
            "avoid": "Avoid heavy gates or restoration settings that cut breaths, tails, word endings, or the room tone between phrases.",
        },
        "game_audio_implementation": {
            "check_label": "Implementation check:",
            "check": "Test the sound in middleware or engine context with repeated triggers, states, and realistic playback levels.",
            "tradeoff_label": "Runtime tradeoff:",
            "tradeoff": "Balance DAW polish against runtime limits: memory, voice count, streaming, sync points, and state changes can matter more than a louder offline export.",
            "avoid": "Avoid approving the sound only in the DAW; interactive playback can reveal different issues.",
        },
        "mastering_safety": {
            "check_label": "Mastering check:",
            "check": "Level-match the before/after, check true peak and loudness, then listen quietly and on a small speaker.",
            "boundary_label": "Mastering boundary:",
            "boundary": "Do not chase loudness until balance, low end, harshness, true peak safety, and level-matched translation checks are under control.",
            "avoid": "Avoid chasing loudness before balance, low end, and harshness are already under control.",
        },
        "mix_diagnosis": {
            "check_label": "Listening check:",
            "check": "Bypass and compare at matched loudness; the change should solve the symptom without making another range worse.",
            "boundary_label": "Diagnosis boundary:",
            "boundary": "Start from the audible symptom, change one variable at a time, and verify at matched loudness before adding another processor.",
            "avoid": "Avoid processing the loudest-looking problem first if the real issue is masking, arrangement, or level balance.",
        },
        "mix_review_followup": {
            "check_label": "Revision check:",
            "check": "Make one focused revision from the review, export a new version, then compare against the previous upload.",
            "avoid": "Avoid fixing every flag at once; that makes it hard to know which change helped.",
        },
        "quick_fix": {
            "check_label": "Check:",
            "check": "Make the smallest useful change, then compare before/after at the same loudness.",
            "avoid": "Avoid stacking fixes before you know whether the first one solved the problem.",
        },
    }
    return profiles.get(answer_mode, profiles["quick_fix"])


def first_move_line(answer_mode: str, steps: list[str]) -> str:
    """Return the first practical action when the answer contains a workflow."""
    if not steps:
        return ""
    first_step = steps[0].strip().rstrip(".")
    if not first_step:
        return ""
    if answer_mode == "deep_explanation":
        return ""
    prefixes = {
        "ableton_steps": "First move in Live",
        "client_delivery": "First move with the client",
        "dialogue_cleanup": "First cleanup move",
        "game_audio_implementation": "First implementation move",
        "mastering_safety": "First mastering move",
        "mix_diagnosis": "First move",
        "mix_review_followup": "First revision move",
        "quick_fix": "First move",
    }
    label = prefixes.get(answer_mode, "First move")
    return f"{label}: {first_step}."


def useful_history_user_turns(history: list | None) -> list[str]:
    turns: list[str] = []
    for turn in normalize_history(history):
        if turn["role"] != "user":
            continue
        content = turn["content"]
        if conversational_intent(content):
            continue
        turns.append(content)
    return turns


def is_session_context_turn(content: str) -> bool:
    return content.lower().startswith("session context for this kenn conversation")


def session_context_matches_query(query: str, turns: list[str]) -> bool:
    """Use UI session targets as answer context only when they match the current topic."""
    query_topic_set = set(query_topics(query))
    if not query_topic_set:
        return False
    context_topics: set[str] = set()
    for turn in turns:
        if is_session_context_turn(turn):
            context_topics.update(query_topics(turn))
    return bool(query_topic_set & context_topics)


def is_followup_query(query: str) -> bool:
    cleaned = re.sub(r"\s+", " ", str(query).lower()).strip()
    if not cleaned or conversational_intent(cleaned):
        return False
    if cleaned.startswith(FOLLOWUP_STARTERS):
        return True
    if cleaned.startswith(
        (
            "what should i ask",
            "what should i check",
            "what should i do next",
            "what should i do first",
            "what do i ask",
            "what do i check",
        )
    ):
        return True
    raw_words = set(cleaned_query(cleaned).split())
    if raw_words & FOLLOWUP_REFERENCES and len(raw_words) <= 9:
        return True
    if re.search(r"\b(why|where|when)\s+(would|should|do|does)\s+(i|it|that|this)\b", cleaned):
        return True
    # Found live-testing 2026-08-02: "should i"/"do i"/"can i" are already in
    # FOLLOWUP_STARTERS, but the startswith() check above only catches them
    # as the very first words. "what release time should I use?" -- an
    # obvious, elliptical follow-up to a sidechain-compression question just
    # asked -- has "should i" mid-sentence, after the short "release time"
    # noun phrase, so it fell through every check above and got treated as
    # a fresh, context-free query. Retrieval then matched "release" to an
    # unrelated arrangement/EDM "tension and release" note instead of the
    # compression release-time parameter the user obviously meant. Catches
    # "what <=3 words> should/do/does/can i ...", the same elliptical shape
    # as the why/where/when pattern just above, generalized to "what".
    return bool(re.search(r"\bwhat\s+(?:\w+\s+){0,3}(should|do|does|can)\s+i\b", cleaned))


def should_use_history(query: str, history: list | None) -> bool:
    turns = useful_history_user_turns(history)
    session_turns = [turn for turn in turns if is_session_context_turn(turn)]
    if session_turns and not query_is_out_of_scope(query):
        if is_followup_query(query) or session_context_matches_query(query, session_turns):
            return True
    if any(turn.lower().startswith("track memory for ") for turn in turns):
        return not query_is_out_of_scope(query)
    if is_followup_query(query) and bool(turns):
        return True
    if any("mix review lab context" in turn.lower() for turn in turns):
        terms = normalized_terms(query)
        return bool(terms & MIX_REVIEW_FOLLOWUP_TERMS)
    return False


def search_query_with_history(query: str, history: list | None, *, session_id: str = "") -> str:
    if not should_use_history(query, history):
        return query
    turns = useful_history_user_turns(history)
    if is_followup_query(query):
        prior = [turn for turn in turns if not is_session_context_turn(turn)][-1:]
    else:
        prior = [
            turn
            for turn in turns
            if turn.lower().startswith(("mix review lab context", "track memory for "))
        ][-1:]
    if not prior:
        return query
    return " ".join([*prior, query])


def history_context_line(query: str, history: list | None) -> str:
    if not should_use_history(query, history):
        return ""
    turns = useful_history_user_turns(history)
    last_user = turns[-1] if turns else ""
    if not last_user:
        return ""
    if last_user.lower().startswith("mix review lab context"):
        return "[Mix Review Context]: Using the latest Mix Review Lab analysis from your uploaded track."
    if last_user.lower().startswith("track memory for "):
        first_line = last_user.splitlines()[0].strip().rstrip(".")
        return f"[Mix Review Memory]: Using saved Mix Review memory: {first_line}."
    if last_user.lower().startswith("session context for this kenn conversation"):
        details = " ".join(last_user.splitlines()[1:3]).strip()
        return f"[Session Context]: Using session context: {details[:160]}"
    snippet = last_user if len(last_user) <= 120 else last_user[:117] + "..."
    return f"[Previous User Question]: {snippet}"
