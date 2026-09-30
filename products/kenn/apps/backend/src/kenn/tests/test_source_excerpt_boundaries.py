"""The source excerpt the model reasons over must be well-formed at its boundaries.

Found on the 28 Sept safety audit, fixed 30 Sept. Three ways the excerpt could be malformed, all of which land in
the same place: the model is handed text where the boundary marking the end of untrusted evidence is broken.
"""

from __future__ import annotations

from kenn.llm.llm_rewrite import _clean_chunk_for_synthesis, _truncate_on_word_boundary, build_raw_context_block

LONG_NOTE = {
    "text": "A compressor with a ratio of 4:1 and a threshold of -20 dB will glue a mix together "
            "across a sixty decibel dynamic range without pumping."
}
REAL_LABEL = "Ableton Live 12 Reference Manual - Mixing Dynamics chapter (curated note, section Dry/Wet para)"


def test_a_truncation_never_severs_a_word() -> None:
    """It used to return '...across a sixty decibel s...' with the fragment glued to the ellipsis."""
    excerpt = _clean_chunk_for_synthesis(LONG_NOTE, 90)
    assert excerpt.endswith("...")
    body = excerpt.removesuffix("...")
    source_words = set(LONG_NOTE["text"].replace(".", "").replace(",", "").split())
    assert body.split()[-1] in source_words, excerpt


def test_the_ellipsis_is_not_glued_to_the_last_word() -> None:
    assert _truncate_on_word_boundary("one two three four five", 11).endswith("two...")
    assert _truncate_on_word_boundary("short", 40) == "short"
    assert _truncate_on_word_boundary("anything", 0) == ""


def test_a_fenced_code_block_is_dropped_rather_than_flattened_into_the_prose() -> None:
    """Joining the lines turned '```python\\nKENN_LLM_CONTEXT_CHARS=650\\n```' into one broken statement."""
    excerpt = _clean_chunk_for_synthesis(
        {"text": "```python\nKENN_LLM_CONTEXT_CHARS=650\n```\nSome prose follows here."}, 240)
    assert excerpt == "Some prose follows here."
    assert "```" not in excerpt and "KENN_LLM_CONTEXT_CHARS" not in excerpt


def test_a_note_that_is_only_a_code_block_yields_nothing_rather_than_broken_markup() -> None:
    assert _clean_chunk_for_synthesis({"text": "```bash\npython main.py build\n```"}, 240) == ""


def test_metadata_and_boilerplate_are_still_stripped() -> None:
    excerpt = _clean_chunk_for_synthesis(
        {"text": "Short answer: yes.\nType: note\nTags: a, b\n# heading\n- How to do it"}, 240)
    assert excerpt == "yes."


def test_an_over_long_label_does_not_produce_an_unterminated_opening_tag() -> None:
    """It used to emit '<source_excerpt label="... section Dry/Wet para</source_excerpt>'."""
    block = build_raw_context_block([(9.4, {"text": "Return effects are a separate bus. " * 12})],
                                    lambda _chunk: REAL_LABEL, max_chars=260)
    assert "<source_excerpt" not in block or block.count("<source_excerpt") == block.count("</source_excerpt>")
    assert block.endswith("</source_excerpt>") or block == "(no source excerpts provided)"


def test_the_excerpt_is_cut_on_a_word_boundary_with_both_tags_intact() -> None:
    block = build_raw_context_block([(9.4, {"text": "Return effects are a separate bus. " * 12})],
                                    lambda _chunk: REAL_LABEL, max_chars=420)
    assert f'<source_excerpt label="{REAL_LABEL}" relevance="9.4">' in block
    assert block.rstrip().endswith("</source_excerpt>")
    body = block.split("\n", 2)[2].removesuffix("</source_excerpt>").strip()
    assert body.endswith("...") and " Return effects" in body
    assert len(block) <= 420


def test_an_excerpt_that_cannot_fit_is_dropped_rather_than_squeezed() -> None:
    """A label this long leaves no room for content; dropping is honest, slicing the tag is not."""
    block = build_raw_context_block([(9.4, {"text": "Return effects are a separate bus. " * 12})],
                                    lambda _chunk: REAL_LABEL, max_chars=260)
    assert block == "(no source excerpts provided)"
