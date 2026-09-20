"""KENN handoff payloads for Mix Review Lab reports."""

from __future__ import annotations


def _measured_analysis_evidence(report: dict) -> dict:
    """Select compact *measurements* from optional deeper analyses.

    This deliberately excludes generated carving suggestions and critique
    prose.  KENN can use these values to select a discriminating test, but
    must not present a stem-analysis estimate as proof of a mix cause.
    """
    evidence: dict = {}
    transient = report.get("transient_preservation")
    if isinstance(transient, dict):
        score = transient.get("preservation_score")
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            evidence["transient_preservation"] = {
                "score": float(score),
                "matched_event_count": transient.get("matched_event_count"),
                "profile": str(transient.get("profile") or ""),
            }
    masking = report.get("stem_masking")
    if isinstance(masking, dict) and masking.get("ok") and isinstance(masking.get("stems"), list):
        candidates = [
            item for item in masking["stems"]
            if isinstance(item, dict) and isinstance(item.get("overall_visibility"), (int, float))
        ]
        if candidates:
            lowest = min(candidates, key=lambda item: float(item["overall_visibility"]))
            evidence["stem_masking"] = {
                "stem_count": len(candidates),
                "lowest_visibility": float(lowest["overall_visibility"]),
                "lowest_visibility_stem": str(lowest.get("name") or "stem"),
            }
    stem_solo = report.get("stem_solo")
    if isinstance(stem_solo, dict):
        low_end = stem_solo.get("low_end_summary")
        ranked = low_end.get("ranked") if isinstance(low_end, dict) else None
        if isinstance(ranked, list):
            measured = [
                {"name": str(item.get("name") or "stem"), "low_end_share": float(item["low_end_share"])}
                for item in ranked[:2]
                if isinstance(item, dict) and isinstance(item.get("low_end_share"), (int, float))
            ]
            if measured:
                evidence["low_end_stems"] = measured
    return evidence


def kenn_handoff(report: dict) -> dict:
    """Build a compact chat context for KENN follow-up questions."""
    metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else {}
    flags = report.get("flags") if isinstance(report.get("flags"), list) else []
    actions = report.get("action_plan") if isinstance(report.get("action_plan"), list) else []
    repairs = report.get("ableton_repair_templates") if isinstance(report.get("ableton_repair_templates"), list) else []
    revision_agent = report.get("revision_agent") if isinstance(report.get("revision_agent"), dict) else {}
    revision_steps = [
        {
            "focus": str(step.get("focus", "")).strip(),
            "action": str(step.get("action", "")).strip(),
            "why": str(step.get("why", "")).strip(),
            "status": str(step.get("status", "todo")).strip() or "todo",
        }
        for step in revision_agent.get("steps", [])[:6]
        if isinstance(step, dict) and str(step.get("action", "")).strip()
    ]
    title = str(report.get("title") or metrics.get("filename") or "uploaded mix").strip()
    mix_goal = metrics.get("mix_goal") if isinstance(metrics.get("mix_goal"), dict) else {}
    perceptual = metrics.get("perceptual_summary") if isinstance(metrics.get("perceptual_summary"), dict) else {}
    technical_metrics = report.get("technical_metrics") if isinstance(report.get("technical_metrics"), dict) else {}
    judgment = report.get("judgment") if isinstance(report.get("judgment"), dict) else {}
    section_analysis = technical_metrics.get("section_analysis") or metrics.get("section_analysis")
    section_highlights = section_analysis.get("highlights", {}) if isinstance(section_analysis, dict) else {}
    flag_payload = [
        {
            "label": str(flag.get("label", "")).strip(),
            "severity": str(flag.get("severity", "")).strip(),
            "detail": str(flag.get("detail", "")).strip(),
            "confidence": str(flag.get("confidence", "")).strip(),
            "confidence_reason": str(flag.get("confidence_reason", "")).strip(),
        }
        for flag in flags[:6]
        if isinstance(flag, dict) and str(flag.get("label", "")).strip()
    ]
    action_payload = [
        {
            "rank": item.get("rank"),
            "decision": str(item.get("decision", "")).strip(),
            "priority": str(item.get("priority", "")).strip(),
            "confidence": str(item.get("confidence", "")).strip(),
            "focus": str(item.get("focus", item.get("title", ""))).strip(),
            "action": str(item.get("action", "")).strip(),
            "reason": str(item.get("reason", "")).strip(),
        }
        for item in actions[:6]
        if isinstance(item, dict) and str(item.get("action", "")).strip()
    ]
    comparison = report.get("comparison") if isinstance(report.get("comparison"), dict) else {}
    version_comparison = report.get("version_comparison") if isinstance(report.get("version_comparison"), dict) else {}
    reference = report.get("reference") if isinstance(report.get("reference"), dict) else {}
    revision_impact = report.get("revision_impact") if isinstance(report.get("revision_impact"), dict) else {}
    revision_plan = report.get("next_revision_plan") if isinstance(report.get("next_revision_plan"), dict) else {}
    closed_loop = report.get("closed_loop_action_plan") if isinstance(report.get("closed_loop_action_plan"), dict) else {}
    repair_chains = report.get("ableton_repair_chains") if isinstance(report.get("ableton_repair_chains"), dict) else {}
    session_report = report.get("session_report") if isinstance(report.get("session_report"), dict) else {}
    analysis_evidence = _measured_analysis_evidence(report)
    metric_payload = {
        "technical_score": metrics.get("technical_score"),
        "technical_rating": metrics.get("technical_rating", ""),
        "peak_dbfs": metrics.get("peak_dbfs"),
        "rms_dbfs_estimate": metrics.get("rms_dbfs_estimate"),
        "crest_factor_db": metrics.get("crest_factor_db"),
        "integrated_lufs": metrics.get("integrated_lufs"),
        "true_peak_dbfs": metrics.get("true_peak_dbfs"),
        "stereo_correlation": metrics.get("stereo_correlation"),
        "dominant_band": perceptual.get("dominant_band", ""),
        "mix_goal": mix_goal.get("label", mix_goal.get("key", "")),
    }
    flag_text = ", ".join(item["label"] for item in flag_payload)
    action_text = "; ".join(
        f"#{item.get('rank') or '?'} {item.get('decision') or 'check'} {item['focus']}: {item['action']}"
        for item in action_payload
    )
    repair_payload = [
        {
            "flag": str(item.get("flag", "")).strip(),
            "severity": str(item.get("severity", "")).strip(),
            "device_chain": str(item.get("device_chain", "")).strip(),
            "move": str(item.get("move", "")).strip(),
            "target": str(item.get("target", "")).strip(),
            "check": str(item.get("check", "")).strip(),
        }
        for item in repairs[:6]
        if isinstance(item, dict) and str(item.get("move", "")).strip()
    ]
    repair_text = "; ".join(
        f"{item['flag']}: {item['device_chain']} -> {item['move']}"
        for item in repair_payload
    )
    perceived_bands = metrics.get("perceptual_bands") or {}
    perceived_text = ", ".join(f"{k}: {v:.1%}" for k, v in perceived_bands.items())

    context_lines = [
        f"Mix Review Lab context for {title}.",
        f"Summary: {report.get('summary', 'No summary available.')}",
        "Metrics: "
        + ", ".join(
            f"{key.replace('_', ' ')}={value}"
            for key, value in metric_payload.items()
            if value not in {None, ""}
        ),
        f"Flags: {flag_text or 'none'}",
        f"Priority actions: {action_text or 'none'}",
    ]
    if perceived_text:
        context_lines.append(f"Perceived loudness shares (Fletcher-Munson): {perceived_text}")
    if repair_text:
        context_lines.append(f"Ableton repair templates: {repair_text}")
    if section_highlights:
        loudest = section_highlights.get("loudest_section") or {}
        low_corr = section_highlights.get("lowest_correlation_section") or {}
        jump = section_highlights.get("biggest_loudness_jump") or {}
        context_lines.append(
            "Section highlights: "
            f"loudest={loudest.get('label', 'n/a')} at {loudest.get('rms_dbfs', 'n/a')} dBFS RMS; "
            f"lowest correlation={low_corr.get('label', 'n/a')} at {low_corr.get('stereo_correlation', 'n/a')}; "
            f"biggest jump={jump.get('delta_db', 'n/a')} dB."
        )
    if reference:
        context_lines.append(f"Reference: {reference.get('name') or reference.get('filename') or 'uploaded reference'}")
    if comparison:
        context_lines.append(
            "Reference deltas: "
            + ", ".join(
                f"{key.replace('_', ' ')}={comparison.get(key)}"
                for key in ("rms_delta_db", "crest_delta_db", "stereo_width_delta")
                if comparison.get(key) not in {None, ""}
            )
        )
    if version_comparison:
        context_lines.append(
            "Version deltas: "
            + ", ".join(
                f"{key.replace('_', ' ')}={version_comparison.get(key)}"
                for key in ("rms_delta_db", "crest_delta_db", "stereo_width_delta")
                if version_comparison.get(key) not in {None, ""}
            )
        )
    if revision_impact:
        context_lines.append(f"Revision impact: {revision_impact.get('verdict', 'mixed')}")
    if revision_plan:
        context_lines.append(f"Next revision focus: {revision_plan.get('focus', '')}")
        plan_steps = [
            f"{step.get('focus', 'Step')}: {step.get('action', '')}"
            for step in revision_plan.get("steps", [])[:4]
            if isinstance(step, dict) and str(step.get("action", "")).strip()
        ]
        if plan_steps:
            context_lines.append("Next revision steps: " + " | ".join(plan_steps))
    if closed_loop:
        context_lines.append(f"Closed-loop primary focus: {closed_loop.get('primary_focus', '')}")
    if repair_chains.get("chains"):
        chain_names = [
            str(chain.get("name", "")).strip()
            for chain in repair_chains.get("chains", [])[:4]
            if isinstance(chain, dict) and str(chain.get("name", "")).strip()
        ]
        if chain_names:
            context_lines.append("Ableton repair chains: " + ", ".join(chain_names))
    memory_lines = [
        str(line).strip()
        for line in session_report.get("kenn_memory_lines", [])
        if str(line).strip()
    ][:8]
    if memory_lines:
        context_lines.append("Session report memory: " + " | ".join(memory_lines))
        
    fm_info = f" Perceived focus is {perceptual.get('dominant_band', 'n/a')}."
    if perceived_text:
        fm_info += f" Perceived loudness shares (Fletcher-Munson): {perceived_text}."
        
    context = (
        f"Mix Review Lab context for {title}.\n"
        f"Technical score: {metrics.get('technical_score', 'unknown')}/100. "
        f"Peak: {metrics.get('peak_dbfs', 'n/a')} dBFS. "
        f"RMS estimate: {metrics.get('rms_dbfs_estimate', 'n/a')} dBFS. "
        f"Crest factor: {metrics.get('crest_factor_db', 'n/a')} dB.{fm_info}\n"
        f"Summary: {report.get('summary', 'No summary available.')}\n"
        f"Flags: {flag_text or 'none'}.\n"
        f"Priority actions: {action_text or 'none'}."
    )
    return {
        "schema": "kenn_mix_review_handoff.v1",
        "title": title,
        "review_summary": str(report.get("summary", "")).strip(),
        "metrics": metric_payload,
        "technical_metrics": technical_metrics,
        "judgment": judgment,
        "section_highlights": section_highlights,
        "flags": flag_payload,
        "priority_actions": action_payload,
        "ableton_repair_templates": repair_payload,
        "revision_steps": revision_steps,
        "reference": {
            "name": reference.get("name", ""),
            "filename": reference.get("filename", ""),
            "comparison": comparison,
            "advice": report.get("comparison_advice", [])[:5],
        } if reference or comparison else {},
        # Also flat, matching server_payloads.py::mix_review_context_turn()'s
        # read shape (context.get("reference_comparison")) -- the nested
        # "reference"."comparison" key above is this function's own
        # long-standing shape, but the reader never looked there, so
        # comparison.eq_bands (the "Boost/Reduce X dB around Y Hz" moves)
        # never actually reached chat for a review sent through this handoff
        # despite the 2026-08-06 fix intending exactly that. Found by tracing
        # the real app.js -> server round trip rather than trusting the
        # synthetic test that fed the reader its expected shape directly.
        "reference_comparison": comparison,
        "reference_filename": reference.get("filename", ""),
        "comparison_advice": report.get("comparison_advice", [])[:5],
        "mix_style": report.get("mix_style") if isinstance(report.get("mix_style"), dict) else {},
        "previous_version": report.get("previous_version") if isinstance(report.get("previous_version"), dict) else {},
        "version_comparison": version_comparison,
        "version_advice": report.get("version_advice", [])[:5],
        "revision_impact": revision_impact,
        "next_revision_plan": revision_plan,
        "closed_loop_action_plan": closed_loop,
        "ableton_repair_chains": repair_chains,
        "session_report": session_report,
        "analysis_evidence": analysis_evidence,
        "context_lines": context_lines,
        "context": context,
        "prompt": "Based on this Mix Review Lab analysis, what are the first three mix fixes I should make?",
        "summary": f"Send this context to KENN to turn the analysis for {title} into practical mix moves.",
    }
