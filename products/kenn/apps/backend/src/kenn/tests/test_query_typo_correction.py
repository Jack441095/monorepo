"""A mistyped word must not leave the search with nothing (4 Oct 2026: "paralel compresion on drms" found no note)."""

from __future__ import annotations

from kenn.core.chat_retrieval import correct_query_typos

NOTES = {
    "parallel": 12, "compression": 40, "compressor": 30, "sidechain": 25, "drums": 20, "harsh": 9, "reverb": 15,
    "relying": 5, "distorting": 7, "finger": 4, "modulation": 8, "modulating": 3,
}
TERMS = {
    "idf": {word: 1.0 for word in NOTES},
    "inverted_index": {word: list(range(count)) for word, count in NOTES.items()},
}


def test_swapped_and_missing_letters_in_long_words_are_fixed():
    assert correct_query_typos("how do i do paralel compresion", TERMS) == "how do i do parallel compression"


def test_a_word_the_notes_already_use_is_left_alone():
    assert correct_query_typos("does the reverb sound harsh", TERMS) == "does the reverb sound harsh"


def test_short_words_are_never_rewritten():
    assert correct_query_typos("hwo doe i drms", TERMS) == "hwo doe i drms"


def test_a_plugin_name_the_notes_lack_stays_as_typed():
    assert correct_query_typos("tune serum and valhalla", TERMS) == "tune serum and valhalla"


def test_ordinary_english_is_not_turned_into_a_producer_word():
    # The first version rewrote these against a thin vocabulary: retyping became relying, disturbing became distorting.
    assert correct_query_typos("retyping disturbing", TERMS) == "retyping disturbing"


def test_a_plural_is_not_a_typo():
    assert correct_query_typos("fingers on modulating", TERMS) == "fingers on modulating"


def test_one_wrong_letter_is_only_fixed_in_a_long_word():
    assert correct_query_typos("modulatien", TERMS) == "modulation"
    assert correct_query_typos("reverp", TERMS) == "reverp"


def test_the_commonest_close_word_wins_a_tie():
    terms = {"idf": {"saturatora": 1.0, "saturatorb": 1.0}, "inverted_index": {"saturatora": [1] * 3, "saturatorb": [1] * 9}}
    assert correct_query_typos("saturatorc", terms) == "saturatorb"


def test_an_empty_index_changes_nothing():
    assert correct_query_typos("paralel compresion", {"idf": {}, "inverted_index": {}}) == "paralel compresion"
