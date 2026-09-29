"""Which kind of source wins when two of them disagree.

Live's own numbers beat the manual, the manual beats our notes, our notes beat someone else's video. Retrieval
already labels every chunk with an evidence class; this puts an order on those classes so a citation can say how much
weight it carries and a contradiction check knows which side to believe.
"""

from __future__ import annotations

TIER_MEASURED = 0
TIER_MANUAL = 1
TIER_NOTE = 2
TIER_THIRD_PARTY = 3
TIER_UNCLASSIFIED = 4

_TIER_OF_CLASS = {
    "measured_live_data": TIER_MEASURED,
    "observed_session_fact": TIER_MEASURED,
    "official_ableton_manual": TIER_MANUAL,
    "manual_reference": TIER_MANUAL,
    "curated_kenn_note": TIER_NOTE,
    "reference_document": TIER_NOTE,
    "youtube_transcript": TIER_THIRD_PARTY,
}
_LABEL = {
    TIER_MEASURED: "Measured in Live",
    TIER_MANUAL: "Ableton manual",
    TIER_NOTE: "KENN note",
    TIER_THIRD_PARTY: "Third-party material",
    TIER_UNCLASSIFIED: "Unclassified",
}


def tier_of(evidence_class: str) -> int:
    return _TIER_OF_CLASS.get(str(evidence_class or "").strip(), TIER_UNCLASSIFIED)


def tier_label(tier: int) -> str:
    return _LABEL.get(tier, _LABEL[TIER_UNCLASSIFIED])


def winner(evidence_class_a: str, evidence_class_b: str) -> str | None:
    """The class to believe when the two disagree, or None when they sit in the same tier."""
    a, b = tier_of(evidence_class_a), tier_of(evidence_class_b)
    if a == b:
        return None
    return evidence_class_a if a < b else evidence_class_b
