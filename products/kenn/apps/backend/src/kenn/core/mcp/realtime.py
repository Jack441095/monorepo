"""Advisory findings promoted from a validated realtime plug-in bus snapshot.

Split out of ``mcp_facade`` so the handler modules and ``server.py`` can share
one copy.  ``mcp_facade`` re-exports these names unchanged.
"""

from __future__ import annotations

import math
from typing import Any

from kenn.core.evidence import MAX_PLUGIN_CONTEXT_AGE_SECONDS


def _realtime_context_is_current(live_context: dict[str, Any]) -> bool:
    """Return whether retained plug-in context is fresh enough for advice."""
    freshness = live_context.get("freshness")
    if not isinstance(freshness, dict):
        return True
    current = freshness.get("current_for_diagnosis")
    if current is False:
        return False
    if current is True:
        return True
    age = freshness.get("age_seconds", live_context.get("age_seconds"))
    return not (
        isinstance(age, (int, float))
        and not isinstance(age, bool)
        and float(age) > MAX_PLUGIN_CONTEXT_AGE_SECONDS
    )


def _realtime_mix_recommendation(live_context: dict[str, Any]) -> Any | None:
    """Convert the realtime spectral observation into advisory guidance.

    Keep this separate from uploaded-render findings: a realtime bus snapshot
    has a different scope and cannot identify a responsible Live track/device.
    The companion has already validated the shape, trend, and freshness; this
    helper only formats the bounded spectral measurement for the recommendation
    list.  ``_realtime_mix_recommendations`` adds the other validated bus
    warnings while retaining this single-item helper for callers that only need
    the spectral finding.
    """
    from kenn.project_analysis import Recommendation

    # The handoff is retained longer than it is diagnostically current so a
    # client can inspect bounded history/recovery state.  Never phrase an old
    # bus snapshot as a current mix recommendation.
    if not _realtime_context_is_current(live_context):
        return None

    reference = live_context.get("pink_noise_reference")
    latest = reference.get("largest_deviation") if isinstance(reference, dict) else None
    window = live_context.get("live_window")
    shape = window.get("pink_noise_shape") if isinstance(window, dict) else None
    median = shape.get("largest_median_deviation") if isinstance(shape, dict) else None
    source = median if isinstance(median, dict) else latest
    if not isinstance(source, dict):
        return None
    frequency = source.get("center_hz")
    deviation_key = "median_deviation_db" if source is median else "deviation_db"
    deviation = source.get(deviation_key)
    if (
        isinstance(frequency, bool) or not isinstance(frequency, (int, float)) or float(frequency) <= 0
        or isinstance(deviation, bool) or not isinstance(deviation, (int, float))
        or not math.isfinite(float(frequency)) or not math.isfinite(float(deviation))
        or abs(float(deviation)) < 1.5
    ):
        return None
    direction = "above" if float(deviation) > 0 else "below"
    trend = str(window.get("status") or "insufficient") if isinstance(window, dict) else "insufficient"
    sample_count = window.get("sample_count") if isinstance(window, dict) else None
    window_note = f" across {int(sample_count)} recent frames" if isinstance(sample_count, int) and sample_count > 1 else ""
    return Recommendation(
        title=f"Realtime bus: inspect around {float(frequency):.0f} Hz",
        category="realtime_mix",
        severity="info",
        confidence=0.78,
        description=(
            f"The validated Mix Assistant plug-in bus is about {abs(float(deviation)):.1f} dB "
            f"{direction} the explicit pink-noise-style baseline around {float(frequency):.0f} Hz"
            f"{window_note}; the recent trend is {trend}."
        ),
        reason=(
            "This is a broad, uncalibrated realtime bus observation, not a track-level diagnosis, "
            "a universal target, or proof that an EQ change is needed."
        ),
        suggestedAction=(
            "Level-match and listen to the full arrangement, then audition likely source changes one at a time; "
            "do not apply automatic master EQ from this bus measurement."
        ),
        requiresConfirmation=False,
    )


def _realtime_mix_recommendations(live_context: dict[str, Any]) -> list[Any]:
    """Promote every validated current bus warning into advisory guidance.

    These findings deliberately remain bus-scoped.  They are useful for the
    assistant's next listening check, but none identifies a responsible track
    or device and none is eligible for automatic Live mutation.
    """
    from kenn.project_analysis import Recommendation

    if not _realtime_context_is_current(live_context):
        return []

    metrics = live_context
    recommendations: list[Any] = []
    peak = metrics.get("peak_dbfs")
    if isinstance(peak, (int, float)) and not isinstance(peak, bool) and float(peak) > -0.3:
        recommendations.append(Recommendation(
            title="Realtime bus: limited peak headroom",
            category="realtime_mix",
            severity="warning",
            confidence=0.95,
            description=(
                f"The current validated bus peak is {float(peak):.1f} dBFS, within 0.3 dB of full scale."
            ),
            reason=(
                "The plug-in reports a momentary bus peak, not calibrated loudness or true peak; this is a reason to listen and inspect the gain/limiter chain."
            ),
            suggestedAction=(
                "Check source gain and limiting at matched loudness, then confirm export headroom; do not lower the master automatically."
            ),
            requiresConfirmation=False,
        ))

    clipped = metrics.get("clipped_samples")
    if isinstance(clipped, (int, float)) and not isinstance(clipped, bool) and float(clipped) > 0:
        recommendations.append(Recommendation(
            title="Realtime bus: recent clipping",
            category="realtime_mix",
            severity="warning",
            confidence=0.98,
            description=(
                f"The latest validated bus block contains {int(float(clipped))} sample(s) at digital full scale."
            ),
            reason="The handoff records a recent clipped-sample count directly from the plug-in bus snapshot.",
            suggestedAction="Locate the gain or limiter stage causing the peak, audition the unclipped path, and recheck the full arrangement.",
            requiresConfirmation=False,
        ))

    correlation = metrics.get("stereo_correlation")
    if isinstance(correlation, (int, float)) and not isinstance(correlation, bool) and float(correlation) < 0.0:
        recommendations.append(Recommendation(
            title="Realtime bus: mono-compatibility risk",
            category="realtime_mix",
            severity="warning",
            confidence=0.88,
            description=f"The current validated bus stereo correlation is {float(correlation):.2f}, below zero.",
            reason="Negative correlation can indicate phase interaction that deserves an audible mono check, but it is not proof of a fault.",
            suggestedAction="Audition the arrangement in mono and compare the affected elements before changing width or polarity.",
            requiresConfirmation=False,
        ))

    width = metrics.get("stereo_width")
    if isinstance(width, (int, float)) and not isinstance(width, bool) and float(width) > 0.75:
        recommendations.append(Recommendation(
            title="Realtime bus: wide side energy",
            category="realtime_mix",
            severity="info",
            confidence=0.76,
            description=f"The current validated bus stereo-width estimate is {float(width):.2f}, above the broad 0.75 review threshold.",
            reason="Width is a stylistic choice; a broad bus estimate cannot identify which source contributes the side energy.",
            suggestedAction="Compare the mix against a level-matched reference and audition mono playback before narrowing anything.",
            requiresConfirmation=False,
        ))

    spectral = _realtime_mix_recommendation(live_context)
    if spectral is not None:
        recommendations.append(spectral)
    return recommendations
