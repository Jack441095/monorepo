"""Tests for Phase 10 — RAFT Dataset Builder and Self-Correction Critique Loop."""

from __future__ import annotations

import json
import sys
import os
import tempfile
from pathlib import Path

# Ensure KENN modules are importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "studio", "kenn"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "studio", "kenn", "kenn", "finetune"))


# ---------------------------------------------------------------------------
# 10.1 RAFT Dataset Builder
# ---------------------------------------------------------------------------

def test_raft_load_training_records():
    """Should load valid records from a JSONL file."""
    from build_raft_dataset import load_training_records

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write(json.dumps({
            "question": "What is sidechain compression?",
            "context": "Sidechain compression routes a signal from one track to control the compressor on another track. This is commonly used for ducking bass under a kick drum.",
            "answer": "Sidechain compression uses one signal to trigger compression on another.",
            "confidence": "high"
        }) + "\n")
        f.write(json.dumps({
            "question": "What is EQ?",
            "context": "too short",  # Below MIN_CHUNK_LENGTH
            "answer": "EQ adjusts frequency balance.",
            "confidence": "medium"
        }) + "\n")
        f.write(json.dumps({
            "question": "",  # Empty question
            "context": "Some context about reverb and delay effects in mixing",
            "answer": "Reverb adds space.",
            "confidence": "medium"
        }) + "\n")
        tmp_path = Path(f.name)

    try:
        records = load_training_records(tmp_path)
        # Only the first record should be valid (second has short context, third has empty question)
        assert len(records) == 1
        assert records[0]["question"] == "What is sidechain compression?"
    finally:
        tmp_path.unlink()


def test_raft_build_examples():
    """Should produce RAFT examples with oracle + distractor chunks."""
    from build_raft_dataset import build_raft_examples

    records = [
        {
            "question": "What is reverb?",
            "context": "Reverb is the persistence of sound after it is produced. It occurs when sound reflects off surfaces in an enclosed space.",
            "answer": "Reverb is the persistence of sound caused by reflections.",
            "confidence": "high"
        },
        {
            "question": "What is delay?",
            "context": "Delay is an audio effect that records an input signal and plays it back after a period of time. Digital delays can create exact copies of the input.",
            "answer": "Delay plays back a copy of the signal after a set time.",
            "confidence": "high"
        },
        {
            "question": "What is compression?",
            "context": "Compression reduces the dynamic range of an audio signal by attenuating louder portions. The key parameters are threshold, ratio, attack, and release.",
            "answer": "Compression reduces dynamic range using threshold, ratio, attack, and release.",
            "confidence": "high"
        },
    ]

    chunk_pool = [r["context"] for r in records]
    examples = build_raft_examples(records, chunk_pool, seed=42)

    assert len(examples) > 0, "Should produce at least some RAFT examples"

    for ex in examples:
        # Each example should have these keys
        assert "question" in ex
        assert "context" in ex
        assert "answer" in ex
        assert "oracle_position" in ex
        assert "is_raft" in ex
        assert ex["is_raft"] is True

        # The context should contain 3 source blocks
        assert "[Source 1]" in ex["context"]
        assert "[Source 2]" in ex["context"]
        assert "[Source 3]" in ex["context"]

        # Oracle position should be 1, 2, or 3
        assert ex["oracle_position"] in (1, 2, 3)

        # The answer should contain chain-of-thought reasoning
        assert "Source" in ex["answer"]


def test_raft_build_examples_insufficient_chunks():
    """With only 1 record and 1 chunk, can't build distractors → 0 examples."""
    from build_raft_dataset import build_raft_examples

    records = [{
        "question": "What is reverb?",
        "context": "Reverb is the persistence of sound after it is produced in an enclosed space.",
        "answer": "Reverb is sound persistence.",
        "confidence": "high"
    }]
    chunk_pool = [records[0]["context"]]

    examples = build_raft_examples(records, chunk_pool, seed=42)
    assert len(examples) == 0, "Should produce 0 examples without enough distractors"


def test_raft_extract_chunk_pool():
    """Should extract unique chunks from records."""
    from build_raft_dataset import _extract_chunk_pool

    records = [
        {"context": "Chunk A about reverb and spatial effects in mixing audio tracks.\n\nChunk B about delay time modulation and feedback."},
        {"context": "Chunk A about reverb and spatial effects in mixing audio tracks."},  # Duplicate
        {"context": "Chunk C about EQ and frequency balance in mastering sessions."},
    ]

    pool = _extract_chunk_pool(records)
    # Should have 3 unique chunks (A, B, C), not 4 (A is duplicated)
    assert len(pool) == 3


# ---------------------------------------------------------------------------
# 10.2 Self-Correction Critique (Heuristic version)
# ---------------------------------------------------------------------------

def test_critique_grounded_answer():
    """A well-grounded answer should pass the heuristic critique."""
    from kenn.llm.kenn_lm import critique_answer

    context = (
        "Sidechain compression routes a signal from one track to control the "
        "compressor on another track. The threshold is typically set at -20 dB. "
        "Attack time should be around 5 ms for kick-driven ducking."
    )
    answer = (
        "Sidechain compression routes a signal from one track to control "
        "the compressor on another. Set the threshold at -20 dB and use "
        "an attack time of 5 ms for kick-driven ducking."
    )

    result = critique_answer(answer, context, "How do I set up sidechain compression?")

    assert result["is_grounded"] is True
    assert result["confidence"] >= 0.75
    assert len(result["issues"]) == 0


def test_critique_ungrounded_numbers():
    """Answer with values not in context should be flagged."""
    from kenn.llm.kenn_lm import critique_answer

    context = "EQ is used to adjust frequency balance. Cut muddy frequencies around 300 Hz."
    answer = "Cut at 300 Hz to reduce mud. Also boost at 12 kHz for air."  # 12 kHz not in context

    result = critique_answer(answer, context, "How should I EQ my mix?")

    assert result["is_grounded"] is False
    assert any("12 kHz" in issue for issue in result["issues"])


def test_critique_hedging_phrases():
    """Answer with hedging phrases should be flagged."""
    from kenn.llm.kenn_lm import critique_answer

    context = "Compression reduces dynamic range by attenuating louder portions."
    answer = "I think compression probably reduces dynamic range. Many engineers use it."

    result = critique_answer(answer, context, "What is compression?")

    assert result["is_grounded"] is False
    assert len(result["issues"]) >= 1


def test_critique_low_overlap():
    """Answer with very different vocabulary from context should be flagged."""
    from kenn.llm.kenn_lm import critique_answer

    context = "Reverb creates spatial depth by simulating room reflections."
    answer = (
        "Guitar amplifiers use vacuum tubes to produce harmonic distortion. "
        "The power stage saturates at high volumes creating warm overdrive tones."
    )

    result = critique_answer(answer, context, "What is reverb?")

    assert result["is_grounded"] is False
    assert result["confidence"] <= 0.75


def test_strip_unsupported_sentences():
    """The sentence stripper should remove matching unsupported content."""
    from kenn.llm.kenn_lm import KennLM

    answer = "EQ adjusts frequency balance. Reverb adds infinite space. Compression reduces range."
    critique = "UNSUPPORTED: Reverb adds infinite space"

    result = KennLM._strip_unsupported(answer, critique)

    assert "Reverb adds infinite space" not in result
    assert "EQ adjusts frequency balance" in result
    assert "Compression reduces range" in result


def test_strip_unsupported_multiline():
    """Multiple unsupported statements should all be stripped."""
    from kenn.llm.kenn_lm import KennLM

    answer = "A is about mixing. B is about mastering. C is about recording."
    critique = "UNSUPPORTED:\n- B is about mastering\n- C is about recording"

    result = KennLM._strip_unsupported(answer, critique)

    assert "A is about mixing" in result
    assert "B is about mastering" not in result
    assert "C is about recording" not in result


def test_strip_unsupported_no_match():
    """If critique fragments don't match, the answer should remain intact."""
    from kenn.llm.kenn_lm import KennLM

    answer = "Sidechain compression is a standard mixing technique."
    critique = "SUPPORTED"

    result = KennLM._strip_unsupported(answer, critique)

    assert result == answer
