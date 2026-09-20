"""Tests for Ableton LM query topic detection."""

from __future__ import annotations

import json

from kenn.retrieval import retrieval
from kenn.retrieval.retrieval import query_topics, rerank_results, source_trust_score, term_matches


def test_sidechain_maps_to_compression() -> None:
    topics = query_topics("how do I sidechain bass to the kick")
    assert "compression" in topics
    assert "bass" in topics


def test_wwise_query() -> None:
    topics = query_topics("how does wwise handle game audio events")
    assert "wwise" in topics
    assert "game_audio" in topics


def test_wwise_game_sync_terms() -> None:
    topics = query_topics("Should footsteps use Wwise States or Switches and when do I need an RTPC?")
    assert "wwise" in topics
    assert "game_audio" in topics


def test_wwise_runtime_troubleshooting_terms() -> None:
    topics = query_topics("Wwise Event is silent after the Unity game build and the SoundBank is missing")
    assert "wwise" in topics
    assert "game_audio" in topics


def test_wwise_advanced_diagnosis_terms() -> None:
    topics = query_topics("Wwise footstep surfaces, combat voices, and conversion clicks after sample rate changes")
    assert "wwise" in topics
    assert "game_audio" in topics


def test_wwise_mobile_combat_terms() -> None:
    topics = query_topics("mobile build runs out of audio memory when ambience and combat are active")
    assert "game_audio" in topics


def test_rerank_rewards_specific_topic_overlap() -> None:
    query = "How do I make vocals wide without muddying the mix?"
    off_topic = {
        "kind": "note",
        "title": "Vocal De-Essing",
        "source": "vocal-deessing.md",
        "text": "Tags: vocals, deesser, sibilance\nFix harsh S sounds.",
    }
    on_topic = {
        "kind": "note",
        "title": "Vocal Width Without Mud",
        "source": "vocal-width-without-mud.md",
        "text": "Tags: vocals, stereo width, wide, mono\nWiden doubles and keep the lead vocal central.",
    }

    ranked = rerank_results(query, [(9.0, off_topic), (8.0, on_topic)])

    assert ranked[0][1]["source"] == "vocal-width-without-mud.md"


def test_trained_reranker_model_loads_and_scores_without_torch(monkeypatch) -> None:
    """The trained reranker (scripts/eval/kenn_reranker_train.py) was sitting
    fully trained and never loaded anywhere (docs/CAPABILITY_IMPROVEMENTS_2026-07-06.md).
    It's a 9-feature linear model — no torch/ML framework needed at inference,
    just arithmetic on the saved weights. Disabled by default (see next test)
    since it measurably regressed 3 real benchmark cases — enabling it here
    to test the loading/scoring machinery in isolation."""
    monkeypatch.setenv("KENN_RERANKER_MODEL_ENABLED", "1")
    retrieval._reranker_model_loaded = False
    model = retrieval._load_reranker_model()
    assert model is not None
    assert len(model["weights"]) == 9

    prob = retrieval._reranker_probability(
        {"sidechain", "kick", "bass"},
        "Sidechain Compression Basics (sidechain-compression-basics.md)",
        "note",
        ["compression"],
        1,
    )
    assert prob is not None
    assert 0.0 <= prob <= 1.0
    retrieval._reranker_model_loaded = False


def test_reranker_disabled_by_default(monkeypatch) -> None:
    """Regression guard: measured against the real benchmark suite, applying
    this reranker by default regressed 3 cases (its dominant `inverse_rank`
    feature just amplifies whatever's already ranked #1 — see
    _load_reranker_model's docstring) with zero cases improved. It must stay
    opt-in (KENN_RERANKER_MODEL_ENABLED=1) until retrained against a harder
    eval set that shows a real top1/MRR delta."""
    monkeypatch.delenv("KENN_RERANKER_MODEL_ENABLED", raising=False)
    retrieval._reranker_model_loaded = False
    assert retrieval._load_reranker_model() is None
    retrieval._reranker_model_loaded = False


def test_reranker_blend_is_a_gentle_nudge_not_a_reordering_override(monkeypatch) -> None:
    """Even when explicitly enabled, the blend must not be strong enough to
    flip an otherwise-clear topic-overlap decision on its own."""
    monkeypatch.setenv("KENN_RERANKER_MODEL_ENABLED", "1")
    retrieval._reranker_model_loaded = False
    query = "How do I make vocals wide without muddying the mix?"
    off_topic = {
        "kind": "note",
        "title": "Vocal De-Essing",
        "source": "vocal-deessing.md",
        "text": "Tags: vocals, deesser, sibilance\nFix harsh S sounds.",
    }
    on_topic = {
        "kind": "note",
        "title": "Vocal Width Without Mud",
        "source": "vocal-width-without-mud.md",
        "text": "Tags: vocals, stereo width, wide, mono\nWiden doubles and keep the lead vocal central.",
    }
    ranked = rerank_results(query, [(9.0, off_topic), (8.0, on_topic)])
    assert ranked[0][1]["source"] == "vocal-width-without-mud.md"
    retrieval._reranker_model_loaded = False


def test_rerank_penalizes_reviewed_hard_negative(tmp_path, monkeypatch) -> None:
    hard_negatives = tmp_path / "kenn_hard_negatives.jsonl"
    hard_negatives.write_text(
        json.dumps(
            {
                "schema": "kenn.hard_negative.v1",
                "case_id": "wide-vocal-wrong-source",
                "question": "How do I make vocals wide without muddying the mix?",
                "negative_source": "vocal-deessing.md",
                "negative_source_label": "Vocal De-Essing",
                "reason": "wrong top source",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(retrieval, "HARD_NEGATIVES_PATH", hard_negatives)
    retrieval._load_hard_negatives_cached.cache_clear()

    query = "How do I make vocals wide without muddying the mix?"
    wrong = {
        "kind": "note",
        "title": "Vocal De-Essing",
        "source": "vocal-deessing.md",
        "text": "Tags: vocals, eq\nTreat sibilance in bright vocals.",
    }
    right = {
        "kind": "note",
        "title": "Vocal Width Without Mud",
        "source": "vocal-width-without-mud.md",
        "text": "Tags: vocals, stereo width, mono\nUse doubles and keep low mids central.",
    }

    ranked = rerank_results(query, [(20.0, wrong), (8.0, right)])

    assert ranked[0][1]["source"] == "vocal-width-without-mud.md"
    retrieval._load_hard_negatives_cached.cache_clear()


def test_hard_negatives_reload_when_file_changes(tmp_path, monkeypatch) -> None:
    hard_negatives = tmp_path / "kenn_hard_negatives.jsonl"
    hard_negatives.write_text("", encoding="utf-8")
    monkeypatch.setattr(retrieval, "HARD_NEGATIVES_PATH", hard_negatives)
    retrieval._load_hard_negatives_cached.cache_clear()

    assert retrieval.load_hard_negatives() == ()

    hard_negatives.write_text(
        json.dumps(
            {
                "schema": "kenn.hard_negative.v1",
                "case_id": "reload-test",
                "question": "How do I make vocals wide?",
                "negative_source": "bad-source.md",
                "negative_source_label": "Bad Source",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    loaded = retrieval.load_hard_negatives()

    assert len(loaded) == 1
    assert loaded[0]["negative_source"] == "bad-source.md"
    retrieval._load_hard_negatives_cached.cache_clear()

def test_source_trust_scores_approved_notes_above_manuals() -> None:
    note = {
        "kind": "note",
        "source": "approved-note.md",
        "text": "Status: Approved\nTags: mixing\nShort answer: test.",
    }
    manual = {"kind": "manual", "source": "live12-manual-en.pdf", "text": "Manual text."}

    assert source_trust_score(note) > source_trust_score(manual)


def test_dynamic_feedback_reranking(tmp_path, monkeypatch) -> None:
    import sqlite3
    import json
    
    # Setup dummy data directory and DB file
    dummy_db_dir = tmp_path / "data"
    dummy_db_dir.mkdir(parents=True, exist_ok=True)
    db_file = dummy_db_dir / "audio_too.db"
    
    conn = sqlite3.connect(str(db_file))
    conn.execute(
        """
        CREATE TABLE demo_feedback (
            rating TEXT,
            sources_json TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO demo_feedback (rating, sources_json) VALUES (?, ?)",
        ("useful", json.dumps([{"source": "good-source.md"}]))
    )
    conn.execute(
        "INSERT INTO demo_feedback (rating, sources_json) VALUES (?, ?)",
        ("not_useful", json.dumps([{"source": "bad-source.md"}]))
    )
    conn.commit()
    conn.close()
    
    # Mock Path.resolve so retrieval.py's repo-root computation (parents[4]) points to tmp_path
    from pathlib import Path
    original_resolve = Path.resolve
    def mock_resolve(self):
        if "retrieval.py" in str(self):
            return tmp_path / "studio" / "kenn" / "kenn" / "retrieval" / "retrieval.py"
        return original_resolve(self)
    monkeypatch.setattr(Path, "resolve", mock_resolve)

    # A prior test in the same run may have already warmed the module-level
    # TTL cache (pointing at a different db_file); force a fresh read.
    monkeypatch.setattr(retrieval, "_feedback_scores_cache", None)
    monkeypatch.setattr(retrieval, "_feedback_scores_cache_time", 0.0)

    # Verify scores loaded
    scores = retrieval.load_source_feedback_scores()
    assert scores["good-source.md"] > 1.0
    assert scores["bad-source.md"] < 1.0
    
    # Verify reranking adjusts scores
    chunk_good = {"source": "good-source.md", "text": "Some text.", "tags": []}
    chunk_bad = {"source": "bad-source.md", "text": "Some text.", "tags": []}
    
    results = [(10.0, chunk_good), (10.0, chunk_bad)]
    reranked = retrieval.rerank_results("query", results)
    
    # First item should be chunk_good
    assert reranked[0][1]["source"] == "good-source.md"
    assert reranked[0][0] > reranked[1][0]


# ── term_matches() single-word substring collisions ─────────────────────
#
# Live-tested 2026-08-03: "ca you help me with bass compression" got tagged
# with an unrelated "vocals" topic, which fed into a Sidechain Bass To Kick
# answer instead of general bass compression advice. Root cause:
# "vocals"'s synonym list includes "comp" (short for "vocal comping"), a
# single word at exactly 4 characters -- one over the old boundary-check
# cutoff of len(needle) <= 3, so it fell through to a naive substring
# check, and "comp" is literally the first four letters of "compression".


def test_short_single_word_term_does_not_match_inside_a_longer_word() -> None:
    assert term_matches("bass compression", "comp") is False


def test_short_single_word_term_still_matches_as_its_own_word() -> None:
    assert term_matches("how do i comp vocal takes", "comp") is True


def test_bass_compression_no_longer_gets_a_spurious_vocals_topic() -> None:
    topics = query_topics("ca you help me with bass compression")
    assert "vocals" not in topics
    assert "bass" in topics
    assert "compression" in topics


def test_comping_synonym_still_detects_vocals_topic() -> None:
    """"comping" is its own separate synonym entry, distinct from bare
    "comp" -- must still work after the boundary-matching fix."""
    topics = query_topics("how do i comp vocal takes together")
    assert "vocals" in topics
