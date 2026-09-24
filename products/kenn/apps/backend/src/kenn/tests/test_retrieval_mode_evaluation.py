from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from kenn.retrieval import retrieval


SCRIPT = Path(__file__).resolve().parents[5] / "tooling" / "scripts" / "evaluate_retrieval_modes.py"
SPEC = importlib.util.spec_from_file_location("evaluate_retrieval_modes", SCRIPT)
evaluation = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(evaluation)


def test_retrieval_comparison_scores_rank_and_rejects_regression(tmp_path: Path) -> None:
    cases = tmp_path / "cases.json"
    cases.write_text(json.dumps({"cases": [{
        "id": "hard-1", "question": "how should I sidechain bass",
        "source_must_include": ["sidechain-bass"],
    }]}), encoding="utf-8")
    good = [(9.0, {"source": "sidechain-bass.md", "title": "Sidechain bass"})]
    miss = [(9.0, {"source": "unrelated.md", "title": "Unrelated"})]

    receipt = evaluation.evaluate(
        cases_path=cases,
        cutoff=4,
        searchers={"bm25": lambda _query, _limit: good, "hybrid": lambda _query, _limit: miss},
    )

    assert receipt["modes"]["bm25"]["summary"]["top1"] == 1.0
    assert receipt["modes"]["hybrid"]["summary"]["recall_at_4"] == 0.0
    assert receipt["decision"]["no_quality_regression"] is False
    assert receipt["decision"]["deploy_candidate"] is False
    assert receipt["privacy"]["stores_questions"] is False


def test_expected_source_rank_deduplicates_chunks_and_requires_each_source() -> None:
    results = [
        (10.0, {"source": "first.md", "title": "First"}),
        (9.0, {"source": "first.md", "title": "First duplicate"}),
        (8.0, {"source": "second.md", "title": "Second"}),
    ]
    assert evaluation._rank(["second"], results) == 2
    assert evaluation._rank(["first", "second"], results) == 2
    assert evaluation._rank(["missing"], results) is None



def test_any_of_sources_counts_the_best_ranked_acceptable_source(tmp_path: Path) -> None:
    cases = tmp_path / "cases.json"
    cases.write_text(json.dumps({"cases": [{
        "id": "purpose-1", "question": "line up two mics",
        "source_must_include": ["align-delay"], "source_any_include": ["align-delay", "align delay"],
    }]}), encoding="utf-8")
    manual = [(9.0, {"source": "manual-pt17.md", "title": "Align Delay in Live 12"}),
              (8.0, {"source": "ableton-align-delay-device.md", "title": "Ableton Align Delay"})]
    neither = [(9.0, {"source": "unrelated.md", "title": "Unrelated"})]

    receipt = evaluation.evaluate(cases_path=cases, cutoff=4,
                                  searchers={"bm25": lambda _q, _l: manual, "hybrid": lambda _q, _l: neither})

    assert receipt["modes"]["bm25"]["rows"][0]["rank"] == 1
    assert receipt["modes"]["hybrid"]["rows"][0]["rank"] is None

def test_reranker_prefers_exact_intent_title_and_normalizes_known_typos(monkeypatch) -> None:
    monkeypatch.setattr(retrieval, "load_source_feedback_scores", lambda: {})
    monkeypatch.setattr(retrieval, "load_hard_negatives", lambda: ())
    broad = {
        "kind": "note", "source": "automix-compression-ratios.md",
        "title": "AutoMix Compression Ratios",
        "text": "Status: Approved\nTags: compression, bass, drums, ratio",
    }
    exact = {
        "kind": "note", "source": "sidechain-bass-to-kick.md",
        "title": "Sidechain Bass To Kick",
        "text": "Status: Approved\nTags: sidechain, bass, kick, compression",
    }

    ranked = retrieval.rerank_results("sidechane bas to kik", [(14.0, broad), (10.0, exact)])

    assert ranked[0][1]["source"] == "sidechain-bass-to-kick.md"


def test_hybrid_fusion_ranks_an_embedding_only_note_without_changing_the_top_score(monkeypatch) -> None:
    import numpy as np

    chunks = [{"id": f"c{i}", "source": f"note-{i}.md", "title": f"Note {i}", "kind": "note"} for i in range(4)]
    # Keywords find notes 0 and 1; the meaning of the question matches note 3, which the keywords missed.
    monkeypatch.setattr(retrieval, "bm25_search", lambda *a, **k: [(10.0, chunks[0]), (8.0, chunks[1])])
    monkeypatch.setattr(retrieval, "embed_text", lambda _q: np.zeros(3))
    monkeypatch.setattr(retrieval, "cosine_similarity_scores", lambda _q, _i: np.array([0.30, 0.20, 0.10, 0.90]))
    monkeypatch.setattr(retrieval, "rerank_results", lambda _q, results: results)
    monkeypatch.setattr(retrieval, "expanded_query_terms", lambda _q: [])

    results = retrieval.hybrid_search("line up two mics", chunks, {"idf": {}}, limit=4, embedding_index=np.zeros((4, 3)))
    ranked = [chunk["id"] for _score, chunk in results]

    assert ranked.index("c3") < 3  # was missing from the list entirely
    top_boosted = 10.0 + max(0.40 * 10.0, 3.0) * ((0.30 - 0.10) / 0.80) * 0.25
    assert results[0][0] == max(score for score, _chunk in results) == top_boosted  # "I don't know" threshold input unchanged
    assert [score for score, _chunk in results] == sorted((score for score, _chunk in results), reverse=True)
