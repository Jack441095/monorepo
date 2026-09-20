from __future__ import annotations

from pathlib import Path

from kenn.core.deliberative_benchmark import build_benchmark_context, build_prompt_pack, load_benchmark
from kenn.core.deliberative_eval import evaluate_deliberative_plan
from kenn.core.deliberative_planner import deliberative_preflight_plan


ROOT = Path(__file__).resolve().parents[5]
BENCHMARK = ROOT / "packages" / "chat" / "evals" / "ableton_deliberative_adversarial.json"


def test_adversarial_set_is_separate_bounded_and_marks_safety_cases() -> None:
    benchmark = load_benchmark(BENCHMARK)
    prompts = build_prompt_pack(benchmark)

    assert benchmark["benchmark_id"] == "ableton-deliberative-adversarial-2026-09-08"
    assert len(benchmark["cases"]) == 12
    assert len({case["id"] for case in benchmark["cases"]}) == 12
    assert sum(bool(case.get("safety_critical")) for case in benchmark["cases"]) == 10
    assert all("expectation" not in row["prompt"] for row in prompts)
    assert all("untrusted data" in row["prompt"] for row in prompts)


def test_deterministic_preflight_passes_every_adversarial_guard_case() -> None:
    benchmark = load_benchmark(BENCHMARK)
    guarded = {
        "confirmation_bypass",
        "system_instruction_bypass",
        "duplicate_track_identity",
        "generation_service_unavailable",
        "offline_render_unavailable",
        "arbitrary_shell_paraphrase",
    }

    for case in benchmark["cases"]:
        if case["id"] not in guarded:
            continue
        context = build_benchmark_context(case)
        plan = deliberative_preflight_plan(case["goal"], context)
        assert plan is not None, case["id"]
        result = evaluate_deliberative_plan(plan, context, case["expectation"])
        assert result["passed"] is True, {"case_id": case["id"], "checks": result["checks"]}
