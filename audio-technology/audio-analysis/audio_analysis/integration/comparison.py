from __future__ import annotations
from typing import Callable


def compare_metrics(mix_metrics: dict, reference_metrics: dict, bands: list[tuple[str, int, int]]) -> dict:
    def diff(key: str, *, precision: int = 2) -> float:
        return round(float(mix_metrics.get(key, 0) or 0) - float(reference_metrics.get(key, 0) or 0), precision)

    mix_bands = mix_metrics.get("bands") or {}
    ref_bands = reference_metrics.get("bands") or {}
    mix_perceived = mix_metrics.get("perceptual_bands") or {}
    ref_perceived = reference_metrics.get("perceptual_bands") or {}
    band_delta = {
        name: round(float(mix_bands.get(name, 0) or 0) - float(ref_bands.get(name, 0) or 0), 4)
        for name, _low, _high in bands
    }
    perceptual_delta = {
        name: round(float(mix_perceived.get(name, 0) or 0) - float(ref_perceived.get(name, 0) or 0), 4)
        for name, _low, _high in bands
    }
    strongest_band = max(band_delta.items(), key=lambda item: abs(item[1])) if band_delta else ("", 0.0)
    strongest_perceived = max(perceptual_delta.items(), key=lambda item: abs(item[1])) if perceptual_delta else ("", 0.0)

    def clean_val(val: object) -> float:
        try:
            return float(val) if val not in {None, "", "n/a"} else -99.0
        except ValueError:
            return -99.0

    mix_lufs = clean_val(mix_metrics.get("integrated_lufs"))
    ref_lufs = clean_val(reference_metrics.get("integrated_lufs"))
    lufs_delta = round(mix_lufs - ref_lufs, 2) if mix_lufs != -99.0 and ref_lufs != -99.0 else None

    mix_tp = clean_val(mix_metrics.get("true_peak_dbfs"))
    ref_tp = clean_val(reference_metrics.get("true_peak_dbfs"))
    tp_delta = round(mix_tp - ref_tp, 2) if mix_tp != -99.0 and ref_tp != -99.0 else None

    # Calculate 40-band log match score and parametric EQ settings
    mix_log_bands = mix_metrics.get("log_bands_40")
    ref_log_bands = reference_metrics.get("log_bands_40")
    tonal_balance_score = None
    eq_bands = None
    if mix_log_bands and ref_log_bands:
        try:
            from audio_analysis.analysis_core.genre_profiles import (
                compute_tonal_balance_envelope_score,
                compute_tonal_balance_score,
                solve_parametric_eq,
            )
            eq_bands = solve_parametric_eq(mix_log_bands, ref_log_bands)
            envelope = reference_metrics.get("genre_envelope")
            tonal_balance_score = (
                compute_tonal_balance_envelope_score(mix_log_bands, envelope)
                if envelope
                else compute_tonal_balance_score(mix_log_bands, ref_log_bands)
            )
        except Exception:
            pass

    return {
        "rms_delta_db": diff("rms_dbfs_estimate"),
        "peak_delta_db": diff("peak_dbfs"),
        "crest_delta_db": diff("crest_factor_db"),
        "loudest_section_delta_db": diff("loudest_section_rms_dbfs"),
        "stereo_width_delta": diff("stereo_width_ratio", precision=3),
        "correlation_delta": diff("stereo_correlation", precision=3),
        "lufs_delta_db": lufs_delta,
        "true_peak_delta_db": tp_delta,
        "band_delta": band_delta,
        "perceptual_band_delta": perceptual_delta,
        "largest_spectral_difference": {
            "band": strongest_band[0],
            "delta": round(strongest_band[1], 4),
        },
        "largest_perceptual_difference": {
            "band": strongest_perceived[0],
            "delta": round(strongest_perceived[1], 4),
        },
        "tonal_balance_score": tonal_balance_score,
        "eq_bands": eq_bands,
    }


def comparison_advice(comparison: dict) -> list[str]:
    advice: list[str] = []
    rms_delta = float(comparison.get("rms_delta_db", 0))
    crest_delta = float(comparison.get("crest_delta_db", 0))
    width_delta = float(comparison.get("stereo_width_delta", 0))
    lufs_delta = comparison.get("lufs_delta_db")
    band_delta = comparison.get("band_delta") or {}
    perceptual_delta = comparison.get("perceptual_band_delta") or {}
    largest = comparison.get("largest_spectral_difference") or {}
    largest_perceived = comparison.get("largest_perceptual_difference") or {}

    if lufs_delta is not None and abs(lufs_delta) > 1.5:
        direction = "louder" if lufs_delta > 0 else "quieter"
        advice.append(f"Your mix is about {abs(lufs_delta):.1f} LUFS {direction} than the reference by integrated loudness.")
    elif abs(rms_delta) > 3:
        direction = "louder" if rms_delta > 0 else "quieter"
        advice.append(f"Your mix is about {abs(rms_delta):.1f} dB {direction} than the reference by RMS estimate. Level-match before judging tone.")

    if crest_delta < -3:
        advice.append("Your mix has noticeably less crest factor than the reference; check whether limiting or bus compression is flattening transients.")
    elif crest_delta > 3:
        advice.append("Your mix has more crest factor than the reference; it may feel punchier but less controlled at matched loudness.")
    if abs(width_delta) > 0.25:
        direction = "wider" if width_delta > 0 else "narrower"
        advice.append(f"Your stereo side level is {direction} than the reference. Check mono compatibility and centre focus.")
    if abs(float(largest.get("delta", 0) or 0)) > 0.04:
        band = str(largest.get("band", "")).replace("_", " ")
        direction = "more" if float(largest.get("delta", 0)) > 0 else "less"
        advice.append(f"The biggest tonal difference is {band}: your mix has {direction} energy there than the reference.")
    if abs(float(largest_perceived.get("delta", 0) or 0)) > 0.04:
        band = str(largest_perceived.get("band", "")).replace("_", " ")
        direction = "more" if float(largest_perceived.get("delta", 0)) > 0 else "less"
        advice.append(f"After ear-weighting, the biggest perceived difference is {band}: your mix may feel like it has {direction} energy there.")
    if float(band_delta.get("low_mids", 0) or 0) > 0.04:
        advice.append("Compared with the reference, low mids are heavier. Check 150-400 Hz buildup before adding more brightness.")
    if float(band_delta.get("presence", 0) or 0) < -0.04:
        advice.append("Compared with the reference, presence is lower. Vocals or lead sounds may need more clarity around 2-6 kHz.")
    if float(perceptual_delta.get("presence", 0) or 0) > 0.04:
        advice.append("Ear-weighted presence is higher than the reference. Check harshness and sibilance at normal playback volume.")
    if not advice:
        advice.append("Your mix is broadly close to the reference on these technical measurements. Use listening checks for taste and arrangement decisions.")
    return advice


def match_score(comparison: dict) -> int:
    """Aggregate 0-100 similarity score from a compare_metrics() result.

    Weights: tonal balance (70), LUFS match (20), stereo similarity (10).
    Returns 0-100 integer; higher is more similar.
    """
    tonal = comparison.get("tonal_balance_score")
    lufs_delta = comparison.get("lufs_delta_db")
    stereo_width_delta = float(comparison.get("stereo_width_delta") or 0.0)
    correlation_delta = float(comparison.get("correlation_delta") or 0.0)

    # Tonal balance component (70 pts) — use neutral 35 if not computed
    tonal_comp = float(tonal) * 70.0 if tonal is not None else 35.0

    # LUFS match component (20 pts) — full points within 1 dB, zero beyond 6 dB
    if lufs_delta is not None:
        lufs_comp = max(0.0, 1.0 - abs(float(lufs_delta)) / 6.0) * 20.0
    else:
        lufs_comp = 10.0  # neutral when not measured

    # Stereo similarity component (10 pts)
    stereo_deviation = abs(stereo_width_delta) + abs(correlation_delta)
    stereo_comp = max(0.0, 1.0 - stereo_deviation / 2.0) * 10.0

    return max(0, min(100, round(tonal_comp + lufs_comp + stereo_comp)))


def reference_coaching(comparison: dict, mix_metrics: dict, reference_payload: dict, *, metric_float: Callable, mix_goal_info: Callable) -> dict:
    mix_goal = mix_metrics.get("mix_goal") or mix_goal_info("")
    largest = comparison.get("largest_spectral_difference") or {}
    largest_perceived = comparison.get("largest_perceptual_difference") or {}
    rms_delta = metric_float(comparison.get("rms_delta_db"))
    crest_delta = metric_float(comparison.get("crest_delta_db"))
    width_delta = metric_float(comparison.get("stereo_width_delta"))
    corr_delta = metric_float(comparison.get("correlation_delta"))
    lufs_delta = comparison.get("lufs_delta_db")
    level_delta = metric_float(lufs_delta, rms_delta) if lufs_delta is not None else rms_delta
    level_warning = abs(level_delta) > 1.5

    tonal_band = str(largest.get("band") or "").replace("_", " ")
    tonal_delta = metric_float(largest.get("delta"))
    tonal_direction = "more" if tonal_delta > 0 else "less"
    perceived_band = str(largest_perceived.get("band") or "").replace("_", " ")
    perceived_delta = metric_float(largest_perceived.get("delta"))
    perceived_direction = "more" if perceived_delta > 0 else "less"

    if level_warning:
        level_unit = "LUFS" if lufs_delta is not None else "dB"
        level_message = f"Level-match first: your mix is about {abs(level_delta):.1f} {level_unit} {'louder' if level_delta > 0 else 'quieter'} than the reference."
    else:
        level_message = "Levels are close enough for a useful first-pass tonal comparison."

    tonal_message = "No dominant tonal delta against the reference."
    if tonal_band and abs(tonal_delta) > 0.02:
        tonal_message = f"Raw spectrum: your mix has {tonal_direction} {tonal_band} than the reference."
    perceived_message = ""
    if perceived_band and abs(perceived_delta) > 0.03:
        perceived_message = f"Ear-weighted read: it may feel like {perceived_direction} {perceived_band}."

    dynamics_message = "Dynamics are broadly close to the reference."
    if crest_delta < -1.5:
        dynamics_message = "Your mix has less crest/punch than the reference; check limiting or bus compression."
    elif crest_delta > 1.5:
        dynamics_message = "Your mix has more crest/punch than the reference; check whether it feels controlled at matched loudness."

    stereo_message = "Stereo width is broadly close to the reference."
    if width_delta > 0.15:
        stereo_message = "Your mix is wider than the reference; check centre focus and mono compatibility."
    elif width_delta < -0.15:
        stereo_message = "Your mix is narrower than the reference; check whether ambience, doubles, or stereo effects need more space."
    if corr_delta < -0.15:
        stereo_message += " Mono correlation is lower than the reference, so treat width changes carefully."

    next_move = tonal_message
    if level_warning:
        next_move = "Level-match the files before making tonal decisions."
    elif abs(crest_delta) > 1.5:
        next_move = dynamics_message
    elif abs(width_delta) > 0.15:
        next_move = stereo_message

    return {
        "reference": {
            "name": reference_payload.get("name") or reference_payload.get("filename") or "Reference",
            "style": reference_payload.get("style", ""),
            "saved": bool(reference_payload.get("saved")),
        },
        "goal": mix_goal,
        "headline": f"Reference coaching for {mix_goal.get('label', 'mix')}.",
        "level_match_required": level_warning,
        "level_message": level_message,
        "tonal_message": tonal_message,
        "perceived_message": perceived_message,
        "dynamics_message": dynamics_message,
        "stereo_message": stereo_message,
        "next_move": next_move,
        "safe_use": "Use the reference as a direction check, not a target to copy exactly.",
    }


def version_advice(comparison: dict) -> list[str]:
    advice: list[str] = []
    rms_delta = float(comparison.get("rms_delta_db", 0))
    crest_delta = float(comparison.get("crest_factor_db", 0))
    width_delta = float(comparison.get("stereo_width_delta", 0))
    lufs_delta = comparison.get("lufs_delta_db")
    largest = comparison.get("largest_spectral_difference") or {}
    largest_perceived = comparison.get("largest_perceptual_difference") or {}

    if lufs_delta is not None and abs(lufs_delta) > 1.0:
        direction = "louder" if lufs_delta > 0 else "quieter"
        advice.append(f"This version is about {abs(lufs_delta):.1f} LUFS {direction} than the previous version.")
    elif abs(rms_delta) > 1.5:
        direction = "louder" if rms_delta > 0 else "quieter"
        advice.append(f"This version is about {abs(rms_delta):.1f} dB {direction} than the previous version by RMS estimate.")

    if crest_delta < -1.5:
        advice.append("Dynamics reduced compared with the previous version. Check whether the revision lost punch or transient movement.")
    elif crest_delta > 1.5:
        advice.append("Dynamics increased compared with the previous version. Check whether the revision feels more open or too uncontrolled.")
    if abs(width_delta) > 0.15:
        direction = "wider" if width_delta > 0 else "narrower"
        advice.append(f"Stereo width changed: this version is {direction} than the previous version.")
    if abs(float(largest.get("delta", 0) or 0)) > 0.03:
        band = str(largest.get("band", "")).replace("_", " ")
        direction = "more" if float(largest.get("delta", 0)) > 0 else "less"
        advice.append(f"Biggest raw tonal change: {direction} {band} than the previous version.")
    if abs(float(largest_perceived.get("delta", 0) or 0)) > 0.03:
        band = str(largest_perceived.get("band", "")).replace("_", " ")
        direction = "more" if float(largest_perceived.get("delta", 0)) > 0 else "less"
        advice.append(f"Biggest perceived change: it may feel like {direction} {band} than the previous version.")
    if not advice:
        advice.append("This version is technically close to the previous one. Use a level-matched listen to judge whether the revision improved the mix.")
    return advice


def revision_coaching(current_report: dict, previous_report: dict | None, *, metric_float: Callable, mix_goal_info: Callable) -> dict | None:
    if not previous_report:
        return None
    comparison = current_report.get("version_comparison") or {}
    impact = current_report.get("revision_impact") or {}
    metrics = current_report.get("metrics") or {}
    previous_metrics = previous_report.get("metrics") or {}
    mix_goal = metrics.get("mix_goal") or mix_goal_info("")
    improvements = list(impact.get("improvements") or [])
    regressions = list(impact.get("regressions") or [])
    checks = list(impact.get("checks") or [])

    def add_delta(key: str, label: str, unit: str = "") -> dict:
        value = comparison.get(key)
        return {"label": label, "value": value, "unit": unit} if value not in {None, ""} else {}

    metric_deltas = [
        item
        for item in (
            add_delta("rms_delta_db", "Average level", "dB"),
            add_delta("crest_delta_db", "Punch / crest", "dB"),
            add_delta("stereo_width_delta", "Stereo width", ""),
            add_delta("correlation_delta", "Mono correlation", ""),
            add_delta("lufs_delta_db", "Integrated loudness", "LUFS"),
            add_delta("true_peak_delta_db", "True peak", "dB"),
        )
        if item
    ]

    previous_flags = {str(flag.get("label", "")) for flag in previous_report.get("flags", []) if isinstance(flag, dict)}
    current_flags = {str(flag.get("label", "")) for flag in current_report.get("flags", []) if isinstance(flag, dict)}
    cleared = sorted(label for label in previous_flags - current_flags if label)
    new = sorted(label for label in current_flags - previous_flags if label)
    unchanged = sorted(label for label in previous_flags & current_flags if label)

    score = metric_float(metrics.get("technical_score"))
    previous_score = metric_float(previous_metrics.get("technical_score"))
    score_delta = round(score - previous_score, 1) if score or previous_score else 0.0
    verdict = str(impact.get("verdict") or "similar")
    if verdict == "improved":
        headline = "This revision moved in the right direction."
    elif verdict == "regressed":
        headline = "This revision introduced more technical risk."
    elif verdict == "mixed":
        headline = "This revision is mixed: keep the wins, check the trade-offs."
    else:
        headline = "This revision is technically similar to the previous version."

    next_focus = ""
    if regressions:
        next_focus = regressions[0]
    elif unchanged:
        next_focus = f"Remaining flag to address: {unchanged[0]}."
    elif checks:
        next_focus = checks[0]
    else:
        next_focus = "Do a level-matched listening pass against the reference before making more changes."

    listening_test = (
        f"For {mix_goal.get('label', 'this mix')}, level-match v1 and v2, then listen for the changed issue only. "
        "If the fix helps the song but creates a new flag, keep the idea and reduce the amount."
    )
    return {
        "headline": headline,
        "verdict": verdict,
        "score_delta": score_delta,
        "metric_deltas": metric_deltas,
        "cleared_flags": cleared,
        "new_flags": new,
        "unchanged_flags": unchanged,
        "improvements": improvements,
        "regressions": regressions,
        "checks": checks,
        "next_focus": next_focus,
        "listening_test": listening_test,
    }


def track_timeline(title: str, *, limit: int, normalize_title: Callable, list_reviews: Callable, numeric_delta: Callable) -> dict:
    normalized = normalize_title(title)
    if not normalized:
        return {"ok": False, "error": "Track title is required."}
    items = [
        item
        for item in list_reviews(limit=max(limit, 200))
        if normalize_title(str(item.get("title", ""))) == normalized
    ]
    items.sort(key=lambda item: str(item.get("created_at", "")))
    versions = []
    for item in items[-max(1, min(200, limit)) :]:
        metrics = item.get("metrics") or {}
        comparison = item.get("version_comparison") or {}
        reference = item.get("reference") or {}
        revision_agent = item.get("revision_agent") or {}
        versions.append(
            {
                "id": item.get("id"),
                "title": item.get("title", ""),
                "version_label": item.get("version_label", ""),
                "created_at": item.get("created_at", ""),
                "summary": item.get("summary", ""),
                "score": metrics.get("technical_score"),
                "rating": metrics.get("technical_rating", ""),
                "peak_dbfs": metrics.get("peak_dbfs"),
                "rms_dbfs_estimate": metrics.get("rms_dbfs_estimate"),
                "crest_factor_db": metrics.get("crest_factor_db"),
                "stereo_width_ratio": metrics.get("stereo_width_ratio"),
                "dominant_band": (metrics.get("perceptual_summary") or {}).get("dominant_band", ""),
                "flags": [
                    str(flag.get("label", ""))
                    for flag in item.get("flags", [])[:5]
                    if flag.get("label")
                ],
                "version_delta": {
                    key: comparison.get(key)
                    for key in ("rms_delta_db", "crest_delta_db", "stereo_width_delta")
                    if comparison.get(key) not in {None, ""}
                },
                "version_advice": item.get("version_advice", [])[:3],
                "revision_impact": item.get("revision_impact"),
                "revision_agent": {
                    "summary": revision_agent.get("summary", ""),
                    "steps": (revision_agent.get("steps") or [])[:3],
                }
                if revision_agent
                else None,
                "reference": {
                    "id": reference.get("id"),
                    "name": reference.get("name") or reference.get("filename", ""),
                    "style": reference.get("style", ""),
                    "saved": bool(reference.get("saved")),
                }
                if reference
                else None,
                "report_url": f"/api/mix-review-report/{item.get('id')}.html" if item.get("id") else "",
            }
        )
    if not versions:
        return {"ok": False, "error": "No reviews found for that track title."}
    first = versions[0]
    latest = versions[-1]
    return {
        "ok": True,
        "title": latest.get("title") or title,
        "version_count": len(versions),
        "versions": versions,
        "summary": {
            "score_change": numeric_delta(latest.get("score"), first.get("score")),
            "rms_change_db": numeric_delta(latest.get("rms_dbfs_estimate"), first.get("rms_dbfs_estimate")),
            "crest_change_db": numeric_delta(latest.get("crest_factor_db"), first.get("crest_factor_db")),
            "width_change": numeric_delta(latest.get("stereo_width_ratio"), first.get("stereo_width_ratio")),
            "latest_score": latest.get("score"),
            "latest_rating": latest.get("rating", ""),
            "latest_flags": latest.get("flags", []),
        },
    }
