"""Tests for kenn.core.mix_revision_intent's detector."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "studio" / "kenn"))

from kenn.core.mix_revision_intent import is_mix_revision_request, strip_revision_phrasing  # noqa: E402


class TestIsMixRevisionRequest:
    def test_detects_a_plain_instruction(self):
        assert is_mix_revision_request("make the vocals warmer") is True

    def test_detects_reverb_with_a_stem_target(self):
        assert is_mix_revision_request("add a bit more reverb on the vocal") is True

    def test_detects_brightness_with_make(self):
        assert is_mix_revision_request("make it brighter") is True

    def test_rejects_a_direct_question(self):
        assert is_mix_revision_request("why is my vocal too quiet?") is False

    def test_rejects_a_question_word_starting_the_sentence(self):
        assert is_mix_revision_request("what would make the drums punchier") is False

    def test_rejects_an_embedded_question_not_at_the_start(self):
        assert is_mix_revision_request("I want to know why my vocal is too quiet") is False

    def test_rejects_unrelated_chat(self):
        assert is_mix_revision_request("what genre is this track") is False

    def test_rejects_a_report_that_a_previous_move_failed(self):
        assert is_mix_revision_request("I already tried EQ cuts and it is still muddy") is False

    def test_rejects_empty_text(self):
        assert is_mix_revision_request("") is False
        assert is_mix_revision_request("   ") is False

    def test_requires_both_topic_and_action(self):
        # topic word only, no action/direction
        assert is_mix_revision_request("the vocal") is False
        # action word only, no recognized topic
        assert is_mix_revision_request("turn it up") is False


class TestStripRevisionPhrasing:
    def test_strips_leading_make(self):
        assert strip_revision_phrasing("make the vocals warmer") == "the vocals warmer"

    def test_strips_please_can_you_make(self):
        assert strip_revision_phrasing("please can you make it brighter") == "it brighter"

    def test_leaves_text_without_a_leading_verb_unchanged(self):
        assert strip_revision_phrasing("a bit more reverb on the vocal") == "a bit more reverb on the vocal"

    def test_falls_back_to_original_text_if_stripping_empties_it(self):
        assert strip_revision_phrasing("make") == "make"
