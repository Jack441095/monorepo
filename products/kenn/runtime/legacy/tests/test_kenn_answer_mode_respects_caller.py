"""Regression: answer_payload() must respect an explicit answer_mode= caller
argument (e.g. "voice"), not silently recompute/discard it.

Found live-testing 2026-08-02, two independent instances of the same bug
class in _answer_payload():

1. Line ~1193 unconditionally did `answer_mode = classify_answer_mode(...)`
   after retrieval, discarding whatever the caller passed in. The early
   clarify/out_of_scope return paths already correctly did
   `answer_mode or classify_answer_mode(...)` -- only the main path (any
   query with real search results) had the bug.
2. A separate, later retroactive-downgrade path (a real answer turns out
   poorly grounded/low quality after the fact, so it's swapped for the
   generic weak_match_answer() fallback) called `weak_match_answer(query)`
   with no answer_mode argument at all -- every other call site in the file
   passes it through.

No current caller passes answer_mode through to answer_payload() yet (the
parameter was only just added, prep work for wiring up an explicit
voice-mode path), but both bugs would have silently broken that the moment
it was used -- an explicit voice-mode request would always have reverted to
the full written template for this specific, real query (which happens to
hit the retroactive-downgrade path in practice, live-verified below).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT / "studio" / "kenn") not in sys.path:
    sys.path.insert(0, str(ROOT / "studio" / "kenn"))

from kenn.core.chat import answer_payload  # noqa: E402


def test_explicit_answer_mode_is_respected_end_to_end():
    payload = answer_payload(
        "how do I sidechain bass to the kick?", limit=5, allow_llm=False, answer_mode="voice",
    )
    assert payload["answer_mode"] == "voice"
    # Voice-mode answers must not contain the written-format section
    # headings or numbered-list structure.
    lowered = payload["answer"].lower()
    assert "try this:" not in lowered
    assert "sources:" not in lowered
    assert "for example:" not in lowered
    assert "1." not in payload["answer"]


def test_answer_mode_still_auto_classifies_when_not_given():
    """Regression guard: the fix must not break the overwhelmingly common
    case of no explicit answer_mode, which every existing test relies on."""
    payload = answer_payload("how do I sidechain bass to the kick?", limit=5, allow_llm=False)
    assert payload["answer_mode"] and payload["answer_mode"] != "voice"
