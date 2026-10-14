"""The E2 grade out of 100: technical health 30, declared target 30, reference match 40.

This only adds up parts that were already scored elsewhere. A part nobody could score (no reference track, no meter
reading) is left out of `points_available` and named in `ungraded`; the total is never rescaled, so a mix with no
reference reads "41.5 of 60", not a flattering 69 of 100. There is no letter and no verdict word: the number, how much
of the 100 it was judged against, and what was left out.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from kenn.core.declared_target import score_declared_target

# The 30/30/40 split was decided with the owner on 14 Oct 2026 (docs/research/e2_grade_proposal_2026-10-14.md).
FULL_MARKS: dict[str, float] = {"technical_health": 30.0, "declared_target": 30.0, "reference_match": 40.0}

_WHY_UNGRADED = {
    "technical_health": "no meter reading in the session to judge",
    "declared_target": "no loudness target stated or named, and no master reading to compare",
    "reference_match": "no reference track supplied",
}


def combine_grade(
    *,
    technical: Optional[dict[str, Any]] = None,
    declared_target: Optional[dict[str, Any]] = None,
    reference_match: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Add the three scored parts into one payload; pass None for a part that was not run.

    `technical` is `MixAuditReport.to_dict()`; the other two are the dicts `score_declared_target` and
    `score_reference_match` return. A part that was run but had nothing scorable (`points_available` of 0) is treated
    the same as one that was not run. The same inputs always give the same payload.
    """
    given = {
        "technical_health": None if technical is None else {
            "points": technical["mqm_score"],
            "points_available": technical["points_available"],
            "note": technical["meaning"],
        },
        "declared_target": declared_target,
        "reference_match": reference_match,
    }
    parts: list[dict[str, Any]] = []
    ungraded: list[dict[str, str]] = []
    for name, part in given.items():
        if not part or not part["points_available"]:
            ungraded.append({"part": name, "reason": _WHY_UNGRADED[name]})
            continue
        parts.append({
            "part": name,
            "points": round(part["points"], 1),
            "points_available": part["points_available"],
            "full_marks": FULL_MARKS[name],
            # Sub-scores that were left out inside a part we did grade (a mono file has no width to compare).
            "left_out": list(part.get("unscored", [])),
            "note": part.get("note", ""),
        })

    points = round(sum(p["points"] for p in parts), 1)
    available = sum(p["points_available"] for p in parts)
    meaning = f"{points:.1f} of {available:.0f} points available, out of a possible {sum(FULL_MARKS.values()):.0f}"
    if ungraded:
        meaning += "; not graded: " + ", ".join(f"{u['part'].replace('_', ' ')} ({u['reason']})" for u in ungraded)
    return {
        "points": points,
        "points_available": available,
        "full_marks": sum(FULL_MARKS.values()),
        "meaning": meaning + ".",
        "parts": parts,
        "ungraded": ungraded,
    }


# Loudness and ceiling are always negative in practice, so we only accept a figure with its minus sign. That keeps
# "give me 2 dBTP of headroom" or "a 3 LUFS boost" from being read as a stated target.
_STATED_LUFS = re.compile(r"(?<![\w.])(-\s?\d{1,2}(?:\.\d+)?)\s*lufs", re.IGNORECASE)
_STATED_CEILING = re.compile(r"(?<![\w.])(-\s?\d{1,2}(?:\.\d+)?)\s*dbtp", re.IGNORECASE)


def stated_target_from_text(text: str) -> dict[str, Any]:
    """Read the target a producer named or stated in plain words; returns kwargs for `score_declared_target`.

    Only Spotify and the AES figure are named targets (see STREAMING_TARGETS). An unnamed target with no figures
    gives {}, which scores the default -1 dBTP ceiling and leaves loudness ungraded.
    """
    lowered = (text or "").lower()
    found: dict[str, Any] = {}
    if "spotify" in lowered:
        found["target"] = "spotify"
    elif re.search(r"\baes\b", lowered):
        found["target"] = "aes_streaming_music"
    loudness = _STATED_LUFS.search(text or "")
    if loudness:
        found["stated_lufs"] = float(loudness.group(1).replace(" ", ""))
    ceiling = _STATED_CEILING.search(text or "")
    if ceiling:
        found["stated_ceiling_dbtp"] = float(ceiling.group(1).replace(" ", ""))
    return found


def grade_session(
    technical: dict[str, Any],
    meters: Optional[dict[str, Any]] = None,
    request: str = "",
    reference_match: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """The combined grade for one audit: `technical` is `MixAuditReport.to_dict()`, `meters` a telemetry frame dict.

    `request` is whatever the producer typed; any target they named or stated in it is scored, otherwise only the
    default ceiling is. `reference_match` stays None until a reference track is supplied (the scorer lives in the
    mix-review package, which the backend does not import), so today the grade reads out of 54 at most.
    """
    meters = meters or {}
    declared = score_declared_target(
        meters.get("integrated_lufs"), meters.get("true_peak_dbtp"), **stated_target_from_text(request)
    )
    return combine_grade(technical=technical, declared_target=declared, reference_match=reference_match)
