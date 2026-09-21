"""KENN LM system-prompt context formatting and error-payload sanitization
for kenn/server.py.

Extracted 2026-07-14 as part of decomposing server.py (1,163 lines,
docs/codebase_scan_12_07.md §2.2 "large un-decomposed files"). Pure,
stateless functions -- no test monkeypatches these as replaceable values
(only calls them directly), so this is a plain extraction with no
monkeypatch-copy-semantics risk (see the llm_improvement.py decomposition,
same session, for what that risk looks like and how to fix it when it
does apply).
"""

from __future__ import annotations

import json

from kenn.core.audiogen_artifacts import safe_artifact_metadata


def safe_error_payload(status: int, payload: dict, error_id: str) -> dict:
    if status < 500:
        return payload
    safe = {key: value for key, value in payload.items() if key not in {"error", "traceback", "path"}}
    safe.update({
        "error": "The request could not be completed.",
        "error_code": str(payload.get("error_code") or "internal_error"),
        "retryable": bool(payload.get("retryable", False)),
        "error_id": error_id,
    })
    return safe


def _format_eq_band_moves(eq_bands: object, limit: int = 4) -> str:
    """Render comparison.eq_bands (the same constrained parametric-EQ solve
    mix_doctor.py's HTML report shows as "Boost/Reduce X dB around Y Hz")
    into a short, human-readable string for the chat context.

    Found live 2026-08-06 (Phase 5, docs/KENN_HUB_UNIFICATION_PLAN_2026-08-05.md):
    the chat follow-up path had a summary of the comparison (rms/crest/width
    deltas, single largest-difference band) but never the actual concrete
    move list the visual report shows -- so asking KENN "what EQ moves
    should I make vs. my reference" got a vaguer answer than the report the
    user was looking at. This mirrors mix_doctor.py's own wording/threshold
    exactly so the two surfaces agree.
    """
    if not isinstance(eq_bands, list):
        return ""
    moves: list[str] = []
    for band in eq_bands:
        if not isinstance(band, dict):
            continue
        try:
            freq = float(band.get("freq"))
            gain = float(band.get("gain"))
        except (TypeError, ValueError):
            continue
        if abs(gain) < 0.5:
            continue
        verb = "Boost" if gain > 0 else "Reduce"
        moves.append(f"{verb} {abs(gain):.1f} dB around {freq:.0f} Hz")
        if len(moves) >= limit:
            break
    return " | ".join(moves)


def _retrieve_approved_genre_evidence() -> str | None:
    """Return an exact approved-source citation id for genre classification,
    or None to abstain.

    Mirrors kenn_advisor.py::_retrieve_approved_evidence's rigor (exact
    source + "Status: Approved" required, not just "something relevant
    turned up") rather than inventing a looser bar for this one call site.
    Deliberately narrower in scope than that function: genre classification
    (report["mix_style"]["genre"]) is grounded here because it's a real,
    coded lookup table (GENRE_SEED_PROFILES); the EQ move list
    (comparison.eq_bands, formatted by _format_eq_band_moves above) stays
    unlabelled by design -- it's solved against the specific uploaded
    reference track, not any genre convention, so grounding it in a genre
    note would misrepresent where the numbers came from (see
    reference-track-genre-archetypes.md's own "Common mistakes" section).
    """
    try:
        from kenn.core.chat_constants import CHUNKS_PATH
        from kenn.core.chat_retrieval import load_chunks, load_terms, search
        from kenn.retrieval.index_store import active_version_id

        results = search(
            "genre archetype classification spectral tonal balance confidence",
            load_chunks(),
            load_terms(),
            limit=5,
        )
        index_version = active_version_id(CHUNKS_PATH.parent)
    except Exception:
        return None
    if not index_version:
        return None
    for score, chunk in results:
        if chunk.get("source") != "reference-track-genre-archetypes.md":
            continue
        if "Status: Approved" not in str(chunk.get("text", "")):
            continue
        chunk_id = str(chunk.get("id", "")).strip()
        if not chunk_id or not (isinstance(score, (int, float)) and score > 0):
            continue
        return f"{chunk_id}@index:{index_version}"
    return None


def _format_genre_classification(mix_style: object) -> str:
    """Render report["mix_style"]["genre"] as a grounded classification
    line, or "" to abstain (no confident classification, or no approved
    source could be retrieved to back the claim -- see
    _retrieve_approved_genre_evidence)."""
    if not isinstance(mix_style, dict):
        return ""
    genre = mix_style.get("genre")
    if not isinstance(genre, dict):
        return ""
    name = str(genre.get("genre_name", "")).strip()
    confidence = genre.get("confidence")
    if not name or name == "Uncategorised" or not isinstance(confidence, (int, float)):
        return ""
    evidence_id = _retrieve_approved_genre_evidence()
    if not evidence_id:
        return ""
    return f"{name}-leaning ({confidence * 100:.0f}% confidence, source: {evidence_id})"


def mix_review_context_turn(context: dict | None) -> dict | None:
    if not isinstance(context, dict):
        return None
    if context.get("schema") == "kenn_mix_review_handoff.v1":
        lines = [str(line).strip() for line in context.get("context_lines") or [] if str(line).strip()]
        title = str(context.get("title", "Uploaded mix")).strip()[:120] or "Uploaded mix"
        if not lines:
            lines = [
                f"Mix Review Lab context for {title}.",
                str(context.get("context", "")).strip(),
            ]
        lines.insert(1, "Use this structured uploaded-track analysis before general retrieval notes.")
        session_context = context.get("session_context") if isinstance(context.get("session_context"), dict) else {}
        mix_goal_label = str(context.get("mix_goal_label") or session_context.get("mix_goal_label") or "").strip()
        session_goal = str(context.get("session_goal") or session_context.get("session_goal") or "").strip()
        if mix_goal_label:
            lines.append(f"Selected mix target: {mix_goal_label[:160]}")
        if session_goal:
            lines.append(f"Session goal: {session_goal[:300]}")
        metrics = context.get("metrics") if isinstance(context.get("metrics"), dict) else {}
        if metrics:
            lines.append(
                "Structured metrics: "
                + ", ".join(
                    f"{key.replace('_', ' ')}={value}"
                    for key, value in metrics.items()
                    if value not in {None, ""}
                )
            )
        flags = context.get("flags") if isinstance(context.get("flags"), list) else []
        if flags:
            lines.append(
                "Structured flags: "
                + " | ".join(
                    f"{item.get('severity', 'check')} {item.get('label', '')}: {item.get('detail', '')}".strip()
                    for item in flags[:6]
                    if isinstance(item, dict)
                )
            )
        actions = context.get("priority_actions") if isinstance(context.get("priority_actions"), list) else []
        if actions:
            lines.append(
                "Structured priority actions: "
                + " | ".join(
                    (
                        f"#{item.get('rank', '?')} {item.get('decision', 'check')} "
                        f"({item.get('confidence', 'unknown')} confidence) "
                        f"{item.get('focus', 'Action')}: {item.get('action', '')}"
                    )
                    for item in actions[:6]
                    if isinstance(item, dict)
                )
            )
        judgment = context.get("judgment") if isinstance(context.get("judgment"), dict) else {}
        if judgment:
            lines.append(f"Structured judgment: {json.dumps(judgment, ensure_ascii=False)[:1400]}")
        technical = context.get("technical_metrics") if isinstance(context.get("technical_metrics"), dict) else {}
        section_highlights = context.get("section_highlights") if isinstance(context.get("section_highlights"), dict) else {}
        if technical:
            compact_technical = {
                key: technical.get(key)
                for key in (
                    "peak_dbfs",
                    "true_peak_dbfs",
                    "integrated_lufs",
                    "crest_factor_db",
                    "stereo_correlation",
                    "duration_seconds",
                )
                if technical.get(key) not in {None, ""}
            }
            if compact_technical:
                lines.append(f"Objective technical metrics: {json.dumps(compact_technical, ensure_ascii=False)}")
        if section_highlights:
            lines.append(f"Structured section highlights: {json.dumps(section_highlights, ensure_ascii=False)[:1400]}")
        repairs = context.get("ableton_repair_templates") if isinstance(context.get("ableton_repair_templates"), list) else []
        if repairs:
            lines.append(
                "Structured Ableton repairs: "
                + " | ".join(
                    f"{item.get('flag', 'Repair')}: {item.get('device_chain', '')} -> {item.get('move', '')}"
                    for item in repairs[:6]
                    if isinstance(item, dict)
                )
            )
        steps = context.get("revision_steps") if isinstance(context.get("revision_steps"), list) else []
        if steps:
            lines.append(
                "Structured revision checklist: "
                + " | ".join(
                    f"{item.get('focus', 'Step')}: {item.get('action', '')}"
                    for item in steps[:6]
                    if isinstance(item, dict)
                )
            )
        reference = context.get("reference") if isinstance(context.get("reference"), dict) else {}
        if reference:
            lines.append(f"Structured reference context: {json.dumps(reference, ensure_ascii=False)[:1200]}")
        reference_comparison = context.get("reference_comparison") if isinstance(context.get("reference_comparison"), dict) else {}
        if reference_comparison:
            lines.append(f"Structured reference comparison: {json.dumps(reference_comparison, ensure_ascii=False)[:1200]}")
            eq_moves = _format_eq_band_moves(reference_comparison.get("eq_bands"))
            if eq_moves:
                lines.append(f"Structured reference EQ moves: {eq_moves}")
        genre_line = _format_genre_classification(context.get("mix_style"))
        if genre_line:
            lines.append(f"Structured genre classification: {genre_line}")
        leave_alone = [str(item).strip() for item in context.get("leave_alone") or [] if str(item).strip()][:6]
        if leave_alone:
            lines.append("Structured leave alone: " + " | ".join(leave_alone))
        version = {
            "previous_version": context.get("previous_version"),
            "version_comparison": context.get("version_comparison"),
            "version_advice": context.get("version_advice"),
            "revision_impact": context.get("revision_impact"),
        }
        if any(version.values()):
            lines.append(f"Structured revision context: {json.dumps(version, ensure_ascii=False)[:1200]}")
        revision_plan = context.get("next_revision_plan") if isinstance(context.get("next_revision_plan"), dict) else {}
        if revision_plan:
            focus = str(revision_plan.get("focus", "")).strip()
            if focus:
                lines.append(f"Structured next revision focus: {focus}")
            plan_steps = [
                f"{item.get('focus', 'Step')}: {item.get('action', '')}"
                for item in revision_plan.get("steps") or []
                if isinstance(item, dict) and str(item.get("action", "")).strip()
            ][:6]
            if plan_steps:
                lines.append("Structured next revision steps: " + " | ".join(plan_steps))
            checks = [str(item).strip() for item in revision_plan.get("checks") or [] if str(item).strip()][:4]
            if checks:
                lines.append("Structured next revision checks: " + " | ".join(checks))
        return {"role": "user", "content": "\n".join(line for line in lines if line)}
    title = str(context.get("title", "Uploaded mix")).strip()[:120] or "Uploaded mix"
    summary = str(context.get("summary", "")).strip()
    flags = [str(item).strip() for item in context.get("flags") or [] if str(item).strip()][:8]
    actions = [str(item).strip() for item in context.get("actions") or [] if str(item).strip()][:6]
    metric_keys = (
        "technical_score",
        "technical_rating",
        "peak_dbfs",
        "rms_dbfs_estimate",
        "crest_factor_db",
        "dominant_band",
    )
    metrics = {
        key: context.get(key)
        for key in metric_keys
        if context.get(key) not in {None, ""}
    }
    if not summary and not flags and not actions and not metrics:
        return None
    lines = [
        f"Mix Review Lab context for {title}.",
        "Use this uploaded-track analysis when the user asks follow-up questions about their mix.",
    ]
    if summary:
        lines.append(f"Review summary: {summary[:900]}")
    if metrics:
        lines.append(
            "Metrics: "
            + ", ".join(f"{key.replace('_', ' ')}={value}" for key, value in metrics.items())
        )
    if flags:
        lines.append("Flags: " + ", ".join(flags))
    if actions:
        lines.append("Priority actions: " + " | ".join(actions))
    session_context = context.get("session_context") if isinstance(context.get("session_context"), dict) else {}
    mix_goal_label = str(context.get("mix_goal_label") or session_context.get("mix_goal_label") or "").strip()
    session_goal = str(context.get("session_goal") or session_context.get("session_goal") or "").strip()
    if mix_goal_label:
        lines.append(f"Selected mix target: {mix_goal_label[:160]}")
    if session_goal:
        lines.append(f"Session goal: {session_goal[:300]}")
    leave_alone = [str(item).strip() for item in context.get("leave_alone") or [] if str(item).strip()][:6]
    if leave_alone:
        lines.append("Leave alone: " + " | ".join(leave_alone))
    repairs = context.get("ableton_repair_templates") if isinstance(context.get("ableton_repair_templates"), list) else []
    if repairs:
        lines.append(
            "Ableton repair templates: "
            + " | ".join(
                f"{item.get('flag', 'Repair')}: {item.get('device_chain', '')} -> {item.get('move', '')}"
                for item in repairs[:6]
                if isinstance(item, dict)
            )
        )
    revision_agent = context.get("revision_agent") if isinstance(context.get("revision_agent"), dict) else {}
    revision_steps = [
        str((step or {}).get("action", "")).strip()
        for step in revision_agent.get("steps") or []
        if isinstance(step, dict) and str(step.get("action", "")).strip()
    ][:6]
    if revision_agent.get("goal"):
        lines.append(f"Revision agent goal: {str(revision_agent.get('goal'))[:240]}")
    if revision_steps:
        lines.append("Revision agent checklist: " + " | ".join(revision_steps))
    previous = context.get("previous_version") if isinstance(context.get("previous_version"), dict) else {}
    version_comparison = context.get("version_comparison") if isinstance(context.get("version_comparison"), dict) else {}
    version_advice = [
        str(item).strip()
        for item in context.get("version_advice") or []
        if str(item).strip()
    ][:5]
    if previous:
        previous_label = str(previous.get("version_label") or previous.get("created_at") or "previous version").strip()
        lines.append(f"Previous version: {previous_label[:160]}")
    if version_comparison:
        compact_version = []
        for key in ("rms_delta_db", "crest_delta_db", "stereo_width_delta"):
            if version_comparison.get(key) not in {None, ""}:
                compact_version.append(f"{key.replace('_', ' ')}={version_comparison[key]}")
        spectral = version_comparison.get("largest_spectral_difference")
        if isinstance(spectral, dict) and spectral.get("band"):
            compact_version.append(
                "largest version spectral change="
                f"{spectral.get('band')} ({spectral.get('delta_db', spectral.get('delta'))})"
            )
        if compact_version:
            lines.append("Version comparison: " + ", ".join(compact_version))
    if version_advice:
        lines.append("Version advice: " + " | ".join(version_advice))
    revision_impact = context.get("revision_impact") if isinstance(context.get("revision_impact"), dict) else {}
    if revision_impact:
        lines.append(f"Revision impact verdict: {str(revision_impact.get('verdict', 'mixed'))[:80]}")
        for label, key in (
            ("Revision improvements", "improvements"),
            ("Revision regressions", "regressions"),
            ("Revision checks", "checks"),
        ):
            items = [
                str(item).strip()
                for item in revision_impact.get(key) or []
                if str(item).strip()
            ][:4]
            if items:
                lines.append(f"{label}: " + " | ".join(items))
    reference_filename = str(context.get("reference_filename", "")).strip()
    comparison = context.get("reference_comparison") if isinstance(context.get("reference_comparison"), dict) else {}
    comparison_advice = [
        str(item).strip()
        for item in context.get("comparison_advice") or []
        if str(item).strip()
    ][:5]
    if reference_filename:
        lines.append(f"Reference WAV: {reference_filename[:160]}")
    if comparison:
        compact = []
        for key in ("rms_delta_db", "crest_delta_db", "stereo_width_delta"):
            if comparison.get(key) not in {None, ""}:
                compact.append(f"{key.replace('_', ' ')}={comparison[key]}")
        spectral = comparison.get("largest_spectral_difference")
        if isinstance(spectral, dict) and spectral.get("band"):
            spectral_delta = spectral.get("delta_db", spectral.get("delta"))
            compact.append(
                "largest spectral difference="
                f"{spectral.get('band')} ({spectral_delta})"
            )
        perceptual = comparison.get("largest_perceptual_difference")
        if isinstance(perceptual, dict) and perceptual.get("band"):
            perceptual_delta = perceptual.get("delta_db", perceptual.get("delta"))
            compact.append(
                "largest perceptual difference="
                f"{perceptual.get('band')} ({perceptual_delta})"
            )
        if compact:
            lines.append("Reference comparison: " + ", ".join(compact))
        eq_moves = _format_eq_band_moves(comparison.get("eq_bands"))
        if eq_moves:
            lines.append(f"Reference EQ moves: {eq_moves}")
    if comparison_advice:
        lines.append("Reference advice: " + " | ".join(comparison_advice))
    genre_line = _format_genre_classification(context.get("mix_style"))
    if genre_line:
        lines.append(f"Genre classification: {genre_line}")
    return {"role": "user", "content": "\n".join(lines)}


def session_context_turn(context: dict | None) -> dict | None:
    if not isinstance(context, dict):
        return None
    mix_goal = str(context.get("mix_goal", "")).strip()
    mix_goal_label = str(context.get("mix_goal_label", "")).strip()
    session_goal = str(context.get("session_goal", "")).strip()
    if not mix_goal and not mix_goal_label and not session_goal:
        return None
    lines = ["Session context for this KENN conversation."]
    if mix_goal or mix_goal_label:
        lines.append(f"Mix target: {mix_goal_label or mix_goal} ({mix_goal or 'unspecified'}).")
    if session_goal:
        lines.append(f"User goal: {session_goal[:300]}.")
    lines.append("Use this context to make advice more specific, but keep source grounding rules.")
    return {"role": "user", "content": "\n".join(lines)}


def public_audiogen_result(result: dict | None) -> dict | None:
    if not isinstance(result, dict):
        return None
    entry = result.get("portfolio_entry") if isinstance(result.get("portfolio_entry"), dict) else {}
    return {
        "ok": bool(result.get("ok")),
        "emotion": result.get("emotion", ""),
        "bars": result.get("bars", ""),
        "k": result.get("k", ""),
        "src": result.get("src", ""),
        "portfolio_title": entry.get("title", ""),
        "artifact": safe_artifact_metadata(result.get("artifact")) if isinstance(result.get("artifact"), dict) else None,
        "error": result.get("error", ""),
    }


def public_audiogen_job(job: dict | None) -> dict | None:
    if not isinstance(job, dict):
        return None
    return {
        "id": job.get("id", ""),
        "status": job.get("status", ""),
        "emotion": job.get("emotion", ""),
        "bars": job.get("bars", ""),
        "k": job.get("k", ""),
        "progress": job.get("progress", 0),
        "message": job.get("message", ""),
        "created_at": job.get("created_at", ""),
        "started_at": job.get("started_at", ""),
        "finished_at": job.get("finished_at", ""),
        "result": public_audiogen_result(job.get("result")),
        "error": job.get("error", ""),
    }


def public_audiogen_status(status: dict) -> dict:
    queue = status.get("render_queue") if isinstance(status.get("render_queue"), dict) else {}
    return {
        "ok": bool(status.get("ok")),
        "has_full_render": bool(status.get("has_full_render")),
        "portfolio_audio_count": status.get("portfolio_audio_count", 0),
        "emotions": status.get("emotions", []),
        "render_queue": {
            "running": [public_audiogen_job(job) for job in queue.get("running", []) if isinstance(job, dict)],
            "queued": [public_audiogen_job(job) for job in queue.get("queued", []) if isinstance(job, dict)],
            "recent": [public_audiogen_job(job) for job in queue.get("recent", [])[:8] if isinstance(job, dict)],
        },
        "render_history_count": status.get("render_history_count", 0),
    }


def public_audiogen_history(items: list[dict]) -> list[dict]:
    return [
        {
            "id": item.get("id", ""),
            "kind": item.get("kind", ""),
            "emotion": item.get("emotion", ""),
            "bars": item.get("bars", ""),
            "src": item.get("src", ""),
            "portfolio_title": item.get("portfolio_title", ""),
            "created_at": item.get("created_at", ""),
        }
        for item in items
        if isinstance(item, dict)
    ]
