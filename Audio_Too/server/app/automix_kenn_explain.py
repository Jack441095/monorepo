"""Ground a KENN chat answer in one specific AutoMix render's own decisions,
so a user can ask "why did you cut my vocal at 3.5kHz?" and get an answer
backed by that render's real decisions_log/quality_gate data instead of
generic mixing advice.

Design note: this deliberately does NOT add a new route/context type inside
KENN's chat orchestration (kenn/core/chat_answer.py, chat_routing.py,
chat_grounding.py). That code is a dense, tightly-coupled state machine
(dozens of `route ==`/`timeline_context` conditionals) built and tuned for
one specific case (Mix Review Lab uploads) -- extending it correctly would
require understanding all of it, and getting it wrong risks silently
degrading grounding trust for the existing feature. Instead, this reshapes
an AutoMix render's manifest into the SAME "kenn_mix_review_handoff.v1"
schema `mix_review_context_turn()` (kenn/server_payloads.py) already
accepts and already trusts unconditionally -- reusing 100% of KENN's
existing, tested grounding machinery with zero changes to KENN itself.
"""

from __future__ import annotations

import json
from pathlib import Path

import artifact_store

_MANIFEST_KIND = "audio.automix.manifest"

# mix_review_context_turn() truncates individual fields itself (titles,
# flag/action counts, JSON blob lengths) but NOT context_lines -- cap it here
# so a render with a long multi-iteration decisions_log can't blow up the
# request payload sent to KENN.
_MAX_CONTEXT_LINES = 40
_MAX_SAFETY_DIAGNOSTICS = 6


def _resource_context_line(profile: object) -> str | None:
    """Render a bounded operational receipt without treating it as audio evidence."""
    if not isinstance(profile, dict) or profile.get("schema") != "automix.resource_profile.v1":
        return None
    stages = profile.get("stages")
    if not isinstance(stages, list):
        return None
    reference_stage = next(
        (item for item in stages if isinstance(item, dict) and item.get("stage") == "reference_matched"),
        None,
    )
    if reference_stage is None:
        return None
    elapsed = reference_stage.get("elapsed_ms")
    rss = reference_stage.get("peak_rss_bytes")
    if not isinstance(elapsed, (int, float)) or isinstance(elapsed, bool):
        return None
    line = f"Operational receipt: reference matching reached {float(elapsed) / 1000.0:.1f}s"
    if isinstance(rss, (int, float)) and not isinstance(rss, bool) and rss > 0:
        line += f" and {float(rss) / (1024 * 1024):.0f} MiB peak RSS"
    return line + ". This is render telemetry, not a mix-quality measurement."


def _mix_graph_context_lines(graph: object) -> list[str]:
    """Summarize only graph facts that are useful in a bounded chat context."""
    if not isinstance(graph, dict) or graph.get("schema") != "audio-too.mix-graph.v1":
        return []
    nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
    edges = graph.get("edges") if isinstance(graph.get("edges"), list) else []
    stems = [item for item in nodes if isinstance(item, dict) and item.get("kind") == "stem"]
    sections = [item for item in nodes if isinstance(item, dict) and item.get("kind") == "section"]
    relationship_edges = [
        item for item in edges
        if isinstance(item, dict) and item.get("type") not in {"routes_to", "active_in"}
    ]
    lines = [
        f"Session mix graph: {len(stems)} uploaded stem node(s), {len(sections)} activity section(s), and {len(relationship_edges)} measured relationship finding(s)."
    ]
    warnings = graph.get("warnings")
    if isinstance(warnings, list):
        for warning in warnings[:3]:
            text = str(warning).strip()
            if text:
                lines.append(f"Mix graph uncertainty: {text}")
    return lines


def find_latest_manifest_artifact(project_id: str) -> dict | None:
    """Most recent AutoMix manifest artifact for a project, or None if this
    project has never completed a render."""
    for item in artifact_store.list_for_project(project_id, limit=500):
        if item.get("kind") == _MANIFEST_KIND:
            return item
    return None


def load_manifest(artifact_id: str) -> dict:
    """Read and parse a manifest artifact's JSON content by artifact id."""
    path = artifact_store.resolve_path(artifact_id)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_mix_review_context_from_manifest(manifest: dict) -> dict:
    """Reshape an AutoMix render manifest (mix_delivery.py's
    package_mixdown_delivery output) into the kenn_mix_review_handoff.v1
    schema kenn/server_payloads.py::mix_review_context_turn() expects.

    Pure function -- no I/O, no KENN dependency -- so this is unit-testable
    against hand-built manifest dicts without a running KENN server.
    """
    if not isinstance(manifest, dict):
        return {}

    project_id = str(manifest.get("project_id", "")).strip()
    genre = str(manifest.get("genre", "")).strip()
    title = f"AutoMix render for project {project_id}" if project_id else "AutoMix render"
    if genre:
        title = f"{title} ({genre})"

    context_lines: list[str] = [
        f"AutoMix render decisions for project {project_id or 'unknown'}.",
    ]
    decisions_log = manifest.get("decisions_log")
    if isinstance(decisions_log, list) and decisions_log:
        context_lines.extend(str(entry).strip() for entry in decisions_log[:_MAX_CONTEXT_LINES] if str(entry).strip())
        if len(decisions_log) > _MAX_CONTEXT_LINES:
            context_lines.append(
                f"...({len(decisions_log) - _MAX_CONTEXT_LINES} more decisions not shown)"
            )
    else:
        context_lines.append("No per-render decisions were logged for this mix.")

    resource_line = _resource_context_line(manifest.get("resource_profile"))
    if resource_line:
        context_lines.append(resource_line)
    context_lines.extend(_mix_graph_context_lines(manifest.get("mix_graph")))

    receipt_lufs_delta: float | None = None
    quality_receipt = manifest.get("quality_receipt")
    if isinstance(quality_receipt, dict) and quality_receipt.get("schema") == "automix.quality_receipt.v1":
        if quality_receipt.get("verification_available") is True:
            context_lines.append(
                "Quality receipt: source-to-delivery measurements and provenance are available for this render."
            )
        receipt_gate = quality_receipt.get("safety_gate")
        if isinstance(receipt_gate, dict):
            safety_passed = receipt_gate.get("safety_passed")
            advisory_passed = receipt_gate.get("advisory_score_passed")
            score = receipt_gate.get("technical_score")
            minimum = receipt_gate.get("minimum_score")
            if safety_passed is True and advisory_passed is False:
                context_lines.append(
                    f"Quality receipt: delivery safety passed, but the advisory technical score "
                    f"({score}/{minimum}) did not meet its target."
                )
            elif safety_passed is True:
                context_lines.append("Quality receipt: delivery safety passed.")
        deltas = quality_receipt.get("measured_deltas")
        if isinstance(deltas, dict):
            lufs_delta = deltas.get("integrated_lufs")
            if isinstance(lufs_delta, (int, float)) and not isinstance(lufs_delta, bool):
                receipt_lufs_delta = float(lufs_delta)

    target_lufs = manifest.get("target_lufs")
    final_lufs = manifest.get("final_lufs")
    metrics: dict = {}
    if target_lufs is not None:
        metrics["target_lufs"] = target_lufs
    if final_lufs is not None:
        metrics["final_lufs"] = final_lufs
    quality_gate = manifest.get("quality_gate")
    technical_metrics: dict = {}
    if receipt_lufs_delta is not None:
        technical_metrics["source_to_delivery_lufs_delta"] = receipt_lufs_delta
    judgment: dict = {}
    flags: list[dict] = []
    if isinstance(quality_gate, dict):
        if quality_gate.get("technical_score") is not None:
            technical_metrics["technical_score"] = quality_gate["technical_score"]
        judgment = {
            "passed": quality_gate.get("passed"),
            "technical_score": quality_gate.get("technical_score"),
            "minimum_score": quality_gate.get("minimum_score"),
        }
        diagnostics = quality_gate.get("safety_diagnostics")
        if isinstance(diagnostics, list):
            for diagnostic in diagnostics[:_MAX_SAFETY_DIAGNOSTICS]:
                text = str(diagnostic).strip()
                if text:
                    flags.append({
                        "severity": "safety",
                        "label": "Delivery safety check",
                        "detail": text,
                    })
    if final_lufs is not None:
        technical_metrics["integrated_lufs"] = final_lufs

    relationships = manifest.get("relationships")
    priority_actions: list[dict] = []
    if isinstance(relationships, list):
        for rank, relationship in enumerate(relationships[:6], start=1):
            if not isinstance(relationship, dict):
                continue
            description = (
                relationship.get("description")
                or relationship.get("summary")
                or relationship.get("relationship_type")
                or "detected stem relationship"
            )
            priority_actions.append({
                "rank": rank,
                "decision": "relationship",
                "confidence": "measured",
                "focus": "Stem relationships",
                "action": str(description).strip(),
            })

    context: dict = {
        "schema": "kenn_mix_review_handoff.v1",
        "title": title[:120],
        "context_lines": context_lines,
    }
    if metrics:
        context["metrics"] = metrics
    if technical_metrics:
        context["technical_metrics"] = technical_metrics
    if judgment:
        context["judgment"] = judgment
    if flags:
        context["flags"] = flags
    if priority_actions:
        context["priority_actions"] = priority_actions
    return context


def build_mix_review_context_for_project(project_id: str) -> dict | None:
    """End-to-end: find this project's latest render manifest artifact, load
    it, and build the KENN grounding context. Returns None if the project
    has no completed render yet (not an error -- a normal "nothing to
    explain yet" case for a caller to handle)."""
    artifact = find_latest_manifest_artifact(project_id)
    if artifact is None:
        return None
    manifest = load_manifest(artifact["id"])
    return build_mix_review_context_from_manifest(manifest)


def _ensure_kenn_importable() -> None:
    """Same sys.path setup business/agents/Shared/kenn_client.py uses for its
    established in-process-KENN pattern -- KENN runs as a separate process
    normally (kenn_proxy_routes.py proxies to it over HTTP on :8090 for
    browser traffic), but server-side callers within this same Python
    process import it directly rather than adding an HTTP round trip."""
    import sys
    from pathlib import Path as _Path

    root = _Path(__file__).resolve().parent.parent.parent
    for path in (root / "studio" / "kenn", root / "studio" / "audio_analysis", root):
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)


def ask_kenn_about_render(project_id: str, question: str) -> dict:
    """Ask KENN a question grounded in project_id's latest AutoMix render.

    Returns {"ok": True, "answer": str, "grounded": bool} on success --
    grounded=False (still answered, just without render-specific context)
    when the project has no completed render yet, matching this function's
    contract as a graceful degradation, not a hard failure. Returns
    {"ok": False, "error": str} only when KENN itself is unavailable.
    """
    question = str(question or "").strip()
    if not question:
        return {"ok": False, "error": "A question is required."}

    context = build_mix_review_context_for_project(project_id)

    _ensure_kenn_importable()
    try:
        from kenn.core.chat_answer import answer_payload
        from kenn.server_payloads import mix_review_context_turn
    except Exception as exc:
        return {"ok": False, "error": f"KENN is not available in-process: {exc}"}

    history: list = []
    if context:
        turn = mix_review_context_turn(context)
        if turn:
            history.append(turn)

    try:
        payload = answer_payload(question, limit=5, history=history)
    except Exception as exc:
        return {"ok": False, "error": f"KENN failed to answer: {exc}"}

    return {
        "ok": True,
        "answer": payload.get("answer", ""),
        "grounded": bool(context),
        "grounding": payload.get("grounding"),
    }
