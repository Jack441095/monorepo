"""M8.5 — Natural Language Mix Control: intent parsing and plan adjustment.

Accepts a free-text instruction ("make the vocal brighter"), uses the KENN LM
to extract a structured intent, and applies a small DSP parameter change to the
existing MixPlan.  Falls back gracefully when the LM is unavailable.
"""

from __future__ import annotations

import json
import os
import re

# ---------------------------------------------------------------------------
# INTENT EXTRACTION  (LLM-assisted with deterministic fallback)
# ---------------------------------------------------------------------------

_INTENT_SYSTEM = (
    "You are an audio engineering assistant. Given a mix revision instruction "
    "and a brief mix summary, extract the user's intent as a single JSON object "
    "with these keys:\n"
    "  target_stem: string — the stem to adjust (e.g. 'vocal', 'kick', 'bass', 'all')\n"
    "  parameter:   string — one of 'gain_db', 'presence_gain', 'sub_gain', "
    "'bass_gain', 'air_gain', 'reverb_level', 'width', 'brightness', 'warmth'\n"
    "  direction:   string — 'up' or 'down'\n"
    "  magnitude:   string — 'subtle' (±0.5 dB), 'moderate' (±1.5 dB), or 'strong' (±3 dB)\n"
    "Output only the JSON object, no extra text."
)

_MAGNITUDE_DB = {"subtle": 0.5, "moderate": 1.5, "strong": 3.0}

_STEM_KEYWORDS: dict[str, list[str]] = {
    "vocal":    ["vocal", "voice", "singer", "lead", "vox"],
    "kick":     ["kick", "bass drum"],
    "snare":    ["snare"],
    "bass":     ["bass", "sub", "low end"],
    "hihat":    ["hihat", "hi-hat", "hat", "cymbal"],
    "guitar":   ["guitar"],
    "piano":    ["piano", "keys", "keyboard"],
    "synth":    ["synth", "pad", "lead synth"],
    "strings":  ["strings", "orchestra"],
    "brass":    ["brass", "horns", "horn section", "trumpet", "trombone", "sax", "saxophone"],
    "drums":    ["drums", "drum bus", "kit"],
}


def _parse_stem(utterance: str) -> str:
    lower = utterance.lower()
    for stem, keywords in _STEM_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return stem
    return "all"


def _keyword_fallback(utterance: str) -> dict:
    lower = utterance.lower()
    
    # 1. Parameter detection
    if any(k in lower for k in ("reverb", "wet", "roomy", "ambience", "ambient", "dry", "drier", "damp")):
        parameter = "reverb_level"
    elif any(k in lower for k in ("bright", "treble", "high", "sizzle", "air", "crisp")):
        parameter = "brightness"
    elif any(k in lower for k in ("warm", "mud", "box", "mid", "dull", "boomy")):
        parameter = "warmth"
    elif any(k in lower for k in ("width", "wider", "narrower", "stereo", "mono", "spacious", "focused")):
        parameter = "width"
    elif any(k in lower for k in ("punchier", "punch", "transient", "attack")):
        parameter = "sub_gain"
    elif any(k in lower for k in ("presence", "forward", "cut through")):
        parameter = "presence_gain"
    elif any(k in lower for k in ("louder", "loud", "up", "boost", "more volume", "quieter", "quiet", "down", "reduce", "less", "vocals", "vocal", "sing", "lead", "drums", "snare", "hihat", "kick", "bass")):
        parameter = "gain_db"
    else:
        has_stem = any(kw in lower for keywords in _STEM_KEYWORDS.values() for kw in keywords)
        has_direction = any(d in lower for d in ("less", "down", "reduce", "cut", "quiet", "quieter", "damp", "dry", "drier", "narrow", "narrower", "mono", "focused", "clear", "tame", "more", "up", "boost", "louder", "loud", "wetter", "roomier", "spacious", "wider", "add"))
        if has_stem or has_direction:
            parameter = "gain_db"
        else:
            parameter = "unrecognized"

    # 2. Direction detection
    direction = "up"
    if parameter == "warmth":
        if any(d in lower for d in ("down", "less", "cut", "clear", "mud", "muddy", "box", "boxiness")):
            direction = "down"
        if any(u in lower for u in ("up", "more", "boost", "warm", "warmer")):
            direction = "up"
    else:
        if any(d in lower for d in ("less", "down", "reduce", "cut", "quiet", "quieter", "damp", "dry", "drier", "narrow", "narrower", "mono", "focused", "clear", "tame")):
            direction = "down"
        if any(u in lower for u in ("more", "up", "boost", "louder", "loud", "wetter", "roomier", "spacious", "wider", "add")):
            direction = "up"

    # 3. Magnitude detection
    magnitude = "moderate"
    if any(m in lower for m in ("subtle", "a little", "bit", "slightly", "small", "gentle", "tiny")):
        magnitude = "subtle"
    elif any(m in lower for m in ("strong", "a lot", "heavy", "much", "very", "extreme", "significantly", "maximum")):
        magnitude = "strong"

    # 4. Stem target
    target_stem = _parse_stem(utterance)

    return {
        "target_stem": target_stem,
        "parameter": parameter,
        "direction": direction,
        "magnitude": magnitude
    }


_CLAUSE_SPLIT_RE = re.compile(r"\s*(?:,|;|\band\b|\balso\b)\s*", re.I)

# Words that anchor a clause to its OWN distinct topic/parameter category --
# deliberately excludes bare direction words (up/down/more/less/cut/...),
# which are ambiguous on their own (see _keyword_fallback_multi's docstring
# for why: "too bright, cut it down" must NOT be read as two separate
# instructions just because "cut" is a direction word). Mirrors
# _keyword_fallback()'s own parameter-detection categories.
_TOPIC_ANCHOR_WORDS = (
    "reverb", "wet", "roomy", "ambience", "ambient", "dry", "drier", "damp",
    "bright", "treble", "high", "sizzle", "air", "crisp",
    "warm", "mud", "box", "mid", "dull", "boomy",
    "width", "wider", "narrower", "stereo", "mono", "spacious", "focused",
    "punchier", "punch", "transient", "attack",
    "presence", "forward", "cut through",
)

_MULTI_INTENT_SYSTEM = (
    "You are an audio engineering assistant. Given a mix revision "
    "instruction (which may describe one or several distinct changes) and "
    "a brief mix summary, extract EVERY distinct change as a JSON array of "
    "objects, one per change. Each object has these keys:\n"
    "  target_stem: string — the stem to adjust (e.g. 'vocal', 'kick', 'bass', 'all')\n"
    "  parameter:   string — one of 'gain_db', 'presence_gain', 'sub_gain', "
    "'bass_gain', 'air_gain', 'reverb_level', 'width', 'brightness', 'warmth'\n"
    "  direction:   string — 'up' or 'down'\n"
    "  magnitude:   string — 'subtle' (±0.5 dB), 'moderate' (±1.5 dB), or 'strong' (±3 dB)\n"
    "Output only the JSON array, no extra text. A single-change instruction "
    "still outputs a one-element array."
)


def _valid_intent(intent: object) -> bool:
    if not isinstance(intent, dict):
        return False
    return all(key in intent for key in ("target_stem", "parameter", "direction", "magnitude"))


def _dedupe_intents(intents: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for intent in intents:
        key = (str(intent.get("target_stem", "")), str(intent.get("parameter", "")))
        if key in seen:
            continue
        seen.add(key)
        out.append(intent)
    return out


def _clause_has_own_topic(clause: str) -> bool:
    lower = clause.lower()
    if any(kw in lower for keywords in _STEM_KEYWORDS.values() for kw in keywords):
        return True
    return any(word in lower for word in _TOPIC_ANCHOR_WORDS)


def _keyword_fallback_multi(utterance: str) -> list[dict]:
    """Split a compound instruction into clauses and parse each
    independently -- _keyword_fallback() alone only ever returns the FIRST
    matching stem/parameter for a whole string (e.g. "vocals louder, bass
    louder too" resolves target_stem="vocal" only, because _parse_stem()
    stops at the first keyword hit anywhere in the string), silently
    dropping every other requested change. Parsing clause-by-clause fixes
    that: each clause gets its own independent stem/parameter resolution.

    Not every comma/"and" is a genuine clause boundary though: "too bright,
    cut it down" is ONE thought (reduce brightness), not two -- "cut it
    down" has no stem/topic word of its own, just a bare direction word
    ("cut") that's ambiguous in isolation. Splitting it off as its own
    clause misreads it as a separate "cut gain on everything" instruction
    AND loses the "down" direction from the brightness clause entirely
    (found via a real regression in the existing brightness-down test
    while building this). A split-off segment with no topic word of its
    own is merged back into the preceding clause instead of parsed alone.
    """
    raw_clauses = [c.strip() for c in _CLAUSE_SPLIT_RE.split(utterance) if c.strip()]
    merged_clauses: list[str] = []
    for clause in raw_clauses:
        if merged_clauses and not _clause_has_own_topic(clause):
            merged_clauses[-1] = f"{merged_clauses[-1]}, {clause}"
        else:
            merged_clauses.append(clause)

    intents = []
    for clause in merged_clauses:
        intent = _keyword_fallback(clause)
        if intent.get("parameter") == "unrecognized":
            continue
        intents.append(intent)
    return _dedupe_intents(intents)


def parse_mix_intents(utterance: str, report: dict) -> list[dict]:
    """Extract every distinct mix-adjustment intent from a free-text
    instruction that may describe one or several changes at once
    ("make the vocal louder, add more reverb, and brighten it up").

    Returns a list of intent dicts (same shape as parse_mix_intent()'s
    single return value), one per distinct (target_stem, parameter) pair,
    in the order they were mentioned. Empty list if nothing recognized.
    Falls back to keyword-clause-splitting when the LLM is unavailable,
    disabled, or returns something that doesn't validate -- never guesses
    at a plan the model didn't actually produce."""
    if not utterance or not utterance.strip():
        return []

    if os.environ.get("AUDIO_TOO_MIX_REVIEW_LLM", "").strip().lower() in {"1", "true", "yes", "on"}:
        try:
            from kenn.llm.llm_rewrite import chat_completion, is_enabled
            if is_enabled():
                summary = ""
                metrics = report.get("metrics") or {}
                tonal = (metrics.get("tonal_balance") or {}).get("profile", "")
                if tonal:
                    summary = f"Current mix: {tonal} tonal balance."
                messages = [
                    {"role": "system", "content": _MULTI_INTENT_SYSTEM},
                    {"role": "user", "content": f'Instruction: "{utterance}"\n{summary}'},
                ]
                raw = chat_completion(messages, task="rewrite").strip()
                if raw.startswith("```"):
                    raw = re.sub(r"^```(?:json)?\s*", "", raw)
                    raw = re.sub(r"\s*```$", "", raw)
                parsed = json.loads(raw)
                if isinstance(parsed, list) and parsed and all(_valid_intent(item) for item in parsed):
                    return _dedupe_intents(parsed)
        except Exception:
            pass

    return _keyword_fallback_multi(utterance)


def apply_intents_to_plan(intents: list[dict], mix_plan) -> object:
    """Apply every intent in sequence, folding each change onto the plan
    from the previous step (matching apply_intent_to_plan()'s own
    additive-not-replacing philosophy)."""
    for intent in intents:
        mix_plan = apply_intent_to_plan(intent, mix_plan)
    return mix_plan


def describe_mix_intents(intents: list[dict]) -> str:
    """Join each intent's description into one sentence fragment ("boost
    the overall level of vocal by a moderate +1.5 dB adjustment, and add
    more reverb on vocal (moderate adjustment)")."""
    if not intents:
        return (
            "make an adjustment based on your feedback -- I couldn't pin down a "
            "specific parameter from that wording, so try being more specific "
            "(e.g. \"boost the vocal\", \"add more reverb\", \"make it brighter\")"
        )
    parts = [describe_mix_intent(intent) for intent in intents]
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + f", and {parts[-1]}"


def parse_mix_intent(utterance: str, report: dict) -> dict:
    """Extract a structured mix adjustment intent from a free-text instruction.

    Returns a dict with keys: target_stem, parameter, direction, magnitude.
    Falls back to keyword heuristics when the LLM is unavailable or disabled.
    """
    if not utterance or not utterance.strip():
        return _keyword_fallback(utterance)

    if os.environ.get("AUDIO_TOO_MIX_REVIEW_LLM", "").strip().lower() not in {"1", "true", "yes", "on"}:
        return _keyword_fallback(utterance)

    try:
        from kenn.llm.llm_rewrite import chat_completion, is_enabled
        if not is_enabled():
            return _keyword_fallback(utterance)

        summary = ""
        metrics = report.get("metrics") or {}
        tonal = (metrics.get("tonal_balance") or {}).get("profile", "")
        if tonal:
            summary = f"Current mix: {tonal} tonal balance."

        messages = [
            {"role": "system", "content": _INTENT_SYSTEM},
            {"role": "user", "content": f'Instruction: "{utterance}"\n{summary}'},
        ]
        raw = chat_completion(messages, task="rewrite").strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()
        intent = json.loads(raw)
        for key in ("target_stem", "parameter", "direction", "magnitude"):
            if key not in intent:
                raise ValueError(f"Missing key: {key}")
        return intent
    except Exception:
        return _keyword_fallback(utterance)


# ---------------------------------------------------------------------------
# PLAN ADJUSTMENT
# ---------------------------------------------------------------------------

def apply_intent_to_plan(intent: dict, mix_plan) -> object:
    """Apply a parsed mix intent to a MixPlan, returning the modified plan.

    Adjustments are small and non-destructive — they add onto existing
    stem parameters rather than replacing them.
    """
    from dataclasses import replace

    target_stem = str(intent.get("target_stem", "all")).lower()
    parameter = str(intent.get("parameter", "gain_db"))
    direction = str(intent.get("direction", "up"))
    magnitude = str(intent.get("magnitude", "moderate"))

    if parameter == "unrecognized":
        return mix_plan

    sign = 1.0 if direction == "up" else -1.0
    delta = _MAGNITUDE_DB.get(magnitude, 1.5) * sign

    if parameter == "brightness":
        new_band = {
            "type": "highshelf",
            "frequency": 8000.0,
            "gain_db": round(delta, 2),
            "q": 0.707,
            "reason": f"Feedback correction: master highshelf {direction} of {round(delta, 2)} dB ({magnitude})"
        }
        new_bus = replace(mix_plan.bus, bus_eq_bands=[*mix_plan.bus.bus_eq_bands, new_band])
        return replace(mix_plan, bus=new_bus)
    elif parameter == "warmth":
        new_band = {
            "type": "peaking",
            "frequency": 300.0,
            "gain_db": round(delta, 2),
            "q": 1.0,
            "reason": f"Feedback correction: master low-mid peaking {direction} of {round(delta, 2)} dB ({magnitude})"
        }
        new_bus = replace(mix_plan.bus, bus_eq_bands=[*mix_plan.bus.bus_eq_bands, new_band])
        return replace(mix_plan, bus=new_bus)

    # Frequency mapping for EQ-based parameters
    _EQ_PARAMS = {
        "presence_gain": {"type": "peaking", "frequency": 3500.0, "q": 0.9},
        "sub_gain":      {"type": "peaking", "frequency": 60.0,   "q": 0.7},
        "bass_gain":     {"type": "peaking", "frequency": 120.0,  "q": 0.8},
        "air_gain":      {"type": "high_shelf", "frequency": 10000.0, "q": 0.7},
    }

    new_stems = []
    for cfg in mix_plan.stems:
        stem_matches = (
            target_stem == "all"
            or target_stem in cfg.stem_name.lower()
            or target_stem == cfg.instrument.lower()
        )
        if not stem_matches:
            new_stems.append(cfg)
            continue

        if parameter == "gain_db":
            new_cfg = replace(cfg, gain_db=round(cfg.gain_db + delta, 2))
        elif parameter == "width":
            new_cfg = replace(cfg, stereo_width=round(max(0.3, min(2.0, cfg.stereo_width + delta * 0.1)), 3))
        elif parameter == "reverb_level":
            new_cfg = replace(cfg, reverb_send=round(max(0.0, min(1.0, cfg.reverb_send + delta * 0.1)), 3))
        elif parameter in _EQ_PARAMS:
            eq_params = _EQ_PARAMS[parameter]
            new_band = {**eq_params, "gain_db": round(delta, 2)}
            new_cfg = replace(cfg, eq_bands=[*cfg.eq_bands, new_band])
        else:
            new_cfg = cfg

        new_stems.append(new_cfg)

    return replace(mix_plan, stems=new_stems)


# ---------------------------------------------------------------------------
# NATURAL-LANGUAGE EXPLANATION
# ---------------------------------------------------------------------------

# Kept next to apply_intent_to_plan()'s real parameter->frequency/target
# mapping deliberately, not in the chat-facing caller (business/app/
# ableton_bridge.py) -- if that mapping ever changes (a different frequency,
# a new parameter), the explanation text changes in the same file, in the
# same review, instead of silently drifting out of sync with what actually
# gets applied.
_PARAMETER_DESCRIPTIONS = {
    "brightness": "the brightness highshelf EQ on the master bus",
    "warmth": "the low-mid warmth EQ on the master bus",
    "presence_gain": "presence around 3.5 kHz on {stem}",
    "sub_gain": "the sub-bass around 60 Hz on {stem}",
    "bass_gain": "the low end around 120 Hz on {stem}",
    "air_gain": "the air/high shelf above 10 kHz on {stem}",
    "gain_db": "the overall level of {stem}",
}


def describe_mix_intent(intent: dict) -> str:
    """Turn a parsed mix intent into a natural-language explanation of the
    actual DSP change about to be queued -- mirrors apply_intent_to_plan()'s
    real parameter mapping exactly, so what's said matches what's applied.

    Returns a plain description ("boost the brightness highshelf EQ on the
    master bus by a moderate +1.5 dB adjustment") with no leading verb/
    pronoun, so callers can compose it into their own sentence (e.g.
    f"I'll {describe_mix_intent(intent)}.").
    """
    target_stem = str(intent.get("target_stem", "all")).lower()
    parameter = str(intent.get("parameter", "gain_db"))
    direction = str(intent.get("direction", "up"))
    magnitude = str(intent.get("magnitude", "moderate"))

    if parameter == "unrecognized":
        return (
            "make an adjustment based on your feedback -- I couldn't pin down a "
            "specific parameter from that wording, so try being more specific "
            "(e.g. \"boost the vocal\", \"add more reverb\", \"make it brighter\")"
        )

    sign = 1.0 if direction == "up" else -1.0
    delta = round(_MAGNITUDE_DB.get(magnitude, 1.5) * sign, 2)
    sign_str = f"+{delta}" if delta >= 0 else str(delta)
    verb = "boost" if direction == "up" else "cut"
    stem_label = "all" if target_stem in ("all", "") else target_stem

    if parameter == "width":
        action = "widen" if direction == "up" else "narrow"
        return f"{action} the stereo image of {stem_label} ({magnitude} adjustment)"
    if parameter == "reverb_level":
        action = "add more" if direction == "up" else "pull back"
        return f"{action} reverb on {stem_label} ({magnitude} adjustment)"

    template = _PARAMETER_DESCRIPTIONS.get(parameter, "{param} on {stem}")
    target = template.format(stem=stem_label, param=parameter.replace("_", " "))
    return f"{verb} {target} by a {magnitude} {sign_str} dB adjustment"
