"""Delivery-spec conformance checker for a finished master.

Advice-only, no DSP: given the same `metrics` dict the analysis engine
already computes for a mix, checks integrated loudness, true-peak ceiling,
clipping, and mono/phase compatibility against a named delivery platform's
published target -- and says pass/fail/why, deterministically. Reuses the
same `_check()`-list report shape as podcast/podcast_analysis.py (same
"boring, explainable, batch-capable" design).

Deliberately does NOT judge loudness range (LRA): unlike spoken word, music
has no universal "should be narrow" target -- a wide-dynamics cinematic
mix and a brickwalled EDM master can both be a legitimate delivery, so LRA
is reported informationally only, never scored.
"""

from __future__ import annotations

__all__ = ["DELIVERY_TARGETS", "check_delivery_conformance"]


# Integrated-loudness targets are each platform's own published loudness-
# normalization spec (not genre-specific tuning) -- Apple/Spotify/YouTube
# numbers match podcast/podcast_analysis.py's PODCAST_TARGETS exactly,
# since it's the same platform target regardless of content type. Club/DJ
# and CD/physical have no loudness-normalization step at all, so there is
# no defensible LUFS target for them -- true-peak safety is checked, the
# loudness check is skipped (lufs: None), and the label says why.
#
# true_peak_max is -1.0 dBTP everywhere: the standard safety margin against
# inter-sample overs regardless of destination. Not asserting a different
# (e.g. tighter) number for CD/club without real evidence for one.
DELIVERY_TARGETS = {
    "spotify": {"lufs": -14.0, "lufs_tol": 1.0, "true_peak_max": -1.0, "label": "Spotify"},
    "apple_music": {"lufs": -16.0, "lufs_tol": 1.0, "true_peak_max": -1.0, "label": "Apple Music"},
    "youtube": {"lufs": -14.0, "lufs_tol": 1.5, "true_peak_max": -1.0, "label": "YouTube"},
    "club": {"lufs": None, "lufs_tol": None, "true_peak_max": -1.0,
             "label": "Club / DJ (no loudness target -- master to taste for the room)"},
    "cd": {"lufs": None, "lufs_tol": None, "true_peak_max": -1.0,
           "label": "CD / Physical (no loudness normalisation downstream)"},
}

# Same threshold and rationale as podcast/podcast_analysis.py's
# PODCAST_MONO_CORR_WARN -- low channel correlation risks a hollow or
# phase-cancelled sum on a mono/club PA fold-down, regardless of content type.
MONO_CORR_WARN = 0.4


def _num(d: dict, key: str) -> float | None:
    try:
        v = d.get(key)
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _check(cid: str, label: str, status: str, measured, target, fix: str) -> dict:
    return {"id": cid, "label": label, "status": status, "measured": measured,
            "target": target, "fix": fix}


def check_delivery_conformance(metrics: dict, *, target: str = "spotify") -> dict:
    """Check a finished master's metrics against a delivery platform's spec.

    Parameters
    ----------
    metrics:
        The analysis-engine metrics dict (integrated_lufs, true_peak_dbfs,
        peak_dbfs, loudness_range_lu, stereo_correlation, ...).
    target:
        Delivery target key in ``DELIVERY_TARGETS`` (default "spotify").

    Returns a JSON-serialisable report: ``{target, target_label, checks,
    loudness_range_lu, score, summary}``. ``status`` per check is
    "ok" | "warn" | "fail".
    """
    metrics = metrics or {}
    spec = DELIVERY_TARGETS.get(target, DELIVERY_TARGETS["spotify"])
    checks: list[dict] = []

    # 1. Integrated loudness on target (skipped when the platform has none).
    lufs = _num(metrics, "integrated_lufs")
    if lufs is not None and spec["lufs"] is not None:
        goal, tol = spec["lufs"], spec["lufs_tol"]
        off = lufs - goal
        if abs(off) <= tol:
            status, fix = "ok", "Loudness is on target."
        else:
            direction = "loud" if off > 0 else "quiet"
            status = "fail" if abs(off) > 2 * tol else "warn"
            fix = (f"Adjust to {goal:.0f} LUFS ({abs(off):.1f} LU too {direction}) for "
                   f"{spec['label']}.")
        checks.append(_check("loudness", "Integrated loudness", status,
                             f"{lufs:.1f} LUFS", f"{goal:.0f} ±{tol:.0f} LUFS", fix))

    # 2. True-peak ceiling.
    tp = _num(metrics, "true_peak_dbfs")
    if tp is not None:
        ceil = spec["true_peak_max"]
        status = "fail" if tp > ceil else "ok"
        fix = (f"Apply a true-peak limiter at {ceil:.1f} dBTP." if status == "fail"
               else "True peak is within ceiling.")
        checks.append(_check("true_peak", "True peak", status, f"{tp:.1f} dBTP",
                             f"≤ {ceil:.1f} dBTP", fix))

    # 3. Clipping.
    peak = _num(metrics, "peak_dbfs")
    if peak is not None and peak >= -0.1:
        checks.append(_check("clipping", "Digital clipping", "fail", f"{peak:.1f} dBFS",
                             "< -0.1 dBFS", "Samples reach full scale -- re-render with headroom "
                             "or apply a true-peak-safe limiter before delivery."))

    # 4. Mono / phase safety (only meaningful for stereo files).
    corr = _num(metrics, "stereo_correlation")
    if corr is not None:
        risky = corr < MONO_CORR_WARN
        checks.append(_check("mono", "Mono compatibility", "warn" if risky else "ok",
                             f"correlation {corr:+.2f}", f"> {MONO_CORR_WARN:+.1f}",
                             "Low channel correlation risks phase cancellation on a mono/club PA "
                             "fold-down; check phase relationships on wide elements." if risky
                             else "Mono-safe."))

    fails = sum(1 for c in checks if c["status"] == "fail")
    warns = sum(1 for c in checks if c["status"] == "warn")
    score = max(0, 100 - fails * 25 - warns * 8)
    if fails:
        summary = f"{fails} blocking issue(s) and {warns} to review before delivery to {spec['label']}."
    elif warns:
        summary = f"Deliverable to {spec['label']}, with {warns} thing(s) worth a listen."
    else:
        summary = f"Conforms to {spec['label']}'s delivery spec -- ready to deliver."

    return {
        "target": target,
        "target_label": spec["label"],
        "checks": checks,
        # Informational only -- see module docstring on why LRA is never scored.
        "loudness_range_lu": _num(metrics, "loudness_range_lu"),
        "score": score,
        "summary": summary,
    }
