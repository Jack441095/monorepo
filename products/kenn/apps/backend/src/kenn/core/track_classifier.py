"""Intelligent Track Taxonomy & Instrument Classifier for KENN.

Classifies Ableton Live session track titles into standard studio instrument roles,
identifying masking risks and complementary processing targets between track roles.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, List, Optional


@dataclass(frozen=True)
class TrackClassification:
    role: str
    display_name: str
    frequency_focus_hz: tuple[float, float]
    masking_partner_roles: list[str]
    suggested_high_pass_hz: Optional[float]
    recommended_dsp_move: str


ROLE_CLASSIFICATIONS: dict[str, TrackClassification] = {
    "vocal_lead": TrackClassification(
        role="vocal_lead",
        display_name="Lead Vocal",
        frequency_focus_hz=(1000.0, 5000.0),
        masking_partner_roles=["guitar", "keys", "synth", "vocal_bg"],
        suggested_high_pass_hz=90.0,
        recommended_dsp_move="High-pass at 90 Hz, gentle 3 kHz clarity boost, 3-5 dB optical/VCA compression.",
    ),
    "vocal_bg": TrackClassification(
        role="vocal_bg",
        display_name="Background Vocals / Harmonies",
        frequency_focus_hz=(1500.0, 6000.0),
        masking_partner_roles=["vocal_lead", "keys", "synth"],
        suggested_high_pass_hz=120.0,
        recommended_dsp_move="High-pass at 120 Hz, cut 500 Hz for space, wide stereo panning, heavy compression.",
    ),
    "kick": TrackClassification(
        role="kick",
        display_name="Kick Drum",
        frequency_focus_hz=(50.0, 100.0),
        masking_partner_roles=["sub_bass", "bass_synth", "drum_bus"],
        suggested_high_pass_hz=30.0,
        recommended_dsp_move="High-pass at 30 Hz, dip 300 Hz for clarity, fast attack VCA compressor for transient crack.",
    ),
    "snare": TrackClassification(
        role="snare",
        display_name="Snare Drum",
        frequency_focus_hz=(200.0, 2500.0),
        masking_partner_roles=["guitar", "vocal_lead", "drum_bus"],
        suggested_high_pass_hz=80.0,
        recommended_dsp_move="High-pass at 80 Hz, body boost at 200 Hz, transient shaper for punch, 2.5 kHz crack.",
    ),
    "drum_bus": TrackClassification(
        role="drum_bus",
        display_name="Drums Bus",
        frequency_focus_hz=(60.0, 10000.0),
        masking_partner_roles=["bass_synth", "sub_bass"],
        suggested_high_pass_hz=35.0,
        recommended_dsp_move="VCA Glue compression (4:1, attack 30ms, release auto, 2-3 dB reduction), parallel punch.",
    ),
    "sub_bass": TrackClassification(
        role="sub_bass",
        display_name="Sub-Bass / 808",
        frequency_focus_hz=(30.0, 80.0),
        masking_partner_roles=["kick", "bass_synth", "drum_bus"],
        suggested_high_pass_hz=25.0,
        recommended_dsp_move="High-pass at 25 Hz, mono below 100 Hz, sidechain compression ducked by Kick transient.",
    ),
    "bass_synth": TrackClassification(
        role="bass_synth",
        display_name="Bass Guitar / Bass Synth",
        frequency_focus_hz=(80.0, 800.0),
        masking_partner_roles=["kick", "sub_bass", "guitar"],
        suggested_high_pass_hz=40.0,
        recommended_dsp_move="High-pass at 40 Hz, carve 60 Hz for Kick, boost 700 Hz for finger/pick articulation.",
    ),
    "guitar": TrackClassification(
        role="guitar",
        display_name="Guitar (Electric / Acoustic / Rhythm)",
        frequency_focus_hz=(300.0, 3500.0),
        masking_partner_roles=["vocal_lead", "snare", "keys", "bass_synth"],
        suggested_high_pass_hz=100.0,
        recommended_dsp_move="High-pass at 100 Hz, carve 300 Hz mud, dip 3 kHz to clear vocal pocket.",
    ),
    "keys": TrackClassification(
        role="keys",
        display_name="Keys / Piano / Rhodes",
        frequency_focus_hz=(250.0, 4000.0),
        masking_partner_roles=["vocal_lead", "guitar", "synth"],
        suggested_high_pass_hz=100.0,
        recommended_dsp_move="High-pass at 100 Hz, gentle mid-dip at 2 kHz for Lead Vocal, stereo chorus/delay.",
    ),
    "synth": TrackClassification(
        role="synth",
        display_name="Synth Lead / Pad",
        frequency_focus_hz=(500.0, 8000.0),
        masking_partner_roles=["vocal_lead", "keys", "guitar"],
        suggested_high_pass_hz=120.0,
        recommended_dsp_move="High-pass at 120 Hz, sidechain ducking, high-shelf air boost at 10 kHz.",
    ),
    "fx_send": TrackClassification(
        role="fx_send",
        display_name="Reverb / Delay / FX Send",
        frequency_focus_hz=(1000.0, 10000.0),
        masking_partner_roles=["vocal_lead"],
        suggested_high_pass_hz=200.0,
        recommended_dsp_move="Abbey Road EQ filter (HPF at 200 Hz, LPF at 8 kHz) on reverb return to keep mix clean.",
    ),
    "mix_bus": TrackClassification(
        role="mix_bus",
        display_name="Mix Bus / Sub-Master",
        frequency_focus_hz=(40.0, 15000.0),
        masking_partner_roles=[],
        suggested_high_pass_hz=30.0,
        recommended_dsp_move="Gentle Glue Compression (2:1, soft knee), broad high-shelf air, true-peak safety ceiling.",
    ),
}

DEFAULT_TRACK_CLASSIFICATION = TrackClassification(
    role="unknown",
    display_name="Audio / MIDI Track",
    frequency_focus_hz=(100.0, 8000.0),
    masking_partner_roles=[],
    suggested_high_pass_hz=80.0,
    recommended_dsp_move="Inspect track signal content and high-pass unused low frequencies.",
)


PATTERNS: list[tuple[str, list[str]]] = [
    ("vocal_lead", [r"\bvoc(?:al)?\b", r"\blead\s*voc\b", r"\bvox\b", r"\bacapella\b", r"\bsinger\b"]),
    ("vocal_bg", [r"\bbgv\b", r"\bback(?:ground)?\s*voc\b", r"\bharm(?:ony)?\b", r"\bchoir\b", r"\badlib\b"]),
    ("kick", [r"\bkick\b", r"\bkck\b", r"\bbass\s*drum\b", r"\bkick\s*in\b", r"\bkick\s*out\b"]),
    ("snare", [r"\bsnare\b", r"\bsnr\b", r"\bsnare\s*top\b", r"\bsnare\s*bot\b", r"\brim\b"]),
    ("drum_bus", [r"\bdrum(?:s)?\b", r"\bdrm(?:s)?\b", r"\bpercussion\b", r"\bperc\b", r"\bhats?\b", r"\bcymbal\b", r"\boverhead\b"]),
    ("sub_bass", [r"\bsub\b", r"\b808\b", r"\bsub\s*bass\b", r"\bdeep\s*bass\b"]),
    ("bass_synth", [r"\bbass\b", r"\bbs\b", r"\bbass\s*guitar\b", r"\bsynth\s*bass\b", r"\bdi\s*bass\b"]),
    ("guitar", [r"\bgtr\b", r"\bguitar\b", r"\begtr\b", r"\bagtr\b", r"\brhythm\s*gtr\b", r"\blead\s*gtr\b"]),
    ("keys", [r"\bkeys?\b", r"\bpiano\b", r"\brhodes\b", r"\borgan\b", r"\bclav\b"]),
    ("synth", [r"\bsynth\b", r"\bpad\b", r"\blead\b", r"\bbrass\b", r"\barp\b", r"\bstrings?\b"]),
    ("fx_send", [r"\brvb\b", r"\breverb\b", r"\bdly\b", r"\bdelay\b", r"\bfx\b", r"\bsend\b", r"\breturn\b"]),
    ("mix_bus", [r"\bmix\s*bus\b", r"\bmaster\b", r"\bpre\s*master\b", r"\bsub\s*mix\b"]),
]


def _matched_role_tokens(value: str) -> list[tuple[str, str]]:
    """Return role evidence after removing only known generic-parent overlaps."""
    matches: list[tuple[str, str]] = []
    for role_key, pattern_list in PATTERNS:
        for pattern in pattern_list:
            match = re.search(pattern, value)
            if match:
                matches.append((role_key, match.group(0)))
                break
    roles = {role for role, _token in matches}
    suppressed: set[str] = set()
    if roles & {"vocal_lead", "vocal_bg", "guitar"}:
        suppressed.add("synth")  # generic "lead" must not override a specific source role
    if roles & {"kick", "snare"}:
        suppressed.add("drum_bus")
    if "sub_bass" in roles:
        suppressed.add("bass_synth")
    if "vocal_bg" in roles:
        suppressed.add("vocal_lead")
    return [(role, token) for role, token in matches if role not in suppressed]


def classify_track_name(track_name: str) -> TrackClassification:
    """Classify an Ableton track title into a studio instrument role."""
    if not track_name:
        return DEFAULT_TRACK_CLASSIFICATION

    normalized = track_name.lower().strip()


    for role_key, pattern_list in PATTERNS:
        for pat in pattern_list:
            if re.search(pat, normalized):
                return ROLE_CLASSIFICATIONS.get(role_key, DEFAULT_TRACK_CLASSIFICATION)

    return DEFAULT_TRACK_CLASSIFICATION


def classify_track_context(
    track_name: str,
    *,
    track_index: int | None = None,
    track_type: str = "",
    devices: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return an evidence-labelled, advisory track-role classification.

    This is deliberately separate from ``classify_track_name`` so existing
    callers keep the small, stable dataclass API.  A name match is useful
    routing evidence, not proof of the audio content; the returned confidence
    therefore stays below the high-confidence band until an independent signal
    is added by a future context builder.
    """
    raw_name = str(track_name or "").strip()
    normalized = raw_name.lower()
    matches = _matched_role_tokens(normalized)
    matched_roles = [role for role, _token in matches]
    matched_tokens = [token for _role, token in matches]

    classification = classify_track_name(raw_name)
    if len(matched_roles) > 1:
        role = "unknown"
        display_name = DEFAULT_TRACK_CLASSIFICATION.display_name
        candidates = matched_roles
        confidence = 0.25
        uncertainty_reason = "ambiguous_name_alias"
    elif matched_roles:
        role = classification.role
        display_name = classification.display_name
        candidates = [role]
        confidence = 0.58
        uncertainty_reason = "name_only"
    elif raw_name:
        role = "unknown"
        display_name = DEFAULT_TRACK_CLASSIFICATION.display_name
        candidates = []
        confidence = 0.12
        uncertainty_reason = "no_role_token"
    else:
        role = "unknown"
        display_name = DEFAULT_TRACK_CLASSIFICATION.display_name
        candidates = []
        confidence = 0.0
        uncertainty_reason = "empty_track_name"

    evidence: list[dict[str, Any]] = []
    if matched_tokens:
        evidence.append({"kind": "track_name", "value": matched_tokens[0], "strength": 0.58})
    elif raw_name:
        evidence.append({"kind": "track_name", "value": raw_name, "strength": 0.0})
    if track_type:
        evidence.append({"kind": "track_type", "value": str(track_type)[:64], "strength": 0.1})
    if devices:
        evidence.append({
            "kind": "device_presence",
            "value": [str(item.get("name") or "")[:96] for item in devices[:16] if isinstance(item, dict)],
            "strength": 0.05,
        })

    band = "high" if confidence >= 0.8 else "medium" if confidence >= 0.5 else "low"
    return {
        "schema": "kenn.track_context.v1",
        "track_index": track_index,
        "track_name": raw_name,
        "role": role,
        "display_name": display_name,
        "confidence": confidence,
        "confidence_band": band,
        "evidence": evidence,
        "candidates": candidates,
        "uncertainty_reason": uncertainty_reason,
        "masking_partners": list(ROLE_CLASSIFICATIONS.get(role, DEFAULT_TRACK_CLASSIFICATION).masking_partner_roles),
        "advisory_only": True,
    }


def analyze_session_arrangement(tracks: list[dict[str, Any]]) -> dict[str, Any]:
    """Return advisory, evidence-labelled roles and potential masking pairs."""
    classified_tracks: list[dict[str, Any]] = []
    role_counts: dict[str, int] = {}
    detected_roles: set[str] = set()

    for idx, t in enumerate(tracks):
        name = t.get("name", f"Track {idx}")
        devices = t.get("devices") if isinstance(t.get("devices"), list) else []
        context = classify_track_context(
            name,
            track_index=t.get("index") if isinstance(t.get("index"), int) else idx,
            track_type=str(t.get("type") or ""),
            devices=[item for item in devices if isinstance(item, dict)],
        )
        role = str(context["role"])
        cls = ROLE_CLASSIFICATIONS.get(role, DEFAULT_TRACK_CLASSIFICATION)

        role_counts[role] = role_counts.get(role, 0) + 1
        if role != "unknown":
            detected_roles.add(role)

        classified_tracks.append({
            "track_index": context["track_index"],
            "track_name": name,
            "role": role,
            "display_name": context["display_name"],
            "confidence": context["confidence"],
            "confidence_band": context["confidence_band"],
            "evidence": context["evidence"],
            "candidates": context["candidates"],
            "uncertainty_reason": context["uncertainty_reason"],
            "suggested_high_pass_hz": cls.suggested_high_pass_hz if role != "unknown" else None,
            "recommended_dsp_move": (
                cls.recommended_dsp_move
                if role != "unknown"
                else "Inspect the signal before recommending processing."
            ),
            "masking_partners": context["masking_partners"],
            "advisory_only": True,
        })

    # Find potential masking interaction pairs in this session
    masking_warnings: list[dict[str, Any]] = []


    # Check Kick + Sub Bass masking risk
    if "kick" in detected_roles and ("sub_bass" in detected_roles or "bass_synth" in detected_roles):
        masking_warnings.append({
            "pair": ("Kick", "Bass"),
            "risk": "Potential low-end frequency collision below 100 Hz",
            "suggestion": "Sidechain compress Bass to duck 2-3 dB during Kick transients, or carve 60 Hz on Bass.",
            "evidence_basis": "name-derived track roles; verify with measurements",
            "advisory_only": True,
        })

    # Check Lead Vocal + Guitar / Keys masking risk
    if "vocal_lead" in detected_roles and ("guitar" in detected_roles or "keys" in detected_roles or "synth" in detected_roles):
        masking_warnings.append({
            "pair": ("Lead Vocal", "Midrange Instruments (Guitar/Keys/Synth)"),
            "risk": "Potential vocal intelligibility masking in 1 kHz - 3 kHz band",
            "suggestion": "Dip 1.5 kHz - 2.5 kHz by 2 dB on Guitars/Keys to carve out a clean vocal pocket.",
            "evidence_basis": "name-derived track roles; verify with measurements",
            "advisory_only": True,
        })

    return {
        "track_count": len(tracks),
        "classified_tracks": classified_tracks,
        "role_summary": role_counts,
        "masking_warnings": masking_warnings,
    }


def question_mentions_role(question: str) -> str | None:
    """Detect a studio-role word in free text, reusing the exact same name
    patterns used to classify a track name. Returns the role key, or
    ``None`` if the question doesn't clearly reference one instrument role
    (never guesses between multiple candidates)."""
    normalized = question.lower().strip()
    matched_roles = [role for role, _token in _matched_role_tokens(normalized)]
    if len(matched_roles) == 1:
        return matched_roles[0]
    return None


def find_tracks_by_question_role(question: str, tracks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Real, bounded track evidence for a question that names one instrument
    role (e.g. "why is my vocal getting masked").

    Ties a chat answer to the actual live session instead of only general
    knowledge: matches the question's role word against each track's own
    name-based classification (never the audio content) and returns the
    matching tracks' real name, index, and device list. Returns an empty
    list -- never a guess -- when the question doesn't name exactly one
    role, or no track matches it.
    """
    role = question_mentions_role(question)
    if role is None:
        return []
    matches: list[dict[str, Any]] = []
    for idx, track in enumerate(tracks):
        if not isinstance(track, dict):
            continue
        name = str(track.get("name") or "")
        devices = track.get("devices") if isinstance(track.get("devices"), list) else []
        context = classify_track_context(
            name,
            track_index=track.get("index", idx),
            devices=[d for d in devices if isinstance(d, dict)],
        )
        if context["role"] == role:
            matches.append({
                "track_index": context["track_index"],
                "track_name": name,
                "role": role,
                "display_name": context["display_name"],
                "devices": [str(d.get("name") or "") for d in devices if isinstance(d, dict)],
            })
    return matches
