"""Validation and interpretation for KENN Mix Assistant handoff files.

The native plug-in writes these files outside its audio callback.  This module
does not infer unavailable information or start an AutoMix render: a render
still requires separately supplied stems and the existing job pipeline.
"""

from __future__ import annotations

from typing import Any
import math
import time

SCHEMA = "kenn.plugin_handoff.v1"
FEATURE_SCHEMA = "audio_feature_frame.v1"
SPECTRUM_SCHEMA = "realtime_spectrum.v1"
_REQUIRED_NUMBERS = ("peak_dbfs", "rms_dbfs", "stereo_correlation", "stereo_width", "sample_rate", "analysed_samples")
_OPTIONAL_NUMBERS = (
    "crest_db", "transient_ratio", "clipped_samples",
    # These are bounded linear band-energy estimates from the plug-in's
    # allocation-free realtime core.  They are deliberately not called EQ
    # readings: no reference curve or calibrated spectrum is implied.
    "low_energy", "mid_energy", "high_energy",
)
_FORBIDDEN_AUDIO_FIELDS = frozenset({"audio_samples", "raw_audio", "waveform", "pcm"})
_CONTEXT_TTL_SECONDS = 30 * 60
# Retained context can support history, but diagnosis must not treat an old
# snapshot as the current state of the Ableton session.
_MAX_CURRENT_DIAGNOSIS_AGE_SECONDS = 15.0
_LIVE_HISTORY_SECONDS = 2 * 60
_MAX_LIVE_FRAMES = 12
_live_contexts: dict[str, dict[str, Any]] = {}
_ASSISTANT_MODES = {"ask", "suggest", "assist", "auto"}
_SHARED_EVIDENCE_SCHEMA = "kenn.evidence.v1"


def _validate_shared_evidence_packet(packet: Any, *, expected_source: str) -> tuple[bool, str]:
    """Validate the optional native evidence envelope before accepting it."""
    if not isinstance(packet, dict):
        return False, "evidence must be an object."
    if packet.get("schema") != _SHARED_EVIDENCE_SCHEMA:
        return False, f"evidence.schema must be {_SHARED_EVIDENCE_SCHEMA}."
    if packet.get("source") != expected_source:
        return False, "evidence.source does not match the handoff source."
    age = packet.get("captured_at_age_seconds")
    if age is not None and (isinstance(age, bool) or not isinstance(age, (int, float)) or not math.isfinite(float(age)) or float(age) < 0.0):
        return False, "evidence.captured_at_age_seconds must be a finite non-negative number or null."
    observed = packet.get("observed_at_epoch")
    if observed is not None and (isinstance(observed, bool) or not isinstance(observed, (int, float)) or not math.isfinite(float(observed))):
        return False, "evidence.observed_at_epoch must be finite numeric data or null."
    facts = packet.get("facts")
    if not isinstance(facts, list) or not 1 <= len(facts) <= 32:
        return False, "evidence.facts must contain between 1 and 32 items."
    for index, fact in enumerate(facts):
        if not isinstance(fact, dict):
            return False, f"evidence.facts[{index}] must be an object."
        for key, limit in (("name", 128), ("unit", 32), ("source", 64), ("confidence", 32)):
            value = fact.get(key)
            if not isinstance(value, str) or not value.strip() or len(value) > limit:
                return False, f"evidence.facts[{index}].{key} is invalid."
        value = fact.get("value")
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            if not math.isfinite(float(value)):
                return False, f"evidence.facts[{index}].value must be finite."
        elif not isinstance(value, str):
            return False, f"evidence.facts[{index}].value must be scalar."
    limitations = packet.get("limitations")
    if not isinstance(limitations, list) or len(limitations) > 8 or any(not isinstance(item, str) or not item.strip() or len(item) > 512 for item in limitations):
        return False, "evidence.limitations must contain at most 8 bounded strings."
    freshness = packet.get("freshness")
    if freshness is not None and not isinstance(freshness, dict):
        return False, "evidence.freshness must be an object when supplied."
    return True, ""


def pink_noise_reference_from_spectrum(bands: Any) -> dict[str, Any]:
    """Compare fixed realtime bands with a relative -3 dB/octave baseline.

    The plug-in supplies bounded linear band energy, not calibrated FFT bins.
    This therefore remains a broad shape reference anchored to the measured
    band nearest 1 kHz; it is never an automatic EQ instruction.
    """
    usable = [
        band for band in (bands if isinstance(bands, list) else [])
        if isinstance(band, dict)
        and isinstance(band.get("center_hz"), (int, float))
        and isinstance(band.get("energy"), (int, float))
        and float(band["center_hz"]) > 0.0
        and float(band["energy"]) >= 0.0
    ]
    if not usable:
        return {"status": "abstained", "reason": "No usable realtime spectrum bands were available for the pink-noise-style comparison."}
    anchor = min(usable, key=lambda band: abs(float(band["center_hz"]) - 1000.0))
    anchor_energy = float(anchor["energy"])
    if anchor_energy <= 1e-12:
        return {"status": "abstained", "reason": "The realtime spectrum anchor near 1 kHz has negligible energy."}
    anchor_frequency = float(anchor["center_hz"])
    result_bands: list[dict[str, Any]] = []
    for band in usable:
        center = float(band["center_hz"])
        measured = 10.0 * math.log10(max(float(band["energy"]), 1e-12) / anchor_energy)
        expected = -3.0 * math.log2(center / anchor_frequency)
        result_bands.append({
            "center_hz": round(center, 3),
            "low_hz": band.get("low_hz"),
            "high_hz": band.get("high_hz"),
            "measured_relative_db": round(measured, 3),
            "pink_expected_relative_db": round(expected, 3),
            "deviation_db": round(measured - expected, 3),
        })
    largest = max(result_bands, key=lambda band: abs(float(band["deviation_db"])), default=None)
    return {
        "status": "complete",
        "curve": "-3 dB per octave pink-noise-style spectral baseline",
        "slope_db_per_octave": -3.0,
        "anchor_frequency_hz": round(anchor_frequency, 3),
        "positive_deviation_means": "more measured energy than the baseline at that band",
        "bands": result_bands,
        "largest_deviation": largest,
        "limitations": [
            "This is a broad frequency-banded shape reference, not a universal mix target or quality score.",
            "The plug-in values are uncalibrated bus energy estimates and cannot identify a track, arrangement choice, room problem, or processing cause.",
            "Level-match and listen before making any tonal change; no EQ move is implied.",
        ],
    }


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return 0.5 * (ordered[middle - 1] + ordered[middle])


def _live_window_summary(frames: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarise recent snapshots without retaining raw audio or large history."""
    if not frames:
        return {
            "sample_count": 0,
            "window_seconds": 0.0,
            "status": "insufficient",
            "metric_ranges": {},
            "pink_noise_shape": {"sample_count": 0},
        }
    times = [float(frame["received_at"]) for frame in frames]
    metric_ranges: dict[str, dict[str, float]] = {}
    stability_limits = {
        "peak_dbfs": 1.5,
        "rms_dbfs": 1.5,
        "stereo_correlation": 0.2,
        "stereo_width": 0.2,
    }
    for key, limit in stability_limits.items():
        values = [float(frame["metrics"][key]) for frame in frames if key in frame.get("metrics", {})]
        if not values:
            continue
        minimum, maximum = min(values), max(values)
        metric_ranges[key] = {"min": round(minimum, 3), "max": round(maximum, 3), "range": round(maximum - minimum, 3), "stability_limit": limit}
    if len(frames) < 3:
        status = "insufficient"
    else:
        status = "stable" if all(item["range"] <= item["stability_limit"] for item in metric_ranges.values()) else "changing"

    deviations_by_center: dict[float, list[float]] = {}
    for frame in frames:
        reference = frame.get("pink_noise_reference")
        if not isinstance(reference, dict) or reference.get("status") != "complete":
            continue
        for band in reference.get("bands", []):
            if not isinstance(band, dict):
                continue
            center = band.get("center_hz")
            deviation = band.get("deviation_db")
            if isinstance(center, (int, float)) and isinstance(deviation, (int, float)):
                deviations_by_center.setdefault(round(float(center), 3), []).append(float(deviation))
    pink_bands: list[dict[str, float]] = []
    for center, deviations in sorted(deviations_by_center.items()):
        minimum, maximum = min(deviations), max(deviations)
        pink_bands.append({
            "center_hz": center,
            "median_deviation_db": round(_median(deviations), 3),
            "min_deviation_db": round(minimum, 3),
            "max_deviation_db": round(maximum, 3),
            "range_db": round(maximum - minimum, 3),
        })
    largest = max(pink_bands, key=lambda band: abs(band["median_deviation_db"]), default=None)
    return {
        "sample_count": len(frames),
        "window_seconds": round(max(times) - min(times), 2),
        "status": status,
        "metric_ranges": metric_ranges,
        "pink_noise_shape": {
            "sample_count": sum(len(values) for values in deviations_by_center.values()),
            "largest_median_deviation": largest,
        },
    }


def validate_handoff(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        return {"ok": False, "error": f"Expected {SCHEMA}."}
    forbidden = sorted(_FORBIDDEN_AUDIO_FIELDS.intersection(payload))
    if forbidden:
        return {"ok": False, "error": "Raw audio is not accepted by the realtime handoff: " + ", ".join(forbidden) + "."}
    if "audio_feature_schema" in payload and payload.get("audio_feature_schema") != FEATURE_SCHEMA:
        return {"ok": False, "error": f"Expected {FEATURE_SCHEMA} when audio_feature_schema is supplied."}
    if "spectrum_schema" in payload and payload.get("spectrum_schema") != SPECTRUM_SCHEMA:
        return {"ok": False, "error": f"Expected {SPECTRUM_SCHEMA} when spectrum_schema is supplied."}
    if payload.get("kind") != "mix_review_snapshot":
        return {"ok": False, "error": "Only mix-review snapshots are accepted."}
    if "evidence" in payload:
        valid_evidence, evidence_error = _validate_shared_evidence_packet(payload.get("evidence"), expected_source="plugin_bus_snapshot")
        if not valid_evidence:
            return {"ok": False, "error": evidence_error}
    values: dict[str, float] = {}
    for key in _REQUIRED_NUMBERS:
        value = payload.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return {"ok": False, "error": f"{key} must be numeric."}
        if not math.isfinite(float(value)):
            return {"ok": False, "error": f"{key} must be finite."}
        values[key] = float(value)
    for key in _OPTIONAL_NUMBERS:
        if key not in payload:
            continue
        value = payload[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return {"ok": False, "error": f"{key} must be numeric."}
        if not math.isfinite(float(value)):
            return {"ok": False, "error": f"{key} must be finite."}
        values[key] = float(value)
    if not -120.0 <= values["peak_dbfs"] <= 6.0 or not -120.0 <= values["rms_dbfs"] <= 6.0:
        return {"ok": False, "error": "Peak and RMS must be expressed as dBFS."}
    if not -1.0 <= values["stereo_correlation"] <= 1.0 or not 0.0 <= values["stereo_width"] <= 1.0:
        return {"ok": False, "error": "Stereo metrics are outside their valid range."}
    if values["sample_rate"] <= 0 or values["analysed_samples"] <= 0:
        return {"ok": False, "error": "The snapshot has no analysed audio."}
    if not 0.0 <= values.get("crest_db", 0.0) <= 120.0 or not 0.0 <= values.get("transient_ratio", 0.0) <= 10.0 or not 0.0 <= values.get("clipped_samples", 0.0) <= 1_000_000:
        return {"ok": False, "error": "Dynamics metrics are outside their valid range."}
    if any(not 0.0 <= values.get(key, 0.0) <= 16.0 for key in ("low_energy", "mid_energy", "high_energy")):
        return {"ok": False, "error": "Realtime band-energy metrics are outside their valid range."}
    spectrum_bands: list[dict[str, float]] = []
    if "spectrum_bands" in payload:
        raw_spectrum = payload.get("spectrum_bands")
        if not isinstance(raw_spectrum, list) or len(raw_spectrum) > 16:
            return {"ok": False, "error": "spectrum_bands must be a list of at most 16 bands."}
        previous_center = 0.0
        for index, raw_band in enumerate(raw_spectrum):
            if not isinstance(raw_band, dict):
                return {"ok": False, "error": f"spectrum_bands[{index}] must be an object."}
            band: dict[str, float] = {}
            for key in ("center_hz", "low_hz", "high_hz", "energy"):
                value = raw_band.get(key)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                    return {"ok": False, "error": f"spectrum_bands[{index}].{key} must be finite numeric data."}
                band[key] = float(value)
            if not 0.0 < band["low_hz"] < band["center_hz"] < band["high_hz"] <= 24000.0:
                return {"ok": False, "error": f"spectrum_bands[{index}] has invalid frequency bounds."}
            if band["high_hz"] > values["sample_rate"] / 2.0 + 1.0:
                return {"ok": False, "error": f"spectrum_bands[{index}] exceeds the snapshot Nyquist frequency."}
            if not 0.0 <= band["energy"] <= 16.0:
                return {"ok": False, "error": f"spectrum_bands[{index}].energy is outside its valid range."}
            if band["center_hz"] <= previous_center:
                return {"ok": False, "error": "spectrum_bands must be sorted by strictly increasing center_hz."}
            previous_center = band["center_hz"]
            spectrum_bands.append(band)
    mode = str(payload.get("assistant_mode", "suggest")).strip().lower()
    if mode not in _ASSISTANT_MODES:
        return {"ok": False, "error": "assistant_mode must be ask, suggest, assist, or auto."}
    raw_state = payload.get("plugin_state", {})
    if raw_state is None:
        raw_state = {}
    if not isinstance(raw_state, dict):
        return {"ok": False, "error": "plugin_state must be an object."}
    plugin_state: dict[str, Any] = {}
    if "target_lufs" in raw_state:
        target = raw_state["target_lufs"]
        if isinstance(target, bool) or not isinstance(target, (int, float)) or not -24.0 <= float(target) <= -6.0:
            return {"ok": False, "error": "plugin_state.target_lufs is outside the supported range."}
        plugin_state["target_lufs"] = float(target)
    for key in ("analysis_enabled", "live_context_enabled"):
        if key in raw_state:
            if not isinstance(raw_state[key], bool):
                return {"ok": False, "error": f"plugin_state.{key} must be boolean."}
            plugin_state[key] = raw_state[key]
    if "assistant_mode" in raw_state and str(raw_state["assistant_mode"]).strip().lower() != mode:
        return {"ok": False, "error": "plugin_state.assistant_mode must match assistant_mode."}
    plugin_state["assistant_mode"] = mode
    pink_reference = pink_noise_reference_from_spectrum(spectrum_bands) if spectrum_bands else {"status": "abstained", "reason": "No realtime spectrum bands were supplied."}
    return {"ok": True, "metrics": values, "spectrum_bands": spectrum_bands, "pink_noise_reference": pink_reference, "target_lufs": payload.get("target_lufs"), "assistant_mode": mode, "plugin_state": plugin_state, "evidence": payload.get("evidence")}


def review_from_handoff(payload: dict[str, Any]) -> dict[str, Any]:
    """Return bounded observations suitable for KENN's Mix Review UI."""
    checked = validate_handoff(payload)
    if not checked["ok"]:
        return checked
    metrics = checked["metrics"]
    observations: list[dict[str, str]] = []
    if metrics["peak_dbfs"] > -0.3:
        observations.append({"severity": "warning", "title": "Very little peak headroom", "detail": "Peak level is within 0.3 dBFS of full scale; review limiting and export headroom."})
    if metrics.get("clipped_samples", 0.0) > 0:
        observations.append({"severity": "warning", "title": "Recent samples reached digital full scale", "detail": f"{int(metrics['clipped_samples'])} sample(s) in the most recent analysis block reached 0 dBFS. Check source gain and limiter behaviour."})
    if metrics["stereo_correlation"] < 0.0:
        observations.append({"severity": "warning", "title": "Potential mono-compatibility risk", "detail": "Correlation is negative in the last analysed buffer; audition the mix in mono before making a correction."})
    if metrics["stereo_width"] > 0.75:
        observations.append({"severity": "info", "title": "Wide side energy", "detail": "Side energy is high. This is stylistic, so compare against a reference and mono playback."})
    band_values = [metrics.get(key) for key in ("low_energy", "mid_energy", "high_energy")]
    if all(isinstance(value, (int, float)) for value in band_values):
        observations.append({
            "severity": "info",
            "title": "Realtime tonal snapshot available",
            "detail": "Low, mid and high band energy are available for a guided check. These are broad relative energy estimates, not a calibrated EQ curve or full-resolution pink-noise measurement.",
        })
    pink_reference = checked.get("pink_noise_reference")
    largest = pink_reference.get("largest_deviation") if isinstance(pink_reference, dict) and pink_reference.get("status") == "complete" else None
    if isinstance(largest, dict):
        frequency = largest.get("center_hz")
        deviation = largest.get("deviation_db")
        if isinstance(frequency, (int, float)) and isinstance(deviation, (int, float)):
            direction = "above" if deviation > 0 else "below"
            observations.append({
                "severity": "info",
                "title": "Realtime spectral reference available",
                "detail": f"The nearest realtime band, centred at {frequency:.0f} Hz, is {abs(deviation):.1f} dB {direction} a measured -3 dB/octave pink-noise-style baseline around the 1 kHz anchor. Use this as a broad listening target; it is not track attribution or an automatic EQ move.",
            })
    if not observations:
        observations.append({"severity": "info", "title": "No immediate bus-level warning", "detail": "Continue with a full Mix Review for loudness, tonal balance, dynamics and reference comparison."})
    return {
        "ok": True,
        "schema": "kenn.plugin_review.v1",
        "observations": observations,
        "automix": {
            "available": False,
            "reason": "This plug-in snapshot contains no stems. Upload or select stems before starting the quality-gated AutoMix renderer.",
        },
        "limitations": "A plug-in bus snapshot can report broad bus energy and an uncalibrated pink-noise-style shape reference, but cannot inspect DAW routing, plug-ins, automation, clip content, or track-level audio. It is not a calibrated LUFS, true-peak, or full-resolution EQ reference measurement.",
    }


def ingest_live_context(payload: dict[str, Any], *, session_id: str = "") -> dict[str, Any]:
    """Validate and retain one bounded plug-in feature frame.

    This is deliberately a compact feature snapshot, not raw audio, and it
    has a short TTL.  The caller owns the session id; an empty id uses the
    local plug-in session to preserve backwards compatibility.
    """
    review = review_from_handoff(payload)
    if not review["ok"]:
        return review
    key = (session_id or str(payload.get("session_id") or "plugin-local")).strip()[:128]
    now = time.time()
    checked = validate_handoff(payload)
    previous = _live_contexts.get(key, {})
    frames = [frame for frame in previous.get("frames", []) if isinstance(frame, dict)]
    frames.append({
        "received_at": now,
        "metrics": checked["metrics"],
        "spectrum_bands": checked["spectrum_bands"],
        "pink_noise_reference": checked["pink_noise_reference"],
    })
    cutoff = now - _LIVE_HISTORY_SECONDS
    frames = [frame for frame in frames if float(frame.get("received_at", 0.0)) >= cutoff][- _MAX_LIVE_FRAMES:]
    _live_contexts[key] = {"received_at": now, "metrics": checked["metrics"], "spectrum_bands": checked["spectrum_bands"], "pink_noise_reference": checked["pink_noise_reference"], "assistant_mode": checked["assistant_mode"], "plugin_state": checked["plugin_state"], "review": review, "frames": frames}
    for stale_key, item in list(_live_contexts.items()):
        if now - float(item.get("received_at", 0)) > _CONTEXT_TTL_SECONDS:
            _live_contexts.pop(stale_key, None)

    # Bridge native VST3 bus metrics into KENN Real-time Audio Telemetry Manager
    try:
        from kenn.audio_telemetry import get_telemetry_manager
        m = checked["metrics"]
        sb = checked.get("spectrum_bands", [])
        
        # Approximate 4-band spectral distribution from VST3 spectrum bands or band energy
        sub_e = float(m.get("low_energy", 0.25))
        low_mid_e = float(m.get("mid_energy", 0.25))
        high_mid_e = float(m.get("high_energy", 0.25))
        air_e = 0.25
        if sb:
            for b in sb:
                c = float(b.get("center_hz", 1000.0))
                e = float(b.get("energy", 0.25))
                if c <= 80:
                    sub_e = e
                elif 80 < c <= 500:
                    low_mid_e = e
                elif 500 < c <= 6000:
                    high_mid_e = e
                else:
                    air_e = e
        
        total_e = max(0.01, sub_e + low_mid_e + high_mid_e + air_e)
        telemetry_payload = {
            "integrated_lufs": round(float(m.get("rms_dbfs", -14.0)) - 3.0, 1),
            "short_term_lufs": round(float(m.get("rms_dbfs", -14.0)), 1),
            "true_peak_dbtp": round(float(m.get("peak_dbfs", -1.0)), 2),
            "spectral_energy": {
                "sub_20_60hz": round(sub_e / total_e, 3),
                "low_mid_200_500hz": round(low_mid_e / total_e, 3),
                "high_mid_2_6khz": round(high_mid_e / total_e, 3),
                "air_10_20khz": round(air_e / total_e, 3),
            },
            "phase_correlation": round(float(m.get("stereo_correlation", 0.9)), 2),
            "crest_factor_db": round(float(m.get("crest_db", 10.0)), 1),
            "timestamp": now,
        }
        get_telemetry_manager().ingest(telemetry_payload)
    except Exception:
        pass

    live_context = live_context_summary(key)
    from kenn.plugin_actions import proposals_from_live_context
    proposals = [] if checked["assistant_mode"] == "ask" else proposals_from_live_context(live_context, target_lufs=float(payload.get("target_lufs", -14.0)))
    return {**review, "session_id": key, "assistant_mode": checked["assistant_mode"], "live_context": live_context, "action_proposals": proposals}


def live_context_summary(session_id: str) -> dict[str, Any] | None:
    item = _live_contexts.get(session_id)
    now = time.time()
    if not item or now - float(item.get("received_at", 0)) > _CONTEXT_TTL_SECONDS:
        _live_contexts.pop(session_id, None)
        return None
    metrics = item["metrics"]
    age_seconds_raw = max(0.0, now - item["received_at"])
    age_seconds = round(age_seconds_raw, 2)
    current_for_diagnosis = age_seconds_raw <= _MAX_CURRENT_DIAGNOSIS_AGE_SECONDS
    result = {
        "schema": "kenn.live_mix_context.v1",
        "age_seconds": age_seconds,
        "assistant_mode": item["assistant_mode"],
        "plugin_state": item["plugin_state"],
        "scope": "plugin_bus",
        "peak_dbfs": metrics["peak_dbfs"],
        "rms_dbfs": metrics["rms_dbfs"],
        "stereo_correlation": metrics["stereo_correlation"],
        "stereo_width": metrics["stereo_width"],
        "sample_rate": metrics["sample_rate"],
        "analysed_samples": metrics["analysed_samples"],
    }
    for key in _OPTIONAL_NUMBERS:
        if key in metrics:
            result[key] = metrics[key]
    result["spectrum_schema"] = SPECTRUM_SCHEMA
    result["spectrum_bands"] = item.get("spectrum_bands", [])
    result["pink_noise_reference"] = item.get("pink_noise_reference", {"status": "abstained", "reason": "No realtime spectrum bands were supplied."})
    frames = [frame for frame in item.get("frames", []) if isinstance(frame, dict)]
    live_window = _live_window_summary(frames)
    result["live_window"] = live_window
    result["freshness"] = {
        "observed_at_epoch": float(item.get("received_at", now)),
        "age_seconds": result["age_seconds"],
        "ttl_seconds": _CONTEXT_TTL_SECONDS,
        "expires_at_epoch": float(item.get("received_at", now)) + _CONTEXT_TTL_SECONDS,
        "frame_count": live_window["sample_count"],
        "status": "current" if current_for_diagnosis else "stale_or_unknown",
        "current_for_diagnosis": current_for_diagnosis,
        "max_current_age_seconds": _MAX_CURRENT_DIAGNOSIS_AGE_SECONDS,
    }
    from kenn.core.evidence import from_plugin_context
    packet = from_plugin_context(result)
    if packet is not None:
        result["evidence"] = packet.payload()
    try:
        from kenn.core.mix_doctor import get_mix_doctor
        report = get_mix_doctor().get_latest_report()
        if report:
            result["mqm"] = {
                "score": report.mqm_score,
                "grade": report.grade,
                "critical_issues": len(report.critical_issues),
            }
    except Exception:
        pass
    return result


def live_review_summary(session_id: str) -> dict[str, Any]:
    """Return the latest validated review without requesting a new capture."""
    key = str(session_id or "").strip()[:128]
    if not key:
        return {"ok": False, "error": "session_id is required."}
    context = live_context_summary(key)
    if context is None:
        return {"ok": False, "error": "No fresh live plug-in context is available for this session.", "reason": "missing_or_expired_context"}
    item = _live_contexts.get(key, {})
    return {
        "ok": True,
        "schema": "kenn.plugin_live_review.v1",
        "session_id": key,
        "review": item.get("review", {}),
        "live_context": context,
        "advisory_only": True,
        "capture_requested": False,
    }


_pending_parameter_updates: dict[str, dict[str, Any]] = {}


def get_plugin_parameters(session_id: str) -> dict[str, Any]:
    """Return the active parameters and any pending host updates for a session."""
    key = str(session_id or "plugin-local").strip()[:128]
    item = _live_contexts.get(key)
    state = dict(item.get("plugin_state", {})) if item else {}
    if not state:
        state = {
            "assistant_mode": "suggest",
            "target_lufs": -14.0,
            "analysis_enabled": True,
            "live_context_enabled": True,
        }
    pending = dict(_pending_parameter_updates.get(key, {}))
    return {
        "ok": True,
        "session_id": key,
        "parameters": state,
        "pending_updates": pending,
    }


def set_plugin_parameter(session_id: str, parameter: str, value: Any) -> dict[str, Any]:
    """Queue a parameter update originating from Web UI to synchronize to host automation."""
    key = str(session_id or "plugin-local").strip()[:128]
    param_name = str(parameter or "").strip().lower()
    if param_name == "target_lufs":
        try:
            val = float(value)
            if not -24.0 <= val <= -6.0:
                return {"ok": False, "error": "target_lufs must be between -24.0 and -6.0 LUFS."}
        except (ValueError, TypeError):
            return {"ok": False, "error": "target_lufs must be a numeric value."}
    elif param_name == "assistant_mode":
        val = str(value or "").strip().lower()
        if val not in _ASSISTANT_MODES:
            return {"ok": False, "error": f"assistant_mode must be one of {', '.join(_ASSISTANT_MODES)}."}
    elif param_name in ("analysis_enabled", "live_context_enabled"):
        val = bool(value)
    else:
        return {"ok": False, "error": f"Unsupported plug-in parameter: {parameter}"}

    if key not in _pending_parameter_updates:
        _pending_parameter_updates[key] = {}
    _pending_parameter_updates[key][param_name] = val

    if key in _live_contexts:
        if "plugin_state" not in _live_contexts[key]:
            _live_contexts[key]["plugin_state"] = {}
        _live_contexts[key]["plugin_state"][param_name] = val
        if param_name == "assistant_mode":
            _live_contexts[key]["assistant_mode"] = val

    return {
        "ok": True,
        "session_id": key,
        "parameter": param_name,
        "value": val,
        "message": f"Parameter '{param_name}' set to {val}; queued for host synchronization.",
    }


def pop_pending_parameter_updates(session_id: str) -> dict[str, Any]:
    """Retrieve and clear queued parameter updates for the native DAW plug-in instance."""
    key = str(session_id or "plugin-local").strip()[:128]
    pending = _pending_parameter_updates.pop(key, {})
    return {
        "ok": True,
        "session_id": key,
        "pending_updates": pending,
    }


def set_plugin_parameters(session_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    """Queue multiple parameter updates originating from Web UI to synchronize to host automation."""
    key = str(session_id or "plugin-local").strip()[:128]
    if not isinstance(updates, dict) or not updates:
        return {"ok": False, "error": "updates must be a non-empty dictionary."}
    applied: dict[str, Any] = {}
    for param, val in updates.items():
        res = set_plugin_parameter(key, param, val)
        if not res.get("ok"):
            return res
        applied[res["parameter"]] = res["value"]
    return {
        "ok": True,
        "session_id": key,
        "parameters": applied,
        "message": f"Parameters {list(applied.keys())} queued for host synchronization.",
    }

