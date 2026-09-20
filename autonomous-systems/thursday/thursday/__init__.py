"""Thursday — the orchestration agent for Audio_Too.

Thursday is a proactive, context-aware orchestrator that:
  - Remembers conversation context across turns
  - Classifies intents and extracts entities
  - Routes to the right module (KENN, AudioGen, Audio Analysis, agents, etc.)
  - Monitors business health proactively with alerts
  - Presents a unified conversational interface

Usage:
    ./audio-too thursday "<your request>"
    ./agent thursday "<your request>"
    ./audio-too thursday --new-session "<your request>"
"""

from __future__ import annotations

# Core modules
from thursday.session_manager import (
    get_or_create_session,
    load_session,
    save_session,
    add_turn,
    update_context,
    get_context,
    clear_context,
    list_sessions,
    new_session,
)

from thursday.intent import classify_intent, extract_entities, resolve_entities
from thursday.resolver import resolve_request, resolve_reply
from thursday.formatter import format_response, format_help, suggest_follow_ups
from thursday.errors import ThursdayError, MissingInfoError, NoMatchError

# Shortcuts for common operations
__all__ = [
    "get_or_create_session",
    "load_session",
    "save_session",
    "add_turn",
    "update_context",
    "get_context",
    "clear_context",
    "list_sessions",
    "new_session",
    "classify_intent",
    "extract_entities",
    "resolve_entities",
    "resolve_request",
    "resolve_reply",
    "format_response",
    "format_help",
    "suggest_follow_ups",
    "ThursdayError",
    "MissingInfoError",
    "NoMatchError",
]
