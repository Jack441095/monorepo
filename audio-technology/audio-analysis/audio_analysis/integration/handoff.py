"""KENN handoff payloads for Mix Review Lab reports."""

from __future__ import annotations

import math
import json
from copy import deepcopy


def transient_preservation_evidence(transient: dict) -> dict:
    """Project qualified pre/post measurements, or retain an abstention marker."""
    activity = transient.get("activity")
    if not isinstance(activity, dict) or activity.get("schema") != "kenn.transient_preservation.activity.v1":
        # Older results do not establish activity before peak normalization.
        return {}
    levels = {}
    for name in ("pre_rms_dbfs", "post_rms_dbfs"):
        value = activity.get(name)
        try:
            value = float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None
        except OverflowError:
            # Unrepresentable values cannot qualify a source for publication.
            return {}
        if value is None or not math.isfinite(value) or value <= -60.0:
            # Both original renders must exceed the uploaded-source -60 dBFS floor.
            return {}
        levels[name] = value
    count = transient.get("matched_event_count")
    score = transient.get("preservation_score")
    profile = transient.get("profile")
    try:
        score = float(score) if isinstance(score, (int, float)) and not isinstance(score, bool) else None
    except OverflowError:
        # An overflowing scalar is not a bounded preservation score.
        return {}
    if not isinstance(count, int) or isinstance(count, bool) or count <= 0 or score is None or not math.isfinite(score) or not 0.0 <= score <= 1.0 or not isinstance(profile, str) or not profile.strip():
        # No matched events or malformed summaries cannot support a transient claim.
        return {}
    # 160 characters retain the short profile label without copying cached prose.
    return {
        "score": score, "matched_event_count": count, "profile": profile.strip()[:160],
        "activity": {"schema": "kenn.transient_preservation.activity.v1", **levels},
    }


# Keep the existing private entry point for older integration callers.
_transient_preservation_evidence = transient_preservation_evidence


def qualified_stem_masking_summary(summary: object) -> dict[str, object] | None:
    """Return bounded ERB preview evidence backed by jointly active source frames."""
    if not isinstance(summary, dict):
        # Legacy visibility scalars do not establish which real audio was compared.
        return None
    activity = summary.get("activity")
    if (
        not isinstance(activity, dict) or activity.get("schema") != "kenn.erb_masking.activity.v1"
        or activity.get("active_floor_dbfs") != -60.0 or activity.get("frame_size_samples") != 4096
    ):
        # The proof describes the existing 4096-sample preview and -60 dBFS RMS floor.
        return None
    sources = activity.get("sources")
    pairs = activity.get("pairs")
    if (
        not isinstance(sources, list) or not 2 <= len(sources) <= 64
        or not isinstance(pairs, list) or not pairs
        or len(pairs) > len(sources) * (len(sources) - 1) // 2
    ):
        # Bound replay to 64 source identities and one entry per unordered pair.
        return None
    normalized_sources = []
    by_name = {}
    for source in sources:
        if not isinstance(source, dict):
            # A malformed source cannot be matched safely to a measured pair.
            return None
        name, rate = source.get("name"), source.get("sample_rate")
        count, active = source.get("frame_count"), source.get("active_frame_count")
        try:
            rate = float(rate) if isinstance(rate, (int, float)) and not isinstance(rate, bool) else None
        except OverflowError:
            # Unrepresentable rates cannot establish aligned preview frames.
            return None
        if (
            not isinstance(name, str) or not name.strip() or name != name.strip()
            or len(name) > 96 or name in by_name
            or rate is None or not math.isfinite(rate) or rate <= 0
            or not isinstance(count, int) or isinstance(count, bool) or not 0 <= count <= 16
            or not isinstance(active, int) or isinstance(active, bool) or not 0 <= active <= count
        ):
            # Exact unique names avoid aliasing; only the first 16 complete frames are measured.
            return None
        normalized = {"name": name, "sample_rate": rate, "frame_count": count, "active_frame_count": active}
        by_name[name] = normalized
        normalized_sources.append(normalized)
    normalized_pairs, seen, paired_names = [], set(), set()
    for pair in pairs:
        names = pair.get("stems") if isinstance(pair, dict) else None
        count = pair.get("simultaneously_active_frame_count") if isinstance(pair, dict) else None
        if (
            not isinstance(names, list) or len(names) != 2
            or not all(isinstance(name, str) and name in by_name for name in names)
            or names[0] == names[1]
        ):
            # Both distinct sources must refer to the exact decoded preview identities.
            return None
        key = tuple(sorted(names))
        first, second = (by_name[name] for name in names)
        if (
            key in seen or first["sample_rate"] != second["sample_rate"]
            or not isinstance(count, int) or isinstance(count, bool)
            or not 0 < count <= min(first["active_frame_count"], second["active_frame_count"])
        ):
            # Unequal frame durations or no shared active frame cannot support masking.
            return None
        seen.add(key)
        paired_names.update(names)
        normalized_pairs.append({"stems": list(names), "simultaneously_active_frame_count": count})
    visibility = summary.get("lowest_visibility")
    name, stem_count = summary.get("lowest_visibility_stem"), summary.get("stem_count")
    try:
        visibility = float(visibility) if isinstance(visibility, (int, float)) and not isinstance(visibility, bool) else None
    except OverflowError:
        # An overflowing value cannot describe a visibility ratio.
        return None
    if (
        visibility is None or not math.isfinite(visibility) or not 0 <= visibility <= 1
        or not isinstance(name, str) or name not in paired_names
        or not isinstance(stem_count, int) or isinstance(stem_count, bool)
        or stem_count != len(paired_names)
    ):
        # The selected visibility must belong to a measured stem, including a valid zero.
        return None
    return {
        "stem_count": stem_count, "lowest_visibility": visibility, "lowest_visibility_stem": name,
        "activity": {"schema": "kenn.erb_masking.activity.v1", "active_floor_dbfs": -60.0,
                     "frame_size_samples": 4096, "sources": normalized_sources, "pairs": normalized_pairs},
    }



def stem_masking_evidence(masking: object) -> dict:
    """Select visibility only from the producer's real jointly active preview group."""
    if not isinstance(masking, dict) or masking.get("ok") is not True or not isinstance(masking.get("stems"), list):
        # Preserve a sentinel so cached critique cannot bypass this abstention.
        return {}
    candidates = masking["stems"]
    if not candidates or not all(isinstance(item, dict) for item in candidates):
        # Empty or malformed stem lists cannot identify a measured minimum.
        return {}
    checked = []
    for item in candidates:
        summary = qualified_stem_masking_summary({"stem_count": len(candidates), "lowest_visibility": item.get("overall_visibility"), "lowest_visibility_stem": item.get("name"), "activity": masking.get("activity")})
        if summary is None:
            # Reject the entire ranking when any candidate lacks matching activity.
            return {}
        checked.append(summary)
    if len({item["lowest_visibility_stem"] for item in checked}) != len(checked):
        # Duplicate identities must not hide a missing participant in the ranking.
        return {}
    return min(checked, key=lambda item: item["lowest_visibility"])


def _low_end_rms_has_activity(value: object) -> bool:
    """Qualify finite raw RMS above the existing -60 dBFS upload floor."""
    try:
        value = float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None
    except OverflowError:
        # Unrepresentable levels cannot qualify a normalized spectrum for publication.
        return False
    return value is not None and math.isfinite(value) and value > -60.0


def qualified_low_end_stems(summary: object) -> list[dict[str, object]]:
    """Copy up to two source-qualified spectrum previews, omitting invalid identities."""
    if not isinstance(summary, list) or not 1 <= len(summary) <= 2:
        # Empty/legacy sections retain an abstention without inventing a measured stem.
        return []
    names = [item.get("name") for item in summary if isinstance(item, dict)]
    qualified = []
    for item in summary:
        if not isinstance(item, dict):
            # Malformed entries do not erase independently qualified stems.
            continue
        name, activity = item.get("name"), item.get("activity")
        if (
            not isinstance(name, str) or not name.strip() or name != name.strip()
            or len(name) > 96 or names.count(name) != 1
        ):
            # Exact unique identities prevent an invalid alias becoming a measured ranking.
            continue
        if (
            not isinstance(activity, dict) or activity.get("schema") != "kenn.low_end_stem.activity.v1"
            or activity.get("active_floor_dbfs") != -60.0
        ):
            # Normalized ratios from older reports lack raw source/window activity proof.
            continue
        if not all(_low_end_rms_has_activity(activity.get(key)) for key in ("source_rms_dbfs", "window_rms_dbfs")):
            # An active full file cannot qualify silence in the actual centered FFT window.
            continue
        count, size, start = (activity.get(key) for key in ("analysis_sample_count", "frame_size_samples", "window_start_sample"))
        if not isinstance(count, int) or isinstance(count, bool) or not 256 <= count <= 2**53 - 1:
            # 256 samples is the existing FFT minimum; JSON transports integers exactly up to 2**53-1.
            continue
        expected_size = 1 << (min(4096, count).bit_length() - 1)
        if (
            not isinstance(size, int) or isinstance(size, bool) or size != expected_size
            or not isinstance(start, int) or isinstance(start, bool) or start != (count - size) // 2
        ):
            # Geometry must describe the existing centered power-of-two FFT, not another active region.
            continue
        rate, share = activity.get("sample_rate"), item.get("low_end_share")
        try:
            rate = float(rate) if isinstance(rate, (int, float)) and not isinstance(rate, bool) else None
            share = float(share) if isinstance(share, (int, float)) and not isinstance(share, bool) else None
        except OverflowError:
            # Unrepresentable scalars cannot qualify a rate or bounded own-spectrum share.
            continue
        if (
            rate is None or not math.isfinite(rate) or rate <= 0
            or share is None or not math.isfinite(share) or not 0 <= share <= 1
        ):
            # A valid zero share is retained; no low-band energy is different from missing audio.
            continue
        qualified.append({
            "name": name, "low_end_share": share,
            "activity": {
                "schema": "kenn.low_end_stem.activity.v1", "active_floor_dbfs": -60.0,
                "source_rms_dbfs": float(activity["source_rms_dbfs"]),
                "window_rms_dbfs": float(activity["window_rms_dbfs"]),
                "sample_rate": rate, "analysis_sample_count": count,
                "frame_size_samples": size, "window_start_sample": start,
            },
        })
    return qualified


def low_end_stems_evidence(stem_solo: object) -> list[dict]:
    """Select two qualified own-spectrum previews without promoting quiet or duplicate identities."""
    low_end = stem_solo.get("low_end_summary") if isinstance(stem_solo, dict) else None
    ranked = low_end.get("ranked") if isinstance(low_end, dict) else None
    if not isinstance(ranked, list):
        # Legacy/malformed sections retain an empty sentinel for cached-prose qualification.
        return []
    names = [item.get("name") for item in ranked if isinstance(item, dict)]
    measured = []
    for item in ranked:
        if not isinstance(item, dict) or names.count(item.get("name")) != 1:
            # An ambiguous name cannot acquire measured status through an unrelated valid entry.
            continue
        measured.extend(qualified_low_end_stems([item]))
        if len(measured) == 2:
            # The chat handoff needs two named previews; rendering can qualify each remaining row.
            break
    return measured


def _measured_analysis_evidence(report: dict) -> dict:
    """Select compact *measurements* from optional deeper analyses.

    This deliberately excludes generated carving suggestions and critique
    prose.  KENN can use these values to select a discriminating test, but
    must not present a stem-analysis estimate as proof of a mix cause.
    """
    evidence: dict = {}
    transient = report.get("transient_preservation")
    if "transient_preservation" in report:
        # Keep an empty section for invalid/legacy results: its presence tells
        # KENN that cached prose may contain an unqualified comparison claim.
        evidence["transient_preservation"] = _transient_preservation_evidence(transient) if isinstance(transient, dict) else {}
    if "stem_masking" in report:
        # Invalid legacy sections still mark cached prose as unqualified.
        evidence["stem_masking"] = stem_masking_evidence(report.get("stem_masking"))
    if "stem_solo" in report:
        # Presence survives abstention so cached low-end prose is requalified by KENN.
        evidence["low_end_stems"] = low_end_stems_evidence(report.get("stem_solo"))
    return evidence


def project_report_publication(report: dict) -> dict:
    """Copy a saved report for publication, rebuilding prose with unqualified inputs.

    Cached narratives mix several analyses without per-sentence provenance.
    When one optional analysis fails qualification we retain independent numeric
    measurements and qualified optional sections, but cannot retain that prose.
    This projection never decodes audio, calls a model, or changes the saved report.
    """
    projected = deepcopy(report)
    limitation = "Optional comparison prose withheld: source activity or preview scope is unqualified."
    rebuild = limitation in (projected.get("publication_limitations") or [])
    qualified = set()
    for container in (projected, projected.get("metrics")):
        if not isinstance(container, dict):
            # Older reports may omit the metrics container entirely.
            continue
        if "transient_preservation" in container:
            raw = container["transient_preservation"]
            safe = transient_preservation_evidence(raw) if isinstance(raw, dict) else {}
            if safe:
                if container is projected or "transient_preservation" not in projected:
                    qualified.add("transient_preservation")
                # Preserve the producer's score key so repeated projection uses
                # the same raw contract rather than a handoff-only summary shape.
                container["transient_preservation"] = {
                    "preservation_score": safe["score"], "profile": safe["profile"],
                    "matched_event_count": safe["matched_event_count"], "activity": safe["activity"],
                }
            else:
                # An empty sentinel keeps the attempted comparison visible downstream.
                container["transient_preservation"] = {}
                rebuild = True
        if "stem_masking" in container:
            raw = container["stem_masking"]
            if stem_masking_evidence(raw):
                if container is projected or "stem_masking" not in projected:
                    qualified.add("stem_masking")
                if raw.get("carving_suggestions") or raw.get("clarity_prediction"):
                    rebuild = True
                # Activity qualifies a relative preview, never historical EQ or clarity predictions.
                raw.pop("carving_suggestions", None)
                raw.pop("clarity_prediction", None)
            else:
                # Legacy name-derived profiles cannot become measured through cached prose.
                container["stem_masking"] = {}
                rebuild = True
        if "stem_solo" in container:
            raw = container["stem_solo"]
            summary = raw.get("low_end_summary") if isinstance(raw, dict) else None
            ranked = summary.get("ranked") if isinstance(summary, dict) else None
            if isinstance(summary, dict) and summary.get("overlap_warning"):
                rebuild = True
            names = [item.get("name") for item in ranked if isinstance(item, dict)] if isinstance(ranked, list) else []
            safe = [entry for item in ranked if isinstance(item, dict) and names.count(item.get("name")) == 1
                    for entry in qualified_low_end_stems([item])] if isinstance(ranked, list) else []
            if safe:
                if container is projected or "stem_solo" not in projected:
                    qualified.add("stem_solo")
            if not safe or len(safe) != len(ranked):
                # One quiet or ambiguous stem does not erase independently qualified rows.
                rebuild = True
            container["stem_solo"] = {
                "low_end_summary": {"ranked": safe, "overlap_warning": None},
            }

    metrics = projected.get("metrics")
    if isinstance(metrics, dict):
        for key in ("transient_preservation", "stem_masking", "stem_solo"):
            if key in metrics and key not in projected:
                # Older metrics-shaped reports use the same canonical optional sections.
                projected[key] = deepcopy(metrics[key])

    # Scan cached narratives before replacing them. Whole-mix low_end_share and
    # ordinary transient_analysis metrics have separate meanings and stay intact.
    narrative_keys = (
        "summary", "flags", "action_plan", "ableton_repair_templates", "ableton_repair_chains",
        "source_hypotheses", "frequency_repair_map", "revision_coaching", "revision_lesson",
        "lesson_cards", "revision_agent", "revision_impact", "kenn_explanations", "mix_review_critique",
        "mix_critique", "prose_summary", "next_revision_plan", "closed_loop_action_plan", "judgment",
        "session_report", "kenn_handoff", "comparison_advice", "version_advice", "reference_coaching",
    )
    cached = json.dumps({key: report.get(key) for key in narrative_keys}, default=str).lower()
    legacy_markers = {
        "transient_preservation": ("transient_preservation", "transient preservation", "transient-preservation"),
        "stem_masking": ("stem_masking", "stem masking", "erb masking", "lowest_visibility", "simultaneous-masking"),
        "stem_solo": ("low_end_stems", "low_end_measured_stems", "low_end_summary", "low-end stem ranking"),
    }
    for key, markers in legacy_markers.items():
        if key not in qualified and any(marker in cached for marker in markers):
            # Some saved exports retained prose after dropping its optional source section.
            projected.setdefault(key, {})
            rebuild = True
    if any(marker in cached for marker in (
        "both carry substantial low-end", "low-end eq carving", "sidechain ducking",
        "clarity_prediction", "carving_suggestions", "most likely getting buried",
    )):
        # Even active previews cannot validate the retired overlap/repair predictions.
        rebuild = True
    if not rebuild:
        # Reports without unqualified optional inputs retain their independent narrative.
        return projected
    for key in narrative_keys:
        projected.pop(key, None)
    projected["publication_limitations"] = [limitation]
    projected["summary"] = limitation + " Independent whole-mix measurements and qualified previews remain available."
    return projected


def kenn_handoff(report: dict) -> dict:
    """Build a compact chat context for KENN follow-up questions."""
    report = project_report_publication(report)
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
        # analyze_wav derives the legacy estimate from decoded true_rms (or
        # sample-square RMS), not peak. KENN's source gate reads the canonical
        # key; an explicit canonical value must retain precedence even if quiet.
        "rms_dbfs": metrics.get("rms_dbfs", metrics.get("rms_dbfs_estimate")),
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
