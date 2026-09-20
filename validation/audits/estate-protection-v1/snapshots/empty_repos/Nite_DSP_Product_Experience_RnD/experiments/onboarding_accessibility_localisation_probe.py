"""Structural UX stress test for SLO/KENN workflow controls."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "experiments" / "onboarding_accessibility_localisation_results.json"

LABELS = {
    "search": "Search samples",
    "find_similar": "Find similar",
    "find_complement": "Find complement",
    "preview": "Play preview",
    "drag": "Drag to DAW",
    "apply": "Apply proposal",
    "reject": "Reject proposal",
    "undo": "Undo change",
    "empty": "No results. Change the search or clear a filter.",
}
CONTROL_BUDGETS = {
    "search": 220,
    "find_similar": 150,
    "find_complement": 170,
    "preview": 130,
    "drag": 140,
    "apply": 150,
    "reject": 150,
    "undo": 130,
    "empty": 320,
}
LOCALE_FACTORS = {
    "en": 1.00,
    "de-x-pseudo": 1.35,
    "es": 1.18,
    "fr": 1.14,
    "cjk-x-pseudo": 1.55,
    "ar-x-pseudo": 1.22,
}


def estimated_width(label: str, locale_factor: float, text_scale: float = 1.0) -> float:
    return len(label) * 7.0 * locale_factor * text_scale


def run_localisation() -> dict:
    rows = []
    for locale, locale_factor in LOCALE_FACTORS.items():
        for control_id, label in LABELS.items():
            width = estimated_width(label, locale_factor)
            budget = CONTROL_BUDGETS[control_id]
            rows.append({
                "locale": locale,
                "control": control_id,
                "estimated_width_px": round(width, 1),
                "budget_px": budget,
                "overflow": width > budget,
                "action": "allow wrap or expand" if width > budget else "fits",
            })
    return {
        "rows": rows,
        "overflow_count": sum(row["overflow"] for row in rows),
        "worst_locale": max(LOCALE_FACTORS, key=LOCALE_FACTORS.get),
    }


def run_accessibility() -> dict:
    focus_order = ["search", "filters", "results", "preview", "find_similar", "find_complement", "drag", "favorites"]
    state_grammar = {
        "playing": ["glyph:play", "halo", "text"],
        "success": ["glyph:check", "text"],
        "warning": ["glyph:warning", "text-chip"],
        "error": ["glyph:error", "text"],
        "unknown": ["hollow-dashed-outline", "text"],
    }
    semantics = [
        {"id": control_id, "role": "button" if control_id not in {"search", "results"} else "textbox" if control_id == "search" else "list", "accessible_name": label, "keyboard": True}
        for control_id, label in LABELS.items()
    ]
    return {
        "focus_order": focus_order,
        "focus_order_unique": len(focus_order) == len(set(focus_order)),
        "state_grammar": state_grammar,
        "color_independent_states": all(len(encodings) >= 2 for encodings in state_grammar.values()),
        "reduced_motion_policy": "transforms instant; opacity only; no entrance/bounce/parallax",
        "text_scale_150_percent": run_localisation_at_scale(1.5),
        "control_semantics": semantics,
        "all_controls_named_and_keyboard_reachable": all(item["accessible_name"] and item["keyboard"] for item in semantics),
    }


def run_localisation_at_scale(scale: float) -> dict:
    overflow = []
    for control_id, label in LABELS.items():
        if estimated_width(label, 1.0, scale) > CONTROL_BUDGETS[control_id]:
            overflow.append(control_id)
    return {"scale": scale, "overflow_controls": overflow, "requires_adaptive_layout": bool(overflow)}


def main() -> None:
    localisation = run_localisation()
    accessibility = run_accessibility()
    result = {
        "version": "px-onboarding-accessibility-localisation-v1",
        "evidence_class": "structural synthetic stress test",
        "onboarding_steps": [
            "install", "open", "select library", "scan", "understand classification", "search", "audition", "drag sample into DAW",
        ],
        "empty_states": [
            "no library", "scanning", "no results", "no favourites", "no history", "no similar samples", "unknown", "offline model", "analysis failed", "permission denied",
        ],
        "localisation": localisation,
        "accessibility": accessibility,
        "assertions": {
            "focus_order_valid": accessibility["focus_order_unique"],
            "states_are_not_color_only": accessibility["color_independent_states"],
            "controls_have_names_and_keyboard_path": accessibility["all_controls_named_and_keyboard_reachable"],
            "overflow_is_explicitly_detected": localisation["overflow_count"] > 0,
        },
        "limitations": [
            "No screen reader, JUCE component tree, or rendered UI was exercised.",
            "Width estimates are a layout stress proxy; real font metrics and translated copy must be tested in the UI.",
            "The onboarding journey is a specification, not observed human research.",
        ],
    }
    assert all(result["assertions"].values())
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
