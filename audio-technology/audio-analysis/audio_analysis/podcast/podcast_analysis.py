"""Podcast / spoken-word audio analysis.

Produces a structured, advice-only "podcast readiness" report from the same
`metrics` dict the analysis engine already computes for a mix — but interpreted
for *dialogue delivery* rather than music. It flags the issues that actually
matter for spoken word and suggests a fix for each. It applies no DSP.

Scope (what a podcast editor is judged on, and what tools like Auphonic /
Adobe Podcast / Descript compete on):

- loudness on target for the destination platform (Apple −16, Spotify −14,
  mono −19 LUFS) and true-peak safe;
- consistent levels (not too dynamic for speech — needs leveling/compression);
- clean low end (no rumble / HVAC / plosive energy below the voice);
- controlled sibilance (de-ess) and no boxy low-mid mud;
- intelligible presence band; mono/phase safe; not clipped.

**Calibration honesty:** the band-proportion thresholds below are conservative
heuristics, NOT calibrated against a rights-cleared spoken-word corpus. They are
module constants precisely so they can be tuned once real reference dialogue is
available. The report says so.
"""

from __future__ import annotations

__all__ = ["analyze_podcast", "PODCAST_TARGETS", "PODCAST_BAND_HEURISTICS"]


# Delivery loudness targets (integrated LUFS) + true-peak ceiling per platform.
PODCAST_TARGETS = {
    "apple": {"lufs": -16.0, "lufs_tol": 1.0, "true_peak_max": -1.0, "label": "Apple Podcasts (stereo)"},
    "spotify": {"lufs": -14.0, "lufs_tol": 1.0, "true_peak_max": -1.0, "label": "Spotify"},
    "mono": {"lufs": -19.0, "lufs_tol": 1.0, "true_peak_max": -1.0, "label": "Mono spoken word (−19)"},
    "youtube": {"lufs": -14.0, "lufs_tol": 1.5, "true_peak_max": -1.0, "label": "YouTube"},
}

# Heuristic band-proportion limits for a clean voice (7-band energy proportions
# from map_40_to_7_bands: sub/bass/low_mids/mids/presence/sibilance/air).
PODCAST_BAND_HEURISTICS = {
    "sub_max": 0.05,          # 20–60 Hz: voice has almost none; excess = rumble/HVAC
    "low_mids_max": 0.34,     # 150–400 Hz: excess = boxy/muddy
    "sibilance_max": 0.09,    # 6–8 kHz: excess = harsh essing, wants a de-esser
    "presence_min": 0.08,     # 2–6 kHz: too little = dull/unintelligible
}

# Spoken word wants consistency; a wide loudness range means levels wander.
PODCAST_LRA_WARN_LU = 11.0
PODCAST_LRA_FAIL_LU = 16.0
# Correlation below this on a stereo file suggests phase/mono-fold-down risk.
PODCAST_MONO_CORR_WARN = 0.4


def _num(d: dict, key: str) -> float | None:
    try:
        v = d.get(key)
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _check(cid: str, label: str, status: str, measured, target, fix: str) -> dict:
    return {"id": cid, "label": label, "status": status, "measured": measured,
            "target": target, "fix": fix}


def analyze_podcast(metrics: dict, *, target: str = "apple", explain: bool = False) -> dict:
    """Analyse a spoken-word/podcast recording's metrics.

    Parameters
    ----------
    metrics:
        The analysis-engine metrics dict (integrated_lufs, true_peak_dbfs,
        peak_dbfs, loudness_range_lu, crest_factor_db, stereo_correlation,
        bands, ...).
    target:
        Delivery target key in ``PODCAST_TARGETS`` (default "apple").
    explain:
        Ground the non-"ok" checks in KENN's knowledge base (best-effort,
        never blocks). Opt-in and off by default: this function is called
        from plain unit tests and other lightweight, previously
        index-independent contexts, not just report-generation. Report-
        generation callers that actually want it (``podcast_check.py``) pass
        ``explain=True`` explicitly.

    Returns a JSON-serialisable report: ``{target, checks, score, summary,
    calibrated}``. ``status`` per check is "ok" | "warn" | "fail".
    """
    metrics = metrics or {}
    spec = PODCAST_TARGETS.get(target, PODCAST_TARGETS["apple"])
    bands = metrics.get("bands") if isinstance(metrics.get("bands"), dict) else {}
    checks: list[dict] = []

    # 1. Integrated loudness on target.
    lufs = _num(metrics, "integrated_lufs")
    if lufs is not None:
        goal, tol = spec["lufs"], spec["lufs_tol"]
        off = lufs - goal
        if abs(off) <= tol:
            status, fix = "ok", "Loudness is on target."
        else:
            direction = "loud" if off > 0 else "quiet"
            status = "fail" if abs(off) > 2 * tol else "warn"
            fix = (f"Normalise to {goal:.0f} LUFS ({abs(off):.1f} LU too {direction}) for "
                   f"{spec['label']}.")
        checks.append(_check("loudness", "Integrated loudness", status,
                             f"{lufs:.1f} LUFS", f"{goal:.0f} ±{tol:.0f} LUFS", fix))

    # 2. True-peak ceiling.
    tp = _num(metrics, "true_peak_dbfs")
    if tp is not None:
        ceil = spec["true_peak_max"]
        status = "fail" if tp > ceil else "ok"
        fix = (f"Apply a true-peak limiter at {ceil:.0f} dBTP." if status == "fail"
               else "True peak is within ceiling.")
        checks.append(_check("true_peak", "True peak", status, f"{tp:.1f} dBTP",
                             f"≤ {ceil:.0f} dBTP", fix))

    # 3. Clipping.
    peak = _num(metrics, "peak_dbfs")
    if peak is not None and peak >= -0.1:
        checks.append(_check("clipping", "Digital clipping", "fail", f"{peak:.1f} dBFS",
                             "< -1 dBFS", "Samples reach full scale — re-record or clip-repair; the "
                             "recording is likely distorted."))

    # 4. Level consistency (loudness range).
    lra = _num(metrics, "loudness_range_lu")
    if lra is not None:
        if lra >= PODCAST_LRA_FAIL_LU:
            status, fix = "fail", "Levels wander a lot — apply leveling/compression so quiet and loud speech sit together."
        elif lra >= PODCAST_LRA_WARN_LU:
            status, fix = "warn", "Fairly wide level variation for speech — consider gentle leveling."
        else:
            status, fix = "ok", "Levels are consistent for speech."
        checks.append(_check("consistency", "Level consistency", status, f"{lra:.1f} LU",
                             f"< {PODCAST_LRA_WARN_LU:.0f} LU", fix))

    # Band checks report OK when clean (a client report should confirm what's
    # good, not only list faults) and warn with a fix when a threshold is crossed.

    # 5. Low-end rumble / plosives.
    sub = _num(bands, "sub")
    if sub is not None:
        over = sub > PODCAST_BAND_HEURISTICS["sub_max"]
        checks.append(_check("rumble", "Low-end rumble", "warn" if over else "ok",
                             f"{sub * 100:.0f}% energy < 60 Hz",
                             f"< {PODCAST_BAND_HEURISTICS['sub_max'] * 100:.0f}%",
                             "High-pass around 80 Hz to remove rumble/HVAC/plosive energy the voice doesn't need."
                             if over else "Clean low end."))

    # 6. Boxy / muddy low-mids.
    low_mids = _num(bands, "low_mids")
    if low_mids is not None:
        over = low_mids > PODCAST_BAND_HEURISTICS["low_mids_max"]
        checks.append(_check("mud", "Low-mid mud", "warn" if over else "ok",
                             f"{low_mids * 100:.0f}% energy 150–400 Hz",
                             f"< {PODCAST_BAND_HEURISTICS['low_mids_max'] * 100:.0f}%",
                             "Gentle 2–3 dB dip around 250–400 Hz to reduce boxiness." if over
                             else "No boxiness."))

    # 7. Sibilance / de-ess.
    sib = _num(bands, "sibilance")
    if sib is not None:
        over = sib > PODCAST_BAND_HEURISTICS["sibilance_max"]
        checks.append(_check("sibilance", "Sibilance", "warn" if over else "ok",
                             f"{sib * 100:.0f}% energy 6–8 kHz",
                             f"< {PODCAST_BAND_HEURISTICS['sibilance_max'] * 100:.0f}%",
                             "Add a de-esser around 6–8 kHz to tame harsh 's' sounds." if over
                             else "Sibilance under control."))

    # 8. Presence / intelligibility.
    presence = _num(bands, "presence")
    if presence is not None:
        under = presence < PODCAST_BAND_HEURISTICS["presence_min"]
        checks.append(_check("presence", "Presence / intelligibility", "warn" if under else "ok",
                             f"{presence * 100:.0f}% energy 2–6 kHz",
                             f"> {PODCAST_BAND_HEURISTICS['presence_min'] * 100:.0f}%",
                             "Voice may sound dull — a small 2–5 kHz lift improves articulation." if under
                             else "Clear and intelligible."))

    # 9. Mono / phase safety (only meaningful for stereo files).
    corr = _num(metrics, "stereo_correlation")
    if corr is not None:
        risky = corr < PODCAST_MONO_CORR_WARN
        checks.append(_check("mono", "Mono compatibility", "warn" if risky else "ok",
                             f"correlation {corr:+.2f}", f"> {PODCAST_MONO_CORR_WARN:+.1f}",
                             "Low channel correlation risks a hollow voice when summed to mono; "
                             "check phase or deliver mono." if risky else "Mono-safe."))

    fails = sum(1 for c in checks if c["status"] == "fail")
    warns = sum(1 for c in checks if c["status"] == "warn")
    score = max(0, 100 - fails * 25 - warns * 8)
    if fails:
        summary = f"{fails} blocking issue(s) and {warns} to review before publishing."
    elif warns:
        summary = f"Publishable, with {warns} improvement(s) worth making."
    else:
        summary = "Clean spoken-word delivery — ready to publish."

    report = {
        "target": target,
        "target_label": spec["label"],
        "checks": checks,
        "score": score,
        "summary": summary,
        "calibrated": False,  # heuristics; calibrate against a real dialogue corpus
    }

    # Proactively explain the non-"ok" checks using KENN's grounded answer
    # pipeline -- same best-effort, never-blocks-the-report contract as
    # mix_review.py's Stage D (annotate_flags_with_kenn).
    if explain and checks:
        try:
            from audio_analysis.integration.kenn_handoff import annotate_podcast_checks_with_kenn

            kenn_explanations = annotate_podcast_checks_with_kenn(checks)
        except Exception:
            kenn_explanations = []
            import logging

            logging.getLogger(__name__).warning(
                "KENN podcast check explanation annotation failed; "
                "delivering report without it", exc_info=True,
            )
        if kenn_explanations:
            report["kenn_explanations"] = kenn_explanations

    return report
