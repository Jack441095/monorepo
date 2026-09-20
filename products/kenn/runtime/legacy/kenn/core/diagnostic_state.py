"""Small, explicit state machine for multi-turn audio troubleshooting.

This stores observations the user actually reported, not hidden chain-of-
thought.  It lets the next answer choose an untested discriminator rather than
repeating a processor that was already tried without success.
"""

from __future__ import annotations

import re
from typing import Any

from kenn.core.diagnostic_framework import plan_for


_KEYS = {
    "The vocal is described as both thin and harsh.": ("harsh_thin_vocal", "My vocal sounds harsh and thin."),
    "The kick loses audibility when the bass plays.": ("kick_bass_conflict", "The kick disappears when the bass comes in."),
    "The bass loses audibility when the kick plays.": ("bass_kick_conflict", "The bass disappears when the kick plays."),
    "The mix is being judged as tonally different from a chosen reference.": ("reference_tonal_difference", "Why is my mix darker than my reference?"),
    "The mix is described as muddy or congested.": ("muddy_mix", "My mix sounds muddy."),
    "The stereo image is unstable or loses energy in mono.": ("mono_phase", "My wide mix collapses in mono and sounds phasey."),
    "The master may be over-driven or dynamically over-controlled.": ("overdriven_master", "My master is too loud and distorted."),
    "The mix is described as flat or lacking front-to-back depth.": ("flat_mix", "My mix sounds flat and has no depth."),
    "The mix does not translate consistently between playback systems; this is a translation check, not a single-speaker verdict.": ("translation", "My mix does not translate between my car and small speakers."),
    "The low end is described as weak or absent.": ("weak_low_end", "My low end sounds weak."),
    "The drums are described as flat or lacking punch.": ("flat_drums", "My drums lack punch."),
    "The vocal has excessive or distracting sibilance.": ("sibilant_vocal", "My vocal has too much sibilance."),
    "The recording may contain distracting room reflections or room coloration.": ("room_reflections", "My recording has distracting room reflections."),
    "The overall mix is described as harsh, brittle, or too bright.": ("harsh_mix", "My mix is harsh and brittle."),
    "The mix is described as squashed or lacking dynamic movement.": ("squashed_mix", "My mix sounds squashed."),
}
_TECHNIQUES = (
    ("sidechain", "sidechaining"), ("eq", "EQ"), ("equaliz", "EQ"),
    ("compress", "compression"), ("saturat", "saturation"),
    ("limit", "limiting"), ("clip", "clipping"), ("de-ess", "de-essing"),
    ("deess", "de-essing"), ("phase", "phase alignment"),
)
_NEGATIVE = re.compile(r"\b(still|no (?:change|difference|luck)|didn'?t work|doesn'?t work|not working|worse)\b", re.I)
_POSITIVE = re.compile(r"\b(helped|better|fixed|works?|clearer|improved)\b", re.I)


def reported_findings(state: dict[str, Any] | None, query: str) -> list[str]:
    """Translate only explicit test outcomes into bounded diagnostic facts.

    A finding is deliberately narrower than a cause: it records what a user
    observed and what that observation supports, while preserving alternative
    hypotheses.  It is never inferred merely from a symptom description.
    """
    if not isinstance(state, dict):
        return []
    text = query.lower()
    key = str(state.get("key") or "")
    findings: list[str] = []
    if key == "kick_bass_conflict" and "bass" in text and any(term in text for term in ("mute", "muted", "mutes")) and any(
        term in text for term in ("kick returns", "kick came back", "kick comes back", "kick is back")
    ):
        findings.append("Your mute test supports kick/bass overlap as a likely interaction. It does not by itself distinguish frequency overlap from timing or polarity.")
    if key == "bass_kick_conflict" and "sidechain" in text and any(term in text for term in ("bypass", "bypassed", "off", "disabled")) and any(
        term in text for term in ("bass returns", "bass came back", "bass is back", "returns")
    ):
        findings.append("Your bypass test supports the sidechain/ducking path as the reason the bass loses audibility. It does not identify whether depth, threshold, release, a volume shaper, or another keyed process is responsible.")
    if key == "reference_tonal_difference" and any(term in text for term in ("level-match", "level matched", "matched loudness")) and any(
        term in text for term in ("still dark", "still darker", "still dull", "still less bright")
    ):
        findings.append("The tonal difference survives level matching, so it is less likely to be only a loudness illusion. It still does not identify the contributing source, arrangement relationship, or whether matching the reference is the right creative goal.")
    if key == "flat_drums" and "bypass" in text and any(term in text for term in ("punch returns", "punch came back", "punch is back", "more punch")):
        findings.append("Your bypass test supports processing or a layer reducing transient contrast. It does not identify which stage until you compare them one at a time.")
    if key in {"harsh_thin_vocal", "sibilant_vocal"} and any(term in text for term in ("raw take", "raw vocal", "dry vocal", "dry take")) and any(
        term in text for term in ("harsh", "sibil", "thin")
    ):
        findings.append("The problem is present on the raw vocal, so capture/source character is supported before mix processing. It does not prove one microphone, room, or performance cause.")
    return findings


def state_for_query(query: str) -> dict[str, Any] | None:
    plan = plan_for(query)
    if not plan:
        return None
    entry = _KEYS.get(plan.symptom)
    if not entry:
        return None
    key, canonical_query = entry
    return {"key": key, "symptom": plan.symptom, "canonical_query": canonical_query, "failed_techniques": [], "confirmed_techniques": [], "confirmed_findings": [], "outcomes": []}


def update(state: dict[str, Any], query: str) -> dict[str, Any] | None:
    """Return updated bounded diagnostic state, or ``None`` when inactive."""
    existing = state.get("diagnostic_state")
    fresh = state_for_query(query)
    diagnosis = dict(fresh or existing or {})
    if not diagnosis:
        return None
    text = query.lower()
    mentioned = [label for token, label in _TECHNIQUES if token in text]
    negative = bool(_NEGATIVE.search(query))
    positive = bool(_POSITIVE.search(query)) and not negative
    if negative or positive:
        field = "failed_techniques" if negative else "confirmed_techniques"
        current = list(diagnosis.get(field) or [])
        for label in mentioned:
            if label not in current:
                current.append(label)
        diagnosis[field] = current[-6:]
        outcome = "did not resolve the symptom" if negative else "helped"
        if mentioned:
            entries = list(diagnosis.get("outcomes") or [])
            entry = f"{', '.join(mentioned)} {outcome}"
            if entry not in entries:
                entries.append(entry)
            diagnosis["outcomes"] = entries[-6:]
    findings = reported_findings(diagnosis, query)
    if findings:
        existing_findings = list(diagnosis.get("confirmed_findings") or [])
        for finding in findings:
            if finding not in existing_findings:
                existing_findings.append(finding)
        diagnosis["confirmed_findings"] = existing_findings[-4:]
    return diagnosis


def followup_query(state: dict[str, Any] | None) -> str:
    """Return a canonical symptom query for an otherwise elliptical follow-up."""
    if not isinstance(state, dict):
        return ""
    return str(state.get("canonical_query") or "")


def failed_techniques(state: dict[str, Any] | None) -> list[str]:
    if not isinstance(state, dict):
        return []
    return [str(item) for item in state.get("failed_techniques") or [] if str(item)]


def confirmed_findings(state: dict[str, Any] | None) -> list[str]:
    if not isinstance(state, dict):
        return []
    return [str(item) for item in state.get("confirmed_findings") or [] if str(item)]
