# tests/test_section_score_components.py
from __future__ import annotations

import math

from composition.section_scoring import (
    SectionScore,
    score_section,
    score_section_with_sampler_adjustments,
)


def test_score_section_exposes_structural_components_matching_total() -> None:
    # Minimal event list: empty is OK for smoke (song scorer + stages best-effort).
    s = score_section([], beats_per_bar=4.0, bars=1)
    assert s.components is not None
    c = s.components
    assert math.isclose(s.score, c.structural_total(), rel_tol=0, abs_tol=1e-5)
    d = s.details
    assert "section_score_components" in d
    assert isinstance(d["section_score_components"], dict)


def test_unified_scorer_forwards_base_components() -> None:
    s = score_section_with_sampler_adjustments(
        [],
        emotion=None,
        root_note=60,
    )
    assert s.components is not None
    assert s.details.get("section_score_before_sampler") == s.components.structural_total()


def test_section_score_backwards_two_arg_constructor() -> None:
    t = SectionScore(score=0.5, details={"a": 1})
    assert t.components is None
    assert t.score == 0.5
