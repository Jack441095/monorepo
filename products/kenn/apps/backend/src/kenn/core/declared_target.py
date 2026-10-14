"""Declared-target part of the E2 grade (30 points): did the master land where the producer said it should?

A target is a loudness and a true-peak ceiling. It comes from a short list of published streaming figures, or from
what the producer states, and the producer's own numbers always win. Every point lost names the figure it was
measured against and where that figure came from. There are no genre targets: nobody has given us one we can cite.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

# Loudness 20 and ceiling 10 is a design choice made on 14 Oct 2026 with the 30/30/40 split, not a measurement.
# Tolerances are placeholders to be checked against the owner's ears under E9; change them here and nowhere else.
DECLARED_TARGET_POINTS: dict[str, float] = {"loudness": 20.0, "true_peak_ceiling": 10.0}
LOUDNESS_TOLERANCE_LU = 1.0  # within 1 LU costs nothing; wide on purpose, since Tech 3341 meters agree to 0.1 LU and nobody mastered to the decimal
LOUDNESS_FULL_LOSS_LU = 6.0  # a master 6 LU off its target loses the whole loudness part
CEILING_FULL_LOSS_DB = 1.0  # a peak 1 dB over the ceiling loses the whole ceiling part; at or under costs nothing

# Spotify's page says -1 dBTP for lossy encodes, so that is the ceiling when the producer names none.
DEFAULT_CEILING_DBTP = -1.0
DEFAULT_CEILING_SOURCE = "Spotify for Artists, Loudness normalization (support.spotify.com), read 14 Oct 2026"


@dataclass(frozen=True)
class LoudnessTarget:
    name: str
    integrated_lufs: float
    ceiling_dbtp: float
    # A master louder than the target gets a lower ceiling when the source says so (Spotify: -2 dBTP above -14 LUFS).
    louder_ceiling_dbtp: Optional[float]
    source: str


# Only figures we read in the publisher's own words or a named summary of the standard. YouTube, Apple Music and
# Tidal are left out until someone reads their own pages; the secondary guides we found disagreed with each other.
STREAMING_TARGETS: dict[str, LoudnessTarget] = {
    "spotify": LoudnessTarget(
        name="Spotify",
        integrated_lufs=-14.0,
        ceiling_dbtp=-1.0,
        louder_ceiling_dbtp=-2.0,
        source="Spotify for Artists, Loudness normalization, Mastering tips (support.spotify.com), read 14 Oct 2026",
    ),
    "aes_streaming_music": LoudnessTarget(
        name="AES streaming music",
        integrated_lufs=-16.0,
        # TD1008 gives no true-peak figure in anything we could read (the -1 dBTP in the sources we found belongs to
        # its predecessor TD1004), so the ceiling is our default, not the AES's.
        ceiling_dbtp=DEFAULT_CEILING_DBTP,
        louder_ceiling_dbtp=None,
        source="AES TD1008 (2021) music distribution loudness for track-normalised services, as summarised at "
               "productionadvice.co.uk/td1008, read 14 Oct 2026; the AES document itself was not opened",
    ),
}


def _loss_fraction(gap: float, tolerance: float, full_loss: float) -> float:
    """0.0 inside the tolerance, rising in a straight line to 1.0 at full_loss and staying there.

    Same rule as `score_reference_match`; that module lives in the mix-review package, which the backend does not import.
    """
    return min(1.0, max(0.0, gap - tolerance) / (full_loss - tolerance))


def score_declared_target(
    integrated_lufs: Optional[float],
    true_peak_dbtp: Optional[float],
    *,
    target: Optional[str] = None,
    stated_lufs: Optional[float] = None,
    stated_ceiling_dbtp: Optional[float] = None,
) -> dict[str, Any]:
    """Score a master out of 30 against a named target and/or the producer's stated figures.

    The producer's stated loudness and ceiling override the named target's. With no loudness target at all (nothing
    named, nothing stated) the loudness part is `unscored`; a reading the meter did not send is `unscored` too.
    Unscored points come off `points_available` and the score is never rescaled up to 30.
    Raises KeyError for a target name that is not in STREAMING_TARGETS, so a typo cannot silently score against nothing.
    """
    named = STREAMING_TARGETS[target] if target else None
    parts: list[dict[str, Any]] = []
    unscored: list[str] = []

    goal_lufs = stated_lufs if stated_lufs is not None else (named.integrated_lufs if named else None)
    if goal_lufs is None or integrated_lufs is None:
        unscored.append("loudness")
    else:
        gap = integrated_lufs - goal_lufs
        available = DECLARED_TARGET_POINTS["loudness"]
        lost = available * _loss_fraction(abs(gap), LOUDNESS_TOLERANCE_LU, LOUDNESS_FULL_LOSS_LU)
        origin = "the loudness you stated" if stated_lufs is not None else named.source
        parts.append({
            "part": "loudness",
            "points": round(available - lost, 1),
            "points_available": available,
            "gap": round(gap, 2),
            "unit": "LU from target",
            "detail": f"integrated loudness is {integrated_lufs:.1f} LUFS against a target of {goal_lufs:.1f} LUFS",
            "source": origin,
        })

    ceiling, ceiling_origin = DEFAULT_CEILING_DBTP, DEFAULT_CEILING_SOURCE
    if stated_ceiling_dbtp is not None:
        ceiling, ceiling_origin = stated_ceiling_dbtp, "the ceiling you stated"
    elif named:
        ceiling, ceiling_origin = named.ceiling_dbtp, named.source
        # A louder-than-target master gets the stricter ceiling only when the source gives one and we know the loudness.
        if (named.louder_ceiling_dbtp is not None and integrated_lufs is not None
                and integrated_lufs > named.integrated_lufs):
            ceiling = named.louder_ceiling_dbtp

    if true_peak_dbtp is None:
        unscored.append("true_peak_ceiling")
    else:
        over = true_peak_dbtp - ceiling
        available = DECLARED_TARGET_POINTS["true_peak_ceiling"]
        # Only overs cost points: a peak well under the ceiling is headroom, not a miss.
        lost = available * _loss_fraction(max(0.0, over), 0.0, CEILING_FULL_LOSS_DB)
        parts.append({
            "part": "true_peak_ceiling",
            "points": round(available - lost, 1),
            "points_available": available,
            "gap": round(over, 2),
            "unit": "dB over the ceiling (negative is headroom)",
            "detail": f"true peak is {true_peak_dbtp:+.1f} dBTP against a ceiling of {ceiling:+.1f} dBTP",
            "source": ceiling_origin,
        })

    return {
        "points": round(sum(p["points"] for p in parts), 1),
        "points_available": sum(p["points_available"] for p in parts),
        "full_marks": sum(DECLARED_TARGET_POINTS.values()),
        "parts": parts,
        "unscored": unscored,
    }
