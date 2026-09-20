"""Scope-aware comparison between a live plug-in bus and an uploaded review."""
from __future__ import annotations

import math
from typing import Any


SCHEMA = "kenn.realtime_mix_comparison.v1"


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _metric_row(
    *,
    key: str,
    label: str,
    unit: str,
    live_value: float,
    uploaded_value: float,
    live_scope: str,
    uploaded_scope: str,
) -> dict[str, Any]:
    return {
        "metric": key,
        "label": label,
        "unit": unit,
        "live_value": round(live_value, 3),
        "uploaded_value": round(uploaded_value, 3),
        "delta_live_minus_uploaded": round(live_value - uploaded_value, 3),
        "live_scope": live_scope,
        "uploaded_scope": uploaded_scope,
        "comparison_status": "directional_same_metric_different_window",
    }


def _pink_shape_summary(live_context: dict[str, Any], review: dict[str, Any]) -> dict[str, Any] | None:
    live_reference = live_context.get("pink_noise_reference")
    live_largest = live_reference.get("largest_deviation") if isinstance(live_reference, dict) else None
    comparison = review.get("reference_comparison")
    uploaded_reference = comparison.get("pink_noise_reference") if isinstance(comparison, dict) else None
    uploaded_largest = uploaded_reference.get("largest_deviation") if isinstance(uploaded_reference, dict) else None
    live_frequency = _number(live_largest.get("center_hz")) if isinstance(live_largest, dict) else None
    live_deviation = _number(live_largest.get("deviation_db")) if isinstance(live_largest, dict) else None
    uploaded_frequency = _number(uploaded_largest.get("center_hz")) if isinstance(uploaded_largest, dict) else None
    uploaded_deviation = _number(uploaded_largest.get("deviation_db")) if isinstance(uploaded_largest, dict) else None
    if live_frequency is None or live_deviation is None or uploaded_frequency is None or uploaded_deviation is None:
        return None
    return {
        "status": "directional_same_baseline_different_resolution",
        "live": {
            "center_hz": round(live_frequency, 1),
            "deviation_db": round(live_deviation, 2),
            "scope": "current_or_recent_plugin_bus_window",
        },
        "uploaded": {
            "center_hz": round(uploaded_frequency, 1),
            "deviation_db": round(uploaded_deviation, 2),
            "scope": "uploaded_whole_file_ltas",
        },
        "deviation_delta_db": round(live_deviation - uploaded_deviation, 2),
        "frequency_difference_hz": round(live_frequency - uploaded_frequency, 1),
        "interpretation": (
            "Both observations use a -3 dB/octave pink-noise-style baseline, but the plug-in uses broad fixed bands "
            "and a short realtime window while the uploaded review uses a whole-file LTAS. Use this to prioritise listening, "
            "not as a direct EQ correction."
        ),
    }


def build_realtime_mix_comparison(
    review: dict[str, Any] | None,
    live_context: dict[str, Any] | None,
    *,
    review_id: str,
    plugin_session_id: str,
) -> dict[str, Any]:
    """Compare two evidence sources without assigning a Live cause or target."""
    review = review if isinstance(review, dict) else {}
    live_context = live_context if isinstance(live_context, dict) else {}
    freshness = live_context.get("freshness") if isinstance(live_context.get("freshness"), dict) else {}
    live_current = freshness.get("current_for_diagnosis") is not False and not (
        isinstance(freshness.get("age_seconds"), (int, float))
        and not isinstance(freshness.get("age_seconds"), bool)
        and float(freshness["age_seconds"]) > 15.0
    )
    uploaded_metrics = review.get("metrics") if isinstance(review.get("metrics"), dict) else {}
    comparisons: list[dict[str, Any]] = []
    metric_specs = (
        ("peak_dbfs", "Sample peak", "dBFS"),
        ("rms_dbfs", "Unweighted RMS", "dBFS"),
        ("crest_factor_db", "Crest factor", "dB"),
    )
    for key, label, unit in metric_specs:
        if not live_current:
            break
        live_key = "crest_db" if key == "crest_factor_db" else key
        live_value = _number(live_context.get(live_key))
        uploaded_value = _number(uploaded_metrics.get(key))
        if live_value is None or uploaded_value is None:
            continue
        comparisons.append(_metric_row(
            key=key,
            label=label,
            unit=unit,
            live_value=live_value,
            uploaded_value=uploaded_value,
            live_scope="current_or_recent_plugin_bus_window",
            uploaded_scope="uploaded_whole_file_review",
        ))

    limitations = [
        "The live values are current or short-window plug-in bus observations; uploaded values are whole-file review measurements.",
        "A delta does not identify the responsible Live track, device, arrangement choice, room problem, or processing cause.",
        "No automatic EQ, gain, width, or other Live mutation is implied; level-match and audition before acting.",
    ]
    missing = []
    if _number(uploaded_metrics.get("integrated_lufs")) is not None:
        missing.append("Integrated LUFS has no like-for-like realtime counterpart.")
    if _number(uploaded_metrics.get("true_peak_dbtp")) is not None:
        missing.append("Uploaded true peak has no like-for-like realtime counterpart.")
    if missing:
        limitations.extend(missing)
    pink_shape = _pink_shape_summary(live_context, review) if live_current else None
    if pink_shape is None:
        limitations.append("No paired pink-noise-style shape observation was available from both sources.")
    if not live_current:
        limitations.append("The retained plug-in context is stale_or_unknown for current diagnosis; comparison is withheld.")
    return {
        "ok": bool(review) and bool(live_context),
        "schema": SCHEMA,
        "review_id": str(review_id)[:128],
        "plugin_session_id": str(plugin_session_id)[:128],
        "comparisons": comparisons,
        "pink_noise_shape": pink_shape,
        "comparison_available": bool(comparisons or pink_shape),
        "scope": {"live": "plugin_bus", "uploaded": "whole_file_mix_review"},
        "advisory_only": True,
        "capture_requested": False,
        "live_target_inference_allowed": False,
        "limitations": limitations,
    }


__all__ = ["SCHEMA", "build_realtime_mix_comparison"]
