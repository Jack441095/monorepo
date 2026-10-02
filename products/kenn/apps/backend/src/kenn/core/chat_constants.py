"""Shared paths, thresholds, and vocab constants for the kenn.core.chat_* modules.

Split out of chat.py (was 4,298 lines) so every chat_* module can depend on a single
low-level constants module without circular imports. See docs/BACKLOG.md for the
decomposition record.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from kenn.core.lm_identity import SYSTEM_INTRO
from kenn.paths import PRODUCT_ROOT

ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = ROOT.parent
REPO_ROOT = PRODUCT_ROOT
WEBSITE_ROOT = REPO_ROOT / "packages" / "website"
ANALYSIS_TOOL_ROOT = REPO_ROOT / "packages" / "audio-analysis"

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

# How far down the ranked list the model reads for context, and therefore how far the evidence gate reads too.
# It is one number because the two drifting apart is the bug, and llm_rewrite.model_evidence() now hands the
# gate the same excerpt list the prompt was built from rather than letting it re-derive one.
#
# 2 Oct 2026, streaming chat, kenn-brain-qwen3-8b, cache off. Widening the model's context to a 12-chunk scan
# with a 1200-char block and 400 chars per chunk was correct, but the gate stayed on display_results(query,
# results, 3) — the top 3 only. So a figure living in chunk #7 was quoted back to us and reported invented,
# because the gate had never read chunk #7. Acceptance fell from 41% (12 of 29) to 27% (4 of 15): 10
# unsupported-measurement rejections and 3 fabricated-source rejections, all caused by chunks the gate
# never looked at. The offline sweep had only confirmed the measurements reached the model; it never checked
# that the gate knew about them. That is the whole class of error here — measure the seam, not one end.
#
# The same seam was then fixed in the other direction. The gate had been reading every chunk's text in full
# while the prompt fitted 2 to 4 excerpts into 1200 chars at 400 each, so on index v-db8c6334cf63 the reverb
# query showed the model 3 excerpts while the gate read 10 chunks, and 22 measurements sat in gate evidence the
# model was never shown. A figure from the model's training prior got waved through on the strength of a chunk
# it had not read.
#
# This is not a loosening of what counts as support. A number still has to appear verbatim in text the model
# was actually shown, and a cited filename still has to be a source it was shown a label for. Only the drift
# between the two sides is gone.
EVIDENCE_SCAN_WINDOW = 12

_TRY_LABEL = re.compile(
    r"(?:try\s+this|try\s+it|to\s+apply\s+this|concrete\s+steps|correction\s+steps)\s*:",
    re.IGNORECASE,
)
_STEP_LINE_START = re.compile(r"^\s*\d+\.\s+\S+")
_STEP_INLINE = re.compile(r"\d+\.\s+\S+")


def count_actionable_steps(text: str) -> int:
    """Numbered steps, whether each sits on its own line or runs on after the label.

    This counted only line-initial steps, so an answer that wrote "Try this: 1. ... 2. ..." on one line
    scored zero and was rejected for having no steps at all. 18 of 29 captured candidates wrote it that
    way and all 4 that were accepted happened to break the lines. The prompt never specified a layout,
    so acceptance was a formatting coin-flip. Inline steps count only on a line carrying an explicit
    "try this" label, so numbered text in prose cannot satisfy the gate.
    """
    total = 0
    for line in text.splitlines():
        if _STEP_LINE_START.match(line):
            total += len(_STEP_LINE_START.findall(line))
        elif _TRY_LABEL.search(line):
            total += len(_STEP_INLINE.findall(line))
    return total
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
    "studio_dialogue",
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
    "ableton_link",
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
