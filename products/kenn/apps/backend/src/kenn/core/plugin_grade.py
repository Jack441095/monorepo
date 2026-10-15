"""Project one owned insert's qualified window into the existing partial grade.

The caller supplies a validated handoff and its currentness decision under the
handoff lock. This never reads process-wide Doctor reports or master telemetry.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from kenn.core.evidence import live_context_has_activity
from kenn.core.grade import combine_grade
from kenn.core.mix_doctor import score_stereo_correlation


_UNSCORED_DIMENSIONS = (
    ("dynamic_health", "No qualified true peak or integrated loudness at this insert; sample peak and RMS cannot substitute."),
    ("low_end_control", "The insert's broad filter powers do not measure the required sub-band fraction."),
    ("spectral_balance", "The insert's broad filter powers do not match the technical grade's spectral fractions."),
    ("stem_separation", "No associated isolated-stem comparison; track names and faders are advice only."),
)
_SCOPE = "Only stereo correlation in this selected insert's contiguous 100 ms window is scored; this is not a whole-mix or release-readiness grade."


def selected_insert_grade(
    *, conversation_id: str, insert_id: str, item: dict[str, Any],
    age_seconds: float, current: bool, max_age_seconds: float,
) -> dict[str, Any]:
    """Return scored points or explicit omissions for exactly this owner and window.

    Older publishers without stereo-validity metadata remain usable for their
    existing observations, but cannot earn correlation points from a placeholder.
    """
    metrics = item["metrics"]
    window = item.get("measurement_window")
    reason = ""
    if not conversation_id or item.get("conversation_id") != conversation_id:
        reason = "The selected insert is not associated with this conversation."
    elif not current:
        reason = "Audio is stale, paused, invalid or awaiting a new source window; replay with analysis enabled."
    elif not window or not window.get("valid"):
        reason = "A complete contiguous 100 ms measurement window is required."
    elif not live_context_has_activity(metrics):
        reason = "Input RMS is at or below the live -80 dBFS activity floor; play an audible passage."
    elif metrics.get("input_channels") != 2:
        reason = "Stereo input layout is missing or mono; a duplicated mono correlation cannot earn stereo points."
    elif metrics.get("correlation_valid") is not True:
        reason = "Correlation is undefined or its validity is unavailable; both stereo channels need measured energy."
    elif any(window.get(key) != metrics.get(key) for key in ("input_channels", "correlation_valid")):
        reason = "Correlation eligibility is not associated with this measurement window."

    stereo = None if reason else score_stereo_correlation(metrics.get("stereo_correlation"))
    if not reason and stereo is None:
        # Validated live frames cannot normally reach this branch; retained older
        # contexts must still abstain if their correlation was malformed.
        reason = "No finite correlation in the meter's -1 to +1 range is available."
    if stereo is not None:
        stereo = {**stereo, "correlation": metrics["stereo_correlation"]}
    unscored = [{"dimension": dimension, "reason": note} for dimension, note in _UNSCORED_DIMENSIONS]
    if stereo is None:
        unscored.append({"dimension": "stereo_imaging", "reason": reason})
    technical = {
        "mqm_score": stereo["points"] if stereo else 0.0,
        "points_available": stereo["points_available"] if stereo else 0.0,
        "meaning": _SCOPE if stereo else reason,
        "unscored": [f"{entry['dimension']}: {entry['reason']}" for entry in unscored],
    }
    grade = combine_grade(
        technical=technical,
        declared_target={"points": 0.0, "points_available": 0.0,
                         "note": "No qualified integrated LUFS or true peak for this insert; the live loudness candidate remains disabled."},
        reference_match={"points": 0.0, "points_available": 0.0,
                         "note": "No associated qualifying reference comparison for this insert."},
    )
    return {
        "schema": "kenn.plugin_insert_grade.v1", "scope": "selected_insert_window",
        "conversation_id": conversation_id, "insert_id": insert_id,
        "host_track_name": item.get("host_track_name", ""), "sample_rate": metrics["sample_rate"],
        "measurement_window": deepcopy(window),
        # Preserve the unrounded capture age: rounding near one second could
        # grant a displayed grade another polling interval of apparent life.
        "freshness": {"age_seconds": age_seconds, "max_age_seconds": max_age_seconds,
                      "current_for_diagnosis": current},
        "status": "graded" if stereo else "ungraded", "reason": reason,
        "grade": grade, "stereo": stereo, "unscored_dimensions": unscored,
    }


def selected_insert_grade_answer(grading: dict[str, Any], name: str) -> str:
    """Describe this captured window's partial grade without inventing mix advice."""
    if grading["status"] != "graded":
        # No available points means unavailable evidence, never a zero-quality
        # verdict. Keep the reason even when the retained window has expired.
        return (f"The selected insert '{name}' is ungraded: {grading['reason']} "
                "No quality score is available. Other technical dimensions, declared targets and reference matching remain ungraded.")
    grade, stereo, window = grading["grade"], grading["stereo"], grading["measurement_window"]
    return (
        f"At '{name}', the measured 100 ms stereo window earns {grade['points']:.1f} of "
        f"{grade['points_available']:.0f} available points out of {grade['full_marks']:.0f} possible. "
        f"This is a selected-insert window, not a whole-mix or release-readiness grade. "
        f"Evidence: samples [{window['start_sample']}, {window['end_sample']}) at {grading['sample_rate']:g} Hz, "
        f"sequence {window['sequence']}, source generation {window['source_generation']}; "
        f"capture age {grading['freshness']['age_seconds']:.3f} seconds when read. "
        f"Correlation {stereo['correlation']:.3f}, threshold band {stereo['threshold_band']}; "
        f"rule {stereo['source']} ({stereo['tier']}). The point weighting is a design choice; "
        f"correlation alone does not establish audible cancellation severity. "
        "Ungraded: dynamic health (qualified LUFS and true peak unavailable), low-end control, "
        "spectral balance, stem separation, declared targets and reference matching. "
        "The live loudness candidate remains disabled."
    )
