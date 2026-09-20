#!/usr/bin/env python3
"""Research-source and note-template helper for KENN.

This intentionally does not scrape YouTube transcripts. It stores attribution
metadata and creates a note template for user-written learning notes.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
SOURCES_DIR = ROOT / "Training_Data_Sources"
NOTES_DIR = ROOT / "Training_Data_Notes"
TRANSCRIPTS_DIR = ROOT / "Training_Data_Transcripts"
SOURCES_PATH = SOURCES_DIR / "sources.json"
TRANSCRIPT_META_PATH = SOURCES_DIR / "transcripts.json"
WORD_RE = re.compile(r"[a-zA-Z0-9_+#-]{3,}")
STOPWORDS = {
    "the", "and", "for", "that", "with", "this", "from", "are", "you", "can", "will", "live",
    "ableton", "yeah", "okay", "like", "just", "really", "thing", "things", "there", "about",
    "have", "your", "when", "what", "then", "into", "some", "they", "them", "here", "now",
    "today", "showing", "make", "makes", "easier", "this", "helps", "because", "first", "next",
    "how", "add", "adds", "lets", "let", "part", "parts", "strongest", "hello", "nerds",
    "short", "one", "little", "cool", "video", "editing", "program", "switching", "adobe",
    "premiere", "davinci", "resolve", "patreon", "download", "want", "bye", "soon", "all",
    "got", "maybe", "information", "whatever", "known", "know", "thought", "kind", "also",
    "lastly", "actually", "made", "useful", "working", "learning", "software",
}
DOMAIN_TERMS = {
    "delay", "repitch", "fade", "jump", "ping", "pong", "modulation", "lfo", "time",
    "pitch", "stretch", "reverse", "audio", "plugin", "plugins", "tape", "stop",
    "glitch", "glitchy", "grainy", "pads", "melodic", "rack", "wash", "automation",
    "rate", "hertz", "mode", "effect", "effects",
}


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return slug or "ableton-note"


def ensure_files() -> None:
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    if not SOURCES_PATH.exists():
        SOURCES_PATH.write_text("[]\n", encoding="utf-8")
    if not TRANSCRIPT_META_PATH.exists():
        TRANSCRIPT_META_PATH.write_text("[]\n", encoding="utf-8")


def load_sources() -> list[dict]:
    ensure_files()
    return json.loads(SOURCES_PATH.read_text(encoding="utf-8"))


def save_sources(sources: list[dict]) -> None:
    ensure_files()
    SOURCES_PATH.write_text(json.dumps(sources, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_transcript_meta() -> list[dict]:
    ensure_files()
    return json.loads(TRANSCRIPT_META_PATH.read_text(encoding="utf-8"))


def save_transcript_meta(records: list[dict]) -> None:
    ensure_files()
    TRANSCRIPT_META_PATH.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def source_type(url: str) -> str:
    lowered = url.lower()
    if "youtube.com" in lowered or "youtu.be" in lowered:
        return "youtube"
    if lowered.endswith(".pdf"):
        return "pdf"
    return "web"


def add_source(url: str, title: str = "", creator: str = "", notes: str = "") -> dict:
    ensure_files()
    sources = load_sources()
    existing = next((item for item in sources if item.get("url") == url), None)
    if existing:
        return existing
    record = {
        "id": str(uuid4())[:8],
        "url": url,
        "title": title or "Untitled source",
        "creator": creator,
        "type": source_type(url),
        "notes": notes,
        "created_at": now(),
    }
    sources.append(record)
    save_sources(sources)
    return record


def note_template(title: str, source: dict | None = None, note_type: str = "Production workflow", tags: str = "ableton, production") -> str:
    source = source or {}
    source_title = source.get("title", "")
    source_creator = source.get("creator", "")
    source_url = source.get("url", "")
    source_id = source.get("id", "")
    return f"""# {title}

Type: {note_type}
Tags: {tags}
Status: Draft
Reviewed:
Source title: {source_title}
Source creator: {source_creator}
Source URL: {source_url}
Source ID: {source_id}

Short answer:
Write the practical idea in your own words. Keep it short and direct.

Try this:
1. Write the first concrete Ableton step.
2. Add the next practical step.
3. Add a listening/checking step.

Why it matters:
Explain when this helps and what problem it solves.

Common mistakes:
- Add one plausible mistake and the symptom it causes.

When this does not apply:
State the boundary, exception, or missing information that should make KENN ask a follow-up question.

Personal notes:
Add your own observations, variations, or warnings here.

Related questions:
- What should I ask next about this topic?
- What problem does this solve?
"""


def gap_note_template(title: str, question: str, tags: str) -> str:
    return f"""# {title}

Type: Production workflow
Tags: {tags}
Status: Draft
Reviewed:
Source title: LM gap
Source creator:
Source URL:
Source ID:

Short answer:
Answer this question in your own words: {question}

Try this:
1. Open Ableton and walk through the main steps for this workflow.
2. Add specific device names, default settings, and listening checks.
3. Note one common mistake clients make on this topic.

Why it matters:
Explain when a producer or client would need this and what goes wrong without it.

Common mistakes:
- Add one tempting but incorrect fix and explain why it fails.

When this does not apply:
State what evidence is still needed or when a different workflow is appropriate.

Personal notes:
Triggered by a weak LM answer. Original question: {question}

Related questions:
- Rephrase the original question as a follow-up a client might ask.
- What should I do before trying this in a paid session?
"""


def create_note_from_question(question: str, topics: list[str] | None = None) -> Path:
    from kenn.retrieval.retrieval import query_topics

    ensure_files()
    q = question.strip()
    if len(q) < 3:
        raise ValueError("Question must be at least 3 characters.")
    title = re.sub(r"\s+", " ", q.rstrip("?"))[:70].title() or "New Topic"
    topic_hits = list(dict.fromkeys([*(topics or []), *query_topics(q)]))
    tag_parts = [t.replace("_", " ") for t in topic_hits[:8]]
    tag_parts.extend(word for word in re.findall(r"[a-z0-9]+", q.lower()) if len(word) > 3)
    tags = ", ".join(dict.fromkeys([*tag_parts, "ableton", "workflow"]))[:120]
    path = NOTES_DIR / f"{slugify(title)}.md"
    suffix = 2
    while path.exists():
        path = NOTES_DIR / f"{slugify(title)}-{suffix}.md"
        suffix += 1
    path.write_text(gap_note_template(title, q, tags), encoding="utf-8")
    return path


def clean_transcript_text(text: str) -> str:
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.upper() == "WEBVTT":
            continue
        if re.match(r"^\d+$", stripped):
            continue
        if "-->" in stripped:
            continue
        stripped = re.sub(r"<[^>]+>", "", stripped)
        stripped = re.sub(r"^\[.*?\]\s*", "", stripped)
        lines.append(stripped)
    cleaned = " ".join(lines)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def top_terms(text: str, limit: int = 18) -> list[str]:
    words = [word.lower() for word in WORD_RE.findall(text) if word.lower() not in STOPWORDS]
    counts = Counter(words)
    ranked = sorted(counts.items(), key=lambda item: (item[0] in DOMAIN_TERMS, item[1]), reverse=True)
    return [word for word, _ in ranked[:limit]]


def transcript_windows(text: str, terms: list[str], limit: int = 5) -> list[str]:
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    if len(sentences) <= 1:
        words = text.split()
        sentences = [" ".join(words[index : index + 35]) for index in range(0, len(words), 35)]
    scored = []
    term_set = set(terms[:10])
    for sentence in sentences:
        lowered = sentence.lower()
        if any(skip in lowered for skip in ("video editing", "davinci", "premiere", "patreon", "see you again")):
            continue
        score = sum(1 for term in term_set if term in lowered)
        score += sum(2 for term in DOMAIN_TERMS if term in lowered)
        if score:
            scored.append((score, sentence.strip()))
    scored.sort(reverse=True)
    windows = []
    for _, sentence in scored[:limit]:
        if len(sentence) > 240:
            sentence = sentence[:237].rstrip() + "..."
        windows.append(sentence)
    return windows


def transcript_note_template(title: str, transcript_path: Path, source: dict | None = None, note_type: str = "Production workflow", tags: str = "ableton, production") -> str:
    raw = transcript_path.read_text(encoding="utf-8", errors="replace")
    cleaned = clean_transcript_text(raw)
    terms = top_terms(cleaned)
    windows = transcript_windows(cleaned, terms)
    source = source or {}
    term_text = ", ".join(terms) or "Add useful terms here"
    window_text = "\n".join(f"- {item}" for item in windows) or "- Add a short reminder of the useful parts after reviewing the transcript."
    return f"""# {title}

Type: {note_type}
Tags: {tags}
Status: Draft
Reviewed:
Source title: {source.get('title', '')}
Source creator: {source.get('creator', '')}
Source URL: {source.get('url', '')}
Source ID: {source.get('id', '')}
Transcript file: {transcript_path.name}

Research reminders:
This note was created from a local transcript file you supplied. Do not paste the raw transcript here. Rewrite the lesson in your own words before rebuilding the chatbot index.

Useful terms found:
{term_text}

Possible moments to review:
{window_text}

Short answer:
Write the practical idea in your own words. Keep it short and direct.

Try this:
1. Write the first concrete Ableton step.
2. Add the next practical step.
3. Add a listening/checking step.

Why it matters:
Explain when this helps and what problem it solves.

Common mistakes:
- Add one plausible mistake and the symptom it causes.

When this does not apply:
State the boundary, exception, or missing information that should make KENN ask a follow-up question.

Personal notes:
Add your own observations, variations, or warnings here.

Related questions:
- What should I ask next about this topic?
- What problem does this solve?
"""




def formal_topic(terms: list[str], fallback: str) -> str:
    useful = [term for term in terms if term not in {"audio", "sound", "music"}]
    if useful:
        return ", ".join(useful[:4])
    return fallback


def technique_lessons(cleaned: str) -> list[str]:
    lowered = cleaned.lower()
    lessons = []
    if "delay" in lowered and "repitch" in lowered and "pitch" in lowered:
        lessons.append("In Delay's Repitch mode, changing delay time can bend the pitch, which can be used for tape-stop or unstable glitch effects.")
    if "fade" in lowered and "no change in pitch" in lowered:
        lessons.append("Fade mode avoids the obvious pitch bend when delay time changes, so the result feels more like time-stretching than repitching.")
    if "stretch" in lowered and "delay time" in lowered:
        lessons.append("Increasing delay time in Fade mode can stretch the delayed audio; larger time changes make the texture more intense and unstable.")
    if "reverse" in lowered:
        lessons.append("Fast delay-time movement can create reversed or smeared playback artefacts, which can work well for experimental transitions.")
    if "modulation" in lowered or "lfo" in lowered:
        lessons.append("The Delay modulation section can automate delay-time movement, creating rhythmic speed-up and slow-down effects without drawing automation by hand.")
    if "ping pong" in lowered:
        lessons.append("Ping Pong mode spreads the movement across the stereo field, making the effect more spacious and disorienting.")
    if "jump mode" in lowered or "jump" in lowered:
        lessons.append("Jump mode changes delay settings abruptly, which can create clicks or hard glitch accents; use it deliberately if the click is part of the sound.")
    if "wash out" in lowered or "washout" in lowered:
        lessons.append("A wash-out rack can use Fade mode with increasing delay time to stretch the end of a phrase into a transition effect.")
    return lessons


def educational_points(cleaned: str, terms: list[str], limit: int = 5) -> list[str]:
    lessons = technique_lessons(cleaned)
    if lessons:
        return lessons[:limit]
    windows = transcript_windows(cleaned, terms, limit=limit)
    points = []
    for item in windows:
        item = re.sub(r"^today\s+", "", item, flags=re.I)
        item = re.sub(r"\bI am showing\b", "The tutorial demonstrates", item, flags=re.I)
        item = re.sub(r"\bI'm showing\b", "The tutorial demonstrates", item, flags=re.I)
        item = re.sub(r"\bI show\b", "The tutorial demonstrates", item, flags=re.I)
        item = re.sub(r"\bwe can\b", "producers can", item, flags=re.I)
        item = re.sub(r"\byou can\b", "producers can", item, flags=re.I)
        item = re.sub(r"\bjust\b|\byeah\b|\bokay\b|\blike\b", "", item, flags=re.I)
        item = re.sub(r"\s+", " ", item).strip(" .")
        if item:
            points.append(item[0].upper() + item[1:] + ".")
    return points or ["Review the transcript and identify the main production technique being demonstrated."]


def technique_steps(cleaned: str) -> list[str]:
    lowered = cleaned.lower()
    if "delay" not in lowered:
        return []
    steps = [
        "Load Ableton Delay on a simple melodic sound, pad, or audio loop so the movement is easy to hear.",
        "Change the Delay mode from Repitch to Fade to avoid obvious pitch bending while delay time changes.",
        "Slowly increase the delay time and listen for the delayed signal stretching into a grainy texture.",
    ]
    if "modulation" in lowered or "lfo" in lowered:
        steps.append("Use the built-in modulation/LFO section to move delay time automatically instead of drawing manual automation.")
    if "ping pong" in lowered:
        steps.append("Enable Ping Pong if you want the stretched repeats to move across the stereo field.")
    if "wash out" in lowered or "washout" in lowered:
        steps.append("For a transition, automate delay time upward near the end of a phrase and save the setup as a wash-out rack.")
    steps.append("Compare Fade, Repitch, and Jump modes so you understand which artefact is useful for the track.")
    return steps


def educational_note_template(title: str, transcript_path: Path, source: dict | None = None, note_type: str = "Production workflow", tags: str = "ableton, production") -> str:
    from kenn.llm.paraphrase_engine import professional_note_markdown

    return professional_note_markdown(title, transcript_path, source, note_type, tags)


def maybe_llm_polish_note(note_path: Path, transcript_path: Path, *, title: str = "") -> bool:
    """Apply optional LLM polish to a draft note. Returns True if the note was updated."""
    try:
        from kenn.llm.llm_rewrite import enhance_paraphrase_note, is_enabled
    except ImportError:
        return False
    if not is_enabled():
        return False
    draft = note_path.read_text(encoding="utf-8", errors="replace")
    note_title = title or note_path.stem.replace("-", " ").title()
    raw = transcript_path.read_text(encoding="utf-8", errors="replace")
    excerpt = clean_transcript_text(raw)[:6000]
    polished = enhance_paraphrase_note(draft, title=note_title, transcript_excerpt=excerpt)
    if not polished:
        return False
    note_path.write_text(polished, encoding="utf-8")
    return True


def paraphrase_transcript(
    transcript_file: Path,
    title: str,
    source_id: str = "",
    note_type: str = "Production workflow",
    tags: str = "ableton, production",
    overwrite: Path | None = None,
    *,
    use_llm: bool = False,
) -> Path:
    ensure_files()
    transcript_file = resolve_input_path(transcript_file)
    if not transcript_file.exists():
        raise SystemExit(f"Transcript file not found: {transcript_file}")
    sources = load_sources()
    source = next((item for item in sources if item.get("id") == source_id), None) if source_id else None
    stored = TRANSCRIPTS_DIR / transcript_file.name
    if transcript_file.resolve() != stored.resolve():
        stored.write_text(transcript_file.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
    else:
        stored = transcript_file
    if overwrite and overwrite.exists():
        note_path = overwrite
    else:
        note_path = NOTES_DIR / f"{slugify(title)}.md"
        suffix = 2
        while note_path.exists():
            note_path = NOTES_DIR / f"{slugify(title)}-{suffix}.md"
            suffix += 1
    note_path.write_text(educational_note_template(title, stored, source, note_type, tags), encoding="utf-8")
    if use_llm:
        maybe_llm_polish_note(note_path, stored, title=title)
    return note_path

def resolve_input_path(path: Path) -> Path:
    if path.exists():
        return path
    project_relative = ROOT / path
    if project_relative.exists():
        return project_relative
    workspace_relative = ROOT.parent / path
    if workspace_relative.exists():
        return workspace_relative
    return path

def import_transcript(transcript_file: Path, title: str, source_id: str = "", note_type: str = "Production workflow", tags: str = "ableton, production") -> Path:
    ensure_files()
    transcript_file = resolve_input_path(transcript_file)
    if not transcript_file.exists():
        raise SystemExit(f"Transcript file not found: {transcript_file}")
    sources = load_sources()
    source = next((item for item in sources if item.get("id") == source_id), None) if source_id else None
    stored = TRANSCRIPTS_DIR / transcript_file.name
    if transcript_file.resolve() != stored.resolve():
        stored.write_text(transcript_file.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
    else:
        stored = transcript_file
    note_path = NOTES_DIR / f"{slugify(title)}.md"
    suffix = 2
    while note_path.exists():
        note_path = NOTES_DIR / f"{slugify(title)}-{suffix}.md"
        suffix += 1
    note_path.write_text(transcript_note_template(title, stored, source, note_type, tags), encoding="utf-8")
    return note_path

def create_note(title: str, source_id: str = "", note_type: str = "Production workflow", tags: str = "ableton, production") -> Path:
    ensure_files()
    sources = load_sources()
    source = next((item for item in sources if item.get("id") == source_id), None) if source_id else None
    path = NOTES_DIR / f"{slugify(title)}.md"
    suffix = 2
    while path.exists():
        path = NOTES_DIR / f"{slugify(title)}-{suffix}.md"
        suffix += 1
    path.write_text(note_template(title, source, note_type, tags), encoding="utf-8")
    return path



def title_from_transcript(path: Path) -> str:
    title = path.stem.replace("_", " ").replace("-", " ")
    title = re.sub(r"\bvr\b", "Virtual Riot", title, flags=re.I)
    title = re.sub(r"\s+", " ", title).strip()
    return title.title() or "Ableton Transcript Lesson"


def creator_from_transcript(path: Path) -> str:
    lowered = path.stem.lower()
    if "virtual-riot" in lowered or "virtual_riot" in lowered or lowered.startswith("virtual riot"):
        return "Virtual Riot"
    if "noisia" in lowered:
        return "Noisia"
    if "feed-me" in lowered or "feed_me" in lowered:
        return "Feed Me"
    return ""


def transcript_text_size(path: Path) -> int:
    return len(clean_transcript_text(path.read_text(encoding="utf-8", errors="replace")))


def find_note_for_transcript(transcript_name: str) -> Path | None:
    if not NOTES_DIR.exists():
        return None
    needle = f"Transcript file: {transcript_name}"
    matches: list[Path] = []
    for note in NOTES_DIR.glob("*.md"):
        try:
            if needle in note.read_text(encoding="utf-8", errors="replace"):
                matches.append(note)
        except OSError:
            continue
    if not matches:
        return None
    return sorted(matches, key=lambda path: (re.search(r"-\d+\.md$", path.name) is not None, len(path.name)))[0]


def note_status(path: Path | None) -> str:
    if path is None or not path.exists():
        return "Missing"
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[:20]:
        if line.lower().startswith("status:"):
            return line.split(":", 1)[1].strip() or "Draft"
    return "Unmarked"


def update_transcript_record(transcript: Path, note: Path | None, fields: dict[str, str], status: str) -> None:
    records = load_transcript_meta()
    existing = next((item for item in records if item.get("file") == transcript.name), None)
    record = existing or {"file": transcript.name, "created_at": now()}
    record.update(
        {
            "title": fields.get("title", record.get("title") or title_from_transcript(transcript)),
            "creator": fields.get("creator", record.get("creator") or creator_from_transcript(transcript)),
            "source_id": fields.get("source", record.get("source_id", "")),
            "type": fields.get("type", record.get("type") or "Production workflow"),
            "tags": fields.get("tags", record.get("tags") or "ableton, production"),
            "status": status,
            "note": note.name if note else record.get("note", ""),
            "updated_at": now(),
        }
    )
    if existing is None:
        records.append(record)
    save_transcript_meta(records)


def resolve_note_path(target: str) -> Path:
    candidate = Path(target)
    candidates = [candidate, NOTES_DIR / target, NOTES_DIR / f"{target}.md", NOTES_DIR / f"{slugify(target)}.md"]
    for item in candidates:
        if item.exists():
            return item
    raise SystemExit(f"Note not found: {target}")


def set_note_status(note: Path, status: str = "Approved") -> Path:
    text = note.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    for index, line in enumerate(lines[:30]):
        if line.lower().startswith("status:"):
            lines[index] = f"Status: {status}"
            break
    else:
        insert_at = 1
        for index, line in enumerate(lines[:12]):
            if line.lower().startswith("tags:"):
                insert_at = index + 1
                break
        lines.insert(insert_at, f"Status: {status}")
    note.write_text("\n".join(lines) + "\n", encoding="utf-8")

    transcript_name = ""
    for line in lines[:30]:
        if line.lower().startswith("transcript file:"):
            transcript_name = line.split(":", 1)[1].strip()
            break
    if transcript_name:
        records = load_transcript_meta()
        for record in records:
            if record.get("file") == transcript_name:
                record["status"] = status
                record["note"] = note.name
                record["updated_at"] = now()
        save_transcript_meta(records)
    return note


def paraphrase_all_transcripts(fields: dict[str, str]) -> list[Path]:
    ensure_files()
    use_llm = fields.get("llm", "").lower() in {"yes", "true", "1"}
    created: list[Path] = []
    transcripts = sorted(path for path in TRANSCRIPTS_DIR.glob("*") if path.suffix.lower() in {".txt", ".vtt", ".md"})
    if not transcripts:
        print(f"No transcripts found in {TRANSCRIPTS_DIR}")
        return created
    for transcript in transcripts:
        if transcript_text_size(transcript) < 20:
            print(f"Skipped empty transcript: {transcript.name}")
            continue
        existing_note = find_note_for_transcript(transcript.name)
        force = fields.get("force", "").lower() in {"yes", "true", "1"}
        if existing_note and not force:
            update_transcript_record(transcript, existing_note, fields, note_status(existing_note))
            print(f"Skipped existing note: {transcript.name} -> {existing_note.name} ({note_status(existing_note)})")
            continue
        title = fields.get("title", "") or title_from_transcript(transcript)
        creator = fields.get("creator", "") or creator_from_transcript(transcript)
        local_fields = dict(fields)
        local_fields.setdefault("title", title)
        local_fields.setdefault("creator", creator)
        note = paraphrase_transcript(
            transcript,
            title,
            fields.get("source", ""),
            fields.get("type", "Production workflow"),
            fields.get("tags", "ableton, production"),
            overwrite=existing_note if existing_note and force else None,
            use_llm=use_llm,
        )
        if creator:
            note_text = note.read_text(encoding="utf-8", errors="replace")
            note_text = note_text.replace("Source creator: \n", f"Source creator: {creator}\n", 1)
            note.write_text(note_text, encoding="utf-8")
        update_transcript_record(transcript, note, local_fields, note_status(note))
        created.append(note)
        print(f"Created draft: {transcript.name} -> {note.name}")
    if use_llm and created:
        print(f"LLM polish pass finished for {len(created)} note(s).")
    return created


def format_transcripts() -> str:
    ensure_files()
    records = {item.get("file"): item for item in load_transcript_meta()}
    transcript_files = sorted(path for path in TRANSCRIPTS_DIR.glob("*") if path.suffix.lower() in {".txt", ".vtt", ".md"})
    if not transcript_files:
        return "No transcripts saved yet."
    lines = ["Transcript pipeline:"]
    for transcript in transcript_files:
        note = find_note_for_transcript(transcript.name)
        record = records.get(transcript.name, {})
        status = note_status(note) if note else record.get("status", "Unprocessed")
        title = record.get("title") or title_from_transcript(transcript)
        note_name = note.name if note else "no note yet"
        lines.append(f"- {transcript.name} | {status} | {note_name} | {title}")
    return "\n".join(lines)


def format_sources() -> str:
    sources = load_sources()
    if not sources:
        return "No research sources saved yet."
    lines = ["Research sources:"]
    for item in sources:
        label = item.get("title") or item.get("url")
        creator = f" by {item.get('creator')}" if item.get("creator") else ""
        lines.append(f"- {item.get('id')} | {item.get('type')} | {label}{creator} | {item.get('url')}")
    return "\n".join(lines)


def format_pdf_catalog() -> str:
    from kenn.retrieval.source_catalog import installed_pdfs, load_pdf_catalog

    present = installed_pdfs()
    entries = load_pdf_catalog()
    if not entries:
        return "No PDF catalog entries. Edit Training_Data_Sources/pdf_sources.json."
    lines = ["PDF catalog (Training_Data_Sources/pdf_sources.json):"]
    for entry in entries:
        filename = entry.get("filename", "")
        status = "installed" if filename and filename in present else ("browser-only" if not filename else "missing")
        lines.append(
            f"- [{status}] {entry.get('title', 'Untitled')} | "
            f"priority: {entry.get('priority', 'medium')} | "
            f"index: {entry.get('index_policy', 'index')}"
        )
        if filename:
            lines.append(f"    File: Training_Data_PDF/{filename}")
        if entry.get("download_url"):
            lines.append(f"    Download: {entry['download_url']}")
        lines.append(f"    Obtain: {entry.get('how_to_obtain', '')}")
        lines.append(f"    License: {entry.get('license', '')}")
    if present:
        lines.extend(["", "Installed PDFs:", *[f"- {name}" for name in sorted(present)]])
    return "\n".join(lines)


def approve_transcript_notes() -> list[Path]:
    approved: list[Path] = []
    for note in sorted(NOTES_DIR.glob("*.md")):
        text = note.read_text(encoding="utf-8", errors="replace")
        if "Transcript file:" not in text:
            continue
        if note_status(note).lower() == "approved":
            continue
        set_note_status(note, "Approved")
        approved.append(note)
    return approved


def train_chatbot(approve: bool = False, build: bool = False, force: bool = False, use_llm: bool = False) -> dict:
    import subprocess
    import sys

    fields: dict[str, str] = {}
    if force:
        fields["force"] = "yes"
    if use_llm:
        fields["llm"] = "yes"
    created = paraphrase_all_transcripts(fields)
    approved_notes: list[str] = []
    if approve:
        for path in approve_transcript_notes():
            approved_notes.append(path.name)
    build_ok = False
    build_output = ""
    if build:
        script = ROOT / "build_index.py"
        python = ROOT / ".venv" / "bin" / "python"
        executable = str(python) if python.exists() else sys.executable
        completed = subprocess.run([executable, str(script)], cwd=ROOT, capture_output=True, text=True, check=False)
        build_ok = completed.returncode == 0
        build_output = ((completed.stdout or "") + (completed.stderr or "")).strip()
    return {
        "paraphrased": [path.name for path in created],
        "approved": approved_notes,
        "build_ok": build_ok,
        "build_output": build_output,
        "message": (
            f"Paraphrased {len(created)} transcript(s). "
            f"Approved {len(approved_notes)} note(s). "
            + ("Index rebuilt." if build_ok else ("Index build failed." if build else "Run ./ableton build when ready."))
        ),
    }


def parse_key_values(items: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for item in items:
        if ":" not in item:
            continue
        key, value = item.split(":", 1)
        values[key.strip().lower().replace("-", "_")] = value.strip()
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage Ableton research sources and note templates")
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add-source", help="Save a source URL for attribution")
    add.add_argument("url")
    add.add_argument("details", nargs="*", help='Optional fields: "title: ..." "creator: ..." "notes: ..."')

    note = sub.add_parser("new-note", help="Create a markdown note template")
    note.add_argument("title")
    note.add_argument("details", nargs="*", help='Optional fields: "source: <id>" "type: ..." "tags: ..."')

    transcript = sub.add_parser("import-transcript", help="Create a note draft from a local transcript file you are allowed to use")
    transcript.add_argument("file", type=Path)
    transcript.add_argument("details", nargs="*", help='Required/optional fields: "title: ..." "source: <id>" "type: ..." "tags: ..."')

    paraphrase = sub.add_parser("paraphrase-transcript", help="Create a more formal educational note from a local transcript file")
    paraphrase.add_argument("file", type=Path)
    paraphrase.add_argument("details", nargs="*", help='Required/optional fields: "title: ..." "source: <id>" "type: ..." "tags: ..."')

    batch = sub.add_parser("paraphrase-all-transcripts", help="Create draft educational notes for every unprocessed transcript")
    batch.add_argument("details", nargs="*", help='Optional fields: "creator: ..." "type: ..." "tags: ..." "force: yes"')

    approve = sub.add_parser("approve-note", help="Approve a note so it can be included in the chatbot index")
    approve.add_argument("note", help="Note filename, path, title, or slug")

    sub.add_parser("transcripts", help="List transcript files, generated notes, and review status")
    sub.add_parser("sources", help="List saved sources")

    fetch_web = sub.add_parser("fetch-web", help="Fetch one public web page and create a draft note (review before approving)")
    fetch_web.add_argument("url")
    fetch_web.add_argument("details", nargs="*", help='Optional: "title: ..." "creator: ..." "tags: ..." "force: yes"')

    sub.add_parser("list-web-pack", help="List URLs in Training_Data_Sources/web_sources.json")

    import_pack = sub.add_parser("import-web-pack", help="Import draft notes from web_sources.json (respects robots.txt)")
    import_pack.add_argument("details", nargs="*", help='Optional: "limit: 5" "force: yes" "suggested: yes"')

    train = sub.add_parser("train-chatbot", help="Paraphrase local transcripts, optionally approve and rebuild the chatbot index")
    train.add_argument("details", nargs="*", help='Optional: "force: yes" "approve: yes" "build: yes"')

    suggest = sub.add_parser("suggest-sources", help="Score PDF catalog and suggested web URLs for a topic")
    suggest.add_argument("query", nargs="+")

    plan = sub.add_parser("research-topic", help="Print a step-by-step research plan for a topic")
    plan.add_argument("query", nargs="+")

    sub.add_parser("list-pdf-catalog", help="List curated PDFs and install status")

    args = parser.parse_args()
    if args.command == "add-source":
        fields = parse_key_values(args.details)
        record = add_source(args.url, fields.get("title", ""), fields.get("creator", ""), fields.get("notes", ""))
        print(f"Saved source {record['id']}: {record['title']}")
        print("Next: ./ableton new-note \"Your note title\" \"source: %s\"" % record["id"])
        return 0
    if args.command == "new-note":
        fields = parse_key_values(args.details)
        path = create_note(args.title, fields.get("source", ""), fields.get("type", "Production workflow"), fields.get("tags", "ableton, production"))
        print(f"Created note template: {path}")
        print("Edit it in your own words, then run: ./ableton build")
        return 0
    if args.command == "import-transcript":
        fields = parse_key_values(args.details)
        title = fields.get("title", args.file.stem.replace("-", " ").replace("_", " ").title())
        path = import_transcript(args.file, title, fields.get("source", ""), fields.get("type", "Production workflow"), fields.get("tags", "ableton, production"))
        print(f"Created transcript note draft: {path}")
        print("Rewrite the lesson in your own words, then run: ./ableton build")
        return 0
    if args.command == "paraphrase-transcript":
        fields = parse_key_values(args.details)
        title = fields.get("title", args.file.stem.replace("-", " ").replace("_", " ").title())
        transcript_path = resolve_input_path(args.file)
        overwrite = None
        if fields.get("force", "").lower() in {"yes", "true", "1"}:
            overwrite = find_note_for_transcript(transcript_path.name)
        path = paraphrase_transcript(
            args.file,
            title,
            fields.get("source", ""),
            fields.get("type", "Production workflow"),
            fields.get("tags", "ableton, production"),
            overwrite=overwrite,
        )
        update_transcript_record(transcript_path, path, fields | {"title": title}, note_status(path))
        print(f"Created educational note draft: {path}")
        print("Review/edit it, then approve it: ./ableton approve-note %s" % path.name)
        return 0
    if args.command == "paraphrase-all-transcripts":
        fields = parse_key_values(args.details)
        created = paraphrase_all_transcripts(fields)
        if created:
            print("Next: review the drafts, approve the good ones, then run: ./ableton build")
        return 0
    if args.command == "approve-note":
        path = set_note_status(resolve_note_path(args.note), "Approved")
        print(f"Approved note: {path}")
        print("Next: ./ableton build")
        return 0
    if args.command == "transcripts":
        print(format_transcripts())
        return 0
    if args.command == "sources":
        print(format_sources())
        return 0
    if args.command == "list-pdf-catalog":
        print(format_pdf_catalog())
        return 0
    if args.command == "suggest-sources":
        from kenn.retrieval.source_catalog import suggest_sources

        query = " ".join(args.query)
        data = suggest_sources(query)
        print(f"Suggestions for: {query}\n")
        if data["pdfs"]:
            print("PDFs:")
            for item in data["pdfs"]:
                status = "installed" if item["installed"] else "missing"
                print(f"  [{status}] {item['title']} ({item['filename']}) — {item['how_to_obtain']}")
        else:
            print("PDFs: (no catalog match)")
        if data["articles"]:
            print("\nWeb articles:")
            for item in data["articles"]:
                print(f"  - {item['title']}\n    {item['url']}")
        else:
            print("\nWeb articles: (no match)")
        return 0
    if args.command == "research-topic":
        from kenn.retrieval.source_catalog import research_plan

        print(research_plan(" ".join(args.query)))
        return 0
    if args.command == "train-chatbot":
        fields = parse_key_values(args.details)
        result = train_chatbot(
            approve=fields.get("approve", "").lower() in {"yes", "true", "1"},
            build=fields.get("build", "").lower() in {"yes", "true", "1"},
            force=fields.get("force", "").lower() in {"yes", "true", "1"},
        )
        print(result.get("message", ""))
        if result.get("paraphrased"):
            print("Paraphrased:", ", ".join(result["paraphrased"]))
        if result.get("approved"):
            print("Approved:", ", ".join(result["approved"]))
        if result.get("build_output"):
            print(result["build_output"][-1200:])
        return 0 if result.get("build_ok", True) else 1
    if args.command in {"fetch-web", "list-web-pack", "import-web-pack"}:
        from kenn.retrieval.web_ingest import fetch_web_article, import_web_pack, list_web_pack_entries

        if args.command == "fetch-web":
            fields = parse_key_values(args.details)
            result = fetch_web_article(
                args.url,
                fields.get("title", ""),
                fields.get("creator", ""),
                fields.get("tags", ""),
                force=fields.get("force", "").lower() in {"yes", "true", "1"},
            )
            print(result.get("message", result))
            if result.get("note"):
                print(f"Next: ./ableton approve-note {result['note']}")
            return 0
        if args.command == "list-web-pack":
            entries = list_web_pack_entries()
            if not entries:
                print("No URLs in web_sources.json yet.")
                return 0
            for entry in entries:
                print(f"- {entry.get('title', 'Untitled')} | {entry.get('url', '')}")
            return 0
        if args.command == "import-web-pack":
            fields = parse_key_values(args.details)
            limit = int(fields["limit"]) if fields.get("limit", "").isdigit() else None
            result = import_web_pack(
                limit=limit,
                force=fields.get("force", "").lower() in {"yes", "true", "1"},
                include_suggested=fields.get("suggested", "").lower() in {"yes", "true", "1"},
            )
            print(result.get("message", ""))
            for item in result.get("results", []):
                if item.get("ok"):
                    print(f"  ok: {item.get('note') or item.get('message')}")
                else:
                    print(f"  fail: {item.get('url')} — {item.get('error')}")
            return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
