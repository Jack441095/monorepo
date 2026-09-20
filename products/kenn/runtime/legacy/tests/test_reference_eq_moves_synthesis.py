"""Phase 5 (docs/KENN_HUB_UNIFICATION_PLAN_2026-08-05.md) synthesis slice:
the chat follow-up path previously had a summary of the reference-track
comparison (rms/crest/width deltas, a single "largest difference" band)
but never the actual concrete EQ move list mix_doctor.py's HTML report
shows ("Boost/Reduce X dB around Y Hz"). These tests cover the fix: the
same move list is now formatted into the chat context payload and
extracted into the chat follow-up's reference_notes, so both surfaces
agree on the same real numbers.
"""

from __future__ import annotations

from kenn.core.chat_routing import _extract_mix_review_items
from kenn.server_payloads import (
    _format_eq_band_moves,
    _format_genre_classification,
    _retrieve_approved_genre_evidence,
    mix_review_context_turn,
)


def test_format_eq_band_moves_skips_negligible_gain():
    eq_bands = [
        {"freq": 3500, "gain": 2.3},
        {"freq": 8000, "gain": -0.2},  # below the 0.5 dB threshold -- dropped
        {"freq": 120, "gain": -1.8},
    ]
    result = _format_eq_band_moves(eq_bands)
    assert result == "Boost 2.3 dB around 3500 Hz | Reduce 1.8 dB around 120 Hz"


def test_format_eq_band_moves_handles_missing_or_malformed_input():
    assert _format_eq_band_moves(None) == ""
    assert _format_eq_band_moves([]) == ""
    assert _format_eq_band_moves([{"freq": "not-a-number", "gain": 2.0}]) == ""
    assert _format_eq_band_moves("not-a-list") == ""


def test_format_eq_band_moves_respects_limit():
    eq_bands = [{"freq": f, "gain": 2.0} for f in (100, 200, 300, 400, 500)]
    result = _format_eq_band_moves(eq_bands, limit=2)
    assert result == "Boost 2.0 dB around 100 Hz | Boost 2.0 dB around 200 Hz"


def test_structured_context_turn_includes_reference_eq_moves_line():
    context = {
        "schema": "kenn_mix_review_handoff.v1",
        "title": "My Track",
        "context_lines": ["Mix Review Lab context for My Track."],
        "reference_comparison": {
            "rms_delta_db": -1.2,
            "eq_bands": [{"freq": 3500, "gain": 2.3}, {"freq": 8000, "gain": -1.1}],
        },
    }
    turn = mix_review_context_turn(context)
    assert turn is not None
    assert "Structured reference EQ moves: Boost 2.3 dB around 3500 Hz | Reduce 1.1 dB around 8000 Hz" in turn["content"]


def test_legacy_context_turn_includes_reference_eq_moves_line():
    context = {
        "title": "My Track",
        "summary": "A rough mix.",
        "reference_comparison": {
            "rms_delta_db": -1.2,
            "eq_bands": [{"freq": 3500, "gain": 2.3}],
        },
    }
    turn = mix_review_context_turn(context)
    assert turn is not None
    assert "Reference EQ moves: Boost 2.3 dB around 3500 Hz" in turn["content"]


def test_extract_mix_review_items_pulls_structured_eq_moves_label():
    context = (
        "Mix Review Lab context for My Track.\n"
        "Structured reference comparison: {\"rms_delta_db\": -1.2}\n"
        "Structured reference EQ moves: Boost 2.3 dB around 3500 Hz | Reduce 1.1 dB around 8000 Hz\n"
    )
    items = _extract_mix_review_items(
        context,
        (
            "Structured reference EQ moves",
            "Reference EQ moves",
            "Structured reference comparison",
            "Reference comparison",
            "Reference advice",
        ),
        limit=4,
    )
    assert "Boost 2.3 dB around 3500 Hz" in items
    assert "Reduce 1.1 dB around 8000 Hz" in items


class TestGenreClassificationGrounding:
    """2026-08-06: genre classification (report["mix_style"]["genre"]) is
    grounded in an approved KENN source (reference-track-genre-archetypes.md)
    because it's backed by a real coded lookup table (GENRE_SEED_PROFILES).
    The EQ moves above stay deliberately ungrounded -- they're solved
    against the specific uploaded reference file, not any genre
    convention -- so this is intentionally a separate, narrower grounding
    path, not a loosening of the EQ-move decision."""

    def test_abstains_when_mix_style_missing(self):
        assert _format_genre_classification(None) == ""
        assert _format_genre_classification({}) == ""

    def test_abstains_when_genre_uncategorised(self):
        mix_style = {"genre": {"genre_key": "", "genre_name": "Uncategorised", "confidence": 0.0}}
        assert _format_genre_classification(mix_style) == ""

    def test_abstains_when_evidence_retrieval_fails(self, monkeypatch):
        import kenn.server_payloads as server_payloads

        monkeypatch.setattr(server_payloads, "_retrieve_approved_genre_evidence", lambda: None)
        mix_style = {"genre": {"genre_key": "pop", "genre_name": "Pop", "confidence": 0.82}}
        assert _format_genre_classification(mix_style) == ""

    def test_includes_grounded_citation_when_evidence_found(self, monkeypatch):
        import kenn.server_payloads as server_payloads

        monkeypatch.setattr(
            server_payloads,
            "_retrieve_approved_genre_evidence",
            lambda: "note_abc123@index:v-test",
        )
        mix_style = {"genre": {"genre_key": "pop", "genre_name": "Pop", "confidence": 0.82}}
        result = _format_genre_classification(mix_style)
        assert result == "Pop-leaning (82% confidence, source: note_abc123@index:v-test)"

    def test_retrieval_finds_the_real_approved_note(self):
        # Not mocked -- proves the curated note is actually indexed and
        # retrievable with "Status: Approved", not just that the formatting
        # function trusts whatever a mock hands it.
        evidence_id = _retrieve_approved_genre_evidence()
        assert evidence_id is not None
        assert "reference-track-genre-archetypes.md" not in evidence_id  # id is a chunk id, not the filename
        assert "@index:" in evidence_id

    def test_structured_context_turn_includes_genre_classification_line(self, monkeypatch):
        import kenn.server_payloads as server_payloads

        monkeypatch.setattr(
            server_payloads,
            "_retrieve_approved_genre_evidence",
            lambda: "note_abc123@index:v-test",
        )
        context = {
            "schema": "kenn_mix_review_handoff.v1",
            "title": "My Track",
            "context_lines": ["Mix Review Lab context for My Track."],
            "mix_style": {"genre": {"genre_key": "pop", "genre_name": "Pop", "confidence": 0.82}},
        }
        turn = mix_review_context_turn(context)
        assert turn is not None
        assert "Structured genre classification: Pop-leaning (82% confidence" in turn["content"]

    def test_legacy_context_turn_includes_genre_classification_line(self, monkeypatch):
        import kenn.server_payloads as server_payloads

        monkeypatch.setattr(
            server_payloads,
            "_retrieve_approved_genre_evidence",
            lambda: "note_abc123@index:v-test",
        )
        context = {
            "title": "My Track",
            "summary": "A rough mix.",
            "mix_style": {"genre": {"genre_key": "edm", "genre_name": "EDM / Dance", "confidence": 0.6}},
        }
        turn = mix_review_context_turn(context)
        assert turn is not None
        assert "Genre classification: EDM / Dance-leaning (60% confidence" in turn["content"]
