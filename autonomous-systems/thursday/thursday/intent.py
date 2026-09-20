"""Intent Classification Engine — replaces fragile keyword scoring.

Categorizes requests into intent categories and extracts entities
using regex patterns and context resolution.
"""

from __future__ import annotations

import re


class Intent:
    """Represents a classified intent with metadata."""

    def __init__(
        self,
        name: str,
        confidence: float = 0.0,
        entities: dict | None = None,
        requires_context: bool = False,
    ):
        self.name = name
        self.confidence = confidence
        self.entities = entities or {}
        self.requires_context = requires_context

    def __repr__(self) -> str:
        return f"Intent({self.name}, conf={self.confidence:.2f}, entities={self.entities})"


# ─── Intent Categories ────────────────────────────────────────────────────

INTENT_CATEGORIES = {
    "business_ops": {
        "patterns": [
            # how(?:'s|s|\s+is) covers "how's", "hows" (no apostrophe, common typing),
            # and "how is" business.
            r"\b(?:how(?:'s|s|\s+is) business|business health|status|health|how are things|overview|dashboard|stats|what(?:'s| is) the status|numbers|give me the status)\b",
            r"\b(?:weekly review|this week|weekly summary)\b",
            r"\b(?:week ahead|next week|weekahead|what(?:'s| is) coming|whats next)\b",
            r"\b(?:pipeline|funnel|sales pipeline|conversion|bottleneck)\b",
            r"\bsales\s+bottleneck\b",
            r"\b(?:monthly report|monthly analytics|lead source|service demand|invoice aging|business report)\b",
            r"\b(?:enquir(?:y|ies)|website enquiry|pending enquiry|new enquiry)\b",
            r"\b(?:template|templates)\b",
            r"\b(?:reminder|reminders|what(?:'s| is) due|whats due|follow up|overdue|past due|stale)\b",
            # Task ledger / daily-status ops commands (Thursday Ops upgrade,
            # phase 1). Without one of these matching, "active tasks" etc.
            # classifies as "unknown" and hits the chat_only LLM brain gate
            # (thursday/orchestrator.py's "LLM Brain Gating" comment) --
            # which structurally can only talk or abstain, never dispatch a
            # service. So a task-ledger command with no keyword coverage
            # here can NEVER reach thursday/registry's trigger scoring,
            # regardless of how exact its ServiceDef trigger phrase is.
            r"\b(?:daily status|where are we today|what should i focus on|"
            r"ops status|company status|active tasks?|blocked tasks?|"
            r"task ledger|list (?:my |active )?tasks|what tasks|"
            r"current tasks|create task|add task|new task|"
            r"marketing plan|marketing readiness|audit marketing|"
            r"campaign plan|ad readiness|advertising readiness|"
            r"ready for ads|ready to advertise|"
            r"funding readiness|investment readiness|ready for investment|"
            r"ready to fundraise|funding report|"
            r"weekly company report|company report|full company report|"
            r"beta readiness|submit beta status|blocking the beta|"
            r"beta checklist|"
            r"brief another agent|brief an agent|brief codex|brief gemini|"
            r"release hygiene|engineering status|repo hygiene|"
            r"repos clean|branch hygiene|"
            r"deployment health|(?:site|website|api) up|infrastructure health|"
            r"pricing summary|our pricing|what do we charge|service pricing|"
            r"faqs?\b|known issues|known bugs|"
            r"launch tracker|launch gates|launch status|"
            r"draft beta invite|draft beta email)\b",
        ],
        "weight": 2.0,
    },
    "calendar_scheduling": {
        "patterns": [
            r"\b(?:calendar|agenda|schedule|my day|what(?:'s| is) on|daily briefing|daily agenda)\b",
            r"\b(?:what\s+does\s+my\s+(?:day|week)\s+look\s+like|whats\s+(?:on|coming|up))\b",
            r"\b(?:remind|reminder)\s+(?:me|set)\s+(?:to\s+)?(.+?)\s+(?:at|in|by|on|for|tomorrow|next|this)\b",
            r"\bset\s+(?:a\s+)?reminder\s+(?:to|for)\b",
            r"\b(?:schedule|book|set\s+up)\s+(?:a\s+)?(?:session|appointment|meeting|call|reminder)\b",
            r"\bset\s+up\s+(?:a\s+)?client\s+call\b",
            # Informal booking phrasing without a session/meeting noun, e.g.
            # "book him in tomorrow", "book her in for friday".
            r"\bbook\s+(?:him|her|them|\w+)\s+in\b",
            r"\b(?:good\s+morning|good\s+afternoon|good\s+evening)\b",
            r"\b(?:briefing|daily\s+briefing|morning\s+briefing)\b",
        ],
        "weight": 2.5,
    },
    "client_mgmt": {
        "patterns": [
            r"(?:tell me about|who is|client info|client details|client summary|client history|client timeline)\s+\w+",
            r"\b(?:client|client info|client details|client summary)\b",
            r"\b(?:who are my|my leads|list leads|show leads|show my leads)\b",
            # Found 2026-07-27: bare "session(s)" matched inside phrases like
            # "a long mixing session" or "my recording session was rough" --
            # "session" is genuinely overloaded in an audio context (business
            # booking vs. an Ableton/studio session), and this bare form beat
            # production_qa's "mixing" trigger on weight alone, misrouting a
            # production question into "No sessions recorded yet." The
            # negative lookbehind excludes the common production qualifiers
            # immediately before "session(s)" while leaving genuine business
            # phrasing ("my sessions", "upcoming sessions", "sessions today")
            # matching exactly as before.
            r"\b(?<!mixing )(?<!mastering )(?<!recording )(?<!tracking )(?<!studio )(?<!vocal )(?<!production )sessions?\b",
            r"\b(?:schedule|book|create|new session)\s+(?:session|appointment|meeting)\b",
        ],
        "weight": 2.0,
    },
    "financial": {
        "patterns": [
            r"\b(?:invoice|invoices|invoice list|show invoices|invoice pdf|generate invoice)\b",
            r"\b(?:expense|expenses|spending|spent|spend|money spent|what did i spend)\b",
            r"\b(?:profit|profit report|pnl|p&l|earnings|revenue|income)\b",
            r"\b(?:draft|drafts|pending draft|unsent|send draft|send approved)(?:\s+(?!email|invoice|outreach))?\b",
            r"\b(?:add expense|record expense|log expense|new expense)\b",
        ],
        "weight": 2.0,
    },
    "production_qa": {
        "patterns": [
            r"\bmaster(?:ing)?\s+(?:this|my|the|a)\s+(?:song|track|mix|record|album)\b",
            # Trailing (?:e?s)? lets plurals match too — "kick" AND "kicks",
            # "drum"/"drums", "vocal"/"vocals", "bass"/"basses". Without it,
            # \bkick\b fails on "kicks", so natural follow-up production
            # questions ("how do I process kicks?") fell through to Thursday.
            r"\b(?:ableton|mixing|mastering|production|studio|sidechain|compression|eq|reverb|delay|plugin|vocal|frequency|bus|limiter|saturation|distortion|filter|synth|snare|kick|drum|bass|hi.hat|cymbal|transient|attack|release|sustain|punch|punchy|thin|thick|muddy|harsh|bright|warm|boxy|boomy|crisp|presence|clarity|body|weight|air|glue|parallel|multiband|high.pass|low.pass|shelf|notch|gain|pan|stereo|mono|phase|latency|headroom|loudness|lufs|rms|peak|clip|clipping|ceiling|gate|expander|compressor|de.ess|pitch|tuning|harmonic|sample|resample|bounce|render|send|return|aux|insert|rack|chain|midi|automation|envelope|velocity|groove|swing|quantize|humanise|humanize)(?:e?s)?\b",
            # Common natural terms the list above misses — "mix"/"master" standalone,
            # "mixdown", loudness/width words, low/high-end phrases, wet/dry, LFO.
            r"\b(?:mix|master|mixdown|remix|louder|quieter|wider|width|widen|narrow|lfo|dynamics|dynamic\s+range|wet|dry|sub|sub.bass|low.end|high.end|top.end|low.mid|high.mid|mid.range|harshness|muddiness|boominess|sibilance|de.essing|comp|comping|automate|automating)(?:e?s)?\b",
            # Game-audio / middleware terms — KENN has deep Wwise/game-audio knowledge
            # but these were entirely absent from this keyword list, so questions like
            # "how do I set up a soundbank in wwise" classified as unknown.
            r"\b(?:wwise|fmod|soundbank|middleware|rtpc|switch\s+container|blend\s+container|game\s+audio|game\s+engine|unity|unreal)(?:e?s)?\b",
            # Modern/slang production shorthand not covered by the formal terms above.
            r"\b(?:808|trap\s+hats|vocal\s+chop|vocal\s+chops|glitch|riser|stutter)(?:e?s)?\b",
        ],
        "weight": 1.5,
    },
    "audio_generation": {
        "patterns": [
            # Optional "me"/"us" object pronoun before the article — "make me a beat".
            r"\b(?:generate|make|create)\s+(?:me\s+|us\s+)?(?:a\s+|an\s+|the\s+)?(?:loop|song|beat|audio|phrase|track)\b",
            r"\b(?:audiogen|render\s+song|full\s+song)\b",
            r"\b(?:generate|make|create)\s+(?:a\s+|an\s+)?(?:joyful|sad|happy|energetic|calm|melancholy|upbeat|dark|bright|warm)\b",
            r"\b(?:render queue|render status|cancel render|retry render|render progress)\b",
            r"\b(?:generate|make|create)\s+[^.]{0,40}\b(?:then|and)\s+(?:render|run|start)\s+(?:an?\s+)?(?:automix|auto[\s-]?mix|mix)\b",
        ],
        "weight": 2.5,
    },
    "mix_review_audio_analysis": {
        "patterns": [
            r"\b(?:mix review|revision plan|mix review compare|check my mix|mix analysis)\b",
            r"\breview\s+(?:this\s+|my\s+|the\s+|that\s+)?(?:mix|track|song|master|recording|record)\b",
            r"\b(?:analyze audio|scan audio|audio analysis|scan my files|analyse (?:my |the )?mix|analyze (?:my |the )?mix|analyze my song|analyse my track|audio scan|scan my project)\b",
            r"\b(?:scan folder|scan directory|analyse file|audio file analysis)\b",
            r"\b(?:compare|version|revision|difference)\s+(?:mix|track|audio|review)\b",
            r"\b(?:review|scan|analyze|track)\s+[a-f0-9]{8,}\b",
        ],
        "weight": 2.5,
    },
    "system_diagnostics": {
        "patterns": [
            r"\b(?:diagnostics|health\s+check|check\s+all\s+systems|system\s+health|check\s+e(?:verything|ach subsystem))\b",
            r"\b(?:is\s+everything\s+working|run\s+(?:a\s+)?health\s+check)\b",
            r"\b(?:fix\s+(?:the\s+)?(?:website|server|kenn|database))\b",
            r"\b(?:usage\s+analytics|analytics|what\s+do\s+i\s+ask\s+you|whats\s+my\s+usage)\b",
        ],
        "weight": 2.6,
    },
    "macro": {
        "patterns": [
            r"\b(?:good\s+morning|morning\s+briefing|start\s+my\s+day|daily\s+briefing)\b",
            r"\b(?:onboard\s+|register\s+(?:a|new)\s+client)\b",
            r"\b(?:full\s+mix\s+review|mix\s+review\s+pipeline)\b",
            r"\b(?:weekly\s+summary|end\s+of\s+week|week\s+wrap.?up|friday\s+review)\b",
            r"\b(?:run\s+(?:my\s+)?(?:(?:morning|daily)\s+)?(?:routine|briefing|summary))\b",
        ],
        "weight": 3.0,
    },
    "agent_tasks": {
        "patterns": [
            r"\b(?:draft|write|compose)\s+(?:an?\s+)?email\b",
            r"\b(?:draft invoice|create invoice|make invoice)\b",
            r"\b(?:send|email)\s+(?:\w+\s+){0,4}(?:an?\s+)?invoice\b",
            r"\b(?:new project|create project|add project)\b",
            r"\b(?:new client|create client|add client|add customer)\b",
            r"\b(?:outreach|draft outreach|write outreach|cold email)\b",
            r"\b(?:social post|draft post|social media|instagram)\b",
            r"\b(?:new lead|add lead|create lead|marketing campaign)\b",
            r"\b(?:research|research plan|research topic|suggest sources|find sources|look up topic)\b",
            r"^(?:(?:please|um)\s+|thursday,\s+)?research\b",
            r"\bresearch\s+[a-z0-9]",
        ],
        "weight": 3.0,
    },
    "system": {
        "patterns": [
            r"\b(?:snapshot|backup|archive|export everything)\b",
            r"\b(?:snapshots|available backups?|show snapshot)\b",
            r"\b(?:daily maintenance|cron daily|run daily|daily cron)\b",
            r"\b(?:weekly maintenance|cron weekly|run weekly|weekly cron)\b",
        ],
        "weight": 2.0,
    },
    "search": {
        "patterns": [
            r"\b(?:search|find me|look up|where is|search for|find records|find projects|find clients|find leads|find invoices|look for|lookup|searching)\b",
        ],
        "weight": 3.0,
    },
    "greeting": {
        "patterns": [
            r"^(?:hi|hey|hello|morning|good\s+morning|good\s+afternoon|good\s+evening|yo|sup|what'?s\s+up|howdy|hiya|greetings)[\s!?.]*$",
            r"^(?:hi|hey|hello)\s+thursday[\s!?.]*$",
        ],
        "weight": 6.0,
    },
    "help": {
        "patterns": [
            r"^(?:help|commands?|menu|options)[\s!?.]*$",
            r"\bwhat\s+can\s+(?:you|thursday)\s+(?:do|help(?:\s+me)?(?:\s+with)?)\b",
            r"\bwhat\s+do\s+you\s+do\b",
            r"\bwhat\s+does\s+thursday\s+do\b",
            r"\b(?:show|tell)\s+me\s+what\s+you\s+can\s+do\b",
            r"\bwhat\s+are\s+your\s+(?:capabilities|commands|features)\b",
            r"\bhow\s+do\s+i\s+use\s+(?:you|thursday)\b",
            r"\btell\s+me\s+what\s+you\s+can\s+help\s+me\s+with\b",
        ],
        "weight": 6.0,
    },
    "kenn_voice_mode": {
        "patterns": [
            # "send me over to kenn", "send me on to kenn", etc. — a filler word
            # (over/on/through/across) commonly slips in between "send me" and
            # "to kenn" in natural/garbled speech-to-text output. Without the
            # optional filler group, "send me over to Ken" fails to match this
            # intent at all and falls through to production_qa (triggered by the
            # unrelated "send" audio-routing term), which then forwards the raw
            # handoff phrase to KENN's answer pipeline as if it were a real
            # question — producing a garbled, content-free answer.
            r"\b(?:speak\s+(?:with|to)|talk\s+to|put\s+me\s+through\s+to|connect\s+(?:me\s+to|to)|switch\s+to|send\s+me\s+(?:over\s+|on\s+|through\s+|across\s+)?to|let\s+me\s+(?:talk|speak)\s+(?:with|to)|give\s+me|get\s+me|i\s+want)\s+kenn?\b",
            r"\bkenn?\s+mode\b",
            r"^kenn?[\s!?.]*$",
            r"\bget\s+kenn?\b",
            r"\b(?:back\s+to|switch\s+(?:back\s+to|to)|talk\s+to|speak\s+(?:with|to))\s+thursday\b",
            r"\bthursday\s+mode\b",
        ],
        "weight": 5.0,
    },
    # Siri-style utility tools (2026-08-07) — kept as their own deterministic
    # intents (not left to fall into "unknown") specifically so they're
    # matched and executed BEFORE brain.py's chat_only general-knowledge path
    # ever gets a turn: that path always returns type "chat"/"abstain" with
    # no way to defer to a real service, so if these fell through to
    # "unknown" a small local model would try (and, for arithmetic,
    # unreliably fail) to answer them itself instead of using real code.
    "calculator": {
        "patterns": [
            r"\b(?:calculate|compute)\b",
            r"\bsquare\s+root\s+of\b",
            r"\d+\s*(?:percent|%)\s+of\s+\d+\b",
            r"\bwhat(?:'s|s|\s+is)\b.{0,40}?\d+.{0,20}?\b(?:plus|minus|times|multiplied\s+by|divided\s+by|over)\b.{0,20}?\d+",
            r"\d+\s*(?:\+|-|\*|/)\s*\d+",
        ],
        "weight": 3.0,
    },
    "unit_conversion": {
        "patterns": [
            r"\bconvert\s+-?\d+(?:\.\d+)?\s*[a-zA-Z°]+\s+(?:to|into)\s+[a-zA-Z°]+\b",
            r"\bhow\s+many\s+[a-zA-Z°]+\s+(?:in|is|are)\s+-?\d+(?:\.\d+)?\s*[a-zA-Z°]+\b",
            r"\b-?\d+(?:\.\d+)?\s*[a-zA-Z°]+\s+(?:to|in)\s+[a-zA-Z°]+\b",
        ],
        "weight": 3.0,
    },
    "timer": {
        "patterns": [
            r"\b(?:set|start|create)\s+(?:a\s+)?(?:timer|countdown)\b",
            r"\btimer\s+for\s+\d+\b",
            r"\bcancel\s+(?:my\s+)?timer\b",
            r"\bhow\s+much\s+time\s+is\s+left\b",
        ],
        "weight": 3.5,
    },
    "weather": {
        "patterns": [
            r"\bweather\b",
            r"\bforecast\b",
            r"\bis\s+it\s+(?:raining|snowing|going\s+to\s+rain)\b",
            r"\bhow\s+(?:hot|cold)\s+is\s+it\b",
            # Direct weather asks only: allow a short leading
            # politeness/address phrase ("hey Thursday,", "would you",
            # "when you can,") but never one containing a subordinator,
            # so subordinate clauses ("...even if it will rain, ...")
            # keep their real intent.
            r"^(?!(?:[a-z',]+\s+){0,3}"
            r"(?:if|whether|even|because|that|unless|until|after|"
            r"before|though)\b)"
            r"(?:[a-z',]+\s+){0,3}"
            r"(?:will\s+(?:it\s+)?rain|is\s+it\s+going\s+to\s+rain)\b",
        ],
        "weight": 3.5,
    },
    "company_state": {
        "patterns": [
            r"\bwhat(?:'s| is|\s+are)\s+(?:the\s+)?(?:blocked|blocking)\b",
            r"\bwhat(?:'s| is)\s+overdue\b",
            r"\boverdue\s+tasks?\b",
            r"\bwhat\s+needs?\s+(?:my\s+|the\s+)?(?:approval|approving)\b",
            r"\b(?:pending|awaiting)\s+approvals?\b",
            r"\bwhich\s+agents?\s+(?:failed|are\s+still\s+working|need\s+attention)\b",
            r"\bagent\s+status\b",
            r"\bwhat(?:'s| is)\s+(?:at\s+risk|blocking\s+\w+)\b",
            r"\bare\s+we\s+on\s+track\b",
            r"\bcompany\s+(?:state|status|overview|snapshot)\b",
        ],
        "weight": 3.0,
    },
    "set_default_location": {
        # "i'm in X"/"i am in X" was tried and dropped -- far too easily
        # matched real, unrelated sentences ("i'm in the middle of a mix",
        # "i am in the studio right now"). Require the unambiguous
        # "my location is"/"set my location" phrasing instead.
        "patterns": [
            r"\b(?:my\s+location\s+is|set\s+my\s+location\s+to)\b",
        ],
        "weight": 3.5,
    },
    "current_time": {
        "patterns": [
            r"\bwhat(?:'s|s|\s+is)\s+the\s+time\b",
            r"\bwhat\s+time\s+is\s+it\b",
            r"\bcurrent\s+time\b",
        ],
        "weight": 3.5,
    },
    "date_query": {
        "patterns": [
            r"\bwhat(?:'s|s|\s+is)\s+(?:the\s+)?date\b",
            r"\bwhat\s+day\s+is\s+it\b",
            r"\bwhat\s+day\s+(?:will\s+it\s+be|is\s+it)\s+in\b",
            r"\bhow\s+many\s+days\s+(?:until|till|to)\b",
        ],
        "weight": 3.5,
    },
    "contextual": {
        "patterns": [
            r"\b(?:him|her|they|it|that|those|these|the (?:client|project|invoice|lead|track|review|file))\b",
            r"\b(?:last (?:week|month|year|time|session|review|scan|analysis))\b",
            r"\b(?:previous|that one|the same|again|also|and)\b",
        ],
        "weight": 1.0,
    },
}


# ─── Entity Extraction Patterns ──────────────────────────────────────────

ENTITY_PATTERNS = [
    # Client name: "tell me about Jordan", "who is Sarah"
    ("client_name", r"(?:tell me about|who is|about|client info for|client details for|client history for|client timeline for)\s+(\w[\w\s]+?)(?:\.|$|\s+(?:service|deadline|project|and|show|send|create|draft))"),
    # Invoice/draft ID
    ("invoice_id", r"(?:invoice|draft)\s+([a-f0-9]{8,12})"),
    # Project name
    ("project_name", r"(?:project|for)\s+([\w\s]+?)(?:\.|$|\s+(?:service|deadline|and|show|with))"),
    # Year
    ("year", r"(?:in |for |during )(20\d{2})"),
    # Review ID (audio analysis)
    ("review_id", r"(?:review|scan|analyze|track)\s+([a-f0-9]{8,12})"),
    # Audio path
    ("audio_path", r"(?:scan|analyze)\s+([\w\/\.~-]+)"),
    # AudioGen job ID
    ("audiogen_job_id", r"(?:render|job|audiogen)\s+([a-f0-9]{8,12})"),
    # Email address
    ("email", r"([\w._%+-]+@[\w.-]+\.[a-zA-Z]{2,})"),
    # Amount (currency)
    ("amount", r"[£$€](\d+(?:,\d{3})*(?:\.\d{2})?)\b"),
]


# ─── Public API ───────────────────────────────────────────────────────────


def classify_intent(text: str, context: dict | None = None) -> Intent:
    """Classify the intent of a user request.

    Returns an Intent with name, confidence score, extracted entities,
    and whether it requires context resolution.
    """
    text_lower = text.lower().strip()
    context = context or {}

    best_intent = "unknown"
    best_score = 0.0
    matched_entities = {}

    # Score each intent category
    scored = {}
    for intent_name, config in INTENT_CATEGORIES.items():
        score = 0.0
        for pattern in config["patterns"]:
            matches = re.findall(pattern, text_lower)
            if matches:
                # Each pattern match adds weight
                score += config["weight"] * len(matches)
                # Check if match is near start of text (higher relevance)
                for m in re.finditer(pattern, text_lower):
                    position_boost = max(0, 1.0 - m.start() / len(text_lower))
                    score += position_boost * 0.5
        if score > 0:
            scored[intent_name] = score

    if scored:
        # Prefer structural intents over the keyword-based production_qa fallback
        sorted_intents = sorted(
            scored.keys(),
            key=lambda k: (
                -1.0 if (k == "production_qa" and any(o != "production_qa" and scored[o] >= 1.5 for o in scored)) else scored[k],
                get_intent_priority(k)
            ),
            reverse=True
        )
        best_intent = sorted_intents[0]
        best_score = scored[best_intent]

    # Extract entities
    matched_entities = extract_entities(text)

    # Determine if context resolution is needed
    requires_context = _needs_context_resolution(text_lower, context)

    # Scores are useful internally, but callers should receive a conventional
    # confidence value rather than an unbounded regex match score.
    confidence = min(1.0, best_score / 3.0) if best_score else 0.0
    return Intent(
        name=best_intent,
        confidence=confidence,
        entities=matched_entities,
        requires_context=requires_context,
    )


def extract_entities(text: str) -> dict:
    """Extract named entities from text using regex patterns."""
    entities = {}
    for entity_name, pattern in ENTITY_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            # Take the first match, clean it
            value = matches[0].strip() if isinstance(matches[0], str) else matches[0][0].strip()
            if value:
                entities[entity_name] = value
    return entities


def resolve_entities(text: str, context: dict | None = None) -> dict:
    """Extract explicit entities and merge references resolved from context."""
    from thursday.resolver import resolve_request

    resolved_text, contextual = resolve_request(text, context or {})
    return {**contextual, **extract_entities(resolved_text)}


def _needs_context_resolution(text: str, context: dict) -> bool:
    """Check if text needs context to be resolved (pronouns, implicit refs)."""
    pronoun_patterns = [
        r"\b(?:him|her|they|it|this|that|those|these)\b",
        r"\bthe\s+(?:client|project|invoice|lead|track|review|file|report|session)\b",
        r"\b(?:last|previous)\s+(?:one|time|session|review|scan)\b",
        r"\b(?:also|too|as well|again)\b",
    ]
    for pattern in pronoun_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            # Only requires context if there's something in context to resolve to
            return any(v is not None for v in context.values())
    return False


def get_intent_priority(intent_name: str) -> int:
    """Get priority level for an intent (higher = more specific)."""
    priorities = {
        "kenn_voice_mode": 15,
        "greeting": 14,
        "help": 13,
        "macro": 12,
        "timer": 11,
        "weather": 11,
        "company_state": 11,
        "calculator": 11,
        "unit_conversion": 11,
        "set_default_location": 11,
        "current_time": 11,
        "date_query": 11,
        "audio_generation": 10,
        "mix_review_audio_analysis": 10,
        "agent_tasks": 9,
        "financial": 8,
        "client_mgmt": 7,
        "calendar_scheduling": 7,
        "business_ops": 6,
        "system_diagnostics": 6,
        "system": 5,
        "search": 4,
        "production_qa": 3,
        "contextual": 2,
        "unknown": 1,
    }
    return priorities.get(intent_name, 1)
