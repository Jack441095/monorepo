"""Typed, provenance-preserving evidence for KENN decisions.

User descriptions, measured audio features, and inferred causes must never be
collapsed into the same string.  This module is the common boundary for the
three available evidence sources: plug-in bus snapshots, Ableton session
metadata, and Mix Review measurements.  It is deliberately compact and JSON
serialisable so it can travel through the existing chat-history transport.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import re
import time
from typing import Any


MARKER = "KENN_EVIDENCE_PACKET_V1:"
MAX_PLUGIN_CONTEXT_AGE_SECONDS = 15.0


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

    def payload(self) -> dict[str, Any]:
        payload = {
            "schema": "kenn.evidence.v1",
            "source": self.source,
            "captured_at_age_seconds": self.captured_at_age_seconds,
            "observed_at_epoch": self.observed_at_epoch,
            "facts": [asdict(fact) for fact in self.facts],
            "limitations": list(self.limitations),
        }
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


def from_plugin_context(context: dict[str, Any] | None) -> EvidencePacket | None:
    """Convert the validated plug-in snapshot into explicit bus evidence."""
    if not isinstance(context, dict) or context.get("schema") != "kenn.live_mix_context.v1":
        return None
    fields = (
        ("peak_dbfs", "dBFS"), ("rms_dbfs", "dBFS"), ("crest_db", "dB"),
        ("transient_ratio", "ratio"), ("clipped_samples", "samples"),
        ("stereo_correlation", "correlation"), ("stereo_width", "ratio"),
        ("low_energy", "linear energy"), ("mid_energy", "linear energy"),
        ("high_energy", "linear energy"), ("sample_rate", "Hz"),
        ("analysed_samples", "samples"),
    )
    facts: list[EvidenceFact] = []
    for name, unit in fields:
        value = context.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        facts.append(EvidenceFact(name, float(value), unit, "plugin_bus_snapshot"))
    pink_noise = context.get("pink_noise_reference")
    if isinstance(pink_noise, dict):
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
        shape = live_window.get("pink_noise_shape")
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
        ),
        observed_at_epoch=(time.time() - age_value) if age_value is not None else None,
    )


def from_mix_review_context(context: dict[str, Any] | None) -> EvidencePacket | None:
    """Convert a structured uploaded-track review into measured evidence.

    Only numeric report metrics become measured facts.  Report flags and
    recommended actions remain interpretations in the existing Mix Review
    context, rather than being falsely elevated to raw measurements.
    """
    if not isinstance(context, dict) or context.get("schema") != "kenn_mix_review_handoff.v1":
        return None
    metrics = context.get("metrics")
    if not isinstance(metrics, dict):
        return None
    facts: list[EvidenceFact] = []
    # These are calculated assessments/labels, not measurements.  They can
    # remain available in the Mix Review narrative, but must not gain the
    # stronger "measured" status simply because they happen to be numeric.
    derived_metric_names = {"technical_score", "quality_score", "confidence_score", "rating_score"}
    for name, value in metrics.items():
        if str(name).lower() in derived_metric_names:
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
        if isinstance(transient, dict):
            score = transient.get("score")
            if isinstance(score, (int, float)) and not isinstance(score, bool):
                facts.append(EvidenceFact("transient_preservation_score", float(score), "ratio", "mix_review_upload"))
            profile = transient.get("profile")
            if isinstance(profile, str) and profile.strip():
                facts.append(EvidenceFact("transient_preservation_profile", profile.strip(), "", "mix_review_upload"))
        masking = analysis.get("stem_masking")
        if isinstance(masking, dict):
            visibility = masking.get("lowest_visibility")
            if isinstance(visibility, (int, float)) and not isinstance(visibility, bool):
                facts.append(EvidenceFact("stem_masking_lowest_visibility", float(visibility), "ratio", "mix_review_upload"))
            stem = masking.get("lowest_visibility_stem")
            if isinstance(stem, str) and stem.strip():
                facts.append(EvidenceFact("stem_masking_lowest_visibility_stem", stem.strip(), "", "mix_review_upload"))
        low_end = analysis.get("low_end_stems")
        if isinstance(low_end, list):
            names = [str(item.get("name") or "").strip() for item in low_end if isinstance(item, dict)]
            names = [name for name in names if name]
            if names:
                facts.append(EvidenceFact("low_end_measured_stems", ", ".join(names), "", "mix_review_upload"))
    comparison = context.get("reference_comparison")
    if isinstance(comparison, dict):
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
        ),
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


def from_stem_masking_context(context: dict[str, Any] | None) -> EvidencePacket | None:
    """Convert bounded stem-energy competition into advisory evidence."""
    if not isinstance(context, dict) or context.get("schema") != "kenn.mix_review_masking_analysis.v1" or context.get("ok") is not True:
        return None
    packet = context.get("evidence")
    if (
        not isinstance(packet, dict)
        or packet.get("schema") != "kenn.evidence.v1"
        or packet.get("source") != "stem_masking_analysis"
    ):
        return None
    raw_facts = packet.get("facts")
    raw_limitations = packet.get("limitations")
    if not isinstance(raw_facts, list) or not isinstance(raw_limitations, list):
        return None
    facts: list[EvidenceFact] = []
    for item in raw_facts[:32]:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            continue
        value = item.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            continue
        facts.append(EvidenceFact(
            item["name"][:128], value, str(item.get("unit") or "")[:32],
            "stem_masking_analysis", str(item.get("confidence") or "measured")[:32],
        ))
    if not facts:
        return None
    limitations = tuple(str(item)[:512] for item in raw_limitations[:8] if str(item).strip())
    return EvidencePacket("stem_masking_analysis", None, tuple(facts), limitations)


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
        for item in raw_facts:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                continue
            value = item.get("value")
            if isinstance(value, (str, int, float, bool)):
                facts.append(EvidenceFact(item["name"], value, str(item.get("unit") or ""), source, str(item.get("confidence") or "measured")))
        if facts:
            age = raw.get("captured_at_age_seconds")
            observed_at = raw.get("observed_at_epoch")
            packets.append(EvidencePacket(
                source,
                float(age) if isinstance(age, (int, float)) else None,
                tuple(facts),
                tuple(str(v) for v in raw.get("limitations") or []),
                float(observed_at) if isinstance(observed_at, (int, float)) else None,
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
                observations.append(f"Measured across the supplied stems: lowest simultaneous-masking visibility was {visibility:.2f} for '{stem}'. This prioritises checking that relationship, not assuming it is the audible cause.")
            if isinstance(names, str) and names:
                observations.append(f"Measured low-end spectrum summaries were supplied for: {names}. These identify analysed stems, not which one should dominate creatively.")
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
