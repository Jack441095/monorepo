from dataclasses import asdict

import numpy as np

from kenn.retrieval import retrieval
from kenn.retrieval.build_index import Chunk, build_terms
from kenn.retrieval.retrieval import bm25_search, hybrid_search, with_hyphen_parts


def _note(chunk_id: str, text: str) -> Chunk:
    return Chunk(id=chunk_id, source=f"{chunk_id}.md", page=0, kind="note", title=chunk_id, text=text)


def test_a_hyphenated_query_word_also_searches_its_parts() -> None:
    terms = with_hyphen_parts("When do I want linear-phase EQ?", ["linear-phase", "eq"])

    assert terms[:2] == ["linear-phase", "eq"]
    assert "linear" in terms and "phase" in terms


def test_re_amp_searches_amp_and_not_the_re_left_over_from_contractions() -> None:
    # Review of 6 Oct 2026: "re" has idf 3.96 in the live index because "you're" tokenizes to it.
    terms = with_hyphen_parts("How do I re-amp a guitar?", ["re-amp", "guitar"])

    assert "amp" in terms and "re" not in terms


def test_linear_phase_with_a_hyphen_finds_the_note_that_writes_it_with_a_space() -> None:
    # 5 Oct 2026: "linear-phase" stayed one token, so "linear" never scored and a minimum-phase note won on "phase eq".
    passages = [
        _note("minimum", "Minimum phase EQ shifts phase around the cut. Most EQ moves are minimum phase EQ."),
        _note("linear", "Linear phase EQ keeps phase intact at the cost of latency and pre-ringing."),
    ]
    results = bm25_search("When do I want linear-phase EQ?", [asdict(p) for p in passages], build_terms(passages))

    assert results[0][1]["id"] == "linear"


def test_an_embedding_hit_outside_the_bm25_top_60_keeps_its_own_keyword_score(monkeypatch) -> None:
    # 5 Oct 2026: the Live delay-compensation note ranked by meaning but scored 0, because 60 generic
    # send/return sections filled BM25's top 60 and nothing scored sat below it, so the display dropped it.
    keyword_fillers = [_note(f"sends-{i}", "sends sends sends") for i in range(60)]
    target = _note("pdc", "Live compensates plugin delay on every track. " + "Lookahead adds latency. " * 6 + "sends")
    meaning_only = [_note(f"other-{i}", f"lorem ipsum filler {i}") for i in range(59)]
    passages = keyword_fillers + [target] + meaning_only

    # Two-dimensional unit vectors: the target is the closest match to the query and the meaning-only chunks come
    # next. Together they are exactly the 60 dense candidates, so no keyword filler gets a dense rank, all of them
    # fall below the meaning-only chunks in the fusion, and nothing with a BM25 score sits under the target.
    cosines = [-1.0] * 60 + [1.0] + [0.9 - 0.01 * i for i in range(59)]
    index = np.array([[c, np.sqrt(max(0.0, 1.0 - c * c))] for c in cosines])
    monkeypatch.setattr(retrieval, "embed_text", lambda text: np.array([1.0, 0.0]))

    chunks = [asdict(p) for p in passages]
    results = hybrid_search("sends", chunks, build_terms(passages), embedding_index=index)
    by_id = {chunk["id"]: score for score, chunk in results}

    assert by_id["pdc"] > 0
