"""Regression: KENN must not silently substitute generic advice when a
user names specific classic hardware the knowledge base doesn't cover.

Live-tested 2026-08-03 through the real HTTP server: "how do I use the SSL
4000 console EQ curve on my vocal" returned a fully confident (grounding
score 90, mode "strong") complete answer about de-essing and sibilance --
nothing to do with the SSL 4000 at all. Retrieval scored high purely on
generic "EQ"/"vocal" keyword overlap; nothing flagged that the knowledge
base has zero coverage of the specific unit named. Reproduced the same
pattern for the 1176, Pultec EQP-1A, and LA-2A -- systemic, not a one-off.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT / "studio" / "kenn") not in sys.path:
    sys.path.insert(0, str(ROOT / "studio" / "kenn"))

from kenn.core.chat_answer import _uncovered_hardware_caveat  # noqa: E402


UNCOVERED_RESULTS = [
    (10.0, {"kind": "note", "source": "vocal-deessing-and-sibilance.md", "text": "De-essing keeps sibilance under control."}),
]

COVERED_RESULTS = [
    (10.0, {"kind": "note", "source": "jack-vocal-recording-mic.md", "text": "Jack uses a Neve 1073 preamp for aggressive vocals."}),
]


def test_caveat_shown_for_named_hardware_with_no_coverage():
    caveat = _uncovered_hardware_caveat(
        "how do I use the SSL 4000 console EQ curve on my vocal", UNCOVERED_RESULTS
    )
    assert "SSL 4000" in caveat
    assert "nothing in the knowledge base covers" in caveat


def test_caveat_empty_when_no_hardware_named():
    assert _uncovered_hardware_caveat("how do I eq a vocal", UNCOVERED_RESULTS) == ""


def test_caveat_empty_when_hardware_is_actually_covered():
    assert _uncovered_hardware_caveat(
        "tell me about using a neve 1073 preamp", COVERED_RESULTS
    ) == ""


def test_caveat_uses_the_correct_display_name_for_each_known_unit():
    assert "1176" in _uncovered_hardware_caveat("how do I use the 1176 compressor on drums", UNCOVERED_RESULTS)
    assert "LA-2A" in _uncovered_hardware_caveat("how do I dial in an la-2a on vocals", UNCOVERED_RESULTS)
    assert "Pultec" in _uncovered_hardware_caveat("whats a good pultec setting for bass", UNCOVERED_RESULTS)
