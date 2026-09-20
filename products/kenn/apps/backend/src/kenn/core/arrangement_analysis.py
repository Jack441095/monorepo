"""Conservative structural observations from a current Live session context.

This is intentionally not an audio analyser or genre classifier.  It observes
only scene/clip-slot topology already present in ``kenn.session_context.v1``
and labels density changes as *candidates* rather than musical verdicts.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from kenn.core.session_context import validate_session_context


SCHEMA = "kenn.arrangement_analysis.v1"
SUGGESTIONS_SCHEMA = "kenn.arrangement_suggestions.v1"
MAX_SCENES = 256
MAX_LOCATORS = 256


def _text(value: Any, limit: int = 128) -> str:
    return str(value or "").strip()[:limit]


def analyze_arrangement_context(context: dict[str, Any]) -> dict[str, Any]:
    """Return bounded scene-density observations from a fresh session context."""
    validation = validate_session_context(context)
    base: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "unavailable",
        "source_fingerprint": _text(context.get("snapshot_fingerprint"), 96) if isinstance(context, dict) else "",
        "sections": [],
        "locators": [],
        "timeline_sections": [],
        "timeline_transitions": [],
        "transitions": [],
        "repetition_candidates": [],
        "suggestions": [],
        "limitations": [
            "This uses Live scene/clip-slot topology and observed locators only; it does not measure loudness, spectral energy, automation, or audible musical quality.",
            "A density change is a structural candidate, not proof that a section needs changing.",
            "Locators are observed Arrangement View anchors; they are not automatically mapped to Session View scenes.",
        ],
        "advisory_only": True,
        "mutation_authorized": False,
    }
    if not validation["ok"]:
        base["errors"] = list(validation.get("errors") or [])[:16]
        return base

    scenes = [item for item in (context.get("scenes") or [])[:MAX_SCENES] if isinstance(item, dict)]
    locators = [
        {
            "index": item.get("index"), "name": _text(item.get("name"), 128),
            "time_beats": item.get("time_beats"), "evidence_class": "observed_session_fact",
            "confidence": "observed_locator",
        }
        for item in (context.get("locators") or [])[:MAX_LOCATORS]
        if isinstance(item, dict) and isinstance(item.get("time_beats"), (int, float))
        and not isinstance(item.get("time_beats"), bool)
    ]
    base["locators"] = locators
    tracks = [item for item in (context.get("tracks") or []) if isinstance(item, dict)]
    timeline_sections: list[dict[str, Any]] = []
    for locator_position, locator in enumerate(locators):
        anchor = float(locator["time_beats"])
        active_roles: Counter[str] = Counter()
        active_clip_count = 0
        active_track_indices: list[int] = []
        for track in tracks:
            track_index = track.get("index")
            role = _text((track.get("classification") or {}).get("role"), 64) or "unknown"
            clip_is_active = False
            for clip in track.get("arrangement_clips") or []:
                if not isinstance(clip, dict):
                    continue
                start, length = clip.get("start_time_beats"), clip.get("length_beats")
                if not isinstance(start, (int, float)) or isinstance(start, bool):
                    continue
                if not isinstance(length, (int, float)) or isinstance(length, bool) or length <= 0:
                    continue
                if float(start) <= anchor < float(start) + float(length):
                    active_clip_count += 1
                    clip_is_active = True
            if clip_is_active:
                active_roles[role] += 1
                if isinstance(track_index, int):
                    active_track_indices.append(track_index)
        next_anchor = locators[locator_position + 1]["time_beats"] if locator_position + 1 < len(locators) else None
        timeline_sections.append({
            "locator_index": locator.get("index"),
            "locator_name": locator.get("name"),
            "start_time_beats": anchor,
            "end_time_beats": next_anchor,
            "active_arrangement_clip_count": active_clip_count,
            "active_track_indices": active_track_indices[:128],
            "role_counts": dict(sorted(active_roles.items())),
            "evidence_class": "observed_session_fact",
            "confidence": "observed_timeline_topology",
        })
    base["timeline_sections"] = timeline_sections
    timeline_peak_density = max((item["active_arrangement_clip_count"] for item in timeline_sections), default=0)
    for section in timeline_sections:
        section["relative_density"] = (
            round(section["active_arrangement_clip_count"] / timeline_peak_density, 3)
            if timeline_peak_density else None
        )
    timeline_transitions: list[dict[str, Any]] = []
    for previous, current in zip(timeline_sections, timeline_sections[1:]):
        if timeline_peak_density <= 0:
            continue
        delta = current["relative_density"] - previous["relative_density"]
        if abs(delta) < 0.25:
            continue
        timeline_transitions.append({
            "from_locator_index": previous.get("locator_index"),
            "to_locator_index": current.get("locator_index"),
            "density_delta": round(delta, 3),
            "candidate": "timeline_density_lift" if delta > 0 else "timeline_density_drop",
            "evidence_class": "observed_session_fact",
            "interpretation": "A timeline-density change worth auditioning around the observed locator.",
        })
    base["timeline_transitions"] = timeline_transitions
    if not scenes:
        base["status"] = "current"
        base["limitations"].append("No Live scenes were observed, so Session View structure cannot be analysed.")
        # Arrangement View evidence remains independently useful.  Do not
        # discard locator-to-locator transition prompts merely because this
        # set has no Session View scenes.
        base["suggestions"] = suggestions_from_analysis(base)
        return base

    sections: list[dict[str, Any]] = []
    clip_names: Counter[str] = Counter()
    for scene in scenes:
        scene_index = scene.get("index")
        active_roles: Counter[str] = Counter()
        active_count = 0
        named_clips: list[str] = []
        for track in tracks:
            role = _text((track.get("classification") or {}).get("role"), 64) or "unknown"
            for slot in track.get("clip_slots") or []:
                if not isinstance(slot, dict) or slot.get("index") != scene_index or slot.get("has_clip") is not True:
                    continue
                active_count += 1
                active_roles[role] += 1
                clip_name = _text(slot.get("name"), 128)
                if clip_name:
                    named_clips.append(clip_name)
                    clip_names[clip_name] += 1
                break
        sections.append({
            "scene_index": scene_index,
            "scene_name": _text(scene.get("name"), 128) or f"Scene {scene_index}",
            "active_clip_count": active_count,
            "role_counts": dict(sorted(active_roles.items())),
            "clip_names": named_clips[:32],
            "evidence_class": "observed_session_fact",
            "confidence": "observed_topology",
        })

    peak_density = max((section["active_clip_count"] for section in sections), default=0)
    for section in sections:
        section["relative_density"] = round(section["active_clip_count"] / peak_density, 3) if peak_density else None

    transitions: list[dict[str, Any]] = []
    for previous, current in zip(sections, sections[1:]):
        if peak_density <= 0:
            continue
        delta = current["relative_density"] - previous["relative_density"]
        if abs(delta) < 0.25:
            continue
        transitions.append({
            "from_scene_index": previous["scene_index"],
            "to_scene_index": current["scene_index"],
            "density_delta": round(delta, 3),
            "candidate": "density_lift" if delta > 0 else "density_drop",
            "evidence_class": "observed_session_fact",
            "interpretation": "A structural density change worth auditioning in context.",
        })

    repetition = [
        {"clip_name": name, "scene_occurrences": count, "evidence_class": "observed_session_fact"}
        for name, count in sorted(clip_names.items())
        if count >= 2
    ][:32]
    base.update({
        "status": "current",
        "sections": sections,
        "transitions": transitions,
        "repetition_candidates": repetition,
    })
    if not any(section["active_clip_count"] for section in sections):
        base["limitations"].append("No populated clip slots matched the observed scene indices; no density conclusion is available.")
    base["suggestions"] = suggestions_from_analysis(base)
    return base


def suggestions_from_analysis(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn observed topology into bounded, conditional creative prompts."""
    if not isinstance(analysis, dict) or analysis.get("schema") != SCHEMA or analysis.get("status") != "current":
        return []
    sections = {
        item.get("scene_index"): item for item in (analysis.get("sections") or [])
        if isinstance(item, dict)
    }
    suggestions: list[dict[str, Any]] = []
    for transition in (analysis.get("transitions") or [])[:4]:
        if not isinstance(transition, dict):
            continue
        target = sections.get(transition.get("to_scene_index"), {})
        target_name = _text(target.get("scene_name"), 128) or "the next scene"
        candidate = transition.get("candidate")
        if candidate == "density_lift":
            prompt = (
                f"If {target_name} is meant to feel like an escalation, audition one small contrast "
                "before it—such as less percussion, a filtered element, or a short gap—then compare at matched level."
            )
        elif candidate == "density_drop":
            prompt = (
                f"If {target_name} is meant as a breakdown rather than an accidental loss of energy, "
                "audition a sustaining texture or transition tail before it and keep only what supports the intended reset."
            )
        else:
            continue
        suggestions.append({
            "schema": SUGGESTIONS_SCHEMA,
            "kind": "creative_arrangement_suggestion",
            "title": f"Audition the {str(candidate).replace('_', ' ')} into {target_name}",
            "prompt": prompt,
            "evidence": {
                "from_scene_index": transition.get("from_scene_index"),
                "to_scene_index": transition.get("to_scene_index"),
                "density_delta": transition.get("density_delta"),
                "evidence_class": "observed_session_fact",
            },
            "advisory_only": True,
            "live_mutation_authorized": False,
        })
    locator_sections = {
        item.get("locator_index"): item for item in (analysis.get("timeline_sections") or [])
        if isinstance(item, dict)
    }
    for transition in (analysis.get("timeline_transitions") or [])[:4]:
        if not isinstance(transition, dict):
            continue
        target = locator_sections.get(transition.get("to_locator_index"), {})
        target_name = _text(target.get("locator_name"), 128) or "the next locator"
        candidate = transition.get("candidate")
        if candidate == "timeline_density_lift":
            prompt = (
                f"At the observed {target_name} locator, more arrangement clips are active than at the prior locator. "
                "If that anchor should land with more impact, audition a small contrast immediately before it and keep it only if it serves the intended transition."
            )
        elif candidate == "timeline_density_drop":
            prompt = (
                f"At the observed {target_name} locator, fewer arrangement clips are active than at the prior locator. "
                "If this is an intentional reset, audition whether one sustained element or transition tail preserves the desired continuity."
            )
        else:
            continue
        suggestions.append({
            "schema": SUGGESTIONS_SCHEMA,
            "kind": "creative_arrangement_suggestion",
            "title": f"Audition the {str(candidate).replace('_', ' ')} into {target_name}",
            "prompt": prompt,
            "evidence": {
                "from_locator_index": transition.get("from_locator_index"),
                "to_locator_index": transition.get("to_locator_index"),
                "density_delta": transition.get("density_delta"),
                "evidence_class": "observed_session_fact",
            },
            "advisory_only": True,
            "live_mutation_authorized": False,
        })
    for repetition in (analysis.get("repetition_candidates") or [])[:3]:
        if not isinstance(repetition, dict):
            continue
        name = _text(repetition.get("clip_name"), 128)
        count = repetition.get("scene_occurrences")
        if not name or not isinstance(count, int):
            continue
        suggestions.append({
            "schema": SUGGESTIONS_SCHEMA,
            "kind": "creative_arrangement_suggestion",
            "title": f"Check whether {name} should vary",
            "prompt": (
                f"{name} appears in {count} observed scenes. If that repetition is intentional, leave it; "
                "otherwise audition one minimal variation such as a fill, mute, velocity change, or tail."
            ),
            "evidence": {"clip_name": name, "scene_occurrences": count, "evidence_class": "observed_session_fact"},
            "advisory_only": True,
            "live_mutation_authorized": False,
        })
    return suggestions[:7]


__all__ = ["SCHEMA", "SUGGESTIONS_SCHEMA", "analyze_arrangement_context", "suggestions_from_analysis"]
