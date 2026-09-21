"""Acoustic Terminology Translation Engine for KENN.

Translates subjective mixing descriptors (e.g. "muddy", "harsh", "boxy", "thin", "boomy")
into precise DSP parameters (frequency bands, Q values, gain adjustments, filter types,
and Ableton EQ Eight / Compressor parameter mappings).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DSPRecommendation:
    descriptor: str
    category: str  # "eq", "dynamics", "filtering"
    target_frequency_hz: float | None
    frequency_range_hz: tuple[float, float] | None
    suggested_gain_db: float | None
    suggested_q: float | None
    filter_type: str  # "bell", "high_shelf", "low_shelf", "high_pass", "low_pass", "de_esser"
    explanation: str
    ableton_eq_eight_bank: dict[str, Any] = field(default_factory=dict)


ACOUSTIC_DICTIONARY: dict[str, DSPRecommendation] = {
    "muddy": DSPRecommendation(
        descriptor="muddy",
        category="eq",
        target_frequency_hz=300.0,
        frequency_range_hz=(200.0, 400.0),
        suggested_gain_db=-3.0,
        suggested_q=1.4,
        filter_type="bell",
        explanation="Accumulation of low-mid energy masking clarity and vocal detail.",
        ableton_eq_eight_bank={"Band": 2, "Type": "Bell", "Frequency": 300.0, "Gain": -3.0, "Q": 1.4},
    ),
    "tubby": DSPRecommendation(
        descriptor="tubby",
        category="eq",
        target_frequency_hz=250.0,
        frequency_range_hz=(180.0, 350.0),
        suggested_gain_db=-2.5,
        suggested_q=1.5,
        filter_type="bell",
        explanation="Resonant chestiness or cabinet resonance in the lower mid-range.",
        ableton_eq_eight_bank={"Band": 2, "Type": "Bell", "Frequency": 250.0, "Gain": -2.5, "Q": 1.5},
    ),
    "harsh": DSPRecommendation(
        descriptor="harsh",
        category="eq",
        target_frequency_hz=3500.0,
        frequency_range_hz=(2500.0, 4500.0),
        suggested_gain_db=-2.5,
        suggested_q=2.0,
        filter_type="bell",
        explanation="Excessive upper-mid energy causing ear fatigue and aggressive bite.",
        ableton_eq_eight_bank={"Band": 5, "Type": "Bell", "Frequency": 3500.0, "Gain": -2.5, "Q": 2.0},
    ),
    "strident": DSPRecommendation(
        descriptor="strident",
        category="eq",
        target_frequency_hz=4000.0,
        frequency_range_hz=(3000.0, 5000.0),
        suggested_gain_db=-3.0,
        suggested_q=2.2,
        filter_type="bell",
        explanation="Piercing upper-mid presence, often from aggressive vocal or guitar transients.",
        ableton_eq_eight_bank={"Band": 6, "Type": "Bell", "Frequency": 4000.0, "Gain": -3.0, "Q": 2.2},
    ),
    "boxy": DSPRecommendation(
        descriptor="boxy",
        category="eq",
        target_frequency_hz=600.0,
        frequency_range_hz=(400.0, 800.0),
        suggested_gain_db=-3.5,
        suggested_q=1.5,
        filter_type="bell",
        explanation="Cardboard-like resonance typical of small room reflections or cheap microphone enclosures.",
        ableton_eq_eight_bank={"Band": 3, "Type": "Bell", "Frequency": 600.0, "Gain": -3.5, "Q": 1.5},
    ),
    "sibilant": DSPRecommendation(
        descriptor="sibilant",
        category="eq",
        target_frequency_hz=7000.0,
        frequency_range_hz=(6000.0, 9000.0),
        suggested_gain_db=-4.0,
        suggested_q=3.0,
        filter_type="de_esser",
        explanation="Harsh 's', 't', and 'z' vocal consonants overloading high frequencies.",
        ableton_eq_eight_bank={"Band": 7, "Type": "Bell", "Frequency": 7000.0, "Gain": -4.0, "Q": 3.0},
    ),
    "thin": DSPRecommendation(
        descriptor="thin",
        category="eq",
        target_frequency_hz=150.0,
        frequency_range_hz=(100.0, 250.0),
        suggested_gain_db=2.0,
        suggested_q=1.2,
        filter_type="bell",
        explanation="Lack of foundational low-end warmth and body.",
        ableton_eq_eight_bank={"Band": 1, "Type": "Bell", "Frequency": 150.0, "Gain": 2.0, "Q": 1.2},
    ),
    "weak": DSPRecommendation(
        descriptor="weak",
        category="eq",
        target_frequency_hz=120.0,
        frequency_range_hz=(80.0, 200.0),
        suggested_gain_db=2.5,
        suggested_q=1.0,
        filter_type="low_shelf",
        explanation="Insufficient low-end power or sub-bass weight.",
        ableton_eq_eight_bank={"Band": 1, "Type": "LowShelf", "Frequency": 120.0, "Gain": 2.5, "Q": 1.0},
    ),
    "dark": DSPRecommendation(
        descriptor="dark",
        category="eq",
        target_frequency_hz=10000.0,
        frequency_range_hz=(8000.0, 14000.0),
        suggested_gain_db=2.5,
        suggested_q=0.7,
        filter_type="high_shelf",
        explanation="Lack of air, treble presence, and top-end shimmer.",
        ableton_eq_eight_bank={"Band": 8, "Type": "HighShelf", "Frequency": 10000.0, "Gain": 2.5, "Q": 0.7},
    ),
    "dull": DSPRecommendation(
        descriptor="dull",
        category="eq",
        target_frequency_hz=8000.0,
        frequency_range_hz=(6000.0, 12000.0),
        suggested_gain_db=2.0,
        suggested_q=0.8,
        filter_type="high_shelf",
        explanation="Muffled high-end translation needing gentle shelf air.",
        ableton_eq_eight_bank={"Band": 8, "Type": "HighShelf", "Frequency": 8000.0, "Gain": 2.0, "Q": 0.8},
    ),
    "boomy": DSPRecommendation(
        descriptor="boomy",
        category="filtering",
        target_frequency_hz=40.0,
        frequency_range_hz=(20.0, 80.0),
        suggested_gain_db=0.0,
        suggested_q=0.7,
        filter_type="high_pass",
        explanation="Uncontrolled sub-bass buildup or room mode excitation masking low-end clarity.",
        ableton_eq_eight_bank={"Band": 1, "Type": "HighPass", "Frequency": 40.0, "Gain": 0.0, "Q": 0.7},
    ),
    "rumbley": DSPRecommendation(
        descriptor="rumbley",
        category="filtering",
        target_frequency_hz=35.0,
        frequency_range_hz=(20.0, 60.0),
        suggested_gain_db=0.0,
        suggested_q=0.7,
        filter_type="high_pass",
        explanation="Sub-audible HVAC, mic stand handling, or foot thuds degrading headroom.",
        ableton_eq_eight_bank={"Band": 1, "Type": "HighPass", "Frequency": 35.0, "Gain": 0.0, "Q": 0.7},
    ),
    "honky": DSPRecommendation(
        descriptor="honky",
        category="eq",
        target_frequency_hz=1200.0,
        frequency_range_hz=(900.0, 1600.0),
        suggested_gain_db=-3.0,
        suggested_q=1.8,
        filter_type="bell",
        explanation="Nasal, megaphone-like mid-range accumulation.",
        ableton_eq_eight_bank={"Band": 4, "Type": "Bell", "Frequency": 1200.0, "Gain": -3.0, "Q": 1.8},
    ),
    "flabby": DSPRecommendation(
        descriptor="flabby",
        category="dynamics",
        target_frequency_hz=100.0,
        frequency_range_hz=(60.0, 150.0),
        suggested_gain_db=None,
        suggested_q=None,
        filter_type="bell",
        explanation="Uncontrolled low-end dynamic tail needing fast compressor control.",
        ableton_eq_eight_bank={"Attack": "10ms", "Release": "50ms", "Ratio": 4.0},
    ),
}


def analyze_acoustic_descriptors(query: str) -> list[DSPRecommendation]:
    """Scan input string for acoustic descriptors and return matching recommendations."""
    if not query:
        return []

    normalized = query.lower()
    matches: list[DSPRecommendation] = []


    for term, rec in ACOUSTIC_DICTIONARY.items():
        pattern = r"\b" + re.escape(term) + r"\b"
        if re.search(pattern, normalized):
            matches.append(rec)

    return matches


def build_acoustic_guidance_prompt(query: str) -> str:
    """Generate precise DSP guidance to append to the LLM system prompt if acoustic terms are present."""
    recs = analyze_acoustic_descriptors(query)
    if not recs:
        return ""

    lines = ["\nAcoustic Translation Guidance:"]
    for r in recs:
        freq_str = f"{r.target_frequency_hz:.0f} Hz" if r.target_frequency_hz else "N/A"
        gain_str = f"{r.suggested_gain_db:+.1f} dB" if r.suggested_gain_db is not None else "N/A"
        q_str = f"Q={r.suggested_q:.1f}" if r.suggested_q else ""
        lines.append(
            f"- '{r.descriptor}': Target ~{freq_str} ({r.filter_type}, {gain_str} {q_str}). {r.explanation}"
        )
    return "\n".join(lines)
