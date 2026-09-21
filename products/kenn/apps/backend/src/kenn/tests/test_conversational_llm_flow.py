"""Tests for KENN's Conversational LLM Pipeline and Studio Partner Dialogue.

Verifies:
1. Natural studio partner system prompt construction.
2. Route-aware valid_response validation (allowing natural audio engineering dialogue
   without forcing rigid "Short answer:" / "Try this:" headers).
3. Quality reporting for studio_dialogue and conversational routes.
4. Generation fallback to specialized studio companion banter/dialogue.
"""

from __future__ import annotations

import unittest
from kenn.llm.llm_rewrite import (
    CONVERSATIONAL_SYSTEM_PROMPT,
    build_system_prompt,
    valid_response,
    valid_structure,
)
from kenn.core.chat_grounding import answer_quality_report, should_use_llm_rewrite
from kenn.core.chat_constants import ANSWER_MODES


class TestConversationalLLMFlow(unittest.TestCase):
    def test_conversational_system_prompt_contains_engineer_persona(self) -> None:
        prompt = CONVERSATIONAL_SYSTEM_PROMPT
        self.assertIn("senior mix/mastering engineer", prompt)
        self.assertIn("Audio_Too", prompt)
        self.assertIn("Ableton", prompt)
        self.assertIn("Fletcher-Munson", prompt)
        self.assertIn("phase smear", prompt)

    def test_mode_instructions_include_studio_dialogue(self) -> None:
        self.assertIn("studio_dialogue", ANSWER_MODES)
        sys_prompt = build_system_prompt(answer_mode="studio_dialogue", route="production", query="Why does my 808 clash with the kick?")
        self.assertIn("seasoned in-studio engineer", sys_prompt)
        self.assertIn("psychoacoustic", sys_prompt)

    def test_valid_response_route_aware(self) -> None:
        # Standard technical answer structure
        rigid_answer = (
            "Short answer: Cut 60 Hz on the bass.\n\n"
            "Try this:\n1. Insert EQ Eight on the bass track.\n2. Apply a 2 dB bell cut at 60 Hz.\n\n"
            "Sources:\n- [EQ Guide](/api/ableton/note?name=eq.md)"
        )
        self.assertTrue(valid_structure(rigid_answer))
        self.assertTrue(valid_response(rigid_answer, answer_mode="ableton_steps", route="ableton"))

        # Natural conversational studio partner answer without headers
        natural_studio_dialogue = (
            "The reason your 808 disappears on phone speakers while shaking your studio monitors comes down to "
            "the physics of small transducer excursion and Fletcher-Munson ear sensitivity. A smartphone speaker "
            "mechanically rolls off hard around 250 to 300 Hz, meaning any fundamental below 100 Hz simply cannot be "
            "reproduced physically. To fix this without ruining your sub headroom, you'll want to generate second and third "
            "order harmonics between 500 Hz and 1.5 kHz using gentle saturation—for instance, Ableton's Roar or Saturator "
            "with a mid-band drive. That gives the listener's brain the psychoacoustic phantom fundamental cue to perceive "
            "the bass note clearly, even when the fundamental is entirely absent from the acoustic playback."
        )

        # In strict technical mode, missing "Short answer:" / "Try this:" fails valid_structure
        self.assertFalse(valid_structure(natural_studio_dialogue))

        # In conversational or studio dialogue mode, natural_studio_dialogue succeeds!
        self.assertTrue(valid_response(natural_studio_dialogue, answer_mode="studio_dialogue", route="production_dialogue"))
        self.assertTrue(valid_response(natural_studio_dialogue, answer_mode="chat", route="conversation"))

    def test_answer_quality_report_for_studio_dialogue(self) -> None:
        natural_studio_dialogue = (
            "When you're deciding between tracking vocals through a hardware optical compressor like an LA-2A versus "
            "doing it entirely in the box, the question isn't whether plugins can match the curve—it's whether catching 2 to 3 dB "
            "of smooth, program-dependent gain reduction at the converter stage gives your singer better headphone confidence and "
            "protects your preamps from rogue dynamic peaks. In modern Live 12 production, tracking with 2 dB of conservative "
            "hardware leveling followed by surgical clip gain and clean digital limiting inside Live gives you the best of both worlds."
        )

        report = answer_quality_report(
            query="Should I track vocals with hardware compression?",
            results=[],
            answer=natural_studio_dialogue,
            route="conversation",
            confidence="high",
            answer_mode="studio_dialogue",
            grounding={"score": 80},
        )
        self.assertGreaterEqual(report["score"], 65)

    def test_should_use_llm_rewrite_enables_studio_dialogue(self) -> None:
        self.assertTrue(
            should_use_llm_rewrite(
                query="How does saturation affect the perception of low end?",
                route="production",
                confidence="high",
                grounding={"score": 80},
                quality={"score": 75},
                answer_mode="studio_dialogue",
            )
        )


if __name__ == "__main__":
    unittest.main()
