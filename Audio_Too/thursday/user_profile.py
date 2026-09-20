"""User Profile & Preference System — long-term personalization for Thursday.

Stores user preferences, learned patterns, shortcuts, and mood state
in a JSON profile that persists across sessions.

Provides:
  - User profile CRUD
  - Frequency tracking for learning
  - Shortcut management
  - Mood/tone state
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from thursday.runtime_paths import PROFILE_DIR

DEFAULT_PROFILE_ID = "default"


# ─── Default Profile Schema ──────────────────────────────────────────────


def _default_profile(profile_id: str = DEFAULT_PROFILE_ID) -> dict:
    """Create a default user profile."""
    return {
        "profile_id": profile_id,
        "user_name": "Jack",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "preferences": {
            "preferred_voice": "Samantha",
            "timezone": "Europe/London",
            "business_hours": {"start": "09:00", "end": "18:00"},
            "work_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
            "default_render_emotion": "joy",
            "default_bars": 8,
            "preferred_output": "concise",
            "auto_speak": False,
            "daily_briefing": True,
            "weekly_summary_day": "Friday",
            "alert_preferences": {
                "stale_leads": True,
                "overdue_invoices": True,
                "enquiries": True,
                "financial_warnings": True,
                "render_complete": True,
            },
        },
        "frequent_clients": [],
        "frequent_services": ["Mixing", "Mastering", "Recording"],
        "shortcuts": {},
        "mood": "neutral",
        "mood_history": [],
        "learning": {
            "request_counts": {},
            "last_request_date": None,
            "services_used_today": [],
            "last_daily_briefing": None,
        },
    }


# ─── Profile Storage ─────────────────────────────────────────────────────


def _profile_path(profile_id: str) -> Path:
    return PROFILE_DIR / f"{profile_id}.json"


def _load_profile(profile_id: str = DEFAULT_PROFILE_ID) -> dict:
    """Load a user profile from disk."""
    path = _profile_path(profile_id)
    if path.exists():
        try:
            loaded = json.loads(path.read_text())
            # Merge with defaults to ensure any new fields exist
            defaults = _default_profile(profile_id)
            for key, value in defaults.items():
                if key not in loaded:
                    loaded[key] = value
                elif isinstance(value, dict) and isinstance(loaded.get(key), dict):
                    for sub_key, sub_value in value.items():
                        if sub_key not in loaded[key]:
                            loaded[key][sub_key] = sub_value
            return loaded
        except (json.JSONDecodeError, OSError):
            pass
    # Create new profile
    profile = _default_profile(profile_id)
    _save_profile(profile)
    return profile


def _save_profile(profile: dict) -> None:
    """Save a user profile to disk."""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    profile["updated_at"] = datetime.now().isoformat()
    path = _profile_path(profile.get("profile_id", DEFAULT_PROFILE_ID))
    try:
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(profile, indent=2), encoding="utf-8")
        temporary.replace(path)
    except OSError:
        pass


# ─── Public API ──────────────────────────────────────────────────────────


def get_profile(profile_id: str = DEFAULT_PROFILE_ID) -> dict:
    """Get the user profile (lazy-loaded from disk)."""
    return _load_profile(profile_id)


def update_preference(key: str, value: Any, profile_id: str = DEFAULT_PROFILE_ID) -> dict:
    """Update a single preference value.

    Supports dot-notation for nested keys (e.g., "alert_preferences.stale_leads").
    """
    profile = _load_profile(profile_id)
    prefs = profile["preferences"]

    if "." in key:
        parts = key.split(".")
        current = prefs
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value
    else:
        prefs[key] = value

    _save_profile(profile)
    return profile


def get_preference(key: str, default: Any = None, profile_id: str = DEFAULT_PROFILE_ID) -> Any:
    """Get a preference value with optional default.

    Supports dot-notation for nested keys.
    """
    profile = _load_profile(profile_id)
    prefs = profile["preferences"]

    if "." in key:
        parts = key.split(".")
        current = prefs
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return default
        return current if current is not None else default

    return prefs.get(key, default)


# ─── Shortcuts ────────────────────────────────────────────────────────────


def add_shortcut(shortcut: str, expansion: str, profile_id: str = DEFAULT_PROFILE_ID) -> bool:
    """Add a shortcut (abbreviation → full name).

    Args:
        shortcut: The short form (e.g., "jj").
        expansion: The expanded value (e.g., "Jordan").
        profile_id: Profile to modify.

    Returns:
        True on success.
    """
    profile = _load_profile(profile_id)
    profile["shortcuts"][shortcut.lower()] = expansion
    _save_profile(profile)
    return True


def remove_shortcut(shortcut: str, profile_id: str = DEFAULT_PROFILE_ID) -> bool:
    """Remove a shortcut."""
    profile = _load_profile(profile_id)
    if shortcut.lower() in profile["shortcuts"]:
        del profile["shortcuts"][shortcut.lower()]
        _save_profile(profile)
        return True
    return False


def expand_shortcuts(text: str, profile_id: str = DEFAULT_PROFILE_ID) -> str:
    """Expand any shortcuts found in the text.

    E.g., "tell me about jj" → "tell me about Jordan"
    """
    profile = _load_profile(profile_id)
    shortcuts = profile.get("shortcuts", {})
    result = text
    for short, full in sorted(shortcuts.items(), key=lambda x: -len(x[0])):
        # Match as whole word
        result = re.sub(rf"\b{re.escape(short)}\b", full, result, flags=re.IGNORECASE)
    return result


# ─── Learning / Frequency Tracking ───────────────────────────────────────


def record_request(service_id: str | None, client_name: str | None = None, profile_id: str = DEFAULT_PROFILE_ID) -> None:
    """Record a request to learn patterns over time.

    Args:
        service_id: The service used (or None).
        client_name: Client referenced (or None).
        profile_id: Profile to update.
    """
    profile = _load_profile(profile_id)
    learning = profile["learning"]

    # Update request counts
    if service_id:
        counts = learning["request_counts"]
        counts[service_id] = counts.get(service_id, 0) + 1

    # Track frequent clients
    if client_name and client_name not in profile["frequent_clients"]:
        profile["frequent_clients"].append(client_name)
        # Keep list manageable
        profile["frequent_clients"] = profile["frequent_clients"][-20:]

    # Update last request date
    learning["last_request_date"] = datetime.now().isoformat()

    # Track services used today
    services_today = learning.get("services_used_today", [])
    if isinstance(services_today, list) and service_id and service_id not in services_today:
        services_today.append(service_id)
    # Prune old entries — keep only today's
    learning["services_used_today"] = services_today

    # Periodic auto-suggestion check
    _maybe_suggest_shortcuts(profile, service_id)

    _save_profile(profile)


def get_frequent_requests(profile_id: str = DEFAULT_PROFILE_ID, top_n: int = 5) -> list[tuple[str, int]]:
    """Get the most frequently requested services.

    Returns:
        List of (service_id, count) tuples sorted by count descending.
    """
    profile = _load_profile(profile_id)
    counts = profile["learning"]["request_counts"]
    return sorted(counts.items(), key=lambda x: -x[1])[:top_n]


def get_suggestions(profile_id: str = DEFAULT_PROFILE_ID) -> list[str]:
    """Get personalized suggestions based on learned patterns.

    Returns:
        List of suggestion strings.
    """
    profile = _load_profile(profile_id)
    suggestions = []

    # Check if daily briefing has been shown today
    last_briefing = profile["learning"].get("last_daily_briefing")
    today = datetime.now().strftime("%Y-%m-%d")
    if last_briefing != today:
        suggestions.append("Start with a daily briefing")

    # Suggest based on frequent requests
    top = get_frequent_requests(profile_id, top_n=3)
    for service_id, count in top:
        if count >= 3:
            service_names = {
                "business_status": "check business health",
                "pipeline": "view pipeline",
                "reminders": "check reminders",
                "invoices": "view invoices",
                "client_info": "check a client",
                "audiogen": "generate audio",
                "audio_analysis": "scan audio files",
            }
            suggestion = service_names.get(service_id)
            if suggestion:
                suggestions.append(f"Would you like to {suggestion}?")

    # Suggest shortcuts for frequent clients
    frequent_clients = profile.get("frequent_clients", [])
    for client in frequent_clients[:3]:
        client_lower = client.lower()
        existing_shortcuts = profile.get("shortcuts", {})
        # Check if this client already has a shortcut
        has_shortcut = any(
            expansion.lower() == client_lower
            for expansion in existing_shortcuts.values()
        )
        if not has_shortcut:
            shortcut = "".join(w[0] for w in client.split()).lower()[:2]
            if shortcut:
                suggestions.append(f"Create shortcut '{shortcut}' for {client}?")

    return suggestions


def _maybe_suggest_shortcuts(profile: dict, service_id: str | None) -> None:
    """Periodically check if a shortcut should be suggested."""
    # This is passive — it updates frequencies for later suggestion
    pass


# ─── Mood / Tone ─────────────────────────────────────────────────────────


MOOD_KEYWORDS = {
    "stressed": [
        r"\b(?:i(?:'?\s*m| am)\s+(?:so\s+)?(?:stressed|overwhelmed|frustrated|annoyed|fed\s*up|angry|upset))\b",
        r"\b(?:why\s+isn'?t\s+this\s+working|this\s+isn'?t\s+working|fix\s+this)\b",
    ],
    "celebrating": [
        r"\bgreat\s+news\b",
        r"\bwe\s+did\s+it\b",
        r"\blove\s+it\b",
        r"\bamazing\b",
        r"\bfantastic\b",
        r"\bexcellent\b",
        r"\b(?:so\s+)?happy\b",
        r"\b(?:that'?s|this\s+is)\s+(?:great|awesome|amazing|fantastic|wonderful)\b",
    ],
    "urgent": [
        r"\bright\s+now\b",
        r"\basap\b",
        r"\bimmediately\b",
        r"\burgent\b",
        r"\bas\s+soon\s+as\s+possible\b",
        r"\bthis\s+minute\b",
        r"\bno\s+time\b",
    ],
    "curious": [
        r"\bjust\s+checking\b",
        r"\bcurious\b",
        r"\bwondering\b",
        r"\bjust\s+wondering\b",
    ],
}


def detect_mood(text: str) -> str | None:
    """Detect mood from user text.

    Args:
        text: The user's input.

    Returns:
        Mood string ("stressed", "celebrating", "urgent", "curious") or None.

    Priority order: stressed > celebrating > urgent > curious
    """
    text_lower = text.lower().strip()

    # Check in priority order
    priority_order = ["stressed", "celebrating", "urgent", "curious"]
    for mood in priority_order:
        patterns = MOOD_KEYWORDS.get(mood, [])
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return mood
    return None


def set_mood(mood: str, profile_id: str = DEFAULT_PROFILE_ID) -> dict:
    """Set the current mood state.

    Args:
        mood: One of "neutral", "stressed", "celebrating", "urgent", "curious".
        profile_id: Profile to update.

    Returns:
        Updated profile.
    """
    profile = _load_profile(profile_id)
    previous_mood = profile.get("mood", "neutral")
    profile["mood"] = mood
    profile.setdefault("mood_history", [])
    profile["mood_history"].append({
        "mood": mood,
        "previous": previous_mood,
        "timestamp": datetime.now().isoformat(),
    })
    # Keep last 20 entries
    profile["mood_history"] = profile["mood_history"][-20:]
    _save_profile(profile)
    return profile


def get_mood(profile_id: str = DEFAULT_PROFILE_ID) -> str:
    """Get the current mood state."""
    profile = _load_profile(profile_id)
    return profile.get("mood", "neutral")


def mark_briefing_shown(profile_id: str = DEFAULT_PROFILE_ID) -> None:
    """Record that the daily briefing was shown today."""
    profile = _load_profile(profile_id)
    profile["learning"]["last_daily_briefing"] = datetime.now().strftime("%Y-%m-%d")
    _save_profile(profile)


def was_briefing_shown_today(profile_id: str = DEFAULT_PROFILE_ID) -> bool:
    """Check if the daily briefing was already shown today."""
    profile = _load_profile(profile_id)
    return profile["learning"].get("last_daily_briefing") == datetime.now().strftime("%Y-%m-%d")


def set_focus_mode(mode: str, profile_id: str = DEFAULT_PROFILE_ID) -> dict:
    """Set the user's active focus mode ("available", "focus_mixing", "do_not_disturb")."""
    profile = _load_profile(profile_id)
    profile.setdefault("preferences", {})["focus_mode"] = mode
    _save_profile(profile)

    # Also update the live EventBus focus mode
    try:
        from thursday.events import get_event_bus
        get_event_bus().set_focus_mode(mode)
    except Exception:
        pass

    return profile


def get_focus_mode(profile_id: str = DEFAULT_PROFILE_ID) -> str:
    """Get the current focus mode preference."""
    profile = _load_profile(profile_id)
    return profile.get("preferences", {}).get("focus_mode", "available")
