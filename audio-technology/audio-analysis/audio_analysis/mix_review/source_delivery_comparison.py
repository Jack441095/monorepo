"""Before/after evidence for an AutoMix render: the raw uploaded stems
(unprocessed, unity-gain sum) versus the finished delivered mixdown.

Unlike match_report.py's build_match_evidence(), there is no reference track
here -- this is a plain two-way comparison answering "what did AutoMix
actually change," using the same 7-band spectral split and loudness metrics
Mix Review already reports for a single file.

    from audio_analysis.mix_review.source_delivery_comparison import (
        build_source_vs_delivery_comparison)
    comparison = build_source_vs_delivery_comparison(source_bytes, delivered_bytes)
"""

from __future__ import annotations

_COMPARISON_FIELDS = (
    "integrated_lufs",
    "true_peak_dbfs",
    "crest_factor_db",
    "stereo_correlation",
    "technical_score",
)


def _snapshot(report: dict) -> dict:
    metrics = report.get("metrics", {}) if isinstance(report, dict) else {}
    return {
        "bands": metrics.get("bands"),
        "perceptual_bands": metrics.get("perceptual_bands"),
        "integrated_lufs": metrics.get("integrated_lufs"),
        "true_peak_dbfs": metrics.get("true_peak_dbfs"),
        "crest_factor_db": metrics.get("crest_factor_db"),
        "stereo_correlation": metrics.get("stereo_correlation"),
        "clipped_frames_estimate": metrics.get("clipped_frames_estimate"),
        "clipping_risk": metrics.get("clipping_risk"),
        "technical_score": metrics.get("technical_score"),
        "technical_rating": metrics.get("technical_rating"),
        # The source-bound feature receipt is intentionally separate from
        # the richer report so a later agent can identify exactly which file
        # produced these measurements.
        "feature_set": report.get("feature_set") if isinstance(report, dict) else None,
    }


def build_quality_receipt(comparison: dict, quality_gate: dict | None) -> dict:
    """Build a verification receipt from real before/after analyses only.

    It does not judge whether a creative choice was good.  It records the
    precise source/delivery feature provenance, measured deltas, and the
    existing renderer safety gate so KENN can explain a completed render
    without blurring recommendation, measurement, and validation.
    """
    before = comparison.get("before") if isinstance(comparison, dict) else None
    after = comparison.get("after") if isinstance(comparison, dict) else None
    deltas = comparison.get("deltas") if isinstance(comparison, dict) else None
    before_features = before.get("feature_set") if isinstance(before, dict) else None
    after_features = after.get("feature_set") if isinstance(after, dict) else None
    valid_comparison = isinstance(before_features, dict) and isinstance(after_features, dict) and isinstance(deltas, dict)
    gate = quality_gate if isinstance(quality_gate, dict) else {}
    return {
        "schema": "automix.quality_receipt.v1",
        "verification_available": valid_comparison,
        "source_feature_set": before_features if isinstance(before_features, dict) else None,
        "delivery_feature_set": after_features if isinstance(after_features, dict) else None,
        "measured_deltas": deltas if isinstance(deltas, dict) else {},
        "safety_gate": {
            "passed": gate.get("passed"),
            "safety_passed": gate.get("safety_passed"),
            "advisory_score_passed": gate.get("advisory_score_passed"),
            "technical_score": gate.get("technical_score"),
            "minimum_score": gate.get("minimum_score"),
            "hard_failures": list(gate.get("hard_failures") or []),
        },
        "limitations": (
            "Receipt verifies measured source-to-delivery changes and delivery safety; "
            "it does not establish whether a creative balance choice is preferred."
        ),
    }


def build_source_vs_delivery_comparison(
    source_wav_bytes: bytes,
    delivered_wav_bytes: bytes,
    *,
    mix_goal: str = "premaster",
) -> dict:
    """Analyze both the raw source baseline and the delivered mixdown with
    the same Mix Review pipeline, and package a focused before/after view:
    7-band spectral (raw + perceptual), LUFS, true peak, crest factor,
    stereo correlation, clipping, and technical score -- plus the numeric
    deltas a frontend needs directly, without recomputing them itself.
    """
    from audio_analysis.mix_review import mix_review

    source_report = mix_review.analyze_wav(source_wav_bytes, "source.wav", mix_goal=mix_goal)
    delivered_report = mix_review.analyze_wav(delivered_wav_bytes, "delivered.wav", mix_goal=mix_goal)

    before = _snapshot(source_report)
    after = _snapshot(delivered_report)

    deltas: dict[str, float | None] = {}
    for key in _COMPARISON_FIELDS:
        b, a = before.get(key), after.get(key)
        if isinstance(b, (int, float)) and isinstance(a, (int, float)):
            deltas[key] = round(float(a) - float(b), 3)
        else:
            deltas[key] = None

    return {"before": before, "after": after, "deltas": deltas}
