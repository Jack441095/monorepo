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
        return {
            "schema": "kenn.evidence.v1",
            "source": self.source,
            "captured_at_age_seconds": self.captured_at_age_seconds,
            "observed_at_epoch": self.observed_at_epoch,
            "facts": [asdict(fact) for fact in self.facts],
            "limitations": list(self.limitations),
        }


def from_plugin_context(context: dict[str, Any] | None) -> EvidencePacket | None:
    """Convert the validated plug-in snapshot into explicit bus evidence."""
    if not isinstance(context, dict) or context.get("schema") != "kenn.live_mix_context.v1":
        return None
    fields = (
        ("peak_dbfs", "dBFS"), ("rms_dbfs", "dBFS"), ("crest_db", "dB"),
        ("transient_ratio", "ratio"), ("clipped_samples", "samples"),
        ("stereo_correlation", "correlation"), ("stereo_width", "ratio"),
    )
    facts: list[EvidenceFact] = []
    for name, unit in fields:
        value = context.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        facts.append(EvidenceFact(name, float(value), unit, "plugin_bus_snapshot"))
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
        if packet.source == "plugin_bus_snapshot":
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
    wants_reference = "reference" in text and any(term in text for term in ("mix", "dark", "bright", "dull", "match", "different"))
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
            if summary:
                observations.append("Measured in the current plug-in bus snapshot: " + ", ".join(summary) + ". This cannot identify what sounds wrong or locate a track/process cause.")
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
        if packet.source == "mix_review_upload" and wants_reference:
            band = values.get("reference_largest_spectral_band")
            delta = values.get("reference_largest_spectral_delta")
            lufs_delta = values.get("reference_lufs_delta_db")
            if isinstance(band, str) and isinstance(delta, (int, float)):
                observations.append(f"Measured against the uploaded reference: largest spectral difference is {band.replace('_', ' ')} ({delta:+.3f}). This compares the two renders; it does not identify the contributing source or require an exact tonal match.")
            if isinstance(lufs_delta, (int, float)):
                observations.append(f"Measured against the uploaded reference: integrated loudness delta is {lufs_delta:+.1f} dB. Level-match before treating tonal differences as reliable.")
        if packet.source == "ableton_session_snapshot" and wants_session_structure:
            parts: list[str] = []
            tempo = values.get("tempo")
            track_count = values.get("track_count")
            track_names = values.get("track_names")
            if isinstance(tempo, (int, float)):
                parts.append(f"tempo {tempo:g} BPM")
            if isinstance(track_count, (int, float)):
                parts.append(f"{int(track_count)} track(s)")
            if isinstance(track_names, str) and track_names:
                parts.append(f"tracks: {track_names}")
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
