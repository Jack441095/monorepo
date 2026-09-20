"""Reusable provenance checks for official Ableton-manual retrieval."""
from __future__ import annotations

from typing import Any, Callable


SCHEMA = "kenn.ableton_manual_grounding_evaluation.v1"
REFERENCE_CASES = (
    {"id": "capture_midi", "category": "midi", "query": "According to the official Ableton manual, how does Capture MIDI work?"},
    {"id": "midi_recording", "category": "midi", "query": "Show the official Ableton manual instructions for recording MIDI into a clip."},
    {"id": "routing", "category": "routing", "query": "What does the Ableton reference manual say about routing audio between tracks?"},
    {"id": "return_tracks", "category": "routing", "query": "According to the official Ableton manual, how do return tracks and sends work?"},
    {"id": "automation", "category": "automation", "query": "Show the official Ableton documentation for editing automation."},
    {"id": "automation_override", "category": "automation", "query": "What does the official Ableton manual say about re-enabling automation after manual changes?"},
    {"id": "session_view", "category": "workflow", "query": "According to the official Ableton manual, how do I launch clips and scenes in Session View?"},
    {"id": "arrangement_view", "category": "workflow", "query": "Show the official Ableton manual guidance for working in Arrangement View."},
    {"id": "clip_editing", "category": "clips", "query": "What does the official Ableton manual say about editing clip loop length and start markers?"},
    {"id": "warping", "category": "clips", "query": "According to the official Ableton manual, how do warp markers and warp modes work?"},
    {"id": "audio_recording", "category": "recording", "query": "Show the official Ableton manual instructions for recording audio into Live."},
    {"id": "freeze_flatten", "category": "recording", "query": "What does the official Ableton manual say about freezing and flattening a track?"},
    {"id": "device_parameters", "category": "devices", "query": "According to the official Ableton manual, how can I configure a device and its parameters?"},
    {"id": "instrument_racks", "category": "devices", "query": "Show the official Ableton manual documentation for Instrument Racks, chains, and macros."},
    {"id": "tempo_transport", "category": "transport", "query": "What does the official Ableton manual say about setting tempo and controlling transport?"},
    {"id": "export_audio", "category": "export", "query": "According to the official Ableton manual, how do I export rendered audio?"},
)

SearchResult = tuple[float, dict[str, Any]]
SearchFn = Callable[[str], list[SearchResult]]
DisplayFn = Callable[[str, list[SearchResult]], list[SearchResult]]


def evaluate_cases(
    cases: tuple[dict[str, str], ...], *, search_fn: SearchFn, display_fn: DisplayFn
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    categories: dict[str, list[bool]] = {}
    for case in cases:
        results = search_fn(case["query"])
        displayed = display_fn(case["query"], results)
        top = displayed[0][1] if displayed else {}
        selected_class = str(top.get("evidence_class") or "")
        row = {
            "id": case["id"], "category": case["category"],
            "selected_evidence_class": selected_class or None,
            "passed": selected_class == "official_ableton_manual",
        }
        rows.append(row)
        categories.setdefault(case["category"], []).append(bool(row["passed"]))
    return {
        "schema": SCHEMA, "status": "evaluated", "case_count": len(rows),
        "passed_case_count": sum(row["passed"] for row in rows),
        "all_cases_passed": all(row["passed"] for row in rows),
        "coverage": {
            "category_count": len(categories),
            "categories": {category: {"case_count": len(values), "all_cases_passed": all(values)} for category, values in sorted(categories.items())},
        },
        "rows": rows,
        "limitations": [
            "This evaluator checks retrieval provenance selection only; factual answer quality, citation precision, and safe execution require separate evaluation.",
            "Explicit official-reference requests without a substantively matching manual chunk must be evaluated through KENN's abstention path.",
        ],
    }
