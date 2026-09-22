"""Read-only, evidence-labelled mix advice for the current Live session."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from kenn.core.arrangement_doctor import get_arrangement_doctor
from kenn.core.audio_analysis import analyze_wav


def _latest_audio(client: Any) -> tuple[bytes, str] | None:
    """Read an already-available capture without initiating recording or export."""
    reader = getattr(client, "get_latest_audio_capture", None)
    try:
        candidate = reader() if callable(reader) else getattr(client, "latest_audio_capture", None)
    except Exception:
        candidate = None
    if isinstance(candidate, bytes):
        return candidate, "live-session-capture.wav"
    if isinstance(candidate, dict):
        payload = candidate.get("payload") or candidate.get("audio")
        if isinstance(payload, bytes):
            return payload, Path(str(candidate.get("filename") or "live-session-capture.wav")).name
        candidate = candidate.get("path")
    configured = str(candidate or os.getenv("KENN_LIVE_AUDIO_CAPTURE_PATH", "")).strip()
    if not configured:
        return None
    path = Path(configured).expanduser()
    try:
        if path.is_file() and path.suffix.casefold() == ".wav":
            return path.read_bytes(), path.name
    except OSError:
        return None
    return None


def _estimated_total_bars(snapshot: dict[str, Any]) -> int:
    furthest_beat = 0.0
    for track in snapshot.get("tracks") or []:
        if not isinstance(track, dict):
            continue
        for clip in track.get("arrangement_clips") or []:
            if not isinstance(clip, dict):
                continue
            try:
                start = float(clip.get("start_time_beats", 0.0))
                length = float(clip.get("length_beats", 0.0))
            except (TypeError, ValueError):
                continue
            furthest_beat = max(furthest_beat, start + length)
    return max(8, int((furthest_beat + 3.999) // 4)) if furthest_beat else 64


def _audio_advice(analysis: dict[str, Any]) -> dict[str, Any] | None:
    if not analysis.get("ok"):
        return None
    findings = [item for item in analysis.get("findings") or [] if isinstance(item, dict)]
    if findings:
        lines = ["I analyzed the latest available session capture. My strongest checks are:"]
        for finding in findings[:5]:
            severity = str(finding.get("severity") or "informational")
            confidence = float(finding.get("confidence") or 0.0)
            explanation = str(finding.get("explanation") or finding.get("type") or "Measured finding")
            test = str(finding.get("suggested_listening_test") or "Level-match and audition before changing the mix.")
            lines.append(f"- {severity.title()} ({confidence:.0%} confidence): {explanation} Listening test: {test}")
    else:
        metrics = analysis.get("metrics") if isinstance(analysis.get("metrics"), dict) else {}
        lines = [
            "I analyzed the latest available session capture and found no high-priority flags in this bounded pass.",
            f"Measured sample peak: {metrics.get('sample_peak_dbfs', 'unavailable')} dBFS; RMS: {metrics.get('rms_dbfs', 'unavailable')} dBFS.",
            "Level-match, check the densest section in mono, and treat this as evidence rather than a quality score.",
        ]
    return {
        "schema": "kenn.ableton_mix_advice.v1",
        "status": "inspected",
        "advice_mode": "audio_analysis",
        "answer": "\n".join(lines),
        "findings": findings,
        "metrics": analysis.get("metrics") or {},
        "analysis_status": analysis.get("analysis_status"),
        "advisory_only": True,
        "changed": False,
    }


def _arrangement_advice(snapshot: dict[str, Any]) -> dict[str, Any]:
    tracks = [track for track in snapshot.get("tracks") or [] if isinstance(track, dict)]
    timeline_sections = snapshot.get("timeline_sections")
    observed_sections = timeline_sections if isinstance(timeline_sections, list) and timeline_sections else None
    total_bars = _estimated_total_bars(snapshot)
    report = get_arrangement_doctor().analyze_timeline(
        tracks=tracks,
        timeline_sections=observed_sections,
        total_bars=total_bars,
    )
    evidence_scope = "observed timeline sections" if observed_sections else "track and clip inventory with a generic arrangement heuristic"
    finding = {
        "type": "arrangement_structure_check",
        "severity": "informational",
        "confidence": 0.65 if observed_sections else 0.35,
        "evidence": {
            "track_count": len(tracks),
            "estimated_total_bars": total_bars,
            "scope": evidence_scope,
        },
        "explanation": (
            f"Audio was not available, so I could not measure tonal balance or masking. "
            f"The arrangement pass sees {len(tracks)} tracks and an estimated {total_bars}-bar span."
        ),
        "suggested_listening_test": "Loop the densest transition, compare it with the preceding section at matched level, then check whether new elements or silence create a clear contrast.",
    }
    if not observed_sections:
        caveat = "The section labels are a planning heuristic, not observed musical structure."
    elif report.drop_contrast_delta < 0.25:
        caveat = "The observed energy labels suggest limited buildup-to-drop contrast."
    else:
        caveat = "The observed section labels provide structural evidence, but not audio evidence."
    return {
        "schema": "kenn.ableton_mix_advice.v1",
        "status": "inspected",
        "advice_mode": "arrangement_fallback",
        "answer": f"{finding['explanation']} {caveat} Listening test: {finding['suggested_listening_test']}",
        "findings": [finding],
        "arrangement": report.to_dict(),
        "advisory_only": True,
        "changed": False,
    }


def mix_advice_from_session(*, service: Any, snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    """Analyze an existing capture, otherwise provide honest structural advice."""
    current = snapshot if isinstance(snapshot, dict) else service.snapshot(include_mixer=True)
    available = _latest_audio(service.client)
    if available is not None:
        payload, filename = available
        try:
            analysis = analyze_wav(payload, filename=filename, include_ltas=True, include_pink_noise_reference=True)
        except Exception:
            analysis = {}
        result = _audio_advice(analysis)
        if result is not None:
            return result
    return _arrangement_advice(current)


__all__ = ["mix_advice_from_session"]
