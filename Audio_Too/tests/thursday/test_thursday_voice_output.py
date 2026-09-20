from __future__ import annotations

from thursday.voice_output import _sanitize_for_speech


def test_sanitize_strips_try_next_trailer():
    """Regression (2026-07-27, Jack live-testing): "what's written doesn't
    match what's said" -- the dashboard's streaming path sends the whole
    formatted answer (including formatter.py's UI-only "**Try next:**"
    suggestion trailer) as speech input. That trailer must never be read
    aloud -- it's a row of clickable chips, not part of the answer.
    """
    text = (
        "Good afternoon, Jack.\n\n"
        "**Try next:** Ask me about 'reminders' for what's due | Try 'pipeline summary'"
    )
    assert _sanitize_for_speech(text) == "Good afternoon, Jack."


def test_sanitize_strips_suggestion_trailer():
    text = (
        "Top service for 2026: Mixing.\n\n"
        "*Suggestion:* Would you like to check a client?"
    )
    assert _sanitize_for_speech(text) == "Top service for 2026: Mixing."


def test_sanitize_strips_both_trailers_together():
    text = (
        "Here's the answer.\n\n"
        "**Try next:** Ask for 'help'\n\n"
        "*Suggestion:* Want the weekly review?"
    )
    assert _sanitize_for_speech(text) == "Here's the answer."


def test_sanitize_leaves_plain_answer_text_untouched():
    text = "A low shelf at 200 Hz is the right move here."
    assert _sanitize_for_speech(text) == text
