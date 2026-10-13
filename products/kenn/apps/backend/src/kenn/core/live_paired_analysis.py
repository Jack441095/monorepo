"""Compare explicitly associated inserts only on a demonstrated shared sample interval."""

from __future__ import annotations

import math
import re
from typing import Any

from kenn.core.live_analysis_binding import bound_insert_contexts


def wants_paired_analysis(question: str) -> bool:
    """Recognise comparison requests without treating one sidechain insert as a pair."""
    lower = question.casefold()
    return bool(re.search(r"\b(?:masking|overlap)\b", lower) or
                (re.search(r"\bkick\b", lower) and re.search(r"\bbass\b", lower) and re.search(r"\b(?:analyse|analyze|sidechain)\b", lower)))


def _targets(question: str, state: dict[str, Any], adapter: Any) -> list[int]:
    numbers = re.findall(r"\b(?:track|channel)\s+(\d+)\b", question.casefold())
    requests = [f"track {number}" for number in numbers]
    if not requests:
        requests = [role for role in ("kick", "bass") if re.search(rf"\b{role}\b", question.casefold())]
    indexes = []
    for request in requests:
        target = adapter.resolve("Analyse " + request, state, "").get("target")
        if target and target["index"] not in indexes:
            indexes.append(target["index"])
    # An unresolved or repeated target cannot stand in for a second source.
    return indexes if len(requests) == len(indexes) == 2 else []


def _windows(context: dict[str, Any]) -> list[dict[str, Any]]:
    if context.get("paired_windows"):
        return context["paired_windows"]
    # Publishers without the six-window cache can still offer their single
    # current FFT; no interpolation or timestamp guessing fills a missing pair.
    return [{**context, "observed_at_epoch": context["freshness"]["observed_at_epoch"], "age_seconds": context["freshness"]["age_seconds"]}]


def _matched_window(left: dict[str, Any], right: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]] | None:
    rate = left["sample_rate"]
    if rate != right["sample_rate"]:
        return None  # A sample index means a different time at a different rate.
    matches = []
    for a in _windows(left):
        for b in _windows(right):
            aw, bw = a.get("measurement_window") or {}, b.get("measurement_window") or {}
            at, bt = aw.get("host_timeline") or {}, bw.get("host_timeline") or {}
            af, bf = (a.get("fft_spectra") or {}).get("low"), (b.get("fft_spectra") or {}).get("low")
            if not at.get("valid") or not bt.get("valid") or not af or not bf:
                continue  # Missing host clocks or long-FFT warm-up do not establish alignment.
            alag, blag = (aw["end_sample"] - af["end_sample"]) / rate, (bw["end_sample"] - bf["end_sample"]) / rate
            # Capture-time agreement within 50 ms rejects separate loop passes
            # at the same sample indexes. Epoch counters are local to each insert.
            if (at["start_sample"] != bt["start_sample"] or at["end_sample"] != bt["end_sample"]
                    or af["size_samples"] != bf["size_samples"] or alag != blag
                    or max(a["age_seconds"] + alag, b["age_seconds"] + blag) > 1.0
                    or abs(a["observed_at_epoch"] - b["observed_at_epoch"]) > 0.050):
                continue
            matches.append((a, b))
    if not matches:
        return None  # Differently timed windows cannot justify a cross-track conclusion.
    return max(matches, key=lambda pair: min(pair[0]["observed_at_epoch"], pair[1]["observed_at_epoch"]))


def answer_paired_analysis(question: str, *, owner: str, state: dict[str, Any], adapter: Any) -> dict[str, Any]:
    """Return measured spectral co-activity and manual auditions; never issue a control card."""
    result: dict[str, Any] = {"ok": True, "route": "live_track_analysis", "answer_mode": "live_analysis", "sources": [], "found": True,
                              "confidence": "unknown", "status": "clarification_required", "requires_confirmation": False,
                              "proposal": None, "confirmation_token": ""}
    analysis = {"schema": "kenn.live_paired_analysis.v1", "measured": {}, "session": {}, "interpretations": [], "recommendations": [],
                "unavailable": ["Audible masking or causal sidechain gain reduction", "Sidechain input, routing and compressor settings", "Durable project identity and host delay-compensation qualification"]}
    result["analysis"] = analysis
    targets = _targets(question, state, adapter)
    if not targets or state.get("status") != "connected":
        result["answer"] = "I cannot determine a cross-track comparison without two identified sources. Name exactly two uniquely identified tracks, such as kick and bass or track 1 and track 2, with Live connected. A comparison needs audio from both inserts."
        return result  # Ambiguous names never pick the first matching Live object.
    candidates = bound_insert_contexts(owner, state)
    sources = []
    for index in targets:
        items = [item for item in candidates if item["binding"]["track_index"] == index]
        current = [item for item in items if item["context"]["freshness"]["current_for_diagnosis"]]
        sources.append(current or items)  # Reloaded processors must not compete with expired audio from their predecessor.
    if any(len(items) != 1 for items in sources):
        result["answer"] = "Place KENN on both tracks and bind each insert to its actual track number in this conversation. Keep one bound insert per track; re-bind after switching sets. No cross-track audio is inferred from the current insert alone."
        return result  # Other owners and duplicate insert declarations cannot supply the missing source.
    a, b = (items[0] for items in sources)
    if not all(item["context"]["freshness"]["current_for_diagnosis"] for item in (a, b)):
        result["answer"] = "Play both bound inserts with analysis enabled and feature publishing active, then ask again. Both audio measurements must be current."
        return result  # A recent measurement on one track cannot refresh the other.
    pair = _matched_window(a["context"], b["context"])
    if not pair:
        result["answer"] = "I have no matching current host-timed FFT interval from both inserts. Play the same passage through both with feature publishing active. Missing clocks, seeks, loops, warm-up or delayed deliveries prevent this comparison."
        return result  # Refuse comparison rather than aligning by insert-local counters or HTTP arrival order.
    aframe, bframe = pair
    fft_a, fft_b = aframe["fft_spectra"]["low"], bframe["fft_spectra"]["low"]
    # Include whole fixed groups whose lower boundary is below 250 Hz. The
    # resulting upper edge is reported exactly, rather than calling it 250 Hz.
    bands = [i for i in range(32) if 20.0 * 1000.0 ** (i / 32) < 250.0]
    power_a = [fft_a["band_power"][i] for i in bands]; power_b = [fft_b["band_power"][i] for i in bands]
    norm = math.sqrt(sum(p*p for p in power_a) * sum(p*p for p in power_b))
    clock = aframe["measurement_window"]["host_timeline"]
    lag_samples = aframe["measurement_window"]["end_sample"] - fft_a["end_sample"]
    fft_end = clock["end_sample"] - lag_samples
    names = [item["binding"]["track_name"] for item in (a, b)]
    measured = {"source": "two_explicitly_bound_insert_ffts", "tracks": names, "sample_rate": a["context"]["sample_rate"],
                "metric_host_start_sample": clock["start_sample"], "metric_host_end_sample": clock["end_sample"],
                "fft_host_start_sample": fft_end - fft_a["size_samples"], "fft_host_end_sample": fft_end,
                "fft_size_samples": fft_a["size_samples"], "bin_hz": fft_a["bin_hz"],
                "group_range_hz": [20.0, 20.0 * 1000.0 ** (len(bands) / 32)],
                "group_mean_square": [sum(power_a), sum(power_b)], "window_rms_dbfs": [aframe["rms_dbfs"], bframe["rms_dbfs"]],
                "capture_age_seconds": [aframe["age_seconds"] + lag_samples/a["context"]["sample_rate"], bframe["age_seconds"] + lag_samples/b["context"]["sample_rate"]]}
    analysis["measured"] = measured
    analysis["session"] = {"source": "fresh_live_snapshot_and_explicit_declarations", "track_indexes": targets, "project_identity": "producer_declared_current_set"}
    if min(sum(power_a), sum(power_b)) < 1e-8 or min(aframe["rms_dbfs"], bframe["rms_dbfs"]) <= -80.0:
        result["answer"] = "The paired capture interval matches, but one part has too little measured low-frequency activity to judge overlap. Play a passage where both parts are audible."
        return result  # -80 dBFS mean-square/activity floor is an abstention threshold, not a mix target.
    overlap = min(1.0, max(0.0, sum(p*q for p, q in zip(power_a, power_b))/norm))
    measured["spectral_shape_similarity"] = overlap
    result.update(status="analysed", confidence="medium")
    if re.search(r"\bsidechain\b", question.casefold()):
        result["confidence"] = "unknown"  # Output spectra do not measure causal gain reduction or routing.
        analysis["sidechain_status"] = "unknown"
    analysis["interpretations"].append({"finding": "Paired low-frequency spectral comparison", "confidence": "medium",
                                         "evidence": {"spectral_shape_similarity": overlap}, "meaning": "Similar band-power shapes may warrant a masking audition; they do not prove audible masking or identify a compressor trigger."})
    analysis["recommendations"].append({"tracks": names, "issue": "possible_low_frequency_competition", "confidence": "medium", "application": "manual",
                                       "change": "Compare both parts together and separately in mono at matched loudness before changing level, timing or EQ", "expected_effect": "Identify whether one part loses attack or body in context", "trade_off": "Reducing either part can weaken the intended balance"})
    result["answer"] = (f"'{names[0]}' and '{names[1]}' have a matching {fft_a['size_samples']}-sample capture: low-frequency band-power shape similarity {overlap:.2f} "
                        f"across 20–{measured['group_range_hz'][1]:.0f} Hz, with {fft_a['bin_hz']:.2f} Hz FFT-bin spacing. "
                        "This measures spectral co-activity; it does not prove audible masking. Compare both parts together and separately in mono at matched loudness before auditioning level, timing or EQ changes. "
                        "This aligns captured buffers; upstream plug-in delay compensation is not yet qualified. "
                        "Sidechain routing, trigger audio and gain reduction are unavailable. Matching output spectra cannot prove that sidechain compression works; a controlled, matched bypass comparison is still needed. No Live settings changed.")
    return result
