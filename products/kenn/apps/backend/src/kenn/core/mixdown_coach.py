"""Evidence-bounded listening guidance from a supplied mix/reference comparison."""
from __future__ import annotations

import math
from typing import Any


SCHEMA = "kenn.mixdown_coach.v1"
MAX_LISTENING_CHECKS = 5
_MIN_TONAL_DELTA_DB = 1.5
_LEVEL_MATCH_DELTA_DB = 1.0


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _region(frequency_hz: float) -> str:
    if frequency_hz < 80:
        return "sub"
    if frequency_hz < 250:
        return "low end"
    if frequency_hz < 600:
        return "low mids"
    if frequency_hz < 2000:
        return "mids"
    if frequency_hz < 6000:
        return "upper mids"
    return "high end"


def _listening_action(frequency_hz: float, delta_db: float) -> str:
    direction = "more" if delta_db > 0 else "less"
    region = _region(frequency_hz)
    if region == "low mids":
        focus = "low-mid masking between bass, kick, and musical layers"
    elif region in {"sub", "low end"}:
        focus = "the kick/bass relationship and unnecessary sub energy"
    elif region == "high end":
        focus = "hats, cymbals, vocal air, and any bright effects"
    else:
        focus = f"the contributors to {region} presence"
    return (
        f"Around {frequency_hz:.0f} Hz the mix is {abs(delta_db):.1f} dB {direction} prominent than the uploaded reference. "
        f"Level-match equivalent sections, then audition {focus} before making a broad tonal change."
    )


def _select_distinct_deltas(comparison: dict[str, Any]) -> list[tuple[float, float]]:
    rows = comparison.get("ltas_40_band_deltas") or []
    largest = comparison.get("largest_ltas_difference")
    if isinstance(largest, dict):
        rows = [largest, *rows]
    candidates: list[tuple[float, float]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        frequency, delta = _number(row.get("center_hz")), _number(row.get("delta_db"))
        if frequency is None or delta is None or frequency <= 0 or abs(delta) < _MIN_TONAL_DELTA_DB:
            continue
        if any(abs(math.log2(frequency / previous_frequency)) < 0.75 for previous_frequency, _ in candidates):
            continue
        candidates.append((frequency, delta))
        if len(candidates) >= MAX_LISTENING_CHECKS:
            break
    return candidates


def _pink_noise_check(comparison: dict[str, Any]) -> dict[str, Any] | None:
    """Render one bounded listening check from the explicit pink baseline."""
    reference = comparison.get("pink_noise_reference")
    largest = reference.get("largest_deviation") if isinstance(reference, dict) else None
    if not isinstance(largest, dict):
        return None
    frequency = _number(largest.get("center_hz"))
    deviation = _number(largest.get("deviation_db"))
    if frequency is None or deviation is None or abs(deviation) < _MIN_TONAL_DELTA_DB:
        return None
    direction = "above" if deviation > 0 else "below"
    return {
        "kind": "pink_noise_shape",
        "confidence": 0.78,
        "frequency_hz": round(frequency, 1),
        "deviation_db": round(deviation, 2),
        "observation": f"The measured LTAS is {abs(deviation):.1f} dB {direction} the explicit -3 dB/octave pink-noise-style baseline around {frequency:.0f} Hz.",
        "action": "Level-match the mix and listen to the relevant sources in the full arrangement; treat this as a broad reference lens, not a reason to EQ the master automatically.",
        "advisory_only": True,
    }


def build_mixdown_coach(review: dict[str, Any] | None) -> dict[str, Any]:
    """Produce a small read-only listening plan without assigning a Live cause.

    The input must be a completed uploaded/rendered Mix Review. The output
    never contains a command, a responsible track assertion, or a universal
    target curve; it is deliberately suitable as context for a producer or a
    separately confirmation-gated proposal flow.
    """
    review = review if isinstance(review, dict) else {}
    comparison = review.get("reference_comparison")
    if not isinstance(comparison, dict):
        return {
            "schema": SCHEMA, "status": "abstain", "listening_checks": [],
            "reason": "No uploaded-reference LTAS comparison is available.",
            "limitations": ["A whole-mix review cannot be inferred from Live structure or a genre label."],
            "live_target_inference_allowed": False,
        }

    tonal_deltas = _select_distinct_deltas(comparison)
    pink_check = _pink_noise_check(comparison)
    if not tonal_deltas and pink_check is None:
        return {
            "schema": SCHEMA, "status": "abstain", "listening_checks": [],
            "reason": "The reference comparison has no sufficiently distinct measured tonal difference to prioritise.",
            "limitations": ["This is not a declaration that the mix and reference sound the same."],
            "live_target_inference_allowed": False,
        }

    checks: list[dict[str, Any]] = []
    lufs_delta = _number(comparison.get("lufs_delta_db"))
    if lufs_delta is not None and abs(lufs_delta) > _LEVEL_MATCH_DELTA_DB:
        checks.append({
            "kind": "level_match", "priority": len(checks) + 1, "confidence": 0.98,
            "observation": f"Integrated loudness differs by {lufs_delta:+.1f} dB between the supplied renders.",
            "action": "Level-match equivalent musical sections before deciding whether a tonal difference needs a change.",
            "advisory_only": True,
        })
    if pink_check is not None and len(checks) < MAX_LISTENING_CHECKS:
        pink_check["priority"] = len(checks) + 1
        checks.append(pink_check)
    for frequency, delta in tonal_deltas[: MAX_LISTENING_CHECKS - len(checks)]:
        checks.append({
            "kind": "reference_ltas", "priority": len(checks) + 1, "confidence": 0.85,
            "frequency_hz": round(frequency, 1), "delta_db": round(delta, 2),
            "observation": f"Normalised 40-band LTAS differs by {delta:+.1f} dB around {frequency:.0f} Hz.",
            "action": _listening_action(frequency, delta), "advisory_only": True,
        })
    return {
        "schema": SCHEMA, "status": "ready", "listening_checks": checks,
        "comparison_basis": str(comparison.get("comparison_basis") or "Uploaded 40-band LTAS comparison."),
        "live_target_inference_allowed": False,
        "limitations": [
            "The measurements compare supplied renders, not a universal pink-noise or genre target.",
            "They do not identify the track, device, arrangement choice, or processing responsible for a difference.",
            "Any EQ move remains an auditionable, confirmation-gated proposal—not an automatic master change.",
        ],
    }
