"""Generate a deterministic synthetic workflow corpus and friction estimates."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "user_journeys" / "synthetic_corpus.json"

ARCHETYPES = (
    "beginner_producer",
    "intermediate_electronic_producer",
    "professional_producer",
    "mix_engineer",
    "sound_designer",
    "ableton_power_user",
    "large_sample_library_user",
    "keyboard_accessibility_user",
    "nite_dsp_company_owner",
)

TASKS = {
    "find_kick": (7, 8, 4, 2, 5, 400, 1, 4, 3, 2, 1, 180, 0, "PROMOTE"),
    "find_complementary_clap": (9, 10, 5, 3, 6, 500, 1, 5, 4, 3, 2, 240, 0, "CONTINUE_R&D"),
    "replace_bass_sample": (8, 8, 4, 2, 5, 450, 1, 5, 3, 2, 1, 220, 0, "PROMOTE"),
    "diagnose_harsh_chorus": (6, 5, 6, 3, 4, 700, 2, 5, 4, 2, 2, 480, 1, "PROMOTE"),
    "compare_reference": (8, 6, 5, 3, 6, 1000, 2, 6, 4, 2, 2, 700, 1, "CONTINUE_R&D"),
    "recover_failed_scan": (8, 6, 4, 2, 5, 1200, 2, 4, 3, 2, 1, 500, 1, "PROMOTE"),
    "navigate_20k_map": (6, 5, 6, 2, 5, 250, 1, 5, 4, 4, 2, 180, 0, "CONTINUE_R&D"),
    "use_slo_keyboard_only": (10, 0, 11, 2, 7, 300, 2, 6, 0, 7, 2, 200, 1, "PROMOTE"),
    "approve_thursday_action": (6, 4, 5, 3, 5, 350, 1, 5, 3, 2, 1, 220, 0, "PROMOTE"),
    "understand_kenn_evidence": (7, 5, 6, 3, 6, 400, 1, 5, 3, 2, 2, 280, 0, "PROMOTE"),
    "switch_language": (5, 4, 5, 2, 4, 150, 1, 4, 3, 2, 1, 120, 0, "CONTINUE_R&D"),
    "use_three_plugin_instances": (7, 6, 5, 3, 5, 600, 2, 5, 4, 2, 2, 450, 1, "CONTINUE_R&D"),
    "find_recent_sample": (5, 5, 3, 2, 4, 180, 1, 3, 2, 1, 1, 100, 0, "PROMOTE"),
    "nothing_needs_fixing": (6, 5, 5, 3, 5, 400, 1, 3, 2, 1, 1, 180, 0, "PROMOTE"),
    "chatbot_first_plugin": (8, 7, 7, 3, 6, 500, 1, 11, 6, 5, 3, 650, 2, "DROP/PARK"),
}


def make_scenario(archetype: str, task_name: str, base: tuple) -> dict:
    current_steps, current_clicks, current_keys, current_contexts, current_decisions, current_wait, current_errors, proposed_steps, proposed_clicks, proposed_keys, proposed_contexts, proposed_wait, proposed_errors, status = base
    proposed_decisions = max(1, round(current_decisions * 0.4))
    scale = {
        "beginner_producer": 1.20,
        "intermediate_electronic_producer": 1.05,
        "professional_producer": 0.90,
        "mix_engineer": 0.95,
        "sound_designer": 1.00,
        "ableton_power_user": 0.85,
        "large_sample_library_user": 1.15,
        "keyboard_accessibility_user": 1.25,
        "nite_dsp_company_owner": 1.00,
    }[archetype]
    keyboard = archetype == "keyboard_accessibility_user"
    return {
        "scenario_id": f"{archetype}:{task_name}",
        "archetype": archetype,
        "task": task_name,
        "evidence_class": "synthetic estimate, not human research",
        "current": {
            "steps": round(current_steps * scale),
            "clicks": 0 if keyboard else round(current_clicks * scale),
            "keystrokes": round(current_keys * (1.15 if keyboard else 1.0)),
            "context_switches": round(current_contexts * scale),
            "decision_points": round(current_decisions * scale),
            "wait_ms": round(current_wait * (1.25 if task_name in {"recover_failed_scan", "compare_reference"} else 1.0)),
            "error_recovery": round(current_errors * scale),
        },
        "proposed": {
            "steps": round(proposed_steps * scale),
            "clicks": 0 if keyboard else round(proposed_clicks * scale),
            "keystrokes": round(proposed_keys * (1.15 if keyboard else 1.0)),
            "context_switches": round(proposed_contexts * scale),
            "decision_points": round(proposed_decisions * scale),
            "wait_ms": round(proposed_wait * (1.25 if task_name in {"recover_failed_scan", "compare_reference"} else 1.0)),
            "error_recovery": round(proposed_errors * scale),
        },
        "promotion_status": status,
    }


def aggregate(scenarios: list[dict]) -> dict:
    totals = {}
    for scenario in scenarios:
        task = scenario["task"]
        current = scenario["current"]
        proposed = scenario["proposed"]
        row = totals.setdefault(task, {"count": 0, "current_steps": 0, "proposed_steps": 0, "step_reduction": 0, "status": scenario["promotion_status"]})
        row["count"] += 1
        row["current_steps"] += current["steps"]
        row["proposed_steps"] += proposed["steps"]
        row["step_reduction"] += current["steps"] - proposed["steps"]
    for row in totals.values():
        row["mean_step_reduction"] = round(row["step_reduction"] / row["count"], 2)
    return totals


def main() -> None:
    scenarios = [make_scenario(archetype, task_name, base) for archetype in ARCHETYPES for task_name, base in TASKS.items()]
    task_totals = aggregate(scenarios)
    result = {
        "version": "px-user-journeys-v1",
        "evidence_class": "synthetic scenario generation and friction estimates",
        "archetype_count": len(ARCHETYPES),
        "task_count": len(TASKS),
        "scenario_count": len(scenarios),
        "archetypes": list(ARCHETYPES),
        "scenarios": scenarios,
        "task_totals": task_totals,
        "best_step_reduction": max(task_totals.items(), key=lambda item: item[1]["mean_step_reduction"])[0],
        "worst_proposed_feature": min(task_totals.items(), key=lambda item: item[1]["mean_step_reduction"])[0],
        "limitations": [
            "Metrics are scenario-model outputs, not observed user timings.",
            "No real users were recruited or contacted.",
            "Promotion status is a research recommendation and still needs technical and human gates.",
        ],
    }
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("version", "archetype_count", "task_count", "scenario_count", "best_step_reduction", "worst_proposed_feature")}, indent=2))


if __name__ == "__main__":
    main()
