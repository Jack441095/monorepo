from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "eval"))

from kenn_model_blind_eval import (  # noqa: E402
    build_messages,
    hallucinated_measurements,
    score_quality,
)


def test_strict_prompt_forbids_memory_and_requires_abstention() -> None:
    messages = build_messages("source text", "question", strict=True)

    assert "ONLY from the provided context" in messages[0]["content"]
    assert "do not contain enough information" in messages[0]["content"]


def test_quality_scores_required_any_and_critical_forbidden_claims() -> None:
    score = score_quality(
        {
            "answer_must_include": ["bass", "kick"],
            "answer_must_include_any": ["release", "tempo"],
            "answer_must_not_include": ["always"],
            "critical_forbidden_claims": ["guaranteed safe"],
        },
        "The kick ducks the bass; tune the release. This is not guaranteed safe.",
    )

    assert score["must_include_total"] == 3
    assert score["must_include_coverage"] == 1.0
    assert score["must_not_violations"] == 1


def test_measurement_grounding_detects_values_absent_from_context() -> None:
    assert hallucinated_measurements("Use 6 dB at 3 kHz", "The source says 3 kHz") == ["6db"]
