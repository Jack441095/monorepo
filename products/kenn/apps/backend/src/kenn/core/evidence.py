"""Typed, provenance-preserving evidence for KENN decisions.

User descriptions, measured audio features, and inferred causes must never be
collapsed into the same string.  This module is the common boundary for the
three available evidence sources: plug-in bus snapshots, Ableton session
metadata, and Mix Review measurements.  It is deliberately compact and JSON
serialisable so it can travel through the existing chat-history transport.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from copy import deepcopy
import json
import math
import re
import time
from typing import Any


MARKER = "KENN_EVIDENCE_PACKET_V1:"
MAX_PLUGIN_CONTEXT_AGE_SECONDS = 15.0
# Match the existing per-insert analysis floor; this is activity in dBFS, not a mix-quality target.
LIVE_ACTIVITY_FLOOR_DBFS = -80.0
# Mirror reference_matching.REFERENCE_MIN_RMS_DBFS (-60 dBFS) without loading
# the optional matching engine. Uploaded reports use mean channel RMS, not its mono sum.
UPLOADED_ACTIVITY_FLOOR_DBFS = -60.0
UPLOADED_SIGNAL_LIMITATION = "RMS is missing, invalid or at/below -60 dBFS; signal measurements, grading and recommendations are withheld."
REFERENCE_SIGNAL_LIMITATION = "Mix and reference RMS must both be finite numeric values above -60 dBFS; reference comparison measurements and recommendations are withheld."
LOW_END_SIGNAL_LIMITATION = "Low-end stem previews lack qualifying raw source or centered-window activity; unqualified stem names and shares are withheld. Both RMS readings must exceed -60 dBFS."
LOW_END_PREVIEW_LIMITATION = "Low-end shares describe each stem's own centered FFT-window spectrum, not relative stem levels, simultaneous audible masking or a whole-song ranking."
ERB_PREVIEW_LIMITATION = "ERB visibility is a relative-spectrum proxy for jointly active preview frames, not calibrated audible masking severity or a whole-song assessment."
STEM_MASKING_SIGNAL_LIMITATION = "ERB stem visibility lacks qualifying jointly active real preview frames; visibility and stem claims are withheld. Preview frames must exceed -60 dBFS RMS. Name-based fallback profiles are not measurements."
TRANSIENT_SIGNAL_LIMITATION = "Transient comparison lacks qualifying pre/post activity or valid matched-event evidence; score, profile and event count are withheld. Pre/post RMS must be finite and above -60 dBFS."


@dataclass(frozen=True)
class EvidenceFact:
    name: str
    value: float | str | bool
    unit: str = ""
    source: str = ""
    confidence: str = "measured"


@dataclass(frozen=True)
class EvidencePacket:
    source: str
    captured_at_age_seconds: float | None
    facts: tuple[EvidenceFact, ...]
    limitations: tuple[str, ...]
    observed_at_epoch: float | None = None
    stem_masking_provenance: dict[str, Any] | None = None
    transient_preservation_provenance: dict[str, Any] | None = None
    erb_masking_provenance: dict[str, Any] | None = None
    low_end_stems_provenance: list[dict[str, Any]] | None = None

    def payload(self) -> dict[str, Any]:
        payload = {
            "schema": "kenn.evidence.v1",
            "source": self.source,
            "captured_at_age_seconds": self.captured_at_age_seconds,
            "observed_at_epoch": self.observed_at_epoch,
            "facts": [asdict(fact) for fact in self.facts],
            "limitations": list(self.limitations),
        }
        if self.source == "stem_masking_analysis" and self.stem_masking_provenance is not None:
            # History must retain the source counts needed to requalify cached masking facts.
            payload["stem_masking_provenance"] = deepcopy(self.stem_masking_provenance)
        if self.source == "mix_review_upload" and self.transient_preservation_provenance is not None:
            # Replay must requalify the pre/post captures instead of trusting cached score facts.
            payload["transient_preservation_provenance"] = deepcopy(self.transient_preservation_provenance)
        if self.source == "mix_review_upload" and self.erb_masking_provenance is not None:
            # Replay requalifies real preview sources instead of trusting cached visibility.
            payload["erb_masking_provenance"] = deepcopy(self.erb_masking_provenance)
        if self.source == "mix_review_upload" and self.low_end_stems_provenance is not None:
            # Replayed names must remain tied to the actual source and centered FFT window.
            payload["low_end_stems_provenance"] = deepcopy(self.low_end_stems_provenance)
        if self.source in {"plugin_bus_snapshot", "realtime_mix_comparison"}:
            age = self.captured_at_age_seconds
            if self.observed_at_epoch is not None:
                age = max(0.0, time.time() - self.observed_at_epoch)
            current = age is not None and age <= MAX_PLUGIN_CONTEXT_AGE_SECONDS
            payload["freshness"] = {
                "status": "current" if current else "stale_or_unknown",
                "current_for_diagnosis": current,
                "age_seconds": round(age, 3) if age is not None else None,
                "max_current_age_seconds": MAX_PLUGIN_CONTEXT_AGE_SECONDS,
            }
        return payload


def live_context_has_activity(context: dict[str, Any] | None) -> bool:
    """Return whether finite numeric bus RMS exceeds the existing -80 dBFS activity floor."""
    if not isinstance(context, dict):
        # Missing telemetry cannot establish measured activity.
        return False
    rms = context.get("rms_dbfs")
    try:
        rms_value = float(rms) if not isinstance(rms, bool) and isinstance(rms, (int, float)) else None
    except OverflowError:
        rms_value = None  # An unrepresentable integer cannot establish the activity floor.
    return rms_value is not None and math.isfinite(rms_value) and rms_value > LIVE_ACTIVITY_FLOOR_DBFS


def uploaded_metrics_have_activity(metrics: dict[str, Any] | None) -> bool:
    """Return whether reported whole-file RMS exceeds the existing -60 dBFS floor."""
    if not isinstance(metrics, dict):
        # Missing report metrics cannot establish activity in the uploaded source.
        return False
    rms = metrics.get("rms_dbfs")
    try:
        value = float(rms) if isinstance(rms, (int, float)) and not isinstance(rms, bool) else None
    except OverflowError:
        # An unrepresentable integer cannot qualify the source for publication.
        return False
    return value is not None and math.isfinite(value) and value > UPLOADED_ACTIVITY_FLOOR_DBFS


def transient_preservation_has_activity(summary: dict[str, Any] | None) -> bool:
    """Qualify both full-file renders and the bounded result fields for a transient comparison."""
    if not isinstance(summary, dict):
        # A score without its two source readings cannot establish what was compared.
        return False
    activity = summary.get("activity")
    if not isinstance(activity, dict) or activity.get("schema") != "kenn.transient_preservation.activity.v1":
        # Older cached scores lack pre/post RMS provenance and must abstain on replay.
        return False
    if not all(uploaded_metrics_have_activity({"rms_dbfs": activity.get(key)}) for key in ("pre_rms_dbfs", "post_rms_dbfs")):
        # An active post-render cannot qualify a quiet or unmeasured pre-render.
        return False
    score = summary.get("score")
    try:
        score_value = float(score) if isinstance(score, (int, float)) and not isinstance(score, bool) else None
    except OverflowError:
        # An unrepresentable score cannot describe a bounded ratio.
        return False
    count = summary.get("matched_event_count")
    profile = summary.get("profile")
    # Cap the profile at 160 characters so replay retains a label, not cached critique prose.
    return (
        score_value is not None and math.isfinite(score_value) and 0.0 <= score_value <= 1.0
        and isinstance(count, int) and not isinstance(count, bool) and count > 0
        and isinstance(profile, str) and bool(profile.strip()) and len(profile.strip()) <= 160
    )


def _qualified_transient_preservation(summary: Any) -> dict[str, Any] | None:
    """Return a normalized score and its exact source activity proof, or abstain."""
    if not transient_preservation_has_activity(summary):
        # Keep malformed or inactive comparisons out of both facts and replay provenance.
        return None
    activity = summary["activity"]
    return {
        "score": float(summary["score"]),
        "matched_event_count": summary["matched_event_count"],
        "profile": summary["profile"].strip(),
        "activity": {
            "schema": "kenn.transient_preservation.activity.v1",
            "pre_rms_dbfs": float(activity["pre_rms_dbfs"]),
            "post_rms_dbfs": float(activity["post_rms_dbfs"]),
        },
    }


def qualified_stem_masking_summary(summary: Any) -> dict[str, Any] | None:
    """Return bounded ERB preview evidence backed by jointly active source frames."""
    if not isinstance(summary, dict):
        # Legacy visibility scalars do not establish which real audio was compared.
        return None
    activity = summary.get("activity")
    if (
        not isinstance(activity, dict) or activity.get("schema") != "kenn.erb_masking.activity.v1"
        or activity.get("active_floor_dbfs") != -60.0 or activity.get("frame_size_samples") != 4096
    ):
        # The proof describes the existing 4096-sample preview and -60 dBFS RMS floor.
        return None
    sources = activity.get("sources")
    pairs = activity.get("pairs")
    if (
        not isinstance(sources, list) or not 2 <= len(sources) <= 64
        or not isinstance(pairs, list) or not pairs
        or len(pairs) > len(sources) * (len(sources) - 1) // 2
    ):
        # Bound replay to 64 source identities and one entry per unordered pair.
        return None
    normalized_sources = []
    by_name = {}
    for source in sources:
        if not isinstance(source, dict):
            # A malformed source cannot be matched safely to a measured pair.
            return None
        name, rate = source.get("name"), source.get("sample_rate")
        count, active = source.get("frame_count"), source.get("active_frame_count")
        try:
            rate = float(rate) if isinstance(rate, (int, float)) and not isinstance(rate, bool) else None
        except OverflowError:
            # Unrepresentable rates cannot establish aligned preview frames.
            return None
        if (
            not isinstance(name, str) or not name.strip() or name != name.strip()
            or len(name) > 96 or name in by_name
            or rate is None or not math.isfinite(rate) or rate <= 0
            or not isinstance(count, int) or isinstance(count, bool) or not 0 <= count <= 16
            or not isinstance(active, int) or isinstance(active, bool) or not 0 <= active <= count
        ):
            # Exact unique names avoid aliasing; only the first 16 complete frames are measured.
            return None
        normalized = {"name": name, "sample_rate": rate, "frame_count": count, "active_frame_count": active}
        by_name[name] = normalized
        normalized_sources.append(normalized)
    normalized_pairs, seen, paired_names = [], set(), set()
    for pair in pairs:
        names = pair.get("stems") if isinstance(pair, dict) else None
        count = pair.get("simultaneously_active_frame_count") if isinstance(pair, dict) else None
        if (
            not isinstance(names, list) or len(names) != 2
            or not all(isinstance(name, str) and name in by_name for name in names)
            or names[0] == names[1]
        ):
            # Both distinct sources must refer to the exact decoded preview identities.
            return None
        key = tuple(sorted(names))
        first, second = (by_name[name] for name in names)
        if (
            key in seen or first["sample_rate"] != second["sample_rate"]
            or not isinstance(count, int) or isinstance(count, bool)
            or not 0 < count <= min(first["active_frame_count"], second["active_frame_count"])
        ):
            # Unequal frame durations or no shared active frame cannot support masking.
            return None
        seen.add(key)
        paired_names.update(names)
        normalized_pairs.append({"stems": list(names), "simultaneously_active_frame_count": count})
    visibility = summary.get("lowest_visibility")
    name, stem_count = summary.get("lowest_visibility_stem"), summary.get("stem_count")
    try:
        visibility = float(visibility) if isinstance(visibility, (int, float)) and not isinstance(visibility, bool) else None
    except OverflowError:
        # An overflowing value cannot describe a visibility ratio.
        return None
    if (
        visibility is None or not math.isfinite(visibility) or not 0 <= visibility <= 1
        or not isinstance(name, str) or name not in paired_names
        or not isinstance(stem_count, int) or isinstance(stem_count, bool)
        or stem_count != len(paired_names)
    ):
        # The selected visibility must belong to a measured stem, including a valid zero.
        return None
    return {
        "stem_count": stem_count, "lowest_visibility": visibility, "lowest_visibility_stem": name,
        "activity": {"schema": "kenn.erb_masking.activity.v1", "active_floor_dbfs": -60.0,
                     "frame_size_samples": 4096, "sources": normalized_sources, "pairs": normalized_pairs},
    }


def stem_masking_has_activity(summary: dict[str, Any] | None) -> bool:
    """Return whether a visibility summary retains jointly active real preview sources."""
    return qualified_stem_masking_summary(summary) is not None


def qualified_low_end_stems(summary: Any) -> list[dict[str, Any]]:
    """Copy up to two source-qualified spectrum previews, omitting invalid identities."""
    if not isinstance(summary, list) or not 1 <= len(summary) <= 2:
        # Empty/legacy sections retain an abstention without inventing a measured stem.
        return []
    names = [item.get("name") for item in summary if isinstance(item, dict)]
    qualified = []
    for item in summary:
        if not isinstance(item, dict):
            # Malformed entries do not erase independently qualified stems.
            continue
        name, activity = item.get("name"), item.get("activity")
        if (
            not isinstance(name, str) or not name.strip() or name != name.strip()
            or len(name) > 96 or names.count(name) != 1
        ):
            # Exact unique identities prevent an invalid alias becoming a measured ranking.
            continue
        if (
            not isinstance(activity, dict) or activity.get("schema") != "kenn.low_end_stem.activity.v1"
            or activity.get("active_floor_dbfs") != -60.0
        ):
            # Normalized ratios from older reports lack raw source/window activity proof.
            continue
        if not all(uploaded_metrics_have_activity({"rms_dbfs": activity.get(key)}) for key in ("source_rms_dbfs", "window_rms_dbfs")):
            # An active full file cannot qualify silence in the actual centered FFT window.
            continue
        count, size, start = (activity.get(key) for key in ("analysis_sample_count", "frame_size_samples", "window_start_sample"))
        if not isinstance(count, int) or isinstance(count, bool) or not 256 <= count <= 2**53 - 1:
            # 256 samples is the existing FFT minimum; JSON transports integers exactly up to 2**53-1.
            continue
        expected_size = 1 << (min(4096, count).bit_length() - 1)
        if (
            not isinstance(size, int) or isinstance(size, bool) or size != expected_size
            or not isinstance(start, int) or isinstance(start, bool) or start != (count - size) // 2
        ):
            # Geometry must describe the existing centered power-of-two FFT, not another active region.
            continue
        rate, share = activity.get("sample_rate"), item.get("low_end_share")
        try:
            rate = float(rate) if isinstance(rate, (int, float)) and not isinstance(rate, bool) else None
            share = float(share) if isinstance(share, (int, float)) and not isinstance(share, bool) else None
        except OverflowError:
            # Unrepresentable scalars cannot qualify a rate or bounded own-spectrum share.
            continue
        if (
            rate is None or not math.isfinite(rate) or rate <= 0
            or share is None or not math.isfinite(share) or not 0 <= share <= 1
        ):
            # A valid zero share is retained; no low-band energy is different from missing audio.
            continue
        qualified.append({
            "name": name, "low_end_share": share,
            "activity": {
                "schema": "kenn.low_end_stem.activity.v1", "active_floor_dbfs": -60.0,
                "source_rms_dbfs": float(activity["source_rms_dbfs"]),
                "window_rms_dbfs": float(activity["window_rms_dbfs"]),
                "sample_rate": rate, "analysis_sample_count": count,
                "frame_size_samples": size, "window_start_sample": start,
            },
        })
    return qualified


def low_end_stems_have_activity(summary: Any) -> bool:
    """Return whether every entry in a nonempty bounded preview list qualifies."""
    qualified = qualified_low_end_stems(summary)
    return bool(qualified) and len(qualified) == len(summary)


def reference_comparison_has_activity(comparison: dict[str, Any] | None) -> bool:
    """Qualify both uploaded sources from the matcher's downmixed RMS provenance."""
    if not isinstance(comparison, dict):
        # A score or cached recommendation alone cannot establish either source's activity.
        return False
    dynamics = comparison.get("dynamics")
    if not isinstance(dynamics, dict):
        # Older receipts without per-source RMS must abstain until they are reanalysed.
        return False
    return all(uploaded_metrics_have_activity(dynamics.get(source)) for source in ("mix", "reference"))


def plugin_context_for_advice(context: dict[str, Any] | None) -> dict[str, Any] | None:
    """Copy a published bus context, retaining only capture provenance when activity is unqualified.

    Raw handoff history remains available to measurement consumers. Advice responses
    use this boundary so nested FFTs, paired windows or cached evidence cannot expose
    signal facts after the top-level meters have been withheld.
    """
    if not isinstance(context, dict):
        # Preserve absence instead of manufacturing a valid-looking empty capture.
        return None
    if live_context_has_activity(context):
        return dict(context)
    safe = {
        key: context[key]
        for key in (
            "schema", "scope", "assistant_mode", "plugin_state", "conversation_id", "host_track_name",
            "sample_rate", "analysed_samples", "age_seconds", "audio_age_seconds", "freshness", "measurement_window",
        )
        if key in context
    }
    window = context.get("live_window")
    if isinstance(window, dict):
        safe["live_window"] = {key: window[key] for key in ("status", "sample_count", "window_seconds") if key in window}
    safe["signal_limitation"] = "RMS is missing, invalid or at/below -80 dBFS; signal-derived measurements and recommendations are withheld."
    # Rebuild rather than trust a cached packet that could predate the activity gate.
    packet = from_plugin_context(safe)
    if packet is not None:
        safe["evidence"] = packet.payload()
    return safe


def from_plugin_context(context: dict[str, Any] | None) -> EvidencePacket | None:
    """Convert the validated plug-in snapshot into explicit bus evidence."""
    if not isinstance(context, dict) or context.get("schema") != "kenn.live_mix_context.v1":
        return None
    has_activity = live_context_has_activity(context)
    fields = (
        ("peak_dbfs", "dBFS"), ("rms_dbfs", "dBFS"), ("crest_db", "dB"),
        ("transient_ratio", "ratio"), ("clipped_samples", "samples"),
        ("stereo_correlation", "correlation"), ("stereo_width", "ratio"),
        ("low_energy", "linear energy"), ("mid_energy", "linear energy"),
        ("high_energy", "linear energy"), ("sample_rate", "Hz"),
        ("analysed_samples", "samples"), ("audio_age_seconds", "seconds"),
    )
    facts: list[EvidenceFact] = []
    for name, unit in fields:
        if not has_activity and name not in {"sample_rate", "analysed_samples", "audio_age_seconds"}:
            # Capture provenance survives abstention; audio measurements cannot ground advice below the floor.
            continue
        value = context.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        facts.append(EvidenceFact(name, float(value), unit, "plugin_bus_snapshot"))
    pink_noise = context.get("pink_noise_reference")
    if has_activity and isinstance(pink_noise, dict):
        pink_largest = pink_noise.get("largest_deviation")
        if isinstance(pink_largest, dict):
            frequency = pink_largest.get("center_hz")
            deviation = pink_largest.get("deviation_db")
            if isinstance(frequency, (int, float)) and not isinstance(frequency, bool):
                facts.append(EvidenceFact("realtime_pink_noise_largest_deviation_frequency_hz", float(frequency), "Hz", "plugin_bus_snapshot"))
            if isinstance(deviation, (int, float)) and not isinstance(deviation, bool):
                facts.append(EvidenceFact("realtime_pink_noise_largest_deviation_db", float(deviation), "dB", "plugin_bus_snapshot"))
        curve = pink_noise.get("curve")
        if isinstance(curve, str) and curve.strip():
            facts.append(EvidenceFact("realtime_pink_noise_reference_curve", curve.strip(), "", "plugin_bus_snapshot"))
    # The 100 ms window the plug-in measured: where it sits in the stream and whether any audio was dropped around it.
    # Without these a reader cannot tell a fresh window from an old one, or a clean one from one with a gap.
    measurement_window = context.get("measurement_window")
    if isinstance(measurement_window, dict):
        for name, unit in (
            ("start_sample", "samples"), ("end_sample", "samples"), ("duration_seconds", "seconds"),
            ("source_generation", "count"), ("dropped_samples", "samples"), ("invalid_samples", "samples"),
        ):
            value = measurement_window.get(name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                # A missing or malformed field is left out rather than guessed; the packet stays valid without it.
                continue
            facts.append(EvidenceFact(f"measurement_window_{name}", float(value), unit, "plugin_bus_snapshot"))
    live_window = context.get("live_window")
    if isinstance(live_window, dict):
        sample_count = live_window.get("sample_count")
        window_seconds = live_window.get("window_seconds")
        status = live_window.get("status")
        if isinstance(sample_count, (int, float)) and not isinstance(sample_count, bool):
            facts.append(EvidenceFact("realtime_window_sample_count", float(sample_count), "snapshots", "plugin_bus_snapshot"))
        if isinstance(window_seconds, (int, float)) and not isinstance(window_seconds, bool):
            facts.append(EvidenceFact("realtime_window_seconds", float(window_seconds), "seconds", "plugin_bus_snapshot"))
        if isinstance(status, str) and status.strip():
            facts.append(EvidenceFact("realtime_window_status", status.strip(), "", "plugin_bus_snapshot"))
        shape = live_window.get("pink_noise_shape") if has_activity else None
        largest_median = shape.get("largest_median_deviation") if isinstance(shape, dict) else None
        if isinstance(largest_median, dict):
            frequency = largest_median.get("center_hz")
            deviation = largest_median.get("median_deviation_db")
            if isinstance(frequency, (int, float)) and not isinstance(frequency, bool):
                facts.append(EvidenceFact("realtime_pink_noise_median_deviation_frequency_hz", float(frequency), "Hz", "plugin_bus_snapshot"))
            if isinstance(deviation, (int, float)) and not isinstance(deviation, bool):
                facts.append(EvidenceFact("realtime_pink_noise_median_deviation_db", float(deviation), "dB", "plugin_bus_snapshot"))
    if not facts:
        return None
    age = context.get("age_seconds")
    age_value = float(age) if isinstance(age, (int, float)) else None
    return EvidencePacket(
        source="plugin_bus_snapshot",
        captured_at_age_seconds=age_value,
        facts=tuple(facts),
        limitations=(
            "Bus snapshot only; no track, source, routing, plug-in, automation, or clip-content analysis.",
            "Low/mid/high values are broad relative energy estimates; the fixed realtime bands are not a calibrated spectrum, and are not LUFS or true-peak measurement.",
            "The pink-noise-style comparison is a broad shape reference and cannot identify a track, cause, or automatic EQ move.",
            "A snapshot cannot establish the audible cause of a mix symptom by itself.",
            *(("RMS is missing, non-finite, or at/below -80 dBFS; signal-derived measurements are withheld until an audible passage is measured.",)
              if not has_activity else ()),
        ),
        observed_at_epoch=(time.time() - age_value) if age_value is not None else None,
    )


def from_mix_review_context(context: dict[str, Any] | None) -> EvidencePacket | None:
    """Convert a structured uploaded-track review into measured evidence.

    Whole-file activity must qualify before any signal fact is published.
    Only numeric report metrics become measured facts.  Report flags and
    recommended actions remain interpretations in the existing Mix Review
    context, rather than being falsely elevated to raw measurements.
    """
    if not isinstance(context, dict) or context.get("schema") != "kenn_mix_review_handoff.v1":
        return None
    metrics = context.get("metrics")
    if not uploaded_metrics_have_activity(metrics):
        # Older stored reviews and caller handoffs can bypass current review publication.
        return EvidencePacket(
            source="mix_review_upload", captured_at_age_seconds=None, facts=(),
            limitations=(UPLOADED_SIGNAL_LIMITATION,),
        )
    facts: list[EvidenceFact] = []
    transient_provenance: dict[str, Any] | None = None
    erb_provenance: dict[str, Any] | None = None
    low_end_provenance: list[dict[str, Any]] | None = None
    limitations: list[str] = []
    # These are calculated assessments/labels, not measurements.  They can
    # remain available in the Mix Review narrative, but must not gain the
    # stronger "measured" status simply because they happen to be numeric.
    derived_metric_names = {"technical_score", "quality_score", "confidence_score", "rating_score"}
    transient_metric_names = {
        "transient_preservation", "transient_preservation_score", "transient_preservation_profile",
        "transient_preservation_matched_event_count", "matched_event_count",
    }
    erb_metric_names = {"stem_masking", "stem_masking_lowest_visibility", "stem_masking_lowest_visibility_stem", "lowest_visibility", "overall_visibility", "lowest_visibility_stem", "stem_count"}
    low_end_metric_names = {"low_end_stems", "low_end_measured_stems", "low_end_summary", "low_end_overlap", "low_end_overlap_warning"}
    for name, value in metrics.items():
        if str(name).lower() in derived_metric_names | transient_metric_names | erb_metric_names | low_end_metric_names:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        unit = ""
        lowered = str(name).lower()
        if "lufs" in lowered:
            unit = "LUFS"
        elif "peak" in lowered or "rms" in lowered:
            unit = "dB"
        elif "correlation" in lowered:
            unit = "correlation"
        elif "width" in lowered:
            unit = "ratio"
        facts.append(EvidenceFact(str(name), float(value), unit, "mix_review_upload"))
    analysis = context.get("analysis_evidence")
    if isinstance(analysis, dict):
        transient = analysis.get("transient_preservation")
        if "transient_preservation" in analysis:
            transient_provenance = _qualified_transient_preservation(transient)
            if transient_provenance is None:
                limitations.append(TRANSIENT_SIGNAL_LIMITATION)
            else:
                facts.extend([
                    EvidenceFact("transient_preservation_score", transient_provenance["score"], "ratio", "mix_review_upload"),
                    EvidenceFact("transient_preservation_profile", transient_provenance["profile"], "", "mix_review_upload"),
                    EvidenceFact("transient_preservation_matched_event_count", transient_provenance["matched_event_count"], "events", "mix_review_upload"),
                ])
        if "stem_masking" in analysis:
            erb_provenance = qualified_stem_masking_summary(analysis.get("stem_masking"))
            if erb_provenance is None:
                limitations.append(STEM_MASKING_SIGNAL_LIMITATION)
            else:
                limitations.append(ERB_PREVIEW_LIMITATION)
                facts.extend([
                    EvidenceFact("stem_masking_lowest_visibility", erb_provenance["lowest_visibility"], "ratio", "mix_review_upload"),
                    EvidenceFact("stem_masking_lowest_visibility_stem", erb_provenance["lowest_visibility_stem"], "", "mix_review_upload"),
                ])
        if "low_end_stems" in analysis:
            low_end = analysis.get("low_end_stems")
            low_end_provenance = qualified_low_end_stems(low_end)
            if not low_end_stems_have_activity(low_end):
                limitations.append(LOW_END_SIGNAL_LIMITATION)
            if low_end_provenance:
                limitations.append(LOW_END_PREVIEW_LIMITATION)
                facts.append(EvidenceFact("low_end_measured_stems", ", ".join(item["name"] for item in low_end_provenance), "", "mix_review_upload"))
    if transient_provenance is None and any(str(name).lower() in transient_metric_names for name in metrics):
        limitations.append(TRANSIENT_SIGNAL_LIMITATION)
    if erb_provenance is None and any(str(name).lower() in erb_metric_names for name in metrics):
        limitations.append(STEM_MASKING_SIGNAL_LIMITATION)
    if not low_end_provenance and any(str(name).lower() in low_end_metric_names for name in metrics):
        limitations.append(LOW_END_SIGNAL_LIMITATION)
    comparison = context.get("reference_comparison")
    if reference_comparison_has_activity(comparison):
        largest = comparison.get("largest_spectral_difference")
        if isinstance(largest, dict):
            band = largest.get("band")
            delta = largest.get("delta", largest.get("delta_db"))
            if isinstance(band, str) and band.strip():
                facts.append(EvidenceFact("reference_largest_spectral_band", band.strip(), "", "mix_review_upload"))
            if isinstance(delta, (int, float)) and not isinstance(delta, bool):
                facts.append(EvidenceFact("reference_largest_spectral_delta", float(delta), "ratio", "mix_review_upload"))
        largest_ltas = comparison.get("largest_ltas_difference")
        if isinstance(largest_ltas, dict):
            frequency = largest_ltas.get("center_hz")
            delta = largest_ltas.get("delta_db")
            if isinstance(frequency, (int, float)) and not isinstance(frequency, bool):
                facts.append(EvidenceFact("reference_largest_ltas_frequency_hz", float(frequency), "Hz", "mix_review_upload"))
            if isinstance(delta, (int, float)) and not isinstance(delta, bool):
                facts.append(EvidenceFact("reference_largest_ltas_delta_db", float(delta), "dB", "mix_review_upload"))
        pink_noise = comparison.get("pink_noise_reference")
        if isinstance(pink_noise, dict):
            pink_largest = pink_noise.get("largest_deviation")
            if isinstance(pink_largest, dict):
                frequency = pink_largest.get("center_hz")
                deviation = pink_largest.get("deviation_db")
                if isinstance(frequency, (int, float)) and not isinstance(frequency, bool):
                    facts.append(EvidenceFact("pink_noise_largest_deviation_frequency_hz", float(frequency), "Hz", "mix_review_upload"))
                if isinstance(deviation, (int, float)) and not isinstance(deviation, bool):
                    facts.append(EvidenceFact("pink_noise_largest_deviation_db", float(deviation), "dB", "mix_review_upload"))
            curve = pink_noise.get("curve")
            if isinstance(curve, str) and curve.strip():
                facts.append(EvidenceFact("pink_noise_reference_curve", curve.strip(), "", "mix_review_upload"))
        lufs_delta = comparison.get("lufs_delta_db")
        if isinstance(lufs_delta, (int, float)) and not isinstance(lufs_delta, bool):
            facts.append(EvidenceFact("reference_lufs_delta_db", float(lufs_delta), "dB", "mix_review_upload"))
    if not facts:
        return None
    return EvidencePacket(
        source="mix_review_upload",
        captured_at_age_seconds=None,
        facts=tuple(facts),
        limitations=(
            "Measurements apply to the uploaded render reviewed by Mix Review, not to unuploaded revisions.",
            "A stereo render cannot prove individual track, routing, plug-in, or automation causes.",
            "Optional stem masking and transient comparisons apply only to the supplied stems/renders; they prioritise tests but do not establish an audible cause on their own.",
            *limitations,
            *((REFERENCE_SIGNAL_LIMITATION,) if isinstance(comparison, dict) and not reference_comparison_has_activity(comparison) else ()),
        ),
        transient_preservation_provenance=transient_provenance,
        erb_masking_provenance=erb_provenance,
        low_end_stems_provenance=low_end_provenance,
    )


def from_realtime_mix_comparison(comparison: dict[str, Any] | None) -> EvidencePacket | None:
    """Convert a validated live-versus-uploaded comparison into answer evidence.

    The comparison is derived from two already-scoped measurements. Keeping it
    as its own packet prevents the answer layer from silently treating a short
    plugin-bus window and a whole-file render as one measurement set.
    """
    if not isinstance(comparison, dict) or comparison.get("schema") != "kenn.realtime_mix_comparison.v1":
        return None
    if comparison.get("comparison_available") is not True:
        return None
    facts: list[EvidenceFact] = []
    for item in (comparison.get("comparisons") or [])[:8]:
        if not isinstance(item, dict):
            continue
        metric = str(item.get("metric") or "").strip().lower()
        if not metric:
            continue
        unit = str(item.get("unit") or "")[:32]
        for field, name in (
            ("live_value", f"realtime_live_{metric}"),
            ("uploaded_value", f"uploaded_{metric}"),
            ("delta_live_minus_uploaded", f"live_minus_uploaded_{metric}"),
        ):
            value = item.get(field)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                facts.append(EvidenceFact(name, float(value), unit, "realtime_mix_comparison", "derived"))
    pink = comparison.get("pink_noise_shape")
    if isinstance(pink, dict):
        live = pink.get("live") if isinstance(pink.get("live"), dict) else {}
        uploaded = pink.get("uploaded") if isinstance(pink.get("uploaded"), dict) else {}
        for source_name, source in (("realtime", live), ("uploaded", uploaded)):
            frequency = source.get("center_hz")
            deviation = source.get("deviation_db")
            if isinstance(frequency, (int, float)) and not isinstance(frequency, bool):
                facts.append(EvidenceFact(f"{source_name}_pink_noise_center_hz", float(frequency), "Hz", "realtime_mix_comparison", "derived"))
            if isinstance(deviation, (int, float)) and not isinstance(deviation, bool):
                facts.append(EvidenceFact(f"{source_name}_pink_noise_deviation_db", float(deviation), "dB", "realtime_mix_comparison", "derived"))
        delta = pink.get("deviation_delta_db")
        if isinstance(delta, (int, float)) and not isinstance(delta, bool):
            facts.append(EvidenceFact("live_minus_uploaded_pink_noise_deviation_db", float(delta), "dB", "realtime_mix_comparison", "derived"))
    live_window = comparison.get("live_window")
    if isinstance(live_window, dict):
        # Same window fields chat gets from the plug-in snapshot, so both answer paths can say how fresh and how clean the live side was.
        for key, unit in (
            ("end_sample", "samples"), ("source_generation", "count"), ("dropped_samples", "samples"),
            ("invalid_samples", "samples"), ("audio_age_seconds", "seconds"),
        ):
            value = live_window.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                facts.append(EvidenceFact(f"realtime_live_window_{key}", float(value), unit, "realtime_mix_comparison", "derived"))
    if not facts:
        return None
    return EvidencePacket(
        source="realtime_mix_comparison",
        captured_at_age_seconds=0.0,
        facts=tuple(facts),
        limitations=tuple(
            str(item)[:512]
            for item in (comparison.get("limitations") or [])[:8]
            if str(item).strip()
        ) or (
            "The live values are current or short-window plugin-bus observations; uploaded values are whole-file review measurements.",
            "The comparison does not identify a responsible Live track or device and does not authorize a mutation.",
        ),
        observed_at_epoch=time.time(),
    )


def _qualified_masking_findings(context: dict[str, Any]) -> list[tuple[list[str], str, float]] | None:
    """Return validated candidates, or None when source activity cannot support a signal conclusion."""
    activity = context.get("activity")
    if not isinstance(activity, dict) or activity.get("schema") != "kenn.stem_masking.activity.v1":
        # Older cached facts cannot establish whether any supplied pair was active.
        return None
    floor = activity.get("active_floor_dbfs")
    if isinstance(floor, bool) or not isinstance(floor, (int, float)) or floor != -50.0:
        # -50 dBFS is the existing masking analyser's band-activity floor.
        return None
    frames = activity.get("frame_count")
    if isinstance(frames, bool) or not isinstance(frames, int) or frames <= 0:
        # Fractions need a measured positive number of overlapping FFT frames.
        return None
    sources, pairs = activity.get("sources"), activity.get("pairs")
    if not isinstance(sources, list) or not 2 <= len(sources) <= 12 or not isinstance(pairs, list) or len(pairs) > 66:
        # Match the analyser's 12-stem limit and its 66 unordered pairs.
        return None
    source_counts: dict[str, int] = {}
    for source in sources:
        name = source.get("name") if isinstance(source, dict) else None
        count = source.get("active_frame_count") if isinstance(source, dict) else None
        if not isinstance(name, str) or not name.strip() or name in source_counts:
            # Ambiguous source identities cannot qualify a named finding.
            return None
        if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= frames:
            # Activity counts must be a subset of the captured frames.
            return None
        source_counts[name] = count
    pair_counts: dict[frozenset[str], int] = {}
    for pair in pairs:
        names = pair.get("stems") if isinstance(pair, dict) else None
        count = pair.get("simultaneously_active_frame_count") if isinstance(pair, dict) else None
        if not isinstance(names, list) or len(names) != 2 or any(not isinstance(name, str) or name not in source_counts for name in names):
            # Each pair must refer to two of these exact measured sources.
            return None
        identity = frozenset(names)
        if len(identity) != 2 or identity in pair_counts:
            # Reversed duplicates must not stand in for a missing pair.
            return None
        if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= min(source_counts[name] for name in names):
            # A simultaneous count cannot exceed either source's active count.
            return None
        if count < max(0, sum(source_counts[name] for name in names) - frames):
            # Two active subsets must overlap once their combined count exceeds the capture.
            return None
        pair_counts[identity] = count
    if len(pair_counts) != len(sources) * (len(sources) - 1) // 2 or not any(pair_counts.values()):
        # A partial grid or no simultaneous activity cannot justify an aggregate zero.
        return None
    findings = context.get("findings")
    bands = {"sub_bass", "bass", "low_mid", "mid", "upper_mid", "presence", "brilliance"}
    if not isinstance(findings, list) or len(findings) > len(pair_counts) * len(bands):
        # The analyser emits at most one candidate for each pair/band relationship.
        return None
    validated: list[tuple[list[str], str, float]] = []
    seen: set[tuple[frozenset[str], str]] = set()
    for finding in findings:
        if not isinstance(finding, dict) or finding.get("fault_family") != "masking" or finding.get("detected") is not True:
            # A scalar lookalike or explicitly undetected result is not a masking candidate.
            return None
        names = finding.get("stems") if isinstance(finding, dict) else None
        band = finding.get("band") if isinstance(finding, dict) else None
        evidence = finding.get("evidence") if isinstance(finding, dict) else None
        if not isinstance(names, list) or len(names) != 2 or any(not isinstance(name, str) for name in names) or not isinstance(band, str) or band not in bands or not isinstance(evidence, dict):
            # Dropping malformed candidates would falsely turn an invalid result into zero.
            return None
        identity = frozenset(names)
        fraction = evidence.get("competing_frame_fraction")
        if isinstance(fraction, bool) or not isinstance(fraction, (int, float)):
            # A candidate must carry a numeric measured fraction, not prose or a flag.
            return None
        try:
            fraction = float(fraction)
        except OverflowError:
            # Unrepresentable fractions cannot describe captured frame counts.
            return None
        if not math.isfinite(fraction) or not 0.20 <= fraction <= 1.0 or len(identity) != 2 or not pair_counts.get(identity):
            # 20% is the analyser's existing candidate threshold; inactive pairs abstain.
            return None
        if fraction > pair_counts[identity] / frames + 0.0005 or (identity, band) in seen:
            # Producer fractions round to three decimals (at most 0.0005 ratio upward).
            return None
        if evidence.get("active_floor_dbfs") != -50.0 or evidence.get("competing_within_db") != 6.0:
            # These are the analyser's existing -50 dBFS activity and 6 dB competition rules.
            return None
        seen.add((identity, band))
        validated.append((names, band, fraction))
    return validated


def from_stem_masking_context(context: dict[str, Any] | None) -> EvidencePacket | None:
    """Rebuild masking facts from activity-qualified findings, retaining capture dimensions on abstention."""
    if not isinstance(context, dict) or context.get("schema") != "kenn.mix_review_masking_analysis.v1" or context.get("ok") is not True:
        return None  # Other result schemas cannot supply masking evidence.
    packet = context.get("evidence")
    if (
        not isinstance(packet, dict)
        or packet.get("schema") != "kenn.evidence.v1"
        or packet.get("source") != "stem_masking_analysis"
    ):
        return None  # The packet must identify the same analyser as the result.
    raw_facts = packet.get("facts")
    raw_limitations = packet.get("limitations")
    if not isinstance(raw_facts, list) or not isinstance(raw_limitations, list):
        return None  # A malformed evidence envelope cannot be projected safely.
    facts: list[EvidenceFact] = []
    provenance_units = {"stem_count": "stems", "sample_rate": "Hz", "analyzed_seconds": "seconds"}
    for item in raw_facts[:32]:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or item["name"] not in provenance_units:
            # Signal claims are rebuilt below; only the three capture metadata names survive here.
            continue
        value = item.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            # Flags and prose cannot replace measured capture dimensions.
            continue
        try:
            value = float(value)
        except OverflowError:
            # Keep the other capture metadata if one legacy number is unrepresentable.
            continue
        if not math.isfinite(value) or value <= 0 or (item["name"] == "stem_count" and (value > 12 or not value.is_integer())):
            # Invalid dimensions remain absent without discarding other capture provenance.
            continue
        facts.append(EvidenceFact(
            item["name"], value, provenance_units[item["name"]], "stem_masking_analysis",
        ))
    limitations = tuple(str(item)[:512] for item in raw_limitations[:8] if str(item).strip())
    findings = _qualified_masking_findings(context)
    provenance = None
    if findings is None:
        # Missing activity, quiet pairs and malformed candidates must not become a reassuring zero.
        limitations += ("No valid simultaneously active stem pair is established above the existing -50 dBFS band floor, or candidate provenance is invalid; masking measurements and recommendations are withheld.",)
    else:
        activity = context["activity"]
        provenance = {
            "activity": {
                "schema": "kenn.stem_masking.activity.v1", "active_floor_dbfs": -50.0,
                "frame_count": activity["frame_count"],
                "sources": [{"name": item["name"], "active_frame_count": item["active_frame_count"]} for item in activity["sources"]],
                "pairs": [{"stems": list(item["stems"]), "simultaneously_active_frame_count": item["simultaneously_active_frame_count"]} for item in activity["pairs"]],
            },
            "findings": [{
                "fault_family": "masking", "detected": True, "stems": list(names), "band": band,
                "evidence": {"competing_frame_fraction": fraction, "active_floor_dbfs": -50.0, "competing_within_db": 6.0},
            } for names, band, fraction in findings],
        }
        facts.append(EvidenceFact("masking_candidate_count", len(findings), "candidates", "stem_masking_analysis", "measured_proxy"))
        if findings:
            names, band, fraction = max(findings, key=lambda item: item[2])
            facts.extend([
                EvidenceFact("masking_highest_competing_frame_fraction", fraction, "ratio", "stem_masking_analysis", "measured_proxy"),
                EvidenceFact("masking_highest_pair", " + ".join(name[:96] for name in names), "", "stem_masking_analysis", "measured_proxy"),
                EvidenceFact("masking_highest_band", band, "", "stem_masking_analysis", "measured_proxy"),
            ])
    return EvidencePacket("stem_masking_analysis", None, tuple(facts), limitations, stem_masking_provenance=provenance)


def from_audio_classification_context(context: dict[str, Any] | None) -> EvidencePacket | None:
    """Convert a completed SLO-style result into advisory answer evidence."""
    if (
        not isinstance(context, dict)
        or context.get("schema") != "kenn.audio_classification.v1"
        or context.get("status") != "completed"
    ):
        return None
    try:
        from kenn.core.audio_classification import AudioClassificationError, normalize
        classification = normalize(context)
    except (AudioClassificationError, ImportError, TypeError, ValueError):
        return None

    def top_labels(values: Any) -> str | None:
        if not isinstance(values, list):
            return None
        labels = []
        for item in values[:3]:
            if not isinstance(item, dict) or not isinstance(item.get("label"), str):
                continue
            probability = item.get("probability")
            if isinstance(probability, (int, float)) and not isinstance(probability, bool):
                labels.append(f"{item['label'][:96]} ({float(probability):.1%})")
        return ", ".join(labels) if labels else None

    ood = classification["out_of_distribution"]
    facts: list[EvidenceFact] = [
        EvidenceFact("classification_selected_label", classification["selected_label"], "", "audio_classification", "specialist_inference"),
        EvidenceFact("classification_selected_source", classification["selected_source"], "", "audio_classification", "specialist_inference"),
        EvidenceFact("classification_confidence_band", classification["confidence_band"], "", "audio_classification", "specialist_inference"),
        EvidenceFact("classification_ood_status", ood["status"], "", "audio_classification", "specialist_inference"),
        EvidenceFact("classification_ood_score", float(ood["score"]), "score", "audio_classification", "specialist_inference"),
    ]
    for name, values in (
        ("classification_audio_only_top_k", classification["audio_only"]),
        ("classification_metadata_assisted_top_k", classification["metadata_assisted"]),
    ):
        rendered = top_labels(values)
        if rendered:
            facts.append(EvidenceFact(name, rendered, "", "audio_classification", "specialist_inference"))
    limitations = [
        "This is specialist classifier inference, not proof of the audio source, track role, or musical quality.",
        "Audio-only and metadata-assisted predictions are separate; metadata may include filenames or folders.",
        "Unknown or out-of-distribution output must remain unresolved until a producer or stronger evidence confirms it.",
    ]
    limitations.extend(
        item[:256] for item in classification["limitations"]
        if isinstance(item, str) and item.strip() and item[:256] not in limitations
    )
    return EvidencePacket("audio_classification", None, tuple(facts), tuple(limitations[:8]))


def from_ableton_session(session: dict[str, Any] | None) -> EvidencePacket | None:
    """Convert a read-only Ableton bridge snapshot into project evidence."""
    if not isinstance(session, dict) or session.get("status") != "connected":
        return None
    facts: list[EvidenceFact] = []
    tempo = session.get("tempo")
    if isinstance(tempo, (int, float)) and not isinstance(tempo, bool):
        facts.append(EvidenceFact("tempo", float(tempo), "BPM", "ableton_session_snapshot"))
    tracks = session.get("tracks")
    if isinstance(tracks, list):
        facts.append(EvidenceFact("track_count", len(tracks), "tracks", "ableton_session_snapshot"))
        named = [str(item.get("name") or "").strip() for item in tracks if isinstance(item, dict)]
        named = [name for name in named if name]
        if named:
            facts.append(EvidenceFact("track_names", ", ".join(named[:12]), "", "ableton_session_snapshot"))
        inventory: list[str] = []
        for number, item in enumerate(tracks[:12], start=1):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip() or f"Track {number}"
            raw_devices = item.get("devices")
            device_names = [
                str(device.get("name") or "").strip()
                for device in (raw_devices if isinstance(raw_devices, list) else [])
                if isinstance(device, dict) and str(device.get("name") or "").strip()
            ]
            inventory.append(f"{number}: {name} ({', '.join(device_names) if device_names else 'no devices'})")
        if inventory:
            facts.append(EvidenceFact("track_inventory", "; ".join(inventory), "", "ableton_session_snapshot"))
    if not facts:
        return None
    return EvidencePacket(
        source="ableton_session_snapshot",
        captured_at_age_seconds=None,
        facts=tuple(facts),
        limitations=(
            "Ableton snapshot exposes project structure and mixer state, not clip content, routing, automation, spectrum, loudness, or phase measurement.",
        ),
    )
def history_turn(packet: EvidencePacket) -> dict[str, str]:
    """Encode measured facts in a non-user turn for the existing chat API."""
    return {"role": "user", "content": MARKER + json.dumps(packet.payload(), separators=(",", ":"))}


def packets_from_history(history: list | None) -> list[EvidencePacket]:
    packets: list[EvidencePacket] = []
    for turn in history or []:
        if not isinstance(turn, dict):
            continue
        text = str(turn.get("content") or "")
        if not text.startswith(MARKER):
            continue
        try:
            raw = json.loads(text[len(MARKER):])
        except (TypeError, ValueError):
            continue
        if not isinstance(raw, dict) or raw.get("schema") != "kenn.evidence.v1":
            continue
        source = str(raw.get("source") or "")
        raw_facts = raw.get("facts")
        if not source or not isinstance(raw_facts, list):
            continue
        facts: list[EvidenceFact] = []
        stale_names: set[str] = set()
        if source == "stem_masking_analysis":
            # Old scalar facts cannot bypass the current source-activity contract on replay.
            provenance = raw.get("stem_masking_provenance")
            provenance = provenance if isinstance(provenance, dict) else {}
            packet = from_stem_masking_context({
                "schema": "kenn.mix_review_masking_analysis.v1", "ok": True,
                "activity": provenance.get("activity"), "findings": provenance.get("findings"),
                "evidence": raw,
            })
            if packet is not None:
                packets.append(packet)
            continue
        if source == "mix_review_upload":
            # Rebuild this derived result only from its captured source RMS values.
            raw_transient = raw.get("transient_preservation_provenance")
            transient_provenance = _qualified_transient_preservation(raw_transient)
            stale_names = {
                "transient_preservation_score", "transient_preservation_profile",
                "transient_preservation_matched_event_count", "transient_preservation", "matched_event_count",
            }
            had_transient = transient_provenance is not None or "transient_preservation_provenance" in raw or any(
                isinstance(item, dict) and item.get("name") in stale_names for item in raw_facts
            )
            limitations = [str(value) for value in raw.get("limitations") or []]
            if had_transient and transient_provenance is None:
                limitations.append(TRANSIENT_SIGNAL_LIMITATION)
            if transient_provenance is not None:
                facts.extend([
                    EvidenceFact("transient_preservation_score", transient_provenance["score"], "ratio", source),
                    EvidenceFact("transient_preservation_profile", transient_provenance["profile"], "", source),
                    EvidenceFact("transient_preservation_matched_event_count", transient_provenance["matched_event_count"], "events", source),
                ])
            erb_provenance = qualified_stem_masking_summary(raw.get("erb_masking_provenance"))
            erb_names = {"stem_masking", "stem_masking_lowest_visibility", "stem_masking_lowest_visibility_stem", "lowest_visibility", "overall_visibility", "lowest_visibility_stem", "stem_count"}
            had_erb = "erb_masking_provenance" in raw or any(isinstance(item, dict) and str(item.get("name")).lower() in erb_names for item in raw_facts)
            stale_names.update(erb_names)
            if erb_provenance is None and had_erb:
                limitations.append(STEM_MASKING_SIGNAL_LIMITATION)
            if erb_provenance is not None:
                if ERB_PREVIEW_LIMITATION not in limitations:
                    # Even a caller-edited receipt must retain the proxy's measurement scope.
                    limitations.append(ERB_PREVIEW_LIMITATION)
                facts.extend([
                    EvidenceFact("stem_masking_lowest_visibility", erb_provenance["lowest_visibility"], "ratio", source),
                    EvidenceFact("stem_masking_lowest_visibility_stem", erb_provenance["lowest_visibility_stem"], "", source),
                ])
            raw_low_end = raw.get("low_end_stems_provenance")
            low_end_names = {"low_end_stems", "low_end_measured_stems", "low_end_summary", "low_end_overlap", "low_end_overlap_warning"}
            had_low_end = "low_end_stems_provenance" in raw or any(isinstance(item, dict) and str(item.get("name")).lower() in low_end_names for item in raw_facts)
            # Absence stays absent across repeated history hops; an empty sentinel means attempted analysis.
            low_end_provenance = qualified_low_end_stems(raw_low_end) if had_low_end else None
            stale_names.update(low_end_names)
            if had_low_end and not low_end_stems_have_activity(raw_low_end):
                limitations.append(LOW_END_SIGNAL_LIMITATION)
            if low_end_provenance:
                if LOW_END_PREVIEW_LIMITATION not in limitations:
                    # A stripped receipt cannot expand a short own-spectrum preview into a song assessment.
                    limitations.append(LOW_END_PREVIEW_LIMITATION)
                facts.append(EvidenceFact("low_end_measured_stems", ", ".join(item["name"] for item in low_end_provenance), "", source))
        else:
            transient_provenance = None
            erb_provenance = None
            low_end_provenance = None
            limitations = [str(value) for value in raw.get("limitations") or []]
        for item in raw_facts:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                continue
            if source == "mix_review_upload" and item["name"].lower() in stale_names:
                continue
            value = item.get("value")
            if isinstance(value, (str, int, float, bool)):
                facts.append(EvidenceFact(item["name"], value, str(item.get("unit") or ""), source, str(item.get("confidence") or "measured")))
        if facts or (source == "mix_review_upload" and limitations):
            age = raw.get("captured_at_age_seconds")
            observed_at = raw.get("observed_at_epoch")
            packets.append(EvidencePacket(
                source,
                float(age) if isinstance(age, (int, float)) else None,
                tuple(facts),
                tuple(limitations),
                float(observed_at) if isinstance(observed_at, (int, float)) else None,
                transient_preservation_provenance=transient_provenance,
                erb_masking_provenance=erb_provenance,
                low_end_stems_provenance=low_end_provenance,
            ))
    return packets


def current_for_diagnosis(packets: list[EvidencePacket]) -> list[EvidencePacket]:
    """Return evidence safe to treat as current in a live diagnosis.

    Uploaded Mix Review reports are immutable evidence about their uploaded
    file, while a plug-in bus frame is only a momentary live observation.  An
    old frame must not silently steer a diagnosis of what is happening now.
    Packets with an unknown plug-in age are kept visible in history but are
    not used as current evidence.
    """
    result: list[EvidencePacket] = []
    for packet in packets:
        if packet.source in {"plugin_bus_snapshot", "realtime_mix_comparison"}:
            age = packet.captured_at_age_seconds
            if packet.observed_at_epoch is not None:
                age = max(0.0, time.time() - packet.observed_at_epoch)
            if age is None or age > MAX_PLUGIN_CONTEXT_AGE_SECONDS:
                continue
        result.append(packet)
    return result


def relevant_observations(query: str, packets: list[EvidencePacket]) -> list[str]:
    """Return only observations relevant to the question; never infer cause."""
    text = query.lower()
    wants_clipping = any(term in text for term in ("clip", "distort", "headroom", "peak", "loud", "limiter"))
    wants_stereo = any(term in text for term in ("mono", "phase", "wide", "width", "stereo", "correlation"))
    wants_dynamics = any(term in text for term in ("squashed", "dynamic", "dynamics", "overcompressed", "pumping", "crest"))
    wants_punch = any(term in text for term in ("punch", "transient", "flat drums", "weak drums"))
    wants_low_end = any(term in text for term in ("kick", "bass", "sub", "808", "low end", "muddy", "mud"))
    wants_masking = any(term in text for term in ("masking", "compete", "competition", "frequency space", "getting in the way"))
    wants_classification = any(term in text for term in ("classify", "classification", "identify this sample", "what sound is this", "what sample is this", "which instrument"))
    wants_reference = ("reference" in text and any(term in text for term in ("mix", "dark", "bright", "dull", "match", "different", "compare", "comparison", "pink", "noise"))) or "pink noise" in text
    wants_mix_overview = bool(re.search(r"\b(?:what(?:'s|\s+is)\s+wrong\s+with\s+(?:my|this|the)\s+mix|analyse\s+(?:my|this|the)\s+mix)\b", text))
    wants_session_structure = any(term in text for term in ("ableton", "session", "track", "arrangement", "tempo", "bpm", "project"))
    observations: list[str] = []
    for packet in packets:
        values = {fact.name: fact.value for fact in packet.facts}
        if packet.source == "mix_review_upload" and wants_clipping:
            measurements: list[str] = []
            for name, value in values.items():
                lowered = name.lower()
                if any(term in lowered for term in ("lufs", "true_peak", "peak")) and isinstance(value, (int, float)):
                    unit = next((fact.unit for fact in packet.facts if fact.name == name), "")
                    measurements.append(f"{name.replace('_', ' ')} {value:g}{(' ' + unit) if unit else ''}")
            if measurements:
                observations.append(
                    "Measured in the uploaded Mix Review: " + ", ".join(measurements[:3]) + ". These describe that uploaded render, not the cause inside individual tracks."
                )
        if wants_clipping:
            clips = values.get("clipped_samples")
            peak = values.get("peak_dbfs")
            if isinstance(clips, (int, float)) and clips > 0:
                observations.append(f"Measured: the latest plug-in bus snapshot recorded {int(clips)} clipped sample(s). This confirms a recent full-scale event, not its source or audibility.")
            elif isinstance(peak, (int, float)):
                observations.append(f"Measured: latest bus peak is {peak:.1f} dBFS. This is a short snapshot, not an integrated loudness or true-peak reading.")
        if wants_stereo:
            correlation = values.get("stereo_correlation")
            width = values.get("stereo_width")
            if isinstance(correlation, (int, float)):
                detail = f"Measured: latest bus correlation is {correlation:.2f}"
                if isinstance(width, (int, float)):
                    detail += f" with width {width:.2f}"
                observations.append(detail + ". Treat this as a momentary indicator; verify by folding the actual section to mono.")
        if packet.source == "plugin_bus_snapshot" and wants_mix_overview:
            summary: list[str] = []
            peak = values.get("peak_dbfs")
            clips = values.get("clipped_samples")
            correlation = values.get("stereo_correlation")
            if isinstance(peak, (int, float)):
                summary.append(f"peak {peak:.1f} dBFS")
            if isinstance(clips, (int, float)):
                summary.append(f"{int(clips)} clipped sample(s)")
            if isinstance(correlation, (int, float)):
                summary.append(f"correlation {correlation:.2f}")
            pink_frequency = values.get("realtime_pink_noise_largest_deviation_frequency_hz")
            pink_deviation = values.get("realtime_pink_noise_largest_deviation_db")
            window_status = values.get("realtime_window_status")
            window_count = values.get("realtime_window_sample_count")
            window_seconds = values.get("realtime_window_seconds")
            if isinstance(pink_frequency, (int, float)) and isinstance(pink_deviation, (int, float)):
                direction = "above" if pink_deviation > 0 else "below"
                summary.append(f"largest broad spectral deviation {abs(pink_deviation):.1f} dB {direction} baseline near {pink_frequency:.0f} Hz")
            if summary:
                observations.append("Measured in the current plug-in bus snapshot: " + ", ".join(summary) + ". The spectral item is a broad pink-noise-style listening reference; this cannot identify what sounds wrong or locate a track/process cause.")
            if isinstance(window_status, str) and isinstance(window_count, (int, float)) and isinstance(window_seconds, (int, float)) and window_count >= 3:
                observations.append(f"The live trend is {window_status} across {int(window_count)} recent bus snapshots spanning {window_seconds:.0f} seconds. Use this to prioritise a listening check, not to infer a track-level cause.")
        if packet.source == "plugin_bus_snapshot" and wants_reference:
            pink_frequency = values.get("realtime_pink_noise_largest_deviation_frequency_hz")
            pink_deviation = values.get("realtime_pink_noise_largest_deviation_db")
            pink_curve = values.get("realtime_pink_noise_reference_curve")
            if isinstance(pink_frequency, (int, float)) and isinstance(pink_deviation, (int, float)):
                direction = "above" if pink_deviation > 0 else "below"
                curve = f" ({pink_curve})" if isinstance(pink_curve, str) and pink_curve else ""
                observations.append(f"Measured in the current plug-in bus snapshot against the explicit pink-noise-style reference{curve}: the nearest band centred at {pink_frequency:.0f} Hz is {abs(pink_deviation):.1f} dB {direction} the baseline around the 1 kHz anchor. This is a broad listening reference, not a quality score, track attribution, or automatic master-EQ instruction.")
            median_frequency = values.get("realtime_pink_noise_median_deviation_frequency_hz")
            median_deviation = values.get("realtime_pink_noise_median_deviation_db")
            window_count = values.get("realtime_window_sample_count")
            window_seconds = values.get("realtime_window_seconds")
            if isinstance(median_frequency, (int, float)) and isinstance(median_deviation, (int, float)) and isinstance(window_count, (int, float)) and window_count >= 3:
                direction = "above" if median_deviation > 0 else "below"
                observations.append(f"Across {int(window_count)} recent bus snapshots over {window_seconds:.0f} seconds, the median deviation near {median_frequency:.0f} Hz was {abs(median_deviation):.1f} dB {direction} the pink-noise-style baseline. This is stronger evidence for a repeatable bus trend, but still not track attribution or an automatic EQ instruction.")
        if packet.source == "realtime_mix_comparison" and (wants_reference or wants_clipping or wants_mix_overview):
            peak_live = values.get("realtime_live_peak_dbfs")
            peak_uploaded = values.get("uploaded_peak_dbfs")
            peak_delta = values.get("live_minus_uploaded_peak_dbfs")
            rms_live = values.get("realtime_live_rms_dbfs")
            rms_uploaded = values.get("uploaded_rms_dbfs")
            rms_delta = values.get("live_minus_uploaded_rms_dbfs")
            parts: list[str] = []
            if isinstance(peak_live, (int, float)) and isinstance(peak_uploaded, (int, float)):
                detail = f"sample peak live {peak_live:.1f} dBFS vs uploaded {peak_uploaded:.1f} dBFS"
                if isinstance(peak_delta, (int, float)):
                    detail += f" (delta {peak_delta:+.1f} dB)"
                parts.append(detail)
            if isinstance(rms_live, (int, float)) and isinstance(rms_uploaded, (int, float)):
                detail = f"RMS live {rms_live:.1f} dBFS vs uploaded {rms_uploaded:.1f} dBFS"
                if isinstance(rms_delta, (int, float)):
                    detail += f" (delta {rms_delta:+.1f} dB)"
                parts.append(detail)
            pink_live = values.get("realtime_pink_noise_deviation_db")
            pink_live_frequency = values.get("realtime_pink_noise_center_hz")
            pink_uploaded = values.get("uploaded_pink_noise_deviation_db")
            if isinstance(pink_live, (int, float)) and isinstance(pink_live_frequency, (int, float)):
                detail = f"realtime pink-noise-style deviation {pink_live:+.1f} dB near {pink_live_frequency:.0f} Hz"
                if isinstance(pink_uploaded, (int, float)):
                    detail += f" vs uploaded {pink_uploaded:+.1f} dB"
                parts.append(detail)
            if parts:
                observations.append(
                    "Scope-labelled comparison: " + "; ".join(parts) + ". The live values are from a current/recent plugin-bus window and the uploaded values are from a whole-file review; use the delta to prioritise listening, not to infer a track cause or automatic EQ move."
                )
        if packet.source == "mix_review_upload" and wants_dynamics:
            crest = values.get("crest_factor_db")
            rms = values.get("rms_dbfs_estimate")
            parts = []
            if isinstance(crest, (int, float)):
                parts.append(f"crest factor {crest:g} dB")
            if isinstance(rms, (int, float)):
                parts.append(f"RMS estimate {rms:g} dB")
            if parts:
                observations.append("Measured in the uploaded Mix Review: " + ", ".join(parts) + ". These describe that render only; they do not by themselves prove that the dynamics are creatively wrong or identify a processing stage.")
        if packet.source == "mix_review_upload" and wants_punch:
            score = values.get("transient_preservation_score")
            if isinstance(score, (int, float)):
                observations.append(f"Measured in the uploaded pre/post comparison: transient-preservation score {score:.2f}/1.00. It compares only those supplied renders and cannot identify which processing stage softened a hit.")
        if packet.source == "mix_review_upload" and wants_low_end:
            visibility = values.get("stem_masking_lowest_visibility")
            stem = values.get("stem_masking_lowest_visibility_stem")
            names = values.get("low_end_measured_stems")
            if isinstance(visibility, (int, float)) and isinstance(stem, str):
                observations.append(f"Measured across jointly active stem preview frames: lowest relative ERB preview visibility was {visibility:.2f} for '{stem}'. This relative-spectrum proxy prioritises a listening check; it does not measure calibrated audible masking severity or the whole song.")
            if isinstance(names, str) and names:
                observations.append(f"Activity-qualified centered FFT-window low-end previews were supplied for: {names}. Own-spectrum shares cannot establish relative stem levels, simultaneous audible masking or a whole-song ranking.")
        if packet.source == "stem_masking_analysis" and (wants_masking or wants_low_end):
            candidate_count = values.get("masking_candidate_count")
            highest_fraction = values.get("masking_highest_competing_frame_fraction")
            highest_pair = values.get("masking_highest_pair")
            highest_band = values.get("masking_highest_band")
            if isinstance(candidate_count, (int, float)) and candidate_count == 0:
                observations.append(
                    "The supplied stem-energy proxy found no flagged competing pair/band above its analysis threshold. This does not prove that the mix is free of audible masking; listen in context."
                )
            elif isinstance(candidate_count, (int, float)):
                detail = f"{int(candidate_count)} candidate pair/band relationship(s)"
                if isinstance(highest_pair, str) and highest_pair:
                    detail += f", strongest in {highest_pair}"
                if isinstance(highest_band, str) and highest_band:
                    detail += f" around {highest_band.replace('_', ' ')}"
                if isinstance(highest_fraction, (int, float)):
                    detail += f" ({highest_fraction:.1%} of overlapping frames)"
                observations.append(
                    "The supplied stem-energy proxy flagged " + detail + ". Treat this as a listening-check priority, not proof of audible masking, a responsible track, or an automatic EQ move."
                )
        if packet.source == "audio_classification" and wants_classification:
            label = values.get("classification_selected_label")
            selected_source = values.get("classification_selected_source")
            confidence = values.get("classification_confidence_band")
            ood_status = values.get("classification_ood_status")
            audio_top = values.get("classification_audio_only_top_k")
            metadata_top = values.get("classification_metadata_assisted_top_k")
            if ood_status in {"unknown", "out_of_distribution"} or selected_source == "unknown":
                observations.append(
                    f"The audio classifier returned {ood_status or 'Unknown'} rather than a dependable class. Treat the sample identity as unresolved and confirm by ear or with stronger evidence."
                )
            elif isinstance(label, str) and label:
                detail = f"The audio classifier suggests '{label}'"
                if isinstance(selected_source, str) and selected_source:
                    detail += f" from the {selected_source.replace('_', ' ')} stream"
                if isinstance(confidence, str) and confidence:
                    detail += f" ({confidence} confidence band)"
                observations.append(
                    detail + ". This is advisory specialist inference, not proof of the sound's identity or its correct musical use."
                )
            if isinstance(audio_top, str) and audio_top:
                observations.append("Audio-only candidates: " + audio_top + ".")
            if isinstance(metadata_top, str) and metadata_top:
                observations.append("Metadata-assisted candidates are kept separate: " + metadata_top + ".")
        if packet.source == "mix_review_upload" and wants_reference:
            band = values.get("reference_largest_spectral_band")
            delta = values.get("reference_largest_spectral_delta")
            ltas_frequency = values.get("reference_largest_ltas_frequency_hz")
            ltas_delta = values.get("reference_largest_ltas_delta_db")
            pink_frequency = values.get("pink_noise_largest_deviation_frequency_hz")
            pink_deviation = values.get("pink_noise_largest_deviation_db")
            pink_curve = values.get("pink_noise_reference_curve")
            lufs_delta = values.get("reference_lufs_delta_db")
            if isinstance(band, str) and isinstance(delta, (int, float)):
                observations.append(f"Measured against the uploaded reference: largest spectral difference is {band.replace('_', ' ')} ({delta:+.3f}). This compares the two renders; it does not identify the contributing source or require an exact tonal match.")
            if isinstance(ltas_frequency, (int, float)) and isinstance(ltas_delta, (int, float)):
                observations.append(f"Measured against the uploaded reference: around {ltas_frequency:.0f} Hz is {ltas_delta:+.1f} dB relative to the reference after each 40-band spectrum is normalised around 1 kHz. Use it as a listening target, not an automatic master-EQ instruction.")
            if isinstance(pink_frequency, (int, float)) and isinstance(pink_deviation, (int, float)):
                curve = f" ({pink_curve})" if isinstance(pink_curve, str) and pink_curve else ""
                direction = "above" if pink_deviation > 0 else "below"
                observations.append(f"Measured against the explicit pink-noise-style reference{curve}: the mix LTAS is {abs(pink_deviation):.1f} dB {direction} the baseline around {pink_frequency:.0f} Hz. This is a broad shape reference, not a quality score, universal target, or automatic master-EQ instruction.")
            if isinstance(lufs_delta, (int, float)):
                observations.append(f"Measured against the uploaded reference: integrated loudness delta is {lufs_delta:+.1f} dB. Level-match before treating tonal differences as reliable.")
        if packet.source == "ableton_session_snapshot" and wants_session_structure:
            parts: list[str] = []
            tempo = values.get("tempo")
            track_count = values.get("track_count")
            track_names = values.get("track_names")
            track_inventory = values.get("track_inventory")
            if isinstance(tempo, (int, float)):
                parts.append(f"tempo {tempo:g} BPM")
            if isinstance(track_count, (int, float)):
                parts.append(f"{int(track_count)} track(s)")
            if isinstance(track_names, str) and track_names:
                parts.append(f"tracks: {track_names}")
            if isinstance(track_inventory, str) and track_inventory:
                parts.append(f"track devices: {track_inventory}")
            if parts:
                observations.append(
                    "Read from the opted-in cached Ableton session snapshot: "
                    + "; ".join(parts)
                    + ". This confirms project structure only, not audio content, routing, automation, or a sonic cause."
                )
    sources = {packet.source for packet in packets}
    if {"plugin_bus_snapshot", "mix_review_upload"} <= sources and (wants_clipping or wants_mix_overview):
        observations.append(
            "Context boundary: the current plug-in snapshot and uploaded Mix Review are different captures. Do not treat their values as a before/after comparison or one combined measurement set."
        )
    return list(dict.fromkeys(observations))
