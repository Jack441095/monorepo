"""Professional paraphrase helpers for local YouTube-style transcripts."""

from __future__ import annotations

import re
from pathlib import Path

from kenn.training.research import (
    DOMAIN_TERMS,
    clean_transcript_text,
    formal_topic,
    technique_lessons,
    top_terms,
    transcript_windows,
)

FILLER_RE = re.compile(
    r"\b(yeah|okay|ok|like|just|really|basically|literally|kind of|sort of|you know|um|uh|hello nerds|bye|smash that like|bell icon|notification bell|link in the description)\b",
    re.I,
)
YOUTUBE_NOISE = (
    "video editing",
    "adobe premiere",
    "davinci resolve",
    "patreon",
    "see you again",
    "subscribe",
    "hello nerds",
    "changing my video editing",
    "sponsor",
    "giveaway",
    "bell icon",
    "notification bell",
    "leave a comment",
    "smash that like",
    "link in the description",
    "use my discount code",
    "channel membership",
    "merch store",
    "subscribe to my channel",
    "like this video",
)

ACTION_PATTERNS = (
    (r"\b(load|insert|add|put)\b.{0,40}\b(delay|saturator|rack|operator|drum rack|eq|compressor|return)\b", "Load the relevant device on the target track and audition the effect in solo first."),
    (r"\b(change|switch|set)\b.{0,30}\b(mode|repitch|fade|jump)\b", "Switch the device mode and compare the sonic difference on a simple loop."),
    (r"\b(turn on|enable)\b.{0,30}\b(ping pong|modulation|lfo)\b", "Enable the feature mentioned in the tutorial and listen for stereo movement or rhythmic change."),
    (r"\b(automate|modulat)\w*\b.{0,40}\b(time|cutoff|send)\b", "Use modulation or automation so the parameter moves musically without manual drawing."),
    (r"\b(drag|drop)\b.{0,40}\b(into|onto)\b", "Drag the source material onto the correct track, pad, or rack chain."),
    (r"\b(group|route|send)\b", "Route the signal through a bus or return so processing stays reusable."),
    (r"\b(freeze|flatten|bounce|resample)\b", "Commit the sound with freeze/flatten or resampling before pushing levels."),
    (r"\b(compress|gain reduction|threshold|ratio|attack|release)\b", "Insert a compressor on the channel, set the threshold for moderate gain reduction, and adjust the attack and release times to match the song's tempo."),
    (r"\b(eq|filter|cut|shelf|highpass|high pass|lowpass|low pass|resonance|bell)\b", "Apply precise EQ cuts or shelves to clear out unwanted frequencies and carve space for other instruments."),
    (r"\b(saturat|warmth|harmonic|distortion|drive|clipper|overdrive)\b", "Add subtle saturation or harmonic drive to introduce richness and make the element stand out in the mix."),
    (r"\b(sidechain|side chain|ducking|duck)\b", "Configure sidechain compression or ducking on the target track to create rhythmic space and prevent frequency clashing."),
)


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [part.strip() for part in parts if len(part.strip()) > 25]


def is_noise_sentence(sentence: str) -> bool:
    lowered = sentence.lower()
    return any(phrase in lowered for phrase in YOUTUBE_NOISE)


def professionalize_sentence(sentence: str) -> str:
    text = FILLER_RE.sub("", sentence)
    replacements = (
        (r"\bI am showing\b", "The workflow demonstrates"),
        (r"\bI'm showing\b", "The workflow demonstrates"),
        (r"\bI show\b", "The workflow demonstrates"),
        (r"\bI want to show you\b", "The technique shows"),
        (r"\bwe can\b", "Producers can"),
        (r"\byou can\b", "Producers can"),
        (r"\byou might\b", "Producers may"),
        (r"\bthat's\b", "That is"),
        (r"\bit's\b", "It is"),
        (r"\bdon't\b", "Do not"),
        (r"\bwon't\b", "Will not"),
    )
    for pattern, repl in replacements:
        text = re.sub(pattern, repl, text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" ,.")
    if not text:
        return ""
    if text[-1] not in ".!?":
        text += "."
    return text[0].upper() + text[1:]


def score_sentence(sentence: str, terms: list[str]) -> int:
    lowered = sentence.lower()
    score = sum(2 for term in terms[:12] if term in lowered)
    score += sum(3 for term in DOMAIN_TERMS if term in lowered)
    score += sum(1 for word in ("ableton", "live", "delay", "rack", "automation", "midi", "audio") if word in lowered)
    if is_noise_sentence(sentence):
        score -= 20
    return score


def ranked_sentences(cleaned: str, terms: list[str], limit: int = 8) -> list[str]:
    ranked: list[tuple[int, str]] = []
    for sentence in split_sentences(cleaned):
        if is_noise_sentence(sentence):
            continue
        polished = professionalize_sentence(sentence)
        if len(polished) < 30:
            continue
        ranked.append((score_sentence(sentence, terms), polished))
    ranked.sort(reverse=True)
    results: list[str] = []
    seen: set[str] = set()
    for _, sentence in ranked:
        key = sentence.lower()[:80]
        if key in seen:
            continue
        seen.add(key)
        results.append(sentence)
        if len(results) >= limit:
            break
    return results


def educational_points(cleaned: str, terms: list[str], limit: int = 5) -> list[str]:
    lessons = technique_lessons(cleaned)
    if lessons:
        return lessons[:limit]
    points = ranked_sentences(cleaned, terms, limit=limit + 2)
    if points:
        return points[:limit]
    windows = transcript_windows(cleaned, terms, limit=limit)
    return [professionalize_sentence(item) for item in windows if professionalize_sentence(item)] or [
        "Identify the core Ableton device or routing choice demonstrated in the source material."
    ]


def extract_action_steps(cleaned: str) -> list[str]:
    lowered = cleaned.lower()
    found: list[str] = []
    for pattern, template in ACTION_PATTERNS:
        if re.search(pattern, lowered, re.I):
            found.append(template)
    return found[:4]


def technique_steps(cleaned: str) -> list[str]:
    lowered = cleaned.lower()
    steps: list[str] = []

    if "delay" in lowered:
        steps.extend(
            [
                "Load Ableton Delay on a simple melodic source so the effect is easy to hear.",
                "Compare Repitch, Fade, and Jump modes and note which one fits the musical goal.",
                "Automate or modulate delay time for movement instead of leaving static settings.",
            ]
        )
        return _dedupe_steps(steps)
    if "drum rack" in lowered or ("drum" in lowered and "rack" in lowered):
        steps.extend(
            [
                "Add a Drum Rack to a MIDI track and assign one sample per pad.",
                "Program a simple pattern, balance pad levels, then add shared processing on a bus.",
            ]
        )
    if "bass" in lowered or "sub" in lowered:
        steps.extend(
            [
                "High-pass non-bass elements to keep the sub band clear.",
                "Use EQ and gentle saturation on the bass group before final level matching against the kick.",
            ]
        )
    if "resampl" in lowered:
        steps.extend(
            [
                "Record the processed signal to a new audio track or use freeze/flatten.",
                "Edit the resampled audio and reuse it as a stable sound source.",
            ]
        )

    if "delay" not in lowered:
        steps.extend(extract_action_steps(cleaned))
    if not steps:
        steps = [
            "Recreate the technique in a blank Live Set with one simple sound.",
            "Name the main device, routing path, or clip type used in the tutorial.",
            "Apply the setting once, listen, then adapt it to your own material.",
            "Save a rack or preset if the result is reusable.",
        ]
    return _dedupe_steps(steps)


def _dedupe_steps(steps: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for step in steps:
        key = step.lower()[:60]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(step)
    return deduped[:7]


def synthesize_short_answer(title: str, points: list[str], terms: list[str]) -> str:
    if not points:
        topic = formal_topic(terms, title)
        return (
            f"This workflow covers {topic} in Ableton Live. "
            "Use the steps below to reproduce the technique in a controlled test session before applying it to a full track."
        )
    lead = points[0].rstrip(".")
    if len(points) == 1:
        return f"{lead}."
    support = points[1].rstrip(".")
    return f"{lead}. {support}."


def infer_tags(terms: list[str], creator: str = "", extra: str = "") -> str:
    tags = ["ableton", "production", "workflow"]
    if creator:
        tags.append(slugify_tag(creator))
    for term in terms[:10]:
        if term not in tags and len(term) > 2:
            tags.append(term)
    if extra:
        for part in extra.split(","):
            tag = part.strip().lower()
            if tag and tag not in tags:
                tags.append(tag)
    return ", ".join(tags[:14])


def slugify_tag(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")


def related_questions(title: str, terms: list[str]) -> list[str]:
    topic = formal_topic(terms, title).lower()
    base = [
        f"When should I avoid this approach to {topic}?",
        "Which Ableton device or rack setting is essential here?",
        "How do I test this on one track before using it in a full mix?",
    ]
    if "delay" in topic or "delay" in terms:
        base.insert(0, "When should I use Fade mode instead of Repitch on Delay?")
    if "drum" in topic or "drum" in terms:
        base.insert(0, "How do I process individual Drum Rack pads separately?")
    if "bass" in topic or "bass" in terms:
        base.insert(0, "How do I sidechain bass to the kick without losing low end?")
    return base[:4]


def professional_note_markdown(
    title: str,
    transcript_path: Path,
    source: dict | None = None,
    note_type: str = "Production workflow",
    tags: str = "",
) -> str:
    raw = transcript_path.read_text(encoding="utf-8", errors="replace")
    cleaned = clean_transcript_text(raw)
    terms = top_terms(cleaned)
    source = source or {}
    creator = source.get("creator", "") or creator_from_transcript(transcript_path)
    tag_string = tags or infer_tags(terms, creator)
    points = educational_points(cleaned, terms)
    short = synthesize_short_answer(title, points, terms)
    steps = technique_steps(cleaned)
    step_text = "\n".join(f"{index}. {step}" for index, step in enumerate(steps, start=1))
    point_text = "\n".join(f"- {point}" for point in points)
    term_text = ", ".join(terms) or tag_string
    related = "\n".join(f"- {item}" for item in related_questions(title, terms))

    return f"""# {title}

Type: {note_type}
Tags: {tag_string}
Status: Draft
Source title: {source.get('title', '')}
Source creator: {creator}
Source URL: {source.get('url', '')}
Source ID: {source.get('id', '')}
Transcript file: {transcript_path.name}

Short answer:
{short}

Key ideas:
{point_text}

Try this:
{step_text}

Why it matters:
Turning tutorial language into a structured Ableton workflow makes the technique repeatable in future sessions and improves chatbot retrieval quality after approval.

Related questions:
{related}

Useful terms:
{term_text}

Editor notes:
Review for accuracy, remove any off-topic creator chatter, and rewrite any remaining informal phrasing before approving.
"""


def creator_from_transcript(transcript_path: Path) -> str:
    lowered = transcript_path.stem.lower()
    if "virtual-riot" in lowered or "virtual_riot" in lowered:
        return "Virtual Riot"
    return ""
