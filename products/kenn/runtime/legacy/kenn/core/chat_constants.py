"""Shared paths, thresholds, and vocab constants for the kenn.core.chat_* modules.

Split out of chat.py (was 4,298 lines) so every chat_* module can depend on a single
low-level constants module without circular imports. See docs/BACKLOG.md for the
decomposition record.
"""

from __future__ import annotations

import sys
from pathlib import Path

from kenn.core.lm_identity import SYSTEM_INTRO

ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = ROOT.parent
REPO_ROOT = PROJECT_ROOT.parent.parent
WEBSITE_ROOT = REPO_ROOT / "business" / "app"
ANALYSIS_TOOL_ROOT = REPO_ROOT / "studio" / "audio_analysis"

if str(WEBSITE_ROOT) not in sys.path:
    sys.path.insert(0, str(WEBSITE_ROOT))
if str(ANALYSIS_TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_TOOL_ROOT))

# mix_review removed to prevent PyTorch loading on chat startup
mix_review = None

INDEX_DIR = ROOT / "data" / "index"
CHUNKS_PATH = INDEX_DIR / "chunks.jsonl"
TERMS_PATH = INDEX_DIR / "terms.json"
CHAT_DIR = ROOT / "chats"
NOTES_DIR = ROOT / "Training_Data_Notes"
ROUTE_MEMORY_PATH = ROOT / "artifacts" / "training" / "kenn_route_memory.jsonl"
MIN_RELEVANT_SCORE = 4.0
NOTE_SCORE_BONUS = 1.2
SYSTEM_NOTE = SYSTEM_INTRO
SOURCE_QUALITY_ORDER = {"low": 0, "medium": 1, "high": 2}
ANSWER_QUALITY_MIN_SCORE = 62
ANSWER_MODES = {
    "ableton_steps",
    "client_delivery",
    "deep_explanation",
    "dialogue_cleanup",
    "game_audio_implementation",
    "mastering_safety",
    "mix_diagnosis",
    "mix_review_followup",
    "quick_fix",
}
OUT_OF_SCOPE_TERMS = {
    "accounting",
    "anxiety",
    "boyfriend",
    "bread",
    "career",
    "contract",
    "cooking",
    "crypto",
    "dating",
    "depression",
    "diagnose",
    "engine",
    "financial",
    "girlfriend",
    "infection",
    "invest",
    "legal",
    "love",
    "marriage",
    "medical",
    "recipe",
    "shares",
    "sourdough",
    "spouse",
    "stocks",
    "tax",
}
INTENT_GUARD_TERMS = {
    "cpu": {
        "buffer",
        "cpu",
        "crackle",
        "glitch",
        "latency",
        "overload",
        "performance",
    },
    "stereo_width": {
        "double",
        "doubler",
        "haas",
        "mono",
        "side",
        "stereo",
        "width",
        "wide",
        "widen",
    },
    "depth": {
        "ambience",
        "delay",
        "depth",
        "predelay",
        "pre",
        "reverb",
        "room",
        "space",
        "throw",
    },
    "translation": {
        "car",
        "mono",
        "phone",
        "reference",
        "speaker",
        "translate",
        "translation",
    },
    "transients": {
        "attack",
        "punch",
        "snap",
        "transient",
    },
    "vocals": {
        "boxy",
        "breath",
        "body",
        "deesser",
        "harsh",
        "mud",
        "sibilance",
        "thin",
        "wide",
        "width",
    },
    "bass": {
        "kick",
        "phase",
        "sub",
        "weight",
    },
}
TERM_ALIASES = {
    "bas": "bass",
    "kik": "kick",
    "sidechane": "sidechain",
    "sidechaine": "sidechain",
    "sidechained": "sidechain",
    "pump": "pumping",
    "pumps": "pumping",
    "pumped": "pumping",
}
GREETING_INPUTS = {
    "hello",
    "hey",
    "hi",
    "hiya",
    "yo",
    "good morning",
    "good afternoon",
    "good evening",
    "hey there",
    "hi there",
    "hello there",
    "whats up",
    "what s up",
    "what up",
    "sup",
    "alright",
    "all right",
}
CHECK_IN_INPUTS = {
    "how are you",
    "how re you",
    "how you doing",
    "how are you doing",
    "how is it going",
    "hows it going",
    "how s it going",
    "are you ok",
    "are you okay",
    "you good",
    "u good",
    "how are things",
    "hows things",
    "how are you today",
    "hows life",
}
THANKS_INPUTS = {
    "thanks",
    "thank you",
    "nice one",
    "cheers",
    "great thanks",
    "awesome thanks",
}
META_CHAT_PATTERNS = (
    r"\bwrong\s+(llm|bot|chat|assistant)\b",
    r"\bthought\s+you\s+were\b",
    r"\b(deepseek|chatgpt|claude|gemini)\b",
    r"\bwho\s+are\s+you\b",
    r"\bwhat\s+are\s+you\b",
)
FOLLOWUP_STARTERS = (
    "what about",
    "how about",
    "and what",
    "and how",
    "and if",
    "what if",
    "also",
    "same",
    "for that",
    "with that",
    "based on that",
    "following on",
    "following up",
    "can you explain",
    "break that down",
    "go deeper",
    "more detail",
    "what next",
    "next",
    "should i",
    "do i",
    "can i",
    "would it",
    "what kind",
    "what relationship",
    "why is that",
    "why does that",
)
FOLLOWUP_REFERENCES = {
    "it",
    "that",
    "this",
    "those",
    "these",
    "previous",
    "earlier",
    "above",
    "same",
}
UNCLEAR_INPUTS = {
    "can you help",
    "can you help me",
    "help me",
    "make it better",
    "what should i do",
    "what should i do next",
    "what next",
    "whats next",
    "what's next",
    "next step",
}
IMPOSSIBLE_PROMISE_TERMS = {
    "instant",
    "instantly",
    "magic",
    "secret",
}
BUSINESS_PRICING_TERMS = {
    "charge",
    "cost",
    # "discount"/"discounts" added 2026-08-02: found live-testing that "can
    # you give me a discount on mixing?" fell through to a generic
    # mixing-workflow tutorial instead of business_pricing_query() routing
    # it to client_delivery mode, the existing, tested pathway with real
    # scope-boundary business content (see client-mix-pricing-and-quotes.md
    # and tests/chat/test_chat_conversation.py's pricing-followup tests) --
    # every other pricing word here was already recognized, "discount" just
    # wasn't in the set.
    "discount",
    "discounts",
    "price",
    "pricing",
    "quote",
    "quoting",
    "rate",
    "rates",
}
MIX_REVIEW_FOLLOWUP_TERMS = {
    "analysis",
    "crest",
    "fix",
    "flag",
    "flags",
    "improve",
    "lab",
    "metric",
    "metrics",
    "mix",
    "peak",
    "progress",
    "review",
    "revision",
    "rms",
    "spectrum",
    "track",
    "version",
}
ABLETON_ROUTE_TOPICS = {
    "automation",
    "arrangement",
    "cpu",
    "freeze",
    "midi",
    "recording",
    "routing",
    "sound_design",
    "warp",
}
PRODUCTION_ROUTE_TOPICS = {
    "acoustics",
    "bass",
    "compression",
    "delay",
    "depth",
    "delivery",
    "drums",
    "eq",
    "export",
    "loudness",
    "mastering",
    "mixing",
    "monitoring",
    "podcast",
    "pricing",
    "reverb",
    "revision",
    "saturation",
    "stereo_width",
    "translation",
    "transients",
    "vocals",
}
GAME_ROUTE_TOPICS = {"game_audio", "wwise"}
GENERIC_TRACK_TITLE_TERMS = {
    "audio",
    "bounce",
    "demo",
    "final",
    "master",
    "mix",
    "my",
    "premaster",
    "real",
    "reference",
    "song",
    "test",
    "title",
    "track",
    "version",
}
