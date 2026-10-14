"""Validation and interpretation for KENN Mix Assistant handoff files.

The native plug-in writes these files outside its audio callback.  This module
does not infer unavailable information or start an AutoMix render: a render
still requires separately supplied stems and the existing job pipeline.
"""

from __future__ import annotations

from typing import Any
import math
import time
import threading

from kenn.core.live_spectrum_contract import validate_fft_spectra, validate_host_timeline

SCHEMA = "kenn.plugin_handoff.v1"
FEATURE_SCHEMA = "audio_feature_frame.v1"
SPECTRUM_SCHEMA = "realtime_spectrum.v1"
_REQUIRED_NUMBERS = ("peak_dbfs", "rms_dbfs", "stereo_correlation", "stereo_width", "sample_rate", "analysed_samples")
_OPTIONAL_NUMBERS = (
    "crest_db", "transient_ratio", "clipped_samples",
    # These are bounded linear band-energy estimates from the plug-in's
    # analysis engine. They are deliberately not called EQ
    # readings: no reference curve or calibrated spectrum is implied.
    "low_energy", "mid_energy", "high_energy",
    "audio_age_seconds",
)
_FORBIDDEN_AUDIO_FIELDS = frozenset({"audio_samples", "raw_audio", "waveform", "pcm"})
_CONTEXT_TTL_SECONDS = 30 * 60
# Retained context can support history, but diagnosis must not treat an old
# snapshot as the current state of the Ableton session.
_MAX_CURRENT_DIAGNOSIS_AGE_SECONDS = 15.0
_MAX_CONTINUOUS_AGE_SECONDS = 1.0  # Two 500 ms publishing intervals; stopped continuous windows retire promptly.
_LIVE_HISTORY_SECONDS = 2 * 60
_MAX_LIVE_FRAMES = 12
_live_contexts: dict[str, dict[str, Any]] = {}
_live_context_lock = threading.RLock()
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


def _valid_export_clock(value: Any, received_at: float) -> bool:
    """Accept finite local epoch seconds up to 50 ms ahead of receipt."""
    # Check the range before finite conversion: an arbitrary-size JSON integer
    # must be refused rather than overflow while validating a feature packet.
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and 0 <= value <= received_at + 0.05 and math.isfinite(value))


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
    if "exported_at_epoch" in payload and not _valid_export_clock(payload["exported_at_epoch"], time.time()):
        # Validate individual Ask/file/upload clocks during batch preflight too;
        # a malformed sibling must not replace another insert's current evidence.
        return {"ok": False, "error": "exported_at_epoch must be finite non-negative local epoch seconds, no more than 50 ms in the future."}
    if "evidence" in payload:
        valid_evidence, evidence_error = _validate_shared_evidence_packet(payload.get("evidence"), expected_source="plugin_bus_snapshot")
        if not valid_evidence:
            return {"ok": False, "error": evidence_error}
    # A host name is only a matching hint, never a durable Live track ID.
    host_track_name = payload.get("host_track_name", "")
    if not isinstance(host_track_name, str) or len(host_track_name) > 128:
        # Bound host text to 128 characters, as for the existing owner key, before matching it.
        return {"ok": False, "error": "host_track_name must be a string of at most 128 characters."}
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
    if values.get("audio_age_seconds", 0.0) < 0.0:
        # Future-dated audio would extend the diagnosis window without new playback.
        return {"ok": False, "error": "audio_age_seconds must be non-negative."}
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
    window = payload.get("measurement_window")
    if window is not None:
        if not isinstance(window, dict) or window.get("schema") != "kenn.continuous_window.v1" or not isinstance(window.get("valid"), bool):
            return {"ok": False, "error": "Invalid continuous measurement window."}
        for field in ("sequence", "source_generation", "start_sample", "end_sample", "dropped_samples", "invalid_samples"):
            value = window.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 2**53:
                return {"ok": False, "error": f"measurement_window.{field} must be a bounded non-negative integer."}
        duration = window.get("duration_seconds")
        span = window["end_sample"] - window["start_sample"]
        if (isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration)
                or span <= 0 or abs(duration - span / values["sample_rate"]) > 1e-6
                or abs(duration - 0.1) > 1.0 / values["sample_rate"] or window["sequence"] == 0 or window["source_generation"] == 0):
            # A coherent publication describes exactly one 100 ms window, within one sample of rounding.
            return {"ok": False, "error": "Continuous window duration/sample bounds disagree."}
        try:
            timeline = validate_host_timeline(window.get("host_timeline"), window)
        except ValueError as error:
            return {"ok": False, "error": str(error)}  # Contradictory clocks cannot ground cross-insert evidence.
        window = {key: window[key] for key in ("schema", "valid", "sequence", "source_generation", "start_sample", "end_sample", "duration_seconds", "dropped_samples", "invalid_samples")}
        if timeline:
            window["host_timeline"] = timeline
    try:
        fft_spectra = validate_fft_spectra(payload.get("fft_spectra"), window, values["sample_rate"])
    except ValueError as error:
        return {"ok": False, "error": str(error)}  # Reject malformed calibrated features rather than quietly using them.
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
    paired_windows = []
    raw_history = payload.get("paired_windows", [])
    if not isinstance(raw_history, list) or len(raw_history) > 6:
        return {"ok": False, "error": "paired_windows must contain at most six feature windows."}
    previous_end = -1
    for raw in raw_history:
        if not isinstance(raw, dict) or not window or not window["valid"]:
            return {"ok": False, "error": "Paired history requires a valid continuous publication."}
        # Only these fields may override the parent. In particular a child
        # cannot recurse, change track/source identity, or smuggle raw audio.
        fields = ("measurement_window", "fft_spectra", "peak_dbfs", "rms_dbfs", "stereo_correlation", "stereo_width", "analysed_samples", "audio_age_seconds")
        if any(key not in fields for key in raw) or any(key not in raw for key in fields):
            return {"ok": False, "error": "Invalid paired feature window fields."}
        child = validate_handoff({**payload, **raw, "paired_windows": []})
        if not child["ok"]:
            return child  # The same DSP and clock contract applies to history and current audio.
        child_window = child["measurement_window"] or {}
        clock, parent_clock = child_window.get("host_timeline") or {}, window.get("host_timeline") or {}
        if (not child_window.get("valid") or not clock.get("valid") or not parent_clock.get("valid")
                or child_window["source_generation"] != window["source_generation"]
                or child_window["dropped_samples"] != window["dropped_samples"] or child_window["invalid_samples"] != window["invalid_samples"]
                or clock["transport_epoch"] != parent_clock["transport_epoch"]
                or not previous_end < child_window["end_sample"] <= window["end_sample"]
                or window["end_sample"] - child_window["end_sample"] > 0.6 * values["sample_rate"]
                or child_window["sequence"] > window["sequence"]
                or abs(clock["end_sample"] - parent_clock["end_sample"] - child_window["end_sample"] + window["end_sample"]) > 0
                or child["metrics"]["audio_age_seconds"] + 0.005 < values.get("audio_age_seconds", 0.0)):
            return {"ok": False, "error": "Paired history straddles a clock/source change or lies outside its publication."}
        previous_end = child_window["end_sample"]
        paired_windows.append({"measurement_window": child_window, "fft_spectra": child["fft_spectra"],
                               **{key: child["metrics"][key] for key in (*_REQUIRED_NUMBERS, "audio_age_seconds")}})
    conversation = payload.get("conversation_id", "")
    if not isinstance(conversation, str) or len(conversation) > 128:
        return {"ok": False, "error": "conversation_id must be a string of at most 128 characters."}
    return {"ok": True, "conversation_id": conversation.strip(), "host_track_name": host_track_name.strip(), "metrics": values, "measurement_window": window, "fft_spectra": fft_spectra, "paired_windows": paired_windows, "spectrum_bands": spectrum_bands, "pink_noise_reference": pink_reference, "target_lufs": payload.get("target_lufs"), "assistant_mode": mode, "plugin_state": plugin_state, "evidence": payload.get("evidence")}


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
    """Serialize HTTP publishers so sample progress and source identity stay paired."""
    with _live_context_lock:
        return _ingest_live_context(payload, session_id=session_id)


def ingest_live_context_batch(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate up to 64 insert frames before caching any; return compact per-insert acknowledgements."""
    received_at = time.time()
    if (payload.get("schema") != "kenn.plugin_handoff_batch.v1" or set(payload) not in
            ({"schema", "frames"}, {"schema", "frames", "exported_at_epoch"})
            or not isinstance(payload.get("frames"), list) or not 1 <= len(payload["frames"]) <= 64):
        # The transport accepts features only; no extra top-level command or unbounded frame list can reach the cache.
        return {"ok": False, "error": "Expected a feature-only batch of one to 64 insert frames."}
    age_reference_at = received_at
    if "exported_at_epoch" in payload:
        exported = payload["exported_at_epoch"]
        if not _valid_export_clock(exported, received_at):
            # A 50 ms future-clock tolerance permits small local clock steps;
            # reject larger jumps atomically rather than extending evidence life.
            return {"ok": False, "error": "exported_at_epoch must be finite non-negative local epoch seconds, no more than 50 ms in the future."}
        age_reference_at = min(received_at, exported)
    # Older batch clients omit the export clock and retain receipt-relative
    # ages. New native clients always supply it to qualify transport freshness.
    identities = set()
    for frame in payload["frames"]:
        key = frame.get("session_id") if isinstance(frame, dict) else None
        if not isinstance(key, str) or not key.strip() or len(key) > 128 or key.strip() in identities:
            # Reject the whole batch before caching: duplicate or truncated IDs could overwrite another insert.
            return {"ok": False, "error": "Every batch frame needs a unique non-empty insert ID of at most 128 characters."}
        checked = validate_handoff(frame)
        if not checked["ok"]:
            return checked  # A malformed sibling cannot partially replace other inserts' evidence.
        identities.add(key.strip())
    with _live_context_lock:
        results = []
        for frame in payload["frames"]:
            # One receipt clock keeps validation time from making siblings
            # appear captured at different times or making older audio younger.
            result = _ingest_live_context(frame, session_id=frame["session_id"], received_at=received_at,
                                          age_reference_at=age_reference_at)
            acknowledgement = {"session_id": frame["session_id"].strip(), "ok": result["ok"]}
            if result["ok"]:
                acknowledgement["freshness"] = result["live_context"]["freshness"]
            else:
                acknowledgement["error"] = result["error"]  # A stale frame is rejected independently; current siblings remain usable.
            results.append(acknowledgement)
    return {"ok": all(item["ok"] for item in results), "schema": "kenn.plugin_handoff_batch.v1", "frames": results}


def _ingest_live_context(payload: dict[str, Any], *, session_id: str = "", received_at: float | None = None,
                         age_reference_at: float | None = None) -> dict[str, Any]:
    """Validate and retain one bounded plug-in feature frame.

    This is deliberately a compact feature snapshot, not raw audio, and it
    has a short TTL.  The caller owns the session id; an empty id uses the
    local plug-in session to preserve backwards compatibility.
    Validated frame/batch export clocks anchor audio age independently of receipt.
    """
    review = review_from_handoff(payload)
    if not review["ok"]:
        return review
    key = (session_id or str(payload.get("session_id") or "plugin-local")).strip()[:128]
    now = time.time() if received_at is None else received_at
    age_reference = now if age_reference_at is None else age_reference_at
    checked = validate_handoff(payload)
    if not checked["ok"]:
        # The local wall clock may step after review. Refuse before reading
        # validated metrics or mutating the cache if the export clock is now invalid.
        return checked
    if "exported_at_epoch" in payload:
        # Use the older anchor when a frame travels in a batch. Neither path
        # may grant another lifetime to audio delayed in collection or transit.
        age_reference = min(age_reference, payload["exported_at_epoch"])
    previous = _live_contexts.get(key, {})
    metrics = checked["metrics"]
    # A reset or host-name change starts a new source history. Count samples,
    # not HTTP deliveries: a stopped/disabled processor can resend old meters.
    same_source = (previous.get("conversation_id", "") == checked["conversation_id"]
                   and previous.get("host_track_name", "") == checked["host_track_name"]
                   and previous.get("metrics", {}).get("sample_rate") == metrics["sample_rate"]
                   and (previous.get("measurement_window") or {}).get("source_generation") == (checked["measurement_window"] or {}).get("source_generation"))
    last_samples = previous.get("metrics", {}).get("analysed_samples", -1)
    advancing = metrics["analysed_samples"] != last_samples
    source_pending = bool(previous and not same_source and not advancing) or bool(previous.get("source_pending") and not advancing)
    old_window, window = previous.get("measurement_window") or {}, checked["measurement_window"] or {}
    if old_window and window and old_window["source_generation"] == window["source_generation"]:
        if window["sequence"] < old_window["sequence"] or (window["sequence"] == old_window["sequence"]
                and window["valid"] and not old_window["valid"]):
            # Concurrent Ask/publisher requests may arrive out of order; never
            # roll back to earlier audio or resurrect a frame retired by a gap.
            return {"ok": False, "error": "Stale continuous publication; wait for a new complete audio window."}
    gap = bool(window and (not window["valid"] or window["dropped_samples"] != old_window.get("dropped_samples", 0)
                          or window["invalid_samples"] != old_window.get("invalid_samples", 0)
                          or (window.get("host_timeline") or {}).get("transport_epoch") != (old_window.get("host_timeline") or {}).get("transport_epoch")))
    frames = list(previous.get("frames", [])) if same_source and metrics["analysed_samples"] >= last_samples and not gap else []
    if advancing and (not window or window["valid"]):
        frames.append({
            "received_at": now,
            "metrics": metrics,
            "spectrum_bands": checked["spectrum_bands"],
            "pink_noise_reference": checked["pink_noise_reference"],
        })
    cutoff = now - _LIVE_HISTORY_SECONDS
    frames = [frame for frame in frames if float(frame.get("received_at", 0.0)) >= cutoff][- _MAX_LIVE_FRAMES:]
    paired_windows = []
    for entry in checked["paired_windows"]:
        observed = age_reference - entry["audio_age_seconds"]
        if same_source and not gap:
            for old in previous.get("paired_windows", []):
                if old["measurement_window"] == entry["measurement_window"]:
                    observed = min(observed, old["observed_at_epoch"])  # HTTP retries cannot make cached audio younger.
        paired_windows.append({**entry, "observed_at_epoch": observed})
    reported_state = dict(checked["plugin_state"])
    requests = dict(previous.get("parameter_requests", {})) if previous.get("conversation_id") == checked["conversation_id"] else {}
    requests = {name: value for name, value in requests.items() if reported_state.get(name) != value}
    # A frame already in flight may follow Pause. Retain the requested state
    # until a native frame acknowledges it; reassignment must not inherit it.
    effective_state = {**reported_state, **requests}
    _live_contexts[key] = {
        "received_at": now if advancing else previous["received_at"],
        "audio_observed_at": (age_reference - metrics.get("audio_age_seconds", 0.0) if advancing else
                              min(previous.get("audio_observed_at", previous["received_at"]), age_reference - metrics.get("audio_age_seconds", 0.0))),
        "host_track_name": checked["host_track_name"], "metrics": metrics,
        "conversation_id": checked["conversation_id"],
        "source_pending": source_pending, "measurement_window": checked["measurement_window"],
        "fft_spectra": checked["fft_spectra"],
        "paired_windows": paired_windows,
        "spectrum_bands": checked["spectrum_bands"], "pink_noise_reference": checked["pink_noise_reference"],
        "assistant_mode": effective_state["assistant_mode"], "plugin_state": effective_state,
        # Queued controls may change plugin_state before the host consumes them.
        # Keep the published state separate so the UI cannot claim a host acknowledgement.
        "reported_plugin_state": reported_state, "parameter_requests": requests,
        "review": review, "frames": frames,
    }
    for stale_key, item in list(_live_contexts.items()):
        if now - float(item.get("received_at", 0)) > _CONTEXT_TTL_SECONDS:
            _live_contexts.pop(stale_key, None)

    # Keep per-insert evidence scoped to its owner. RMS is not LUFS and sample
    # peak is not true peak; neither may be bridged into global master telemetry.
    live_context = live_context_summary(key)
    from kenn.plugin_actions import proposals_from_live_context
    may_propose = bool(live_context and live_context["freshness"]["current_for_diagnosis"])
    # Expired or invalid frames may remain useful as labelled history, but
    # cannot justify even a delivery-target suggestion.
    proposals = [] if checked["assistant_mode"] == "ask" or not may_propose else proposals_from_live_context(live_context, target_lufs=float(payload.get("target_lufs", -14.0)))
    return {**review, "session_id": key, "assistant_mode": checked["assistant_mode"], "live_context": live_context, "action_proposals": proposals}


def live_context_summary(session_id: str) -> dict[str, Any] | None:
    """Read a consistent feature history; the native audio thread never calls here."""
    with _live_context_lock:
        return _live_context_summary(session_id)


def _audio_currentness(item: dict[str, Any], now: float) -> tuple[float, bool]:
    """Return audio age in seconds and whether queued controls still permit diagnosis."""
    age = max(0.0, now - item.get("audio_observed_at", item["received_at"]))
    window = item.get("measurement_window")
    maximum = _MAX_CONTINUOUS_AGE_SECONDS if window else _MAX_CURRENT_DIAGNOSIS_AGE_SECONDS
    state = item["plugin_state"]
    # A native Ask can send a fresh window while background publishing is off.
    # A queued Pause still retires cached audio immediately; late frames must
    # not restore diagnosis before the host receives that request.
    return age, bool(age <= maximum and state.get("analysis_enabled", True)
                     and item.get("parameter_requests", {}).get("live_context_enabled") is not False
                     and not item.get("source_pending")
                     and (not window or window["valid"]))


def plugin_insert_sources(conversation_id: str, selected_insert: str = "") -> dict[str, Any]:
    """List up to 64 retained inserts for an explicit conversation, without selecting one.

    An unpublished launch insert remains selectable so its owner can opt into
    publishing. A known insert owned by another conversation is refused.
    """
    owner = str(conversation_id or "").strip()
    selected = str(selected_insert or "").strip()
    if not owner or len(owner) > 128 or len(selected) > 128:
        # Malformed launch identities must not fall back to a global insert list.
        return {"ok": False, "error": "A conversation ID of at most 128 characters is required."}
    with _live_context_lock:
        now = time.time()
        items = {key: item for key, item in _live_contexts.items()
                 if now - item["received_at"] <= _CONTEXT_TTL_SECONDS}
        selected_item = items.get(selected)
        if selected_item and selected_item.get("conversation_id") != owner:
            # Knowing an insert ID does not associate its audio with this chat.
            return {"ok": False, "error": "Selected insert belongs to another conversation. Open KENN from that insert."}
        owned = [(key, item) for key, item in items.items() if item.get("conversation_id") == owner]
        owned.sort(key=lambda entry: (entry[0] != selected, -entry[1]["received_at"], entry[0]))
        sources = []
        for key, item in owned[:64]:  # Match the native publisher's 64-insert batch limit.
            age, current = _audio_currentness(item, now)
            sources.append({"insert_id": key, "host_track_name": item.get("host_track_name", ""),
                            "audio_age_seconds": round(age, 2), "current_for_diagnosis": current,
                            "requested_parameters": dict(item["plugin_state"]),
                            "reported_parameters": dict(item.get("reported_plugin_state", item["plugin_state"]))})
        return {"ok": True, "conversation_id": owner, "sources": sources,
                "selected_status": "known" if selected_item else "waiting_for_publication"}


def queue_owned_plugin_parameters(insert: str, conversation_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    """Queue browser controls for its launch insert; never resolve a conversation to a sibling."""
    with _live_context_lock:
        ownership = plugin_insert_sources(conversation_id, insert)
        if not insert or not ownership.get("ok"):
            # Before first publication the explicit launch ID can bootstrap opt-in;
            # once published, conflicting ownership always blocks the request.
            return {"ok": False, "error": ownership.get("error", "Select an insert before changing audio analysis.")}
        return set_plugin_parameters(insert, updates, direct_insert=True)


def _live_context_summary(session_id: str) -> dict[str, Any] | None:
    item = _live_contexts.get(session_id)
    now = time.time()
    if not item or now - float(item.get("received_at", 0)) > _CONTEXT_TTL_SECONDS:
        # Expired features cannot ground a current-session answer; callers request new playback.
        _live_contexts.pop(session_id, None)
        return None
    metrics = item["metrics"]
    # Include native audio age even on the first HTTP delivery after a stop.
    age_seconds_raw, current_for_diagnosis = _audio_currentness(item, now)
    age_seconds = round(age_seconds_raw, 2)
    window = item.get("measurement_window")
    max_age = _MAX_CONTINUOUS_AGE_SECONDS if window else _MAX_CURRENT_DIAGNOSIS_AGE_SECONDS
    result = {
        "schema": "kenn.live_mix_context.v1",
        "age_seconds": age_seconds,
        "assistant_mode": item["assistant_mode"],
        "plugin_state": item["plugin_state"],
        "scope": "plugin_bus",
        "conversation_id": item.get("conversation_id", ""),
        "host_track_name": item.get("host_track_name", ""),
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
    if window:
        result["measurement_window"] = dict(window)
    if item.get("fft_spectra"):
        result["fft_spectra"] = item["fft_spectra"]
    result["paired_windows"] = [{**entry, "age_seconds": max(0.0, now - entry["observed_at_epoch"])} for entry in item.get("paired_windows", [])]
    result["spectrum_schema"] = SPECTRUM_SCHEMA
    result["spectrum_bands"] = item.get("spectrum_bands", [])
    result["pink_noise_reference"] = item.get("pink_noise_reference", {"status": "abstained", "reason": "No realtime spectrum bands were supplied."})
    frames = [frame for frame in item.get("frames", []) if isinstance(frame, dict)]
    live_window = _live_window_summary(frames)
    result["live_window"] = live_window
    result["freshness"] = {
        "observed_at_epoch": float(item.get("audio_observed_at", item["received_at"])),
        "received_at_epoch": float(item["received_at"]),
        "age_seconds": result["age_seconds"],
        "ttl_seconds": _CONTEXT_TTL_SECONDS,
        "expires_at_epoch": float(item.get("received_at", now)) + _CONTEXT_TTL_SECONDS,
        "frame_count": live_window["sample_count"],
        "status": "current" if current_for_diagnosis else "stale_or_unknown",
        "current_for_diagnosis": current_for_diagnosis,
        "max_current_age_seconds": max_age,
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
                "points_available": report.points_available,
                "meaning": report.meaning,
                "critical_issues": len(report.critical_issues),
            }
            # The plug-in has no request text, so only the default -1 dBTP ceiling is scored for the target part.
            from kenn.audio_telemetry import get_telemetry_manager
            from kenn.core.grade import grade_session
            latest = get_telemetry_manager().get_latest()
            result["grade"] = grade_session(report.to_dict(), latest.to_dict() if latest else None)
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


def _parameter_key(session_id: str) -> str:
    """Resolve a single insert for older conversation-keyed parameter callers."""
    key = str(session_id or "plugin-local").strip()[:128]
    with _live_context_lock:
        if key in _live_contexts or key in _pending_parameter_updates:
            return key
        matches = [insert for insert, item in _live_contexts.items() if item.get("conversation_id") == key
                   and time.time() - item["received_at"] <= _CONTEXT_TTL_SECONDS]
        if len(matches) > 1:
            raise ValueError("This conversation has multiple inserts; select the insert ID before changing its parameters.")
        return matches[0] if matches else key  # Preserve pre-publication and legacy parameter queues.


def get_plugin_parameters(session_id: str) -> dict[str, Any]:
    """Return the active parameters and any pending host updates for a session."""
    try:
        key = _parameter_key(session_id)
    except ValueError as error:
        return {"ok": False, "error": str(error)}  # An ambiguous conversation cannot select an audio instance.
    item = _live_contexts.get(key)
    state = dict(item.get("plugin_state", {})) if item else {}
    if not state:
        state = {
            "assistant_mode": "suggest",
            "target_lufs": -14.0,
            "analysis_enabled": True,
            "live_context_enabled": False,  # Native publishing requires explicit opt-in.
        }
    pending = dict(_pending_parameter_updates.get(key, {}))
    return {
        "ok": True,
        "session_id": key,
        "parameters": state,
        "pending_updates": pending,
    }


def set_plugin_parameter(session_id: str, parameter: str, value: Any, *, direct_insert: bool = False) -> dict[str, Any]:
    """Queue a parameter update originating from Web UI to synchronize to host automation."""
    try:
        key = session_id if direct_insert else _parameter_key(session_id)
    except ValueError as error:
        return {"ok": False, "error": str(error)}  # Never queue the update for whichever insert published last.
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
        _live_contexts[key].setdefault("parameter_requests", {})[param_name] = val
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
    try:
        key = _parameter_key(session_id)
    except ValueError as error:
        return {"ok": False, "error": str(error)}  # Ambiguous callers cannot consume another insert's pending update.
    pending = _pending_parameter_updates.pop(key, {})
    return {
        "ok": True,
        "session_id": key,
        "pending_updates": pending,
    }


def set_plugin_parameters(session_id: str, updates: dict[str, Any], *, direct_insert: bool = False) -> dict[str, Any]:
    """Queue multiple parameter updates originating from Web UI to synchronize to host automation."""
    key = str(session_id or "plugin-local").strip()[:128]
    if not isinstance(updates, dict) or not updates:
        return {"ok": False, "error": "updates must be a non-empty dictionary."}
    applied: dict[str, Any] = {}
    for param, val in updates.items():
        res = set_plugin_parameter(key, param, val, direct_insert=direct_insert)
        if not res.get("ok"):
            return res
        applied[res["parameter"]] = res["value"]
    return {
        "ok": True,
        "session_id": key,
        "parameters": applied,
        "message": f"Parameters {list(applied.keys())} queued for host synchronization.",
    }
