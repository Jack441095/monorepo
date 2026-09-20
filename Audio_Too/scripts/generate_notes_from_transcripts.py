"""generate_notes_from_transcripts.py

Converts raw YouTube transcripts in Training_Data_Transcripts/ into
KENN-formatted knowledge notes saved to Training_Data_Notes/.

Each transcript is chunked (8K chars), and Ollama extracts 1-2 focused
notes per chunk. Notes are fully rewritten in KENN's voice — source
attribution is generic so there are no licensing concerns.

Usage:
    python scripts/generate_notes_from_transcripts.py [--dry-run] [--file NAME]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import textwrap
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRANSCRIPTS_DIR = ROOT / "studio" / "kenn" / "kenn" / "Training_Data_Transcripts"
NOTES_DIR = ROOT / "studio" / "kenn" / "kenn" / "Training_Data_Notes"
DONE_FILE = ROOT / "studio" / "kenn" / "kenn" / "Training_Data_Transcripts" / ".processed.json"

CHUNK_SIZE = 4000       # chars per chunk — keeps total prompt under 2K tokens
CHUNK_OVERLAP = 300    # overlap so we don't cut mid-technique
TODAY = date.today().isoformat()

SYSTEM_PROMPT = textwrap.dedent("""
You are KENN, an AI audio engineering assistant with deep studio knowledge.
Your notes are direct, practical, and aimed at producers using Ableton Live.

Given a chunk of a YouTube tutorial transcript, extract ONE focused audio
engineering note. The note must:
- Focus on a single specific technique or concept (not a broad summary)
- Be written entirely in your own words — do NOT quote the speaker
- Sound like a studio practitioner explaining to another producer
- Follow the EXACT format below (fill every section)

OUTPUT FORMAT (write exactly this, no extra text):
# [Short descriptive title]

Type: [one of: Mixing technique, Sound design workflow, Recording workflow, Performance workflow, Signal chain, Creative technique]
Tags: [5-8 comma-separated lowercase tags]
Status: Approved
Reviewed: {today}

Short answer:
[2-3 sentences. The key idea stated directly and practically.]

Try this:
1. [Step — specific, actionable, includes parameter values where relevant]
2. [Step]
3. [Step]
4. [Step if needed]
5. [Step if needed]

Why it matters:
[1-2 sentences on the real-world impact.]

Common mistakes:
- [Mistake and why it happens]
- [Mistake and why it happens]

Related questions:
- [Question a producer would actually ask]
- [Question a producer would actually ask]
- [Question a producer would actually ask]

---
If the chunk contains no clear audio engineering technique (it's intro/outro/filler),
reply with exactly: NO_TECHNIQUE
""".strip()).format(today=TODAY)


def _ollama_extract(chunk: str, model: str = "qwen2.5:1.5b", *, max_attempts: int = 3) -> str:
    """Call Ollama and return the raw text response.

    Retries transient connection/timeout failures with a short backoff --
    without this, a single mid-batch network hiccup silently dropped that
    transcript chunk forever, indistinguishable from a legitimate
    NO_TECHNIQUE response (both return ""). Retrying here doesn't fully
    fix that ambiguity (still "" either way to the caller), but it removes
    the far more common failure mode: transient errors that a second or
    third attempt would have succeeded at.
    """
    import time
    import urllib.error
    import urllib.request

    payload = json.dumps({
        "model": model,
        "prompt": f"{SYSTEM_PROMPT}\n\nTRANSCRIPT CHUNK:\n{chunk}",
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 700, "num_ctx": 3000},
    }).encode()

    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
                return data.get("response", "").strip()
        except (urllib.error.URLError, TimeoutError) as e:
            last_error = e
            if attempt < max_attempts:
                print(f"  [ollama error, attempt {attempt}/{max_attempts}] {e} -- retrying", file=sys.stderr)
                time.sleep(2.0 * attempt)
                continue
        except Exception as e:
            # Non-transient (bad response format, etc.) -- no point retrying.
            last_error = e
            break
    print(f"  [ollama error, giving up after {max_attempts} attempt(s)] {last_error}", file=sys.stderr)
    return ""


def _slug_from_title(title: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", title.lower())
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")
    return slug[:60]


def _extract_title(note_text: str) -> str:
    m = re.search(r"^#\s+(.+)$", note_text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def _is_duplicate(title: str) -> bool:
    slug = _slug_from_title(title)
    return (NOTES_DIR / f"{slug}.md").exists()


def _save_note(note_text: str, dry_run: bool) -> str | None:
    title = _extract_title(note_text)
    if not title:
        return None
    slug = _slug_from_title(title)
    path = NOTES_DIR / f"{slug}.md"
    if path.exists():
        print(f"  [skip] {slug}.md already exists")
        return None
    if dry_run:
        print(f"  [dry-run] Would write: {slug}.md")
        print(textwrap.indent(note_text[:300], "    "))
        return slug
    path.write_text(note_text + "\n", encoding="utf-8")
    print(f"  [saved] {slug}.md")
    return slug


def _chunk_text(text: str) -> list[str]:
    """Split text into overlapping chunks."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunk = text[start:end]
        # Try to break at a sentence boundary (only if there's more text after)
        if end < len(text):
            last_period = chunk.rfind(". ")
            if last_period > CHUNK_SIZE // 2:
                chunk = chunk[: last_period + 1]
        chunks.append(chunk.strip())
        # Always advance by at least 1 to prevent infinite loop on short remainders
        advance = max(1, len(chunk) - CHUNK_OVERLAP)
        start += advance
        if end >= len(text):
            break
    return [c for c in chunks if len(c) > 200]


def _load_done() -> dict:
    if DONE_FILE.exists():
        try:
            return json.loads(DONE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_done(done: dict) -> None:
    DONE_FILE.write_text(json.dumps(done, indent=2), encoding="utf-8")


def process_transcript(path: Path, dry_run: bool, model: str) -> int:
    """Process one transcript file. Returns number of notes saved."""
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return 0

    chunks = _chunk_text(text)
    print(f"\n[{path.stem}] {len(chunks)} chunk(s) to process")

    saved = 0
    seen_titles: set[str] = set()

    for i, chunk in enumerate(chunks, 1):
        print(f"  chunk {i}/{len(chunks)}...", end=" ", flush=True)
        result = _ollama_extract(chunk, model=model)

        if not result or result.strip().upper() == "NO_TECHNIQUE":
            print("no technique found")
            continue

        # Ollama sometimes returns multiple notes separated by "---"
        note_blocks = re.split(r"\n---\n", result)
        for block in note_blocks:
            block = block.strip()
            if not block or block.upper() == "NO_TECHNIQUE":
                continue

            title = _extract_title(block)
            if not title:
                print("(no title)")
                continue

            if title in seen_titles:
                print(f"(dup title: {title[:40]})")
                continue
            seen_titles.add(title)

            slug = _save_note(block, dry_run)
            if slug:
                saved += 1

    return saved


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert YouTube transcripts to KENN notes")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing files")
    parser.add_argument("--file", metavar="NAME", help="Process only this transcript (stem name)")
    parser.add_argument("--model", default="qwen2.5:1.5b", help="Ollama model to use")
    parser.add_argument("--force", action="store_true", help="Re-process already-done transcripts")
    args = parser.parse_args()

    NOTES_DIR.mkdir(parents=True, exist_ok=True)

    done = _load_done()
    files = sorted(TRANSCRIPTS_DIR.glob("*.txt"))

    if args.file:
        files = [f for f in files if args.file in f.stem]
        if not files:
            print(f"No transcript matching '{args.file}'")
            sys.exit(1)

    total_saved = 0
    for f in files:
        if not args.force and done.get(f.stem):
            print(f"[skip] {f.stem} (already processed — use --force to redo)")
            continue

        saved = process_transcript(f, dry_run=args.dry_run, model=args.model)
        total_saved += saved

        if not args.dry_run and saved > 0:
            done[f.stem] = {"date": TODAY, "notes_saved": saved}
            _save_done(done)

    print(f"\nDone. {total_saved} note(s) saved.")
    if total_saved > 0 and not args.dry_run:
        print("Next: rebuild KENN index with:")
        print("  cd Audio_Too/studio/kenn && python3 kenn/main.py build")


if __name__ == "__main__":
    main()
