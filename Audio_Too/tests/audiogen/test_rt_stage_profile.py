from tools.benchmark_realtime_audio import (
    evaluate_cold_start,
    evaluate_stage_profile,
    summarize_cold_start,
    summarize_stage_samples,
)


def test_stage_profile_summary_identifies_dominant_stage_and_budget_counts():
    summary = summarize_stage_samples(
        [
            {
                "render_ratio": 0.5,
                "culprit": "chords",
                "stages_ms": {"mono": 10.0, "chords": 80.0, "mix": 20.0, "master": 5.0, "total": 115.0},
            },
            {
                "render_ratio": 1.1,
                "culprit": "chords",
                "stages_ms": {"mono": 12.0, "chords": 100.0, "mix": 25.0, "master": 7.0, "total": 144.0},
            },
        ]
    )

    assert summary["bars_profiled"] == 2
    assert summary["dominant_stage"] == "chords"
    assert summary["dominant_culprit"] == "chords"
    assert summary["over_budget_bars"] == 1
    assert summary["near_budget_bars"] == 1
    assert summary["render_ratio_max"] == 1.1


def test_stage_profile_gate_reports_threshold_failures():
    gate = evaluate_stage_profile(
        {"bars_profiled": 1, "render_ratio_max": 1.2, "over_budget_bars": 1},
        max_render_ratio=1.0,
        max_over_budget_bars=0,
        min_profiled_bars=2,
    )

    assert gate["ok"] is False
    assert "profiled bars 1 < required 2" in gate["failures"]
    assert "max render ratio 1.200 > 1.000" in gate["failures"]
    assert "over-budget bars 1 > allowed 0" in gate["failures"]


def test_cold_start_summary_tracks_first_profiled_bar():
    summary = summarize_cold_start(
        stats={
            "last_emotion_switch_latency_ms": 900.0,
            "last_emotion_switch_stage": "cold_start",
            "last_section_compose_time_ms": 700.0,
            "chunks_generated": 3,
        },
        stage_samples=[
            {
                "chunk": 1,
                "elapsed_ms": 1800.0,
                "render_ratio": 0.5,
                "culprit": "master",
                "stages_ms": {"total": 1200.0},
            }
        ],
        init_ms=25.0,
        elapsed_ms=8000.0,
    )

    assert summary["emotion_switch_latency_ms"] == 900.0
    assert summary["first_profiled_chunk"] == 1
    assert summary["first_profiled_elapsed_ms"] == 1800.0
    assert summary["first_profiled_dominant_stage"] == "master"
    assert summary["chunks_generated"] == 3


def test_cold_start_gate_reports_slow_or_missing_first_bar():
    slow = evaluate_cold_start({"first_profiled_elapsed_ms": 2500.0}, max_cold_start_ms=2000.0)
    missing = evaluate_cold_start({"first_profiled_elapsed_ms": 0.0}, max_cold_start_ms=2000.0)

    assert slow["ok"] is False
    assert "first profiled bar 2500.0ms > allowed 2000.0ms" in slow["failures"]
    assert missing["ok"] is False
    assert "no profiled first bar for cold-start gate" in missing["failures"]
