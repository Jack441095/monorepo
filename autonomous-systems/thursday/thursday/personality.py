"""Thursday's Personality & Character — tone, catchphrases, greetings,
and emotional intelligence.

Provides a configurable persona that makes Thursday feel like a companion,
not just a tool. Adapts tone based on time of day, user mood, and context.
"""

from __future__ import annotations

from datetime import datetime

import thursday.user_profile as profile_api


# ─── Catchphrases ────────────────────────────────────────────────────────

CATCHPHRASES = {
    "on_it": [
        "On it.",
        "Let me look into that.",
        "One moment.",
        "I'm on it.",
        "Right away.",
    ],
    "done": [
        "Done.",
        "All set.",
        "There you go.",
        "Finished.",
        "Sorted.",
    ],
    "presenting": [
        "Here's what I found:",
        "Here you go:",
        "Here's the summary:",
        "I found this for you:",
        "Here are the results:",
    ],
    "alerts": [
        "I've got a few things to flag.",
        "A few things need your attention:",
        "I noticed a couple of things:",
        "Quick heads up:",
    ],
    "whats_next": [
        "What's next?",
        "What else can I do for you?",
        "Anything else?",
        "Ready for more?",
        "Let me know what you need next.",
    ],
    "thinking": [
        "One sec...",
        "Let me think about that...",
        "Checking on that now...",
        "Give me a moment...",
    ],
    "error": [
        "Hmm, something went wrong.",
        "I ran into an issue:",
        "That didn't quite work. Here's what happened:",
    ],
    "no_match": [
        "I'm not sure what to do with that.",
        "I'm not following. Could you rephrase?",
        "I don't quite understand. Try asking differently:",
    ],
}


# ─── Greeting Templates ──────────────────────────────────────────────────

def _morning_greeting(name: str = "") -> str:
    variants = [
        f"Good morning{', ' + name if name else ''}.",
        # No exclamation mark here on purpose: Kokoro TTS reads a "!" right
        # after the opening word with emphatic, faster prosody, which Jack
        # reported as sounding "aggressive" and "a bit fast" (2026-07-10).
        f"Morning{', ' + name.split()[0] if name else ''}. Ready to get started?",
        f"Good morning{', ' + name if name else ''}. I've got your day lined up.",
    ]
    import random
    return random.choice(variants)


def _afternoon_greeting(name: str = "") -> str:
    variants = [
        f"Good afternoon{', ' + name if name else ''}.",
        f"Afternoon{', ' + name.split()[0] if name else ''}. How's your day going?",
        f"Good afternoon. Hope you're having a productive day{', ' + name if name else ''}.",
    ]
    import random
    return random.choice(variants)


def _evening_greeting(name: str = "") -> str:
    variants = [
        f"Good evening{', ' + name if name else ''}.",
        f"Evening{', ' + name.split()[0] if name else ''}. Still going? I've got things under control.",
        "Good evening. Here's a quick update — let me know if you need anything else.",
    ]
    import random
    return random.choice(variants)


def _returning_greeting(name: str = "") -> str:
    variants = [
        f"Welcome back{', ' + name.split()[0] if name else ''}. A few things happened while you were away.",
        f"Good to see you again{', ' + name if name else ''}. I've been keeping an eye on things.",
        f"Back{', ' + name.split()[0] if name else ''}. Let me catch you up.",
    ]
    import random
    return random.choice(variants)


def _weekend_greeting(name: str = "") -> str:
    variants = [
        f"Hey{', ' + name.split()[0] if name else ''}. It's the weekend. Let me keep it short.",
        "Quiet day. I'll keep an eye on things.",
        f"Hope you're enjoying the weekend{', ' + name.split()[0] if name else ''}. I'm here if you need anything.",
    ]
    import random
    return random.choice(variants)


# ─── Tone Adaptation ─────────────────────────────────────────────────────


def get_greeting(profile: dict | None = None, context: dict | None = None) -> str:
    """Get a context-aware greeting.

    Args:
        profile: User profile (or None to load default).
        context: Session context (to check time between visits).

    Returns:
        Greeting string.
    """
    if profile is None:
        profile = profile_api.get_profile()

    name = profile.get("user_name", "")
    now = datetime.now()
    hour = now.hour

    # Weekend check
    if now.weekday() >= 5:
        return _weekend_greeting(name)

    # Check if this is a returning user (gap > 2 hours)
    if context and context.get("last_visit"):
        try:
            last_visit = context["last_visit"]
            if isinstance(last_visit, str):
                from datetime import datetime as dt2
                last_dt = dt2.fromisoformat(last_visit.replace("Z", "+00:00")).replace(tzinfo=None)
            else:
                last_dt = last_visit
            gap_hours = (now - last_dt).total_seconds() / 3600
            if gap_hours > 2:
                return _returning_greeting(name)
        except (ValueError, TypeError):
            pass

    # Time of day greeting
    if 5 <= hour < 12:
        return _morning_greeting(name)
    elif 12 <= hour < 17:
        return _afternoon_greeting(name)
    else:
        return _evening_greeting(name)


def format_with_tone(response: str, tone: dict | None = None) -> str:
    """Apply tone modifiers to a response.

    Args:
        response: The raw response text.
        tone: Dict with "style" (concise/detailed/warm/professional).

    Returns:
        Tone-adjusted response.
    """
    if not tone:
        return response

    style = tone.get("style", "professional")

    if style == "concise":
        # Strip verbose phrasing, keep it short
        lines = response.split("\n")
        concise_lines = [ln for ln in lines if not ln.startswith("**Try next") and "suggest" not in ln.lower()]
        return "\n".join(concise_lines[:min(len(concise_lines), 10)])

    if style == "warm":
        # Add emoji-friendly touches
        response = response.replace("Here's", "Here's ✨")
        if "Done." in response:
            response = response.replace("Done.", "Done! ✅")
        if "On it." in response:
            response = response.replace("On it.", "On it! 🚀")

    return response


# ─── Mood Response Mapper ────────────────────────────────────────────────


MOOD_RESPONSE_MODIFIERS = {
    "stressed": {
        "prefix": "Let me help sort that out.",
        "style": "concise",
        "extra_suggestions": ["Take a breath", "Want to reschedule anything?"],
    },
    "celebrating": {
        "prefix": "That's great!",
        "style": "warm",
        "extra_suggestions": ["Want to share this on social media?", "Celebrate this win!"],
    },
    "urgent": {
        "prefix": "On it right now.",
        "style": "concise",
        "skip_greeting": True,
        "extra_suggestions": [],
    },
    "curious": {
        "prefix": "Happy to help with that.",
        "style": "detailed",
        "extra_suggestions": [],
    },
    "neutral": {
        "prefix": None,
        "style": "professional",
        "extra_suggestions": [],
    },
}


def get_mood_response_modifiers(mood: str) -> dict:
    """Get response modifiers for a given mood.

    Args:
        mood: The detected mood ("stressed", "celebrating", "urgent", etc.).

    Returns:
        Dict with "prefix", "style", "extra_suggestions".
    """
    return MOOD_RESPONSE_MODIFIERS.get(mood, MOOD_RESPONSE_MODIFIERS["neutral"])


# ─── Response Shortcuts ──────────────────────────────────────────────────


def short_response(key: str) -> str:
    """Get a random catchphrase for a given key.

    Args:
        key: One of "on_it", "done", "presenting", "alerts", etc.

    Returns:
        A random catchphrase string.
    """
    import random
    phrases = CATCHPHRASES.get(key, ["OK."])
    return random.choice(phrases)


def identify_text(text: str, profanity_check: bool = True) -> str:
    """Interpret user cues about mood and urgency to set tone."""
    text_lower = text.lower().strip()

    if any(w in text_lower for w in ["stressed", "overwhelmed", "frustrated", "angry"]):
        return "stressed"
    if any(w in text_lower for w in ["great", "amazing", "fantastic", "celebrate", "awesome"]):
        return "celebrating"
    if any(w in text_lower for w in ["urgent", "asap", "right now", "immediately", "hurry"]):
        return "urgent"
    if any(w in text_lower for w in ["just checking", "wondering", "curious"]):
        return "curious"

    return "neutral"

