"""Every Ollama answer opens with the same system text, so Ollama can reuse the prompt it read on the last call."""

from __future__ import annotations

import os

from kenn.llm.llm_rewrite import MODE_INSTRUCTIONS, build_system_prompt

# One turn for each input that changes the system prompt: the route, the mode, a query that asks for sources, a
# skill level, and a query that pulls in a genre profile and acoustic guidance ("techno", "boomy").
TURNS = [
    dict(answer_mode="quick_fix", route="production", query="How do I stop my kick and bass fighting?"),
    dict(answer_mode="deep_explanation", route="ableton", query="How do I route a return track in Live?"),
    dict(answer_mode="voice", route="game_audio", query="Show me sources for Wwise voice limits",
         skill_level="advanced"),
    dict(answer_mode="studio_dialogue", route="mix_review", skill_level="beginner",
         query="What LUFS should a techno master hit, and why does my small room sound boomy?"),
]


def test_every_turn_opens_with_the_whole_rule_block() -> None:
    # Regression (11 Oct v4 bench, 4B): the route sat on line two and the mode above the Rules, so a new route let
    # Ollama reuse 24 tokens and a new mode 248, and those prompts took about 4.0 s to read instead of 1.7 s.
    shared = os.path.commonprefix([build_system_prompt(**turn) for turn in TURNS])
    # The last line of the Rules, so everything above it is shared too.
    assert "instead of pretending to have listened." in shared, shared[-200:]


def test_the_turn_specific_lines_still_reach_the_prompt() -> None:
    # Moving them below the Rules must not drop any: the mode's own boundary line and the length rule are scored.
    prompt = build_system_prompt(**TURNS[3])
    for line in ("Specialty: Mix review", "Mode-specific guidance:", "Do NOT include a 'Sources:' section",
                 "new to this", "Genre Target Profile", "Acoustic Translation Guidance", "Length:"):
        assert line in prompt, line
    assert "Sources: (List sources ONLY as markdown links" in build_system_prompt(**TURNS[2])


def test_the_quick_fix_mode_asks_for_the_short_answer() -> None:
    # Regression (11 Oct A/B, 4B): quick_fix asked for a "single-paragraph response", and once the mode line sat below
    # the Rules a drum-balance answer came back without "Short answer:" in both runs.
    assert "Short answer" in MODE_INSTRUCTIONS["quick_fix"]
    assert "single-paragraph response" not in MODE_INSTRUCTIONS["quick_fix"]
