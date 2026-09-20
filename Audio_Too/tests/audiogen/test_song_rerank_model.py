"""Phase B learned song reranker."""

from __future__ import annotations

from composition.audit_aligned_score import professional_quality_score
from composition.song_rerank_model import (
    SongRerankModel,
    evaluate_model,
    fit_ridge_regressor,
    learned_rerank_score_from_details,
)


def _synthetic_rows(n: int = 24):
    rows = []
    for i in range(n):
        row = {
            "in_key_primary_ratio": 0.95 + 0.01 * (i % 3),
            "lead_abs_interval_p95": 6.0 + (i % 5),
            "lead_repeat_frac": 0.08 + 0.01 * (i % 4),
            "lead_arp_overlap": 0.15 + 0.02 * (i % 3),
            "lead_activity": 0.4 + 0.02 * (i % 6),
            "chord_change_rate_per_bar": 0.7 + 0.05 * (i % 4),
            "mh_strongbeat_chord_tone_frac": 0.7,
            "mh_phrase_end_chord_tone_frac": 0.75,
            "hook_identity_score": 0.5 + 0.05 * (i % 5),
            "chorus_payoff_score": 0.55,
            "motif_development_score": 0.5,
            "counter_melody_events_per_bar": 0.12,
            "emotion_match_score": 90.0 + float(i % 7),
        }
        row["professional_quality_score"] = professional_quality_score(row)
        rows.append(row)
    return rows


def test_fit_rerank_regressor_correlates_with_target():
    rows = _synthetic_rows(30)
    model = fit_ridge_regressor(rows, ridge_lambda=0.5)
    metrics = evaluate_model(model, rows)
    assert metrics["n"] >= 20.0
    assert metrics["mae"] < 12.0
    assert metrics["corr"] > 0.25


def test_learned_rerank_score_fallback_without_model():
    details = {"lead_activity": 0.5, "lead_repeat_frac": 0.1, "lead_arp_overlap": 0.2, "in_key_primary_ratio": 1.0}
    score, meta = learned_rerank_score_from_details(details, model_path="")
    assert meta["rerank_score_source"] == "heuristic"
    assert 0.0 <= score <= 100.0


def test_model_save_load_roundtrip(tmp_path):
    model = fit_ridge_regressor(_synthetic_rows(20))
    path = tmp_path / "rerank.json"
    model.save(path)
    loaded = SongRerankModel.load(path)
    row = _synthetic_rows(1)[0]
    assert abs(loaded.predict_row(row) - model.predict_row(row)) < 0.5
