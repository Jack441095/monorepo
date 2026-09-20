from kenn.llm.llm_rewrite import valid_response, valid_structure
from kenn.llm.linter import lint_response


def test_valid_structure_accepts_a_mode_specific_synonym_heading_with_numbered_steps() -> None:
    """Regression (2026-08-02, live-tested): a real qwen2.5:1.5b answer used
    a MODE_INSTRUCTIONS-driven header ("Symptom and likely cause:" for
    mix_diagnosis mode) instead of the literal "Short answer:" string, with
    real numbered guidance instead of a literal "Try this:" -- the old
    strict 3-exact-string check discarded this outright even though it's a
    complete, substantive answer."""
    text = (
        "Symptom and likely cause:\n"
        "The kick and bass are masking each other in the low end.\n\n"
        "1. Sidechain the bass to the kick.\n"
        "2. Set a fast attack and a release that breathes with the tempo.\n\n"
        "Sources:\n- Sidechain Bass To Kick (sidechain-bass-to-kick.md)"
    )
    assert valid_structure(text)


def test_valid_structure_accepts_a_try_this_synonym_phrase_without_numbered_steps() -> None:
    text = (
        "Short answer: use a de-esser before brightness EQ.\n"
        "Here are the concrete steps: insert a de-esser, then sweep for the harsh range.\n"
        "Sources:\n- Vocal De-Essing (vocal-deessing.md)"
    )
    assert valid_structure(text)


def test_valid_structure_still_rejects_text_with_no_real_structure() -> None:
    """Regression guard: the broadened synonym/numbered-steps check must not
    turn into "accept anything" -- genuinely unstructured text (no
    short-answer marker, no try-this marker or numbered list, no sources)
    still fails."""
    assert not valid_structure("Just do it.")


def test_valid_structure_still_requires_a_sources_line() -> None:
    """"sources:" has no accepted synonym -- unlike the other two sections,
    there's no legitimate substitute for citing sources."""
    text = (
        "Short answer: use a de-esser before brightness EQ.\n"
        "1. Insert a de-esser.\n"
        "2. Sweep for the harsh range."
    )
    assert not valid_structure(text)


def test_voice_response_accepts_natural_speech_without_written_headings() -> None:
    assert valid_response(
        "The vocal is masking the snare. Pull the vocal down one decibel, then compare at matched loudness.",
        "voice",
    )


def test_voice_response_rejects_written_format_and_excessive_length() -> None:
    assert not valid_response("Short answer: Reduce the vocal. Try this: lower it.", "voice")
    assert not valid_response("word " * 101, "voice")


def test_written_response_still_requires_core_sections() -> None:
    assert valid_response("Short answer: Yes.\nTry this: Do it.\nSources:\n- Note", "quick_fix")
    assert not valid_response("Just do it.", "quick_fix")


def test_linter_removes_internal_error_text() -> None:
    raw = "The operation failed [error] traceback. Database error: lost connection. Here is the answer."
    clean = lint_response(raw, "quick_fix")
    assert "error" not in clean.lower()
    assert "traceback" not in clean.lower()
    assert "database error" not in clean.lower()
    assert clean.endswith("Here is the answer.")


def test_linter_collapses_duplicated_headings() -> None:
    raw = "Short answer:\nShort answer:\nTry this:\nTry this:\nHere is the advice."
    clean = lint_response(raw, "quick_fix")
    assert clean.count("Short answer:") == 1
    assert clean.count("Try this:") == 1


def test_linter_voice_strips_tables_and_formatting() -> None:
    raw = (
        "Here is the comparison table:\n"
        "| Parameter | Value |\n"
        "|---|---|\n"
        "| Attack | 10 ms |\n"
        "| Release | 100 ms |\n"
        "Check [our reference doc](file:///notes/eq.md) for details.\n"
        "- Step 1\n"
        "- Step 2\n"
    )
    clean = lint_response(raw, "voice")
    assert "|" not in clean
    assert "---" not in clean
    assert "Attack" not in clean
    assert "Release" not in clean
    assert "[our reference doc]" not in clean
    assert "our reference doc" in clean
    assert "file://" not in clean
    assert "-" not in clean
    assert "Step 1 Step 2" in clean


def test_linter_voice_truncates_at_sentence_boundary() -> None:
    # 90 words with distinct sentences
    raw = (
        "First sentence is here. Second sentence starts now. "
        "We are repeating a word to make it long. " * 15
    )
    clean = lint_response(raw, "voice")
    words = clean.split()
    assert len(words) <= 85
    assert clean.endswith(".") or clean.endswith("?") or clean.endswith("!")
