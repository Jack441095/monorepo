"""Conversational rewrite pass for Thursday's deterministic service replies.

format_response() renders raw service data mechanically (thursday/formatter.py's
_humanize() turns a dict into "  Key Name: value" lines) -- accurate, but not
how a person talks. This optionally passes that same, already-correct text
through an LLM to phrase it the way Thursday would actually say it out loud,
without changing any of the underlying facts.

Opt-in via THURSDAY_CONVERSATIONAL_REPLIES (default off), same pattern as
THURSDAY_BRAIN_ENABLED/THURSDAY_TTS_PARALLEL_CHUNKS elsewhere in this codebase
-- Jack turns it on deliberately rather than it silently changing behaviour.

Goes through thursday.llm_provider (the same swappable provider abstraction
thursday/brain.py uses), defaulting to the same audio_too.model_runtime.
DEFAULT_LLM provider brain.py already calls successfully in this environment
(local-first via Ollama, auto-resolving without needing AUDIO_TOO_LLM_ENABLED
set at all -- see EnvGatedProvider). studio/kenn/kenn/llm/llm_rewrite.py was
considered instead (it already has a plain-text chat_completion() with
caching/retry), but its readiness gate requires AUDIO_TOO_LLM_ENABLED
specifically, which is unset in Jack's .env even though
THURSDAY_BRAIN_ENABLED=1 already works -- that mismatch would have made this
feature silently no-op. json_mode=False here (not response_schema) so it
doesn't force JSON-object output the way brain.py's structured decisions
need -- thursday.llm_provider.AudioTooProvider forwards it to the underlying
DEFAULT_LLM.generate() call unchanged from before this module used the
provider abstraction.
"""

from __future__ import annotations

import logging
import os
import re

from thursday.llm_provider import get_llm_provider

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are Thursday, a warm, direct studio-business assistant for Jack at "
    "Audio_Too. Rewrite the raw data below into a short, natural, spoken-style "
    "reply -- the way you'd actually say it to Jack, not a report.\n\n"
    "The raw data is a single point-in-time snapshot. It contains NO history, "
    "NO previous period, and NO trend information.\n\n"
    "Rules:\n"
    "- Do NOT invent, round, or omit any number, name, date, or fact. Every "
    "figure in your reply must appear in the raw data below, verbatim.\n"
    "- Do NOT claim anything went up, down, grew, dropped, or changed, and do "
    "NOT compare this to a previous period -- the raw data has no such "
    "information, so any comparison would be invented.\n"
    "- Do NOT add advice, opinions, editorial judgement (\"great\", \"nice\", "
    "\"balanced\"), or context that isn't in the raw data. State the facts "
    "plainly and warmly, nothing more.\n"
    "- Keep it brief: 1-3 sentences for a simple result, a short natural list "
    "for a multi-item result.\n"
    "- Never say \"as an AI\" or describe your own process.\n"
    "- If the raw data says nothing was found or an error occurred, say that "
    "plainly and naturally -- don't paper over it."
)

# Matches integers/decimals, optionally with a leading sign or trailing '%' --
# deliberately simple (business data: counts, dollar amounts, percentages,
# dates), not the audio-unit-aware regex KENN's chat_grounding.py uses.
# The decimal group requires a digit after the '.' (\.\d+, not \.?\d*) so a
# number sitting at the end of a sentence ("...in revenue.") doesn't swallow
# the full stop into the token and then get falsely flagged as unsupported.
_NUMBER_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?%?")

# format_response()'s raw data is always digits (thursday/formatter.py's
# _humanize() renders raw values, never spells numbers out as words), but a
# rewrite can hallucinate a wrong figure in word form -- live-tested
# 2026-08-02 against the real local model (qwen2.5:1.5b): asked to restate
# "Active Clients: 4", it wrote "five active clients" in one run. The
# digit-only check above can't see that at all, so spelled-out runs get
# parsed to their numeric value and checked the same way.
_ONES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}
_SCALES = {"hundred": 100, "thousand": 1000, "million": 1_000_000, "billion": 1_000_000_000}

# format_response()'s raw data is always a single point-in-time snapshot
# (thursday/formatter.py's _humanize() has no concept of a prior period) --
# so any trend/comparison language in a rewrite is, by construction, an
# invented claim, even when it uses spelled-out numbers ("twenty five
# thousand") that the digit-only grounding check above can't see. Live-
# tested 2026-08-02 against the real local model (qwen2.5:1.5b): asked to
# describe a flat revenue figure, it fabricated "moving past the halfway
# point" and "a bump up by twenty five thousand dollars" -- both false,
# neither caught by the number check since no raw digits were echoed.
# Expanded 2026-08-02 after a second live run past the first version of this
# list: "The revenue's up from a few weeks ago" slipped through ("up from"
# and "a few weeks ago" weren't covered). Deliberately generous -- a false
# rejection is cheap (falls back to the mechanical text), a missed
# fabricated trend is not.
_TREND_MARKERS = (
    "increase", "increased", "decrease", "decreased", "compared to",
    "versus", " vs ", "last month", "last week", "last year",
    "previous month", "previous period", "growth", "grew", "grown",
    "bump up", "bumped up", "jump", "jumped", "halfway", "trending",
    "on track", "ahead of", "behind", "up by", "down by", "up from",
    "down from", "rose", "fell", " ago", "since last", "recently",
    "earlier this", "a few weeks", "a few days", "than before",
    "than last", "so far compared",
)

# "revenue are up!" / "client count is down" -- a bare directional predicate,
# not caught by the phrase list above (which looks for "up by"/"up from",
# not standalone "up"/"down"). Scoped to this specific is/are/looks+up/down
# predicate pattern rather than banning "up"/"down" as bare substrings,
# which would false-positive on "up next", "signed up", "up for review" and
# make the feature reject almost everything. Also excludes "up to date"/
# "up for renewal" -- plausible, non-trend business phrasing in exactly this
# domain (invoices, contracts) that isn't a directional claim at all.
_DIRECTIONAL_PREDICATE_RE = re.compile(
    r"\b(?:is|are|looks?|seems?|remains?)\s+(?:up|down)\b(?!\s+(?:to\s+date|for\s+renewal))"
)


def is_enabled() -> bool:
    return os.environ.get("THURSDAY_CONVERSATIONAL_REPLIES", "0").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _numbers_in(text: str) -> set[str]:
    # Strip thousand-separator commas so "1,250" and "1250" compare equal --
    # the LLM reformatting a number for readability isn't a hallucination.
    return {tok.replace(",", "") for tok in _NUMBER_RE.findall(text)}


def _word_numbers_in(text: str) -> set[str]:
    """Find runs of English number words (e.g. "twenty five thousand", "four")
    and return each run's numeric value as a digit string. Deliberately
    covers only the realistic range for business data (counts, dollar
    amounts up to billions) -- not ordinals, fractions, or "a"/"an" as
    an implicit one.

    Deliberately biased toward over-rejecting: "one" used as an indefinite
    pronoun ("just check on one of these") can trigger a false rejection if
    "1" never appears in the raw data. That's an acceptable trade-off here --
    a false rejection just falls back to the existing, always-correct
    mechanical text (see rewrite()'s callers), while a missed hallucination
    shows Jack a wrong fact outright.
    """
    tokens = re.findall(r"[a-z]+", text.lower())
    values: set[str] = set()
    current = 0
    total = 0
    in_run = False

    def _flush() -> None:
        nonlocal current, total, in_run
        if in_run and (total + current) > 0:
            values.add(str(total + current))
        current = 0
        total = 0
        in_run = False

    for tok in tokens:
        if tok in _ONES:
            current += _ONES[tok]
            in_run = True
        elif tok in _TENS:
            current += _TENS[tok]
            in_run = True
        elif tok == "hundred" and in_run:
            current = (current or 1) * 100
        elif tok in ("thousand", "million", "billion") and in_run:
            total += (current or 1) * _SCALES[tok]
            current = 0
        elif tok == "and" and in_run:
            continue
        else:
            _flush()
    _flush()
    return values


def rewrite(question: str, raw_text: str, service_name: str) -> str | None:
    """Return a natural-language rewrite of raw_text, or None to keep raw_text as-is.

    Returns None (falls back to the existing mechanical text -- never breaks a
    working reply) when: the feature is off, there's no question context, the
    LLM is unavailable/misconfigured, the call fails, or the grounding check
    below rejects the result because it introduced a number not present in
    the raw data.
    """
    if not is_enabled() or not question.strip() or not raw_text.strip():
        return None

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"User asked: {question}\n\n"
                f"Raw data from {service_name}:\n{raw_text}"
            ),
        },
    ]
    try:
        from thursday.llm_provider import default_timeout, get_llm_provider
        result = get_llm_provider().generate(messages, timeout=default_timeout(), json_mode=False)
    except Exception:
        logger.warning("Thursday conversational rewrite call failed", exc_info=True)
        return None

    text = (result.content or "").strip()
    if not text:
        return None

    # Grounding safety net (mirrors studio/kenn/kenn/core/chat_grounding.py's
    # rejection of unsupported measurements): a rewrite is only trustworthy if
    # every number it states was already in the source data. This is a strict
    # superset check, not a claim the LLM only ever changes wording -- any new
    # number is treated as a possible hallucination and the whole rewrite is
    # discarded in favour of the always-correct mechanical text.
    raw_numbers = _numbers_in(raw_text)
    unsupported = _numbers_in(text) - raw_numbers
    if unsupported:
        logger.warning(
            "Rejected conversational rewrite for %s: unsupported numbers %s",
            service_name, sorted(unsupported),
        )
        return None

    unsupported_words = _word_numbers_in(text) - raw_numbers
    if unsupported_words:
        logger.warning(
            "Rejected conversational rewrite for %s: unsupported spelled-out numbers %s",
            service_name, sorted(unsupported_words),
        )
        return None

    # Second grounding check: trend/comparison language is always invented
    # (see _TREND_MARKERS above) since the raw data has no prior-period
    # figures to compare against, and it can smuggle in a false claim using
    # spelled-out numbers the digit check above can't see.
    lowered_text = text.lower()
    lowered_raw = raw_text.lower()
    invented_trend_claims = [
        marker for marker in _TREND_MARKERS
        if marker in lowered_text and marker not in lowered_raw
    ]
    if invented_trend_claims:
        logger.warning(
            "Rejected conversational rewrite for %s: invented trend/comparison language %s",
            service_name, invented_trend_claims,
        )
        return None

    if _DIRECTIONAL_PREDICATE_RE.search(lowered_text) and not _DIRECTIONAL_PREDICATE_RE.search(lowered_raw):
        logger.warning(
            "Rejected conversational rewrite for %s: bare directional claim (e.g. 'revenue are up')",
            service_name,
        )
        return None

    return text
