"""Tests for the operational Live-command shadow report."""

from __future__ import annotations

from scripts.analyze_shadow_logs import analyze, render


def _row(command: str, *, llm_status: str, comparison_status: str | None, deterministic: str, llm_action: str, timestamp: float = 0.0) -> dict:
    llm = {
        "mode": "shadow",
        "status": llm_status,
        "plan": {"schema": "kenn.ableton_llm_plan.v1", "action": llm_action},
    }
    if comparison_status:
        llm["comparison"] = {
            "status": comparison_status,
            "deterministic_action": deterministic,
            "llm_action": llm_action,
            "differences": [] if comparison_status == "match" else [{"field": "action"}],
            "deterministic_missing": [],
        }
    return {"response": {"command": command, "llm": llm, "timestamp": timestamp}}


def test_shadow_report_counts_acceptance_matches_divergence_and_novel_phrasing() -> None:
    report = analyze([
        _row("mute the bass", llm_status="accepted", comparison_status="match", deterministic="set_mute", llm_action="set_mute", timestamp=1_000_000),
        _row("tuck the vocal a touch", llm_status="accepted", comparison_status="mismatch", deterministic="clarify", llm_action="set_volume", timestamp=1_086_400),
        _row("invent a synth", llm_status="rejected", comparison_status=None, deterministic="clarify", llm_action="clarify"),
    ])

    assert report["total_commands"] == 3
    assert report["schema_acceptance_rate"] == 2 / 3
    assert report["deterministic_match_rate"] == 1 / 2
    assert report["divergence_count"] == 1
    assert report["observation_days"] == 1.0
    assert report["divergence_samples"][0]["command"] == "tuck the vocal a touch"
    assert report["novel_phrasings"][0]["llm_action"] == "set_volume"
    assert "Schema acceptance: 2/3 (66.7%)" in render(report)


def test_shadow_report_handles_empty_logs() -> None:
    report = analyze([])

    assert report["total_commands"] == 0
    assert report["schema_acceptance_rate"] == 0.0
    assert report["deterministic_match_rate"] == 0.0
