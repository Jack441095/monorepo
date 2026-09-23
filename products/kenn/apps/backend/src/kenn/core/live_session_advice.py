"""Read-only, evidence-labelled mix advice for the current Live session."""

from __future__ import annotations

import hashlib
import os
import threading
from collections import OrderedDict
from copy import deepcopy
from pathlib import Path
from typing import Any

from kenn.core.arrangement_doctor import get_arrangement_doctor
from kenn.core.audio_analysis import analyze_wav


_ANALYSIS_CACHE_MAX_ENTRIES = 4
_ANALYSIS_CACHE: OrderedDict[tuple[str, str], dict[str, Any]] = OrderedDict()
_ANALYSIS_CACHE_LOCK = threading.RLock()


def _analyze_cached(payload: bytes, *, filename: str) -> tuple[dict[str, Any], str, bool]:
    """Analyze immutable audio once per content hash, with a small memory bound."""
    digest = hashlib.sha256(payload).hexdigest()
    key = (digest, Path(filename).suffix.casefold())
    with _ANALYSIS_CACHE_LOCK:
        cached = _ANALYSIS_CACHE.get(key)
        if cached is not None:
            _ANALYSIS_CACHE.move_to_end(key)
            return deepcopy(cached), digest, True

    analysis = analyze_wav(
        payload,
        filename=filename,
        include_ltas=True,
        include_pink_noise_reference=True,
    )
    if isinstance(analysis, dict) and analysis.get("ok"):
        with _ANALYSIS_CACHE_LOCK:
            _ANALYSIS_CACHE[key] = deepcopy(analysis)
            _ANALYSIS_CACHE.move_to_end(key)
            while len(_ANALYSIS_CACHE) > _ANALYSIS_CACHE_MAX_ENTRIES:
                _ANALYSIS_CACHE.popitem(last=False)
    return analysis, digest, False


def _latest_audio(client: Any, *, scope: str) -> tuple[bytes, str] | None:
    """Read an already-available, scope-matched capture without recording."""
    is_vocal = scope == "vocal"
    reader_name = "get_latest_vocal_capture" if is_vocal else "get_latest_audio_capture"
    value_name = "latest_vocal_capture" if is_vocal else "latest_audio_capture"
    reader = getattr(client, reader_name, None)
    try:
        candidate = reader() if callable(reader) else getattr(client, value_name, None)
    except Exception:
        candidate = None
    if isinstance(candidate, bytes):
        return candidate, "live-session-capture.wav"
    if isinstance(candidate, dict):
        payload = candidate.get("payload") or candidate.get("audio")
        if isinstance(payload, bytes):
            return payload, Path(str(candidate.get("filename") or "live-session-capture.wav")).name
        candidate = candidate.get("path")
    env_name = "KENN_LIVE_VOCAL_CAPTURE_PATH" if is_vocal else "KENN_LIVE_AUDIO_CAPTURE_PATH"
    configured = str(candidate or os.getenv(env_name, "")).strip()
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


def _low_end_finding(analysis: dict[str, Any]) -> dict[str, Any] | None:
    spectral = analysis.get("spectral") if isinstance(analysis.get("spectral"), dict) else {}
    reference = spectral.get("pink_noise_reference") if isinstance(spectral.get("pink_noise_reference"), dict) else {}
    bands = reference.get("bands") if isinstance(reference.get("bands"), list) else []
    low_bands = [
        row for row in bands
        if isinstance(row, dict)
        and isinstance(row.get("center_hz"), (int, float))
        and 20.0 <= float(row["center_hz"]) <= 250.0
        and isinstance(row.get("deviation_db"), (int, float))
    ]
    if not low_bands:
        return None
    strongest = max(low_bands, key=lambda row: float(row["deviation_db"]))
    deviation = float(strongest["deviation_db"])
    band_levels = spectral.get("band_energy_dbfs") if isinstance(spectral.get("band_energy_dbfs"), dict) else {}
    low_rms = band_levels.get("low")
    if deviation >= 3.0:
        explanation = (
            f"The {int(float(strongest['center_hz']) + 0.5)} Hz band is {deviation:.1f} dB above the "
            "anchored pink-noise-style baseline, which is consistent with a low-end-heavy balance; "
            "that reference is diagnostic, not a mix target."
        )
        finding_type = "possible_low_end_excess"
        severity = "informational"
        confidence = 0.65
    else:
        explanation = (
            f"The strongest measured low-band deviation is {deviation:+.1f} dB at "
            f"{float(strongest['center_hz']):g} Hz; this bounded pass does not show a strong low-end excess."
        )
        finding_type = "low_end_balance_measurement"
        severity = "informational"
        confidence = 0.55
    return {
        "type": finding_type,
        "severity": severity,
        "confidence": confidence,
        "evidence": {
            "center_hz": strongest["center_hz"],
            "pink_baseline_deviation_db": round(deviation, 3),
            "low_band_rms_dbfs": low_rms,
            "reference": "anchored -3 dB/octave pink-noise-style baseline",
        },
        "explanation": explanation,
        "suggested_listening_test": "Level-match the mix, then alternate kick and bass solos in mono through the densest section before changing EQ or level.",
    }


def _audio_advice(analysis: dict[str, Any], *, scope: str) -> dict[str, Any] | None:
    if not analysis.get("ok"):
        return None
    findings = [dict(item) for item in analysis.get("findings") or [] if isinstance(item, dict)]
    if scope == "low_end":
        low_end = _low_end_finding(analysis)
        if low_end is not None:
            findings.insert(0, low_end)
    elif scope == "vocal":
        findings.sort(key=lambda item: 0 if item.get("type") == "clipping" else 1)
    if findings:
        source = "isolated vocal capture" if scope == "vocal" else "latest available session capture"
        lines = [f"I analyzed the {source}. My strongest checks are:"]
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
        "analysis_scope": scope,
        "advisory_only": True,
        "changed": False,
    }


def _arrangement_advice(snapshot: dict[str, Any], *, scope: str) -> dict[str, Any]:
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
    if scope == "vocal":
        unavailable = "An isolated vocal capture was not available, so I could not attribute clipping to the vocal."
        listening_test = "Render or provide an isolated vocal stem, then inspect its loudest phrase with a sample- and true-peak meter."
    else:
        unavailable = "Audio was not available, so I could not measure tonal balance, clipping, or masking."
        listening_test = "Loop the densest transition, compare it with the preceding section at matched level, then check whether new elements or silence create a clear contrast."
    finding = {
        "type": "arrangement_structure_check",
        "severity": "informational",
        "confidence": 0.65 if observed_sections else 0.35,
        "evidence": {
            "track_count": len(tracks),
            "estimated_total_bars": total_bars,
            "scope": evidence_scope,
        },
        "explanation": f"{unavailable} The arrangement pass sees {len(tracks)} tracks and an estimated {total_bars}-bar span.",
        "suggested_listening_test": listening_test,
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
        "analysis_scope": scope,
        "answer": f"{finding['explanation']} {caveat} Listening test: {finding['suggested_listening_test']}",
        "findings": [finding],
        "arrangement": report.to_dict(),
        "advisory_only": True,
        "changed": False,
    }


def mix_advice_from_session(
    *, service: Any, snapshot: dict[str, Any] | None = None, question: str = "",
) -> dict[str, Any]:
    """Analyze an existing capture, otherwise provide honest structural advice."""
    current = snapshot if isinstance(snapshot, dict) else service.snapshot(include_mixer=True)
    normalized = " ".join(str(question or "").casefold().split())
    scope = "vocal" if "vocal" in normalized else ("low_end" if "low end" in normalized or "low-end" in normalized else "mix")
    available = _latest_audio(service.client, scope=scope)
    if available is not None:
        payload, filename = available
        try:
            analysis, digest, cache_hit = _analyze_cached(payload, filename=filename)
        except Exception:
            analysis = {}
        result = _audio_advice(analysis, scope=scope)
        if result is not None:
            result["analysis_source"] = {
                "filename": filename,
                "sha256": digest,
                "cache_hit": cache_hit,
            }
            return result
    return _arrangement_advice(current, scope=scope)


__all__ = ["mix_advice_from_session"]
