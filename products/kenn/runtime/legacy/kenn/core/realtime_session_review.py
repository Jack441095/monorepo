"""Compose a scope-labelled, read-only review of the current Live session."""

from __future__ import annotations

import math
import re
from typing import Any, Iterable

from kenn.project_analysis import analyze_project_doctor, normalize_session


SCHEMA = "kenn.realtime_session_review.v1"
MAX_TRACKS = 256
MAX_ALERTS = 64
MAX_RECOMMENDATIONS = 32


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _track_observations(session: dict[str, Any]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    tracks = session.get("tracks") if isinstance(session.get("tracks"), list) else []
    for position, raw in enumerate(tracks[:MAX_TRACKS]):
        if not isinstance(raw, dict):
            continue
        item: dict[str, Any] = {
            "track_index": raw.get("index", position),
            "track_name": str(raw.get("name") or "").strip()[:128],
            "muted": bool(raw.get("muted")),
            "soloed": bool(raw.get("soloed")),
        }
        for key in ("output_meter_level", "output_meter_right"):
            value = _number(raw.get(key))
            if value is not None and 0.0 <= value <= 1.0:
                item[key] = value
        observations.append(item)
    return observations


def _safe_alerts(alerts: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    safe: list[dict[str, Any]] = []
    for raw in list(alerts)[:MAX_ALERTS]:
        if not isinstance(raw, dict):
            continue
        item = {
            key: raw[key]
            for key in ("id", "type", "severity", "message", "fix_action", "fix_label")
            if key in raw and isinstance(raw[key], (str, int, float, bool))
        }
        track_index = raw.get("track_index")
        if isinstance(track_index, int) and not isinstance(track_index, bool):
            item["track_index"] = track_index
        track_indices = raw.get("track_indices")
        if isinstance(track_indices, list):
            item["track_indices"] = [
                value for value in track_indices[:MAX_TRACKS]
                if isinstance(value, int) and not isinstance(value, bool)
            ]
        if item:
            safe.append(item)
    return safe


def _safe_pink_noise_reference(value: Any) -> dict[str, Any] | None:
    """Preserve bounded pink-noise-shape evidence without raw audio."""
    if not isinstance(value, dict):
        return None
    status = str(value.get("status") or "").strip()[:32]
    if status == "abstained":
        reason = str(value.get("reason") or "").strip()[:256]
        return {"status": status, **({"reason": reason} if reason else {})}
    if status != "complete":
        return None
    safe: dict[str, Any] = {"status": status}
    for key in ("curve", "positive_deviation_means"):
        text = str(value.get(key) or "").strip()[:256]
        if text:
            safe[key] = text
    for key in ("slope_db_per_octave", "anchor_frequency_hz"):
        number = _number(value.get(key))
        if number is not None:
            safe[key] = number
    bands: list[dict[str, float]] = []
    for raw in list(value.get("bands") or [])[:16]:
        if not isinstance(raw, dict):
            continue
        row: dict[str, float] = {}
        for key in ("center_hz", "measured_relative_db", "pink_expected_relative_db", "deviation_db"):
            number = _number(raw.get(key))
            if number is not None:
                row[key] = number
        if row.get("center_hz", 0.0) > 0.0 and "deviation_db" in row:
            bands.append(row)
    if bands:
        safe["bands"] = bands
    largest = value.get("largest_deviation")
    if isinstance(largest, dict):
        row: dict[str, float] = {}
        for key in ("center_hz", "measured_relative_db", "pink_expected_relative_db", "deviation_db"):
            number = _number(largest.get(key))
            if number is not None:
                row[key] = number
        if row.get("center_hz", 0.0) > 0.0 and "deviation_db" in row:
            safe["largest_deviation"] = row
    return safe if "largest_deviation" in safe or bands else None


def _safe_pink_noise_shape(value: Any) -> dict[str, Any] | None:
    """Keep the aggregate realtime trend separate from the latest frame."""
    if not isinstance(value, dict):
        return None
    safe: dict[str, Any] = {}
    sample_count = value.get("sample_count")
    if isinstance(sample_count, int) and not isinstance(sample_count, bool) and 0 <= sample_count <= 192:
        safe["sample_count"] = sample_count
    largest = value.get("largest_median_deviation")
    if isinstance(largest, dict):
        row: dict[str, float] = {}
        for key in ("center_hz", "median_deviation_db", "min_deviation_db", "max_deviation_db", "range_db"):
            number = _number(largest.get(key))
            if number is not None:
                row[key] = number
        if row.get("center_hz", 0.0) > 0.0 and "median_deviation_db" in row:
            safe["largest_median_deviation"] = row
    return safe or None


def _safe_plugin_bus(
    plugin_review: dict[str, Any] | None,
    plugin_recommendations: Iterable[dict[str, Any]],
) -> dict[str, Any] | None:
    if not isinstance(plugin_review, dict):
        return None
    context = plugin_review.get("live_context") if isinstance(plugin_review.get("live_context"), dict) else None
    if plugin_review.get("ok") is not True or context is None:
        return {
            "status": "unavailable",
            "scope": "plugin_bus",
            "error": str(plugin_review.get("error") or "No validated realtime plug-in context was available.")[:512],
            "recommendations": [],
            "advisory_only": True,
            "capture_requested": False,
        }
    metrics = {
        key: context[key]
        for key in (
            "peak_dbfs", "rms_dbfs", "crest_db", "stereo_correlation", "stereo_width",
            "clipped_samples", "low_energy", "mid_energy", "high_energy",
        )
        if _number(context.get(key)) is not None
    }
    recommendations = []
    for raw in list(plugin_recommendations)[:MAX_RECOMMENDATIONS]:
        if not isinstance(raw, dict):
            continue
        item = {
            key: raw[key]
            for key in ("title", "category", "severity", "confidence", "description", "reason", "suggestedAction", "canAutoFix", "requiresConfirmation")
            if key in raw and isinstance(raw[key], (str, int, float, bool))
        }
        if isinstance(raw.get("track_indices"), list):
            item["track_indices"] = [
                value for value in raw["track_indices"][:MAX_TRACKS]
                if isinstance(value, int) and not isinstance(value, bool)
            ]
        if item:
            recommendations.append(item)
    freshness = context.get("freshness") if isinstance(context.get("freshness"), dict) else {}
    safe_freshness = {
        key: freshness[key]
        for key in ("frame_count", "age_seconds", "ttl_seconds", "current_for_diagnosis", "status")
        if key in freshness and isinstance(freshness[key], (str, int, float, bool))
    }
    live_window = context.get("live_window") if isinstance(context.get("live_window"), dict) else {}
    safe_live_window = {
        key: live_window[key]
        for key in ("status", "sample_count", "window_seconds")
        if key in live_window and isinstance(live_window[key], (str, int, float, bool))
    }
    pink_shape = _safe_pink_noise_shape(live_window.get("pink_noise_shape"))
    if pink_shape is not None:
        safe_live_window["pink_noise_shape"] = pink_shape
    return {
        "status": "current",
        "scope": "plugin_bus",
        "metrics": metrics,
        "freshness": safe_freshness or None,
        "live_window": safe_live_window or None,
        "pink_noise_reference": _safe_pink_noise_reference(context.get("pink_noise_reference")),
        "recommendations": recommendations,
        "advisory_only": True,
        "capture_requested": False,
        "live_target_inference_allowed": False,
    }


def realtime_knowledge_guidance(query: str, report: dict[str, Any]) -> list[dict[str, Any]]:
    """Retrieve bounded, provenance-labelled guidance for a review focus."""
    mixing_doctor = report.get("mixing_doctor") if isinstance(report.get("mixing_doctor"), dict) else {}
    project_health = report.get("project_health") if isinstance(report.get("project_health"), dict) else {}
    plugin_bus = report.get("plugin_bus") if isinstance(report.get("plugin_bus"), dict) else {}
    query_parts = [str(query or "").strip()]
    for collection in (
        mixing_doctor.get("alerts"),
        project_health.get("recommendations"),
        plugin_bus.get("recommendations"),
    ):
        if not isinstance(collection, list):
            continue
        for item in collection[:6]:
            if not isinstance(item, dict):
                continue
            query_parts.extend(
                str(item.get(key) or "").strip()
                for key in ("type", "title", "message", "description")
            )
    if not any(part for part in query_parts):
        query_parts.append("Ableton Live mixing session gain staging arrangement workflow")
    retrieval_query = " ".join(part for part in query_parts if part)[:1_200]

    def excerpt(value: Any) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if not text:
            return ""
        markers = (
            "Short answer:", "Try this:", "The ", "Use ", "Compare ",
            "Place ", "Check ", "If ", "When ",
        )
        positions = [text.find(marker) for marker in markers if text.find(marker) >= 40]
        if positions:
            text = text[min(positions):]
        return re.sub(r"^#+\s*", "", text)[:280].strip()

    try:
        from kenn.core.chat_retrieval import (
            display_results,
            evidence_class,
            evidence_label,
            load_chunks,
            load_terms,
            search,
        )
        from kenn.retrieval.retrieval import bm25_search

        chunks = load_chunks()
        terms = load_terms()
        results = search(retrieval_query, chunks, terms, limit=8)
        candidates: list[tuple[float, dict[str, Any]]] = []
        # Hybrid retrieval is practical-note friendly. Add one independently
        # ranked manual and transcript candidate so duplicate notes cannot
        # hide the higher-value provenance classes.
        for required_class, class_hint in (
            ("official_ableton_manual", "Ableton Live manual"),
            ("youtube_transcript", "producer mixing transcript"),
        ):
            try:
                candidates.extend(
                    bm25_search(
                        f"{class_hint} {retrieval_query}",
                        chunks,
                        terms,
                        limit=4,
                        allowed=lambda chunk, expected=required_class: (
                            evidence_class(chunk) == expected
                        ),
                    )[:1]
                )
            except (Exception, SystemExit):
                continue
        candidates.extend(display_results(retrieval_query, results, 8))
        guidance: list[dict[str, Any]] = []
        source_counts: dict[str, int] = {}
        seen_sources: set[str] = set()
        allowed_classes = {"official_ableton_manual", "youtube_transcript", "curated_kenn_note"}
        for _score, chunk in candidates:
            if not isinstance(chunk, dict):
                continue
            source_kind = evidence_class(chunk)
            if source_kind not in allowed_classes or source_counts.get(source_kind, 0) >= 2:
                continue
            source_key = str(chunk.get("source") or "").strip()[:160]
            if not source_key or source_key in seen_sources:
                continue
            if chunk.get("kind") == "note":
                source = f"{str(chunk.get('title') or source_key).strip()[:100]} ({source_key})"
            else:
                source = f"{source_key}, page {str(chunk.get('page') or '?')[:16]}"
            text = excerpt(chunk.get("text"))
            if not text:
                continue
            guidance.append({
                "source": source,
                "evidence_class": source_kind,
                "evidence_label": evidence_label(chunk),
                "excerpt": text,
                "advisory_only": True,
            })
            source_counts[source_kind] = source_counts.get(source_kind, 0) + 1
            seen_sources.add(source_key)
            if len(guidance) >= 4:
                break
        return guidance
    except (Exception, SystemExit):
        # Source guidance is optional and must never make a valid review fail.
        return []


def build_realtime_session_review(
    session: dict[str, Any] | None,
    *,
    mixing_alerts: Iterable[dict[str, Any]] = (),
    plugin_review: dict[str, Any] | None = None,
    plugin_recommendations: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Build one read-only report without polling or authorising mutation.

    Ableton observations, structural health findings, and plug-in bus metrics
    remain separate so a bus measurement cannot be mistaken for a track
    diagnosis.  The supplied session is normally Mixing Doctor's cached
    snapshot; this function never opens a Live or plug-in connection.
    """
    session = session if isinstance(session, dict) else {}
    status = str(session.get("status") or "unknown")
    current = status in {"connected", "dispatched"}
    normalized = normalize_session(session)
    project_findings = [item.payload() for item in analyze_project_doctor(normalized)]
    alerts = _safe_alerts(mixing_alerts)
    track_observations = _track_observations(session)
    metered_track_count = sum(
        1 for item in track_observations
        if "output_meter_level" in item or "output_meter_right" in item
    )
    limitations = [
        "This report composes cached read-only observations; it does not poll Live or request audio capture.",
        "Instantaneous Live track meters are post-fader 0.0-1.0 observations, not audio-rate peak, LUFS, true-peak, spectrum, or masking measurements.",
        "Plug-in findings are bus-scoped and cannot identify a responsible Live track or device.",
        "No recommendation in this report authorizes a Live mutation; supported changes still require the normal proposal, confirmation, stale check, readback, and receipt path.",
    ]
    result: dict[str, Any] = {
        "ok": current,
        "schema": SCHEMA,
        "status": "current" if current else "unavailable",
        "scope": {
            "live_session": "ableton_session_snapshot",
            "mixing_doctor": "cached_session_audits",
            "plugin_bus": "validated_plugin_bus_snapshot" if plugin_review is not None else "not_supplied",
        },
        "live_session": {
            "status": status,
            "track_count": len(session.get("tracks") or []),
            "metered_track_count": metered_track_count,
            "track_observations": track_observations,
        },
        "mixing_doctor": {
            "status": "current" if current else "unavailable",
            "alerts": alerts if current else [],
        },
        "project_health": {
            "recommendations": project_findings if current else [],
            "available_data": list(normalized.available_capabilities) if current else [],
            "unavailable_data": list(normalized.unavailable_capabilities),
        },
        "plugin_bus": _safe_plugin_bus(plugin_review, plugin_recommendations),
        "limitations": limitations,
        "advisory_only": True,
        "capture_requested": False,
        "mutation_authorized": False,
    }
    if not current:
        result["error"] = "The current Ableton session snapshot is unavailable; no Live analysis was inferred."
    return result


__all__ = ["SCHEMA", "build_realtime_session_review", "realtime_knowledge_guidance"]
