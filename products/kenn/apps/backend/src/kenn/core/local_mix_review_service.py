"""Local Mix Review service for the KENN companion.

The repository already owns a bounded deterministic WAV analyser in
``mix-review/core/local_engine.py``.  This adapter gives the local companion a
small metadata-only review registry so Mix Review evidence can participate in
the supervised Ableton workflow without requiring the historical external
Audio_Too package or retaining uploaded audio.
"""

from __future__ import annotations

from email.parser import BytesParser
from email.policy import default as email_default
from datetime import datetime, timezone
import copy
import functools
import hashlib
import html
import importlib.util
import json
import math
import os
from pathlib import Path
import tempfile
from threading import Lock
import uuid
from typing import Any

from kenn.core.evidence import (
    REFERENCE_SIGNAL_LIMITATION,
    UPLOADED_ACTIVITY_FLOOR_DBFS,
    UPLOADED_SIGNAL_LIMITATION,
    reference_comparison_has_activity,
    uploaded_metrics_have_activity,
)
from kenn.core.grade import grade_session
from kenn.core.mix_doctor import MixDoctor
from kenn.paths import PACKAGES_ROOT


_SERVICE_ROOT = PACKAGES_ROOT / "mix-review"
_REFERENCE_MIN_RMS_DBFS = UPLOADED_ACTIVITY_FLOOR_DBFS
_ENGINE_PATH = _SERVICE_ROOT / "core" / "local_engine.py"
_MASKING_PATH = _SERVICE_ROOT / "core" / "masking_analysis.py"
_MATCHING_PATH = _SERVICE_ROOT / "core" / "reference_matching.py"
_MAX_TEXT = 512
MAX_REVIEWS = 500


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"KENN Mix Review module was not found at {path}")
    module = importlib.util.module_from_spec(spec)
    # Register before exec so a sibling module loaded the same way (e.g.
    # masking_analysis.py's own `from local_engine import ...` fallback,
    # used when it's reached with no parent package) resolves against this
    # exact loaded instance instead of re-importing a second copy.
    import sys as _sys
    _sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_engine():
    return _load_module("local_engine", _ENGINE_PATH)


_engine = _load_engine()
MAX_UPLOAD_BYTES = int(_engine.MAX_UPLOAD_BYTES)
# "Too large" alone left testers guessing; 150 MB is about 14 minutes of 16-bit, 44.1 kHz stereo.
TOO_LARGE_ADVICE = (
    f"Mix Review takes WAV files up to {MAX_UPLOAD_BYTES // (1024 * 1024)} MB (about 14 minutes of 16-bit, "
    "44.1 kHz stereo, or 9 minutes at 24-bit). Bounce a shorter section or a 16-bit version and try again."
)
_masking_engine = _load_module("masking_analysis", _MASKING_PATH)


@functools.cache
def _matching_engine():
    return _load_module("reference_matching", _MATCHING_PATH)


def analyze_stem_masking(stems: list[tuple[str, bytes]]) -> dict[str, Any]:
    """Analyze frequency-band energy competition across 2+ time-aligned stems.

    Thin pass-through to ``mix-review/core/masking_analysis.py`` -- stateless
    and not part of the review registry below, since a masking analysis is
    evidence about a set of stems, not a single tracked mix review.
    """
    return _masking_engine.analyze_stem_masking(stems)


def _text(value: Any, limit: int = _MAX_TEXT) -> str:
    return str(value or "").strip()[:limit]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _safe_flag(finding: dict[str, Any]) -> dict[str, Any] | None:
    if not finding.get("detected"):
        return None
    family = _text(finding.get("fault_family"), 96)
    label = family.replace("_", " ").strip().title() or "Measured mix finding"
    severity = _text(finding.get("severity"), 32).lower()
    if severity not in {"critical", "high", "medium", "low", "warning", "info"}:
        severity = "low"
    confidence = finding.get("confidence")
    if not isinstance(confidence, (int, float)):
        confidence = 0.0
    return {
        "label": label,
        "detail": _text(finding.get("explanation"), 1024),
        "severity": severity,
        "confidence": max(0.0, min(1.0, float(confidence))),
        "fault_family": family,
    }


def _finite(value: Any) -> float | None:
    try:
        number = _number(value)
        return number if number is not None and math.isfinite(number) else None
    except OverflowError:
        # An unrepresentable legacy number cannot safely contribute to a score or comparison.
        return None


def _grade_from_report(
    report: dict[str, Any], *, reference_match: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The E2 grade for one uploaded file, from the readings the analyser actually took.

    Only integrated loudness, true peak, crest factor and (for stereo files) the mean windowed correlation are handed
    to the Mix Doctor. The 7-band shares are not the Doctor's 20-60 / 200-500 / 2-6k / 10-20k Hz bands, so spectral
    balance is left unscored instead of guessed. A mono file has no correlation to read: the engine fills its timeline
    with 1.0, which would read as a perfect stereo image.
    """
    metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else {}
    source_is_significant = uploaded_metrics_have_activity(metrics)
    meters: dict[str, float] = {}
    if source_is_significant:
        for key in ("integrated_lufs", "true_peak_dbtp", "crest_factor_db"):
            value = _finite(metrics.get(key))
            if value is not None:
                meters[key] = value
        layout = (report.get("input_context") or {}).get("channel_layout")
        timeline = metrics.get("correlation_timeline")
        windows = [v for v in (timeline.get("correlation") if isinstance(timeline, dict) else None) or [] if _finite(v) is not None]
        if layout == "stereo" and windows:
            meters["phase_correlation"] = sum(windows) / len(windows)
    # No session behind an uploaded file, so there are no tracks for the Doctor's name and fader advice to read.
    technical = MixDoctor().audit_session({"tracks": []}, meters=meters).to_dict()
    # Only the comparison for this upload may contribute reference points; ordinary reviews leave it absent.
    if not source_is_significant:
        # Keep the scorer's explicit quiet-side reason, but never let a stale or inconsistent score through.
        reason = None
        if isinstance(reference_match, dict) and _finite(reference_match.get("points_available")) == 0.0:
            reason = reference_match.get("note")
        reference_match = {
            "points": 0.0,
            "points_available": 0.0,
            "note": reason if isinstance(reason, str) and reason else UPLOADED_SIGNAL_LIMITATION,
        }
    return grade_session(technical, meters, reference_match=reference_match)


def _review_from_report(
    report: dict[str, Any],
    *,
    review_id: str,
    filename: str,
    source_sha256: str,
    project_id: str,
    reference_match: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw_metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else {}
    source_is_significant = uploaded_metrics_have_activity(raw_metrics)
    signal_limitation = UPLOADED_SIGNAL_LIMITATION if not source_is_significant else None
    findings = []
    if source_is_significant:
        findings = [
            flag for flag in (_safe_flag(item) for item in report.get("findings") or [] if isinstance(item, dict))
            if flag is not None
        ]
    limitations = report.get("limitations", "")
    if signal_limitation:
        limitations = f"{limitations} {signal_limitation}".strip()
    return {
        "schema": "kenn.mix_review.local_review.v1",
        "review_id": review_id,
        "created_at": _text(report.get("timestamp"), 64),
        "status": "completed" if report.get("ok", False) else "failed",
        "analysis_version": _text(report.get("analysis_version"), 128),
        "source": {"filename": Path(filename).name[:256], "sha256": source_sha256},
        "project_id": _text(project_id, 128),
        "input_context": report.get("input_context", {}) if isinstance(report.get("input_context"), dict) else {},
        "metrics": raw_metrics if source_is_significant else {},
        "evidence": report.get("evidence") if source_is_significant and isinstance(report.get("evidence"), dict) else None,
        "findings": report.get("findings", []) if source_is_significant and isinstance(report.get("findings"), list) else [],
        "flags": findings,
        "action_plan": report.get("action_plan", []) if source_is_significant and isinstance(report.get("action_plan"), list) else [],
        "technical_rating": _text(report.get("technical_rating"), 128) if source_is_significant else "",
        "grade": _grade_from_report(report, reference_match=reference_match),
        "signal_limitation": signal_limitation,
        "limitations": limitations,
        "qualified_fault_families": report.get("qualified_fault_families", []),
        "not_evaluated_fault_families": report.get("not_evaluated_fault_families", []),
        "storage": "metadata_only",
        "audio_retained": False,
        "external_network": False,
    }


def _published_review(review: dict[str, Any]) -> dict[str, Any]:
    """Return a publication-safe copy of a stored review, including legacy receipts."""
    published = copy.deepcopy(review)
    schema = published.get("schema")
    if schema == "kenn.mix_review.reference_comparison.v1":
        comparison = published.get("reference_comparison")
        if reference_comparison_has_activity(comparison):
            return published
        dynamics = comparison.get("dynamics") if isinstance(comparison, dict) else {}
        if isinstance(dynamics, dict) and isinstance(dynamics.get("mix"), dict):
            mix_active = uploaded_metrics_have_activity(dynamics["mix"])
        else:
            mix_active = uploaded_metrics_have_activity(published.get("mix_metrics"))
        published.pop("reference_comparison", None)
        grade = published.get("grade") if isinstance(published.get("grade"), dict) else {}
        published["grade"] = _grade_without_reference_match(
            grade, retain_mix_grade=mix_active,
        )
        for key in (
            "metrics", "evidence", "findings", "flags", "action_plan", "technical_rating",
            "qualified_fault_families", "not_evaluated_fault_families", "analysis_evidence",
        ):
            published.pop(key, None)
        if not uploaded_metrics_have_activity(published.get("mix_metrics")):
            # A comparison's RMS can qualify the mix without exposing an unqualified metric bundle.
            published.pop("mix_metrics", None)
        _append_reference_limitation(published)
        return published
    if schema != "kenn.mix_review.local_review.v1":
        # Other registry records have different source and significance contracts.
        return published
    metrics = published.get("metrics") if isinstance(published.get("metrics"), dict) else {}
    if uploaded_metrics_have_activity(metrics):
        comparison = published.get("reference_comparison")
        if isinstance(comparison, dict) and not reference_comparison_has_activity(comparison):
            published.pop("reference_comparison", None)
            grade = published.get("grade") if isinstance(published.get("grade"), dict) else {}
            published["grade"] = _grade_without_reference_match(grade, retain_mix_grade=True)
            _append_reference_limitation(published)
        return published

    original_metrics = review.get("metrics") if isinstance(review.get("metrics"), dict) else {}
    reference_match = None
    comparison = review.get("reference_comparison")
    score = comparison.get("reference_match_score") if isinstance(comparison, dict) else None
    if isinstance(score, dict):
        reference_match = score
    report = {
        "metrics": original_metrics,
        "input_context": review.get("input_context") if isinstance(review.get("input_context"), dict) else {},
    }
    for key in (
        "metrics", "evidence", "findings", "flags", "action_plan", "technical_rating",
        "qualified_fault_families", "not_evaluated_fault_families",
    ):
        if key in {"metrics", "evidence"}:
            published[key] = {} if key == "metrics" else None
        elif key == "technical_rating":
            published[key] = ""
        else:
            published[key] = []
    # A legacy comparison bundles spectral deltas, tonal profiles, and EQ actions in one object.
    published.pop("reference_comparison", None)
    published["grade"] = _grade_from_report(report, reference_match=reference_match)
    published["signal_limitation"] = UPLOADED_SIGNAL_LIMITATION
    limitations = published.get("limitations")
    if not isinstance(limitations, str):
        # Legacy records without narrative limitations still need an explicit abstention reason.
        limitations = ""
    if UPLOADED_SIGNAL_LIMITATION not in limitations:
        limitations = f"{limitations} {UPLOADED_SIGNAL_LIMITATION}".strip()
    published["limitations"] = limitations
    return published


def _grade_without_reference_match(grade: dict[str, Any], *, retain_mix_grade: bool) -> dict[str, Any]:
    """Remove only the paired score when saved parts let us recompute the remaining grade exactly."""
    ungraded = grade.get("ungraded") if isinstance(grade.get("ungraded"), list) else []
    prior_reason = next((
        _text(item.get("reason"), 512)
        for item in ungraded
        if isinstance(item, dict) and item.get("part") == "reference_match" and item.get("reason")
    ), REFERENCE_SIGNAL_LIMITATION)
    parts = grade.get("parts")
    if not retain_mix_grade or not isinstance(parts, list):
        # Without qualified mix RMS and explicit parts, the old aggregate cannot be separated safely.
        return {
            "points": 0.0,
            "points_available": 0.0,
            "full_marks": grade.get("full_marks", 100.0),
            "meaning": "0.0 of 0 points available; reference comparison withheld.",
            "parts": [],
            "ungraded": [{"part": "reference_match", "reason": prior_reason}],
        }
    safe_parts = []
    for part in parts:
        if not isinstance(part, dict) or not isinstance(part.get("part"), str):
            # A malformed own-grade part prevents an exact aggregate from being rebuilt.
            return _grade_without_reference_match({}, retain_mix_grade=False)
        if part["part"] == "reference_match":
            continue
        points_value = _finite(part.get("points"))
        available_value = _finite(part.get("points_available"))
        if points_value is None or available_value is None:
            # Keep only scores whose saved components can be added without guessing.
            return _grade_without_reference_match({}, retain_mix_grade=False)
        safe_parts.append(copy.deepcopy(part))
    full_marks = _finite(grade.get("full_marks"))
    if full_marks is None:
        # E2 grades use a fixed 100-point total, so an old missing field has a known default.
        full_marks = 100.0
    points = round(sum(float(part["points"]) for part in safe_parts), 1)
    available = sum(float(part["points_available"]) for part in safe_parts)
    ungraded = [copy.deepcopy(item) for item in ungraded if isinstance(item, dict) and item.get("part") != "reference_match"]
    ungraded.append({"part": "reference_match", "reason": prior_reason})
    meaning = f"{points:.1f} of {available:.0f} points available, out of a possible {full_marks:.0f}; reference comparison withheld."
    return {**grade, "points": points, "points_available": available, "meaning": meaning, "parts": safe_parts, "ungraded": ungraded}


def _append_reference_limitation(review: dict[str, Any]) -> None:
    limitations = review.get("limitations")
    if isinstance(limitations, list):
        values = list(limitations)
        if REFERENCE_SIGNAL_LIMITATION not in values:
            values.append(REFERENCE_SIGNAL_LIMITATION)
        review["limitations"] = values
    else:
        text = limitations if isinstance(limitations, str) else ""
        if REFERENCE_SIGNAL_LIMITATION not in text:
            text = f"{text} {REFERENCE_SIGNAL_LIMITATION}".strip()
        review["limitations"] = text


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _ltas_comparison(mix_spectral: dict[str, Any], reference_spectral: dict[str, Any]) -> list[dict[str, Any]]:
    mix_rows = mix_spectral.get("ltas_40_band_relative_db") or []
    reference_rows = reference_spectral.get("ltas_40_band_relative_db") or []
    mix_by_index = {row.get("index"): row for row in mix_rows if isinstance(row, dict)}
    reference_by_index = {row.get("index"): row for row in reference_rows if isinstance(row, dict)}
    deltas = []
    for index in sorted(set(mix_by_index) & set(reference_by_index)):
        mix, reference = mix_by_index[index], reference_by_index[index]
        mix_level, reference_level = _number(mix.get("relative_db")), _number(reference.get("relative_db"))
        center_hz = _number(mix.get("center_hz"))
        if mix_level is None or reference_level is None or center_hz is None:
            continue
        deltas.append({
            "index": index,
            "center_hz": round(center_hz, 2),
            "low_hz": mix.get("low_hz"),
            "high_hz": mix.get("high_hz"),
            "mix_relative_db": round(mix_level, 3),
            "reference_relative_db": round(reference_level, 3),
            "delta_db": round(mix_level - reference_level, 3),
        })
    return sorted(deltas, key=lambda item: abs(float(item["delta_db"])), reverse=True)


def _advisory_eq_moves(ltas_deltas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Suggest only bounded, partial starting points; never an auto-apply."""
    moves = []
    for item in ltas_deltas:
        delta = _number(item.get("delta_db"))
        frequency = _number(item.get("center_hz"))
        if delta is None or frequency is None or abs(delta) < 1.5:
            continue
        gain = max(-3.0, min(3.0, -delta * 0.5))
        moves.append({
            "freq": round(frequency, 1),
            "gain": round(gain, 2),
            "q": 0.7,
            "reason": "Advisory partial move from uploaded-reference LTAS; level-match, audition, and bypass before keeping it.",
        })
        if len(moves) >= 5:
            break
    return moves


def compare_reference_audio(
    mix_bytes: bytes,
    mix_filename: str,
    reference_bytes: bytes,
    reference_filename: str,
) -> dict[str, Any]:
    """Measure two local WAV renders without retaining either audio payload.

    This is deliberately a comparison, not an automatic matching engine. A
    measured spectral or loudness delta does not identify its musical cause or
    imply that the uploaded reference should be copied.
    """
    inputs = (("Mix", mix_bytes, mix_filename), ("Reference", reference_bytes, reference_filename))
    reports: list[dict[str, Any]] = []
    spectral_reports: list[dict[str, Any]] = []
    for label, payload, filename in inputs:
        if not isinstance(payload, (bytes, bytearray)) or not payload:
            return {"ok": False, "error": f"{label} WAV is empty."}
        if len(payload) > MAX_UPLOAD_BYTES:
            return {"ok": False, "error": f"{label} WAV is too large. {TOO_LARGE_ADVICE}"}
        clean_name = Path(str(filename or f"{label.lower()}.wav")).name[:256] or f"{label.lower()}.wav"
        if Path(clean_name).suffix.lower() not in _engine.DECODABLE_SUFFIXES:
            return {"ok": False, "error": f"{label} must be a supported WAV file."}
        validation = _engine.validate_wav_upload(bytes(payload), clean_name, label=label)
        if not validation.get("ok"):
            return {"ok": False, "error": str(validation.get("error") or f"{label} WAV validation failed.")}
        try:
            reports.append(dict(_engine.analyze_wav(bytes(payload), filename=clean_name, mix_goal="reference_comparison")))
            from kenn.core.audio_analysis import analyze_wav
            spectral_reports.append(dict(
                analyze_wav(
                    bytes(payload),
                    filename=clean_name,
                    include_ltas=True,
                    include_pink_noise_reference=True,
                )
            ))
        except Exception as exc:
            return {"ok": False, "error": f"{label} analysis failed: {type(exc).__name__}: {exc}"}

    mix_report, reference_report = reports
    mix_spectral, reference_spectral = spectral_reports

    matching_result = None
    try:
        # A bare `from reference_matching import` only worked when some other import had put
        # mix-review/core on sys.path; the companion never does, so Reference Match quietly lost
        # its tonal balance, matching gains and EQ Eight preset (found Sept 2026).
        compare_mix_to_reference = _matching_engine().compare_mix_to_reference
        matching_result = compare_mix_to_reference(
            mix_bytes,
            reference_bytes,
            mix_name=Path(mix_filename).name[:256],
            ref_name=Path(reference_filename).name[:256],
        )
    except Exception:
        # A failed optional matcher leaves comparison details unavailable rather than guessed.
        matching_result = None

    dynamics = (matching_result or {}).get("dynamics") or {}
    comparison_is_significant = all(
        (rms := _finite((dynamics.get(source) or {}).get("rms_dbfs"))) is not None
        and rms > _REFERENCE_MIN_RMS_DBFS
        for source in ("mix", "reference")
    )

    mix_spectral_data = mix_spectral.get("spectral") or {}
    reference_spectral_data = reference_spectral.get("spectral") or {}
    mix_bands = mix_spectral_data.get("band_energy_dbfs") or {}
    reference_bands = reference_spectral_data.get("band_energy_dbfs") or {}
    band_deltas = []
    for band in sorted(set(mix_bands) & set(reference_bands)):
        mix_level, reference_level = _number(mix_bands.get(band)), _number(reference_bands.get(band))
        if mix_level is None or reference_level is None:
            continue
        band_deltas.append({
            "band": band,
            "mix_dbfs": round(mix_level, 2),
            "reference_dbfs": round(reference_level, 2),
            "delta_db": round(mix_level - reference_level, 2),
        })
    band_deltas.sort(key=lambda item: abs(float(item["delta_db"])), reverse=True)
    if not comparison_is_significant:
        band_deltas = []
    largest = band_deltas[0] if band_deltas else None
    ltas_deltas = _ltas_comparison(mix_spectral_data, reference_spectral_data) if comparison_is_significant else []
    largest_ltas = ltas_deltas[0] if ltas_deltas else None
    pink_noise = mix_spectral_data.get("pink_noise_reference")
    pink_noise_summary = None
    if comparison_is_significant and isinstance(pink_noise, dict):
        largest_pink = pink_noise.get("largest_deviation")
        if isinstance(largest_pink, dict):
            pink_noise_summary = {
                "status": _text(pink_noise.get("status"), 32),
                "curve": _text(pink_noise.get("curve"), 128),
                "slope_db_per_octave": pink_noise.get("slope_db_per_octave"),
                "anchor_frequency_hz": pink_noise.get("anchor_frequency_hz"),
                "largest_deviation": {
                    key: largest_pink[key]
                    for key in ("center_hz", "measured_relative_db", "pink_expected_relative_db", "deviation_db")
                    if key in largest_pink
                },
                "limitations": [
                    "This is a broad spectral-shape reference, not a universal mix target or quality score.",
                    "A deviation does not identify a track, arrangement choice, room problem, or processing cause.",
                ],
            }
    mix_lufs = _number((mix_report.get("metrics") or {}).get("integrated_lufs"))
    reference_lufs = _number((reference_report.get("metrics") or {}).get("integrated_lufs"))
    lufs_delta = (
        round(mix_lufs - reference_lufs, 2)
        if comparison_is_significant and mix_lufs is not None and reference_lufs is not None
        else None
    )

    reference_score = {
        "points": 0.0,
        "points_available": 0.0,
        "note": "reference supplied, but reference-match analysis unavailable",
    }
    ref_comp: dict[str, Any] = {
        # Keep an unavailable result explicit so callers cannot mistake it for an omitted reference.
        "reference_match_score": reference_score,
        "largest_spectral_difference": largest,
        "largest_ltas_difference": largest_ltas,
        "ltas_40_band_deltas": ltas_deltas[:8],
        "eq_bands": _advisory_eq_moves(ltas_deltas),
        "lufs_delta_db": lufs_delta,
        "pink_noise_reference": pink_noise_summary,
        "comparison_basis": "Each 40-band logarithmic LTAS is normalised around 1 kHz; it is measured against the uploaded reference, not a universal pink-noise target.",
    }
    if matching_result and matching_result.get("ok"):
        reference_score = matching_result.get("reference_match_score") or reference_score
        ref_comp["reference_match_score"] = reference_score
        if comparison_is_significant:
            # Keep actionable gaps beside the grade only when both renders clear the significance floor.
            ref_comp.update({
                "tonal_balance_7band": matching_result.get("tonal_balance"),
                "matching_gains_db": matching_result.get("matching_gains_db"),
                "dynamics": matching_result.get("dynamics"),
                "stereo": matching_result.get("stereo"),
                "coaching": matching_result.get("coaching_summary"),
                "recommendations": matching_result.get("recommendations"),
                "eq8_preset_adv_base64": matching_result.get("eq8_preset_adv_base64"),
            })

    result = {
        "schema": "kenn.mix_review.reference_comparison.v1",
        "ok": bool(mix_report.get("ok")) and bool(reference_report.get("ok")),
        "analysis_version": _text(mix_report.get("analysis_version"), 128),
        "reference_comparison": ref_comp,
        "grade": _grade_from_report(mix_report, reference_match=reference_score),
        "source_mix": {"filename": Path(mix_filename).name[:256], "sha256": hashlib.sha256(mix_bytes).hexdigest()},
        "source_reference": {"filename": Path(reference_filename).name[:256], "sha256": hashlib.sha256(reference_bytes).hexdigest()},
        "storage": "in_memory_only",
        "audio_retained": False,
        "external_network": False,
        "limitations": [
            "Differences are whole-file measurements, not a judgement of which mix is better.",
            "Level-match and compare equivalent musical sections before making tonal changes.",
            "The comparison cannot identify the source, arrangement, or processing responsible for a difference.",
        ],
    }
    if not comparison_is_significant and uploaded_metrics_have_activity(mix_report.get("metrics")):
        # Retain only the independently qualified mix readings; quiet-source RMS stays private.
        result["mix_metrics"] = dict(mix_report.get("metrics") or {})
    return result


class LocalMixReviewService:
    """Small bounded review registry backed by JSON metadata outside the repo."""

    MAX_UPLOAD_BYTES = MAX_UPLOAD_BYTES
    MAX_REVIEWS = MAX_REVIEWS

    def __init__(self, runtime_dir: Path | str | None = None):
        configured = runtime_dir or os.getenv(
            "KENN_MIX_REVIEW_RUNTIME_DIR",
            str(Path(tempfile.gettempdir()) / "nite-kenn-mix-review"),
        )
        self.runtime_dir = Path(configured).expanduser().resolve()
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self.runtime_dir / "reviews.json"
        self._lock = Lock()
        self._reviews: dict[str, dict[str, Any]] = {}
        self.init_reviews_table()

    def init_reviews_table(self) -> None:
        with self._lock:
            try:
                raw = json.loads(self._index_path.read_text(encoding="utf-8"))
            except (FileNotFoundError, OSError, json.JSONDecodeError):
                raw = {}
            if isinstance(raw, dict):
                self._reviews = {
                    str(key): value for key, value in raw.items() if isinstance(value, dict)
                }
                if self._prune_reviews():
                    self._persist()

    def _prune_reviews(self) -> bool:
        """Retain only the newest bounded metadata records.

        ``sort_keys=True`` means JSON object order cannot represent age across
        restarts, so pruning uses the analyser timestamp stored in each review.
        The review id is a stable tie-breaker for legacy/equal timestamps.
        """
        if len(self._reviews) <= self.MAX_REVIEWS:
            return False
        ordered = sorted(
            self._reviews.items(),
            key=lambda item: (_text(item[1].get("created_at"), 64), item[0]),
        )
        self._reviews = dict(ordered[-self.MAX_REVIEWS :])
        return True

    def _persist(self) -> None:
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.runtime_dir,
                prefix=".reviews.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                json.dump(self._reviews, handle, ensure_ascii=False, sort_keys=True)
            os.chmod(temporary, 0o600)
            os.replace(temporary, self._index_path)
            os.chmod(self._index_path, 0o600)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def save_review(
        self,
        file_bytes: bytes,
        filename: str,
        *,
        project_id_override: str = "",
        mix_goal: str = "general",
        reference_audio: tuple[bytes, str] | None = None,
    ) -> dict[str, Any]:
        """Analyze a mix and optional reference, then persist measurements without either WAV payload."""
        if not isinstance(file_bytes, (bytes, bytearray)) or not file_bytes:
            return {"ok": False, "error": "Mix Review audio is empty."}
        if len(file_bytes) > self.MAX_UPLOAD_BYTES:
            return {"ok": False, "error": f"This WAV is too large. {TOO_LARGE_ADVICE}"}
        clean_filename = Path(str(filename or "mix.wav")).name[:256] or "mix.wav"
        if Path(clean_filename).suffix.lower() not in _engine.DECODABLE_SUFFIXES:
            return {"ok": False, "error": "Only WAV files are supported by the local Mix Review engine."}
        payload = bytes(file_bytes)
        validation = _engine.validate_wav_upload(payload, clean_filename, label="Local mix")
        if not validation.get("ok"):
            return {"ok": False, "error": str(validation.get("error") or "WAV validation failed.")}
        comparison = None
        if reference_audio is not None:
            reference_bytes, reference_filename = reference_audio
            if len(reference_bytes) > self.MAX_UPLOAD_BYTES:
                # The request allows two files, but each still has the same per-WAV byte limit.
                return {"ok": False, "error": f"Reference WAV is too large. {TOO_LARGE_ADVICE}"}
            comparison = compare_reference_audio(payload, clean_filename, reference_bytes, reference_filename)
            if not comparison.get("ok"):
                # Reject the pair before saving: a mix-only receipt would hide the supplied reference's failure.
                return comparison
        try:
            report = dict(_engine.analyze_wav(payload, filename=clean_filename, mix_goal=_text(mix_goal, 64)))
        except Exception as exc:
            return {"ok": False, "error": f"Mix Review analysis failed: {type(exc).__name__}: {exc}"}
        review_id = f"review-{uuid.uuid4().hex}"
        review = _review_from_report(
            report,
            review_id=review_id,
            filename=clean_filename,
            source_sha256=hashlib.sha256(payload).hexdigest(),
            project_id=project_id_override,
            reference_match=comparison["reference_comparison"]["reference_match_score"] if comparison else None,
        )
        if comparison:
            # Keep the normal review's goal-specific findings; the comparison contributes only its own evidence.
            review["reference"] = comparison["source_reference"]
            review["reference_comparison"] = comparison["reference_comparison"]
            score = comparison["reference_comparison"].get("reference_match_score")
            if isinstance(score, dict) and _finite(score.get("points_available")) == 0.0:
                reason = _text(score.get("note"), 512)
                if reason:
                    review["limitations"] = f'{review.get("limitations", "")} Reference comparison unavailable: {reason}.'.strip()
        review = _published_review(review)
        with self._lock:
            self._reviews[review_id] = review
            self._prune_reviews()
            self._persist()
        return {"ok": review["status"] == "completed", "review_id": review_id, "status": review["status"], "review": review}

    @staticmethod
    def _multipart_parts(content_type: str, body: bytes) -> list[tuple[str, bytes, str]]:
        envelope = BytesParser(policy=email_default).parsebytes(
            (f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n").encode("utf-8") + body
        )
        parts: list[tuple[str, bytes, str]] = []
        for part in envelope.walk():
            if part.get_content_disposition() != "form-data":
                continue
            name = _text(part.get_param("name", header="content-disposition"), 96)
            filename = _text(part.get_filename(), 256)
            value = part.get_payload(decode=True)
            if isinstance(value, (bytes, bytearray)):
                parts.append((name, bytes(value), filename))
        return parts

    def handle_multipart_review(self, content_type: str, body: bytes, *, project_id_override: str = "") -> dict[str, Any]:
        parts = self._multipart_parts(content_type, body)
        # Select by role, not attachment order: a reference sent first must never become the mix.
        # Older clients used other names for the sole mix file, so only "reference" is reserved here.
        mixes = [(value, filename) for name, value, filename in parts if name != "reference" and (filename or name == "file")]
        references = [(value, filename) for name, value, filename in parts if name == "reference"]
        if len(mixes) != 1 or len(references) > 1 or any(not filename for _, filename in [*mixes, *references]):
            # Ambiguous or nameless attachments cannot produce a receipt tied to a known pair of sources.
            return {"ok": False, "error": "Attach one mix WAV and at most one reference WAV for local Mix Review."}
        audio = mixes[0]
        mix_goal = next((value.decode("utf-8", "replace") for name, value, filename in parts if name == "mix_goal" and not filename), "general")
        return self.save_review(
            audio[0], audio[1], project_id_override=project_id_override, mix_goal=mix_goal,
            reference_audio=references[0] if references else None,
        )

    def mix_review_status(self, review_id: str) -> dict[str, Any]:
        review_id = _text(review_id, 128)
        with self._lock:
            review = self._reviews.get(review_id)
        if review is None:
            return {"ok": False, "error": "Mix Review was not found.", "review": None, "review_id": review_id}
        return {"ok": True, "review_id": review_id, "status": review.get("status", "unknown"), "review": _published_review(review)}

    def list_reviews(self, limit: int = 20) -> list[dict[str, Any]]:
        try:
            bounded = max(1, min(200, int(limit)))
        except (TypeError, ValueError):
            bounded = 20
        with self._lock:
            values = list(self._reviews.values())[-bounded:]
        return [_published_review(item) for item in reversed(values)]

    def runtime_state_counts(self) -> dict[str, int]:
        """Expose counts and limits without review IDs, names, or content."""
        with self._lock:
            return {"mix_reviews": len(self._reviews), "mix_reviews_limit": self.MAX_REVIEWS}

    def report_json_bytes(self, review_id: str) -> bytes:
        result = self.mix_review_status(review_id)
        return json.dumps(result.get("review") or result, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")

    def report_html(self, review_id: str) -> bytes:
        result = self.mix_review_status(review_id)
        body = html.escape(json.dumps(result.get("review") or result, ensure_ascii=False, indent=2, sort_keys=True))
        return f"<!doctype html><html><body><pre>{body}</pre></body></html>".encode("utf-8")

    def handle_multipart_reference(self, content_type: str, body: bytes) -> dict[str, Any]:
        parts = self._multipart_parts(content_type, body)
        wavs = [(name, value, filename) for name, value, filename in parts if filename and filename.lower().endswith(".wav")]
        if len(wavs) < 2:
            return {"ok": False, "error": "Attach a mix WAV and a reference WAV for comparison."}
        named = {name.lower(): (value, filename) for name, value, filename in wavs}
        mix = named.get("mix") or named.get("source") or (wavs[0][1], wavs[0][2])
        reference = named.get("reference") or (wavs[1][1], wavs[1][2])
        result = compare_reference_audio(mix[0], mix[1], reference[0], reference[1])
        if not result.get("ok"):
            return result
        review_id = f"reference-{uuid.uuid4().hex}"
        # The record contains only bounded filenames, hashes, and calculated
        # measurements. Both WAV byte payloads have already gone out of scope.
        review = {
            **result,
            "review_id": review_id,
            "created_at": _now(),
            "status": "completed",
            "storage": "metadata_only",
            "audio_retained": False,
        }
        review = _published_review(review)
        with self._lock:
            self._reviews[review_id] = review
            self._prune_reviews()
            self._persist()
        return {"ok": True, "review_id": review_id, "status": "completed", "review": review}


local_mix_review = LocalMixReviewService()


__all__ = ["LocalMixReviewService", "MAX_REVIEWS", "MAX_UPLOAD_BYTES", "TOO_LARGE_ADVICE", "local_mix_review"]
