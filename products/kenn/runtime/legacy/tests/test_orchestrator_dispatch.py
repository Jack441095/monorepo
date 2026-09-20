"""Regression: KennOrchestrator.classify() must not hijack ordinary
production questions into a specialist sub-agent based on loose keyword
proximity.

Live-tested 2026-08-04: "How do I make vocals sound wide without muddying
the mix?" matched _AUDIOGEN_PATTERNS' `\\b(make|...)\\b.*\\b(...|sound)\\b`
(unbounded wildcard between "make" and "sound" -- both extremely common
words in ordinary mixing questions, where "sound" is a linking verb, not
the noun being generated) and got answered with "I can generate that for
you! Use the AudioGen panel..." instead of the actual mixing question.
Same pattern for "how do I use the SSL 4000 console EQ curve on my vocal"
matching _LTAS_PATTERNS' `\\b(frequency|eq)\\b.*\\b(...|curve)\\b` -- "EQ"
and "curve" appear in essentially any conversation about EQ shapes.
dispatch()'s result overrides the entire normal Q&A pipeline with a
hardcoded confidence: "high", so a false-positive classification silently
replaces a real, correct answer with a canned specialist-agent response.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT / "studio" / "kenn") not in sys.path:
    sys.path.insert(0, str(ROOT / "studio" / "kenn"))

from kenn.orchestrator import get_orchestrator  # noqa: E402

ORCH = get_orchestrator()


def test_make_sound_wide_does_not_trigger_audiogen():
    assert ORCH.classify("How do I make vocals sound wide without muddying the mix?") is None


def test_make_it_sound_clearer_does_not_trigger_audiogen():
    assert ORCH.classify("what EQ move would make the vocal sound clearer") is None


def test_eq_curve_question_does_not_trigger_ltas():
    assert ORCH.classify("how do I use the SSL 4000 console EQ curve on my vocal") is None


def test_audiogen_requests_defer_to_the_real_generation_path():
    """Audiogen is deliberately NOT classified by the orchestrator (see
    orchestrator.py's classify() comment) -- chat_answer.py's
    _answer_payload_raw() already calls the real, fully-working
    chat_routing.audio_generation_payload() further down the same
    function, which actually queues render jobs. Classifying it here too
    made dispatch() short-circuit before that real path ever ran,
    downgrading working generation requests into a stub "click the
    button" message."""
    assert ORCH.classify("make me a lo-fi loop") is None
    assert ORCH.classify("generate a dark drill beat") is None


def test_genuine_ltas_request_still_matches():
    assert ORCH.classify("match my mix to a commercial reference EQ curve") == "ltas_matcher"


def test_genuine_mix_review_request_still_matches():
    assert ORCH.classify("review my mix for issues") == "mix_reviewer"


# ── Systemic question-vs-request guard ───────────────────────────────────
#
# The two fixes above only patched the specific patterns that matched the
# two originally-reported queries. Testing more broadly turned up the same
# blind spot across every single specialist category: none of the patterns
# distinguish "how do I do X" (an informational question) from "do X [for
# me]" (an actual request to run a tool). All confirmed genuine trigger
# cases are imperative requests with no question word, so gating on
# question-shape is a reliable, low-risk systemic fix.

def test_reference_level_match_question_is_not_dispatched():
    assert ORCH.classify("how do I level match a reference track against my mix") is None


def test_mix_translation_question_is_not_dispatched():
    assert ORCH.classify("How do I check if my mix translates on phone speakers and in the car?") is None


def test_mix_review_lab_question_is_not_dispatched():
    assert ORCH.classify("What does crest factor and spectrum balance tell me in the Mix Review Lab?") is None


def test_mid_sentence_what_should_i_question_is_not_dispatched():
    assert ORCH.classify("My master is loud but distorted, what should I check first?") is None


def test_ableton_word_sense_ambiguity_is_not_dispatched():
    """"show" means a concert/performance here, not "show me the status"."""
    assert ORCH.classify("Can Ableton diagnose my ear infection after a loud show?") is None


def test_describing_an_existing_loop_is_not_dispatched():
    """"loop" is the genuine grammatical object of "make", but the sentence
    describes an existing loop's problem, not a request to generate one."""
    assert ORCH.classify(
        "Can sample-rate conversion make a Wwise ambience loop click if the source WAV was clean?"
    ) is None
