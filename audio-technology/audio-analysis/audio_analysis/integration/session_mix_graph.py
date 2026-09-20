"""Canonical, evidence-only session mix graph for an AutoMix render.

The graph adapts existing role, arrangement, and relationship results; it
does not perform a second inference pass or claim DAW routing that was not
supplied.  It gives KENN one project-scoped structure to reason over instead
of three unrelated lists in a render manifest.
"""

from __future__ import annotations

from typing import Any

MIX_GRAPH_SCHEMA = "audio-too.mix-graph.v1"


def _bounded_text(value: object, *, limit: int = 160) -> str:
    return str(value or "").strip()[:limit]


def build_session_mix_graph(
    *,
    project_id: str,
    musical_roles: object,
    arrangement: object,
    relationships: object,
) -> dict[str, Any]:
    """Build a versioned graph from already-established AutoMix evidence."""
    roles = musical_roles if isinstance(musical_roles, list) else []
    arrangement_map = arrangement if isinstance(arrangement, dict) else {}
    sections = arrangement_map.get("sections") if isinstance(arrangement_map.get("sections"), list) else []
    findings = relationships if isinstance(relationships, list) else []

    nodes: list[dict[str, Any]] = [{
        "id": "bus:master", "kind": "bus", "name": "Master", "confidence": 1.0,
        "provenance": "automix_render_path",
    }]
    edges: list[dict[str, Any]] = []
    warnings: list[str] = []
    stem_ids: set[str] = set()
    for role in roles:
        if not isinstance(role, dict):
            continue
        stem_name = _bounded_text(role.get("stem_name"))
        if not stem_name or stem_name in stem_ids:
            continue
        stem_ids.add(stem_name)
        confidence = role.get("confidence")
        numeric_confidence = float(confidence) if isinstance(confidence, (int, float)) and not isinstance(confidence, bool) else 0.0
        nodes.append({
            "id": f"stem:{stem_name}",
            "kind": "stem",
            "name": stem_name,
            "instrument": _bounded_text(role.get("instrument")),
            "role": _bounded_text(role.get("role")),
            "priority": _bounded_text(role.get("priority")),
            "confidence": round(max(0.0, min(1.0, numeric_confidence)), 4),
            "ambiguous": bool(role.get("ambiguous", False)),
            "provenance": _bounded_text(role.get("inference_source")) or "musical_role",
        })
        edges.append({"type": "routes_to", "source": f"stem:{stem_name}", "target": "bus:master", "confidence": 1.0})
        if role.get("ambiguous"):
            warnings.append(f"Role for {stem_name!r} remains ambiguous; do not use it as an automatic priority decision.")

    for section in sections[:256]:
        if not isinstance(section, dict):
            continue
        section_id = _bounded_text(section.get("section_id"))
        if not section_id:
            continue
        node_id = f"section:{section_id}"
        nodes.append({
            "id": node_id, "kind": "section", "name": section_id,
            "start_seconds": section.get("start_seconds"), "end_seconds": section.get("end_seconds"),
            "density_band": _bounded_text(section.get("density_band")),
            "confidence": section.get("boundary_confidence"), "provenance": "arrangement_activity",
        })
        active_stems = section.get("active_stems")
        if isinstance(active_stems, list):
            for stem_name in active_stems:
                stem_name = _bounded_text(stem_name)
                if stem_name in stem_ids:
                    edges.append({"type": "active_in", "source": f"stem:{stem_name}", "target": node_id, "confidence": 1.0})

    for finding in findings[:256]:
        if not isinstance(finding, dict):
            continue
        related = finding.get("source_stems")
        if not isinstance(related, list):
            continue
        related_names = [_bounded_text(item) for item in related]
        related_names = [item for item in related_names if item in stem_ids]
        if len(related_names) < 2:
            continue
        evidence = finding.get("evidence") if isinstance(finding.get("evidence"), dict) else {}
        edge = {
            "type": _bounded_text(finding.get("relationship_type")) or "spectral_competition",
            "sources": [f"stem:{name}" for name in related_names],
            "protected": f"stem:{_bounded_text(finding.get('protected_stem'))}" if _bounded_text(finding.get("protected_stem")) in stem_ids else None,
            "intervention_target": f"stem:{_bounded_text(finding.get('intervention_target'))}" if _bounded_text(finding.get("intervention_target")) in stem_ids else None,
            "confidence": finding.get("confidence"),
            "status": _bounded_text(finding.get("status")),
            "measurement_scope": _bounded_text(evidence.get("measurement_scope")),
            "provenance": "stem_relationship_inference",
        }
        edges.append(edge)

    return {
        "schema": MIX_GRAPH_SCHEMA,
        "project_id": _bounded_text(project_id, limit=128),
        "nodes": nodes,
        "edges": edges,
        "warnings": warnings,
        "limitations": [
            "Graph represents uploaded stems and AutoMix evidence only; it does not assert DAW routing, plug-in state, or automation outside this render.",
            "Ambiguous role nodes are preserved as uncertainty, not used as automatic priority evidence.",
        ],
    }
