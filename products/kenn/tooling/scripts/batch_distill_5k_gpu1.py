#!/usr/bin/env python3
"""Autonomous Batch Distillation Pipeline for KENN Knowledge Base.

Runs continuously on Remote GPU 1 (RTX 4090 D via local tunnel at http://127.0.0.1:11436).
Transforms scraped Ableton Live 12 documentation, producer masterclasses, and technical
articles into dense, schema-validated KENN Knowledge Notes at zero token cost ($0.00).
Includes checkpointing & resumability.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import time
import urllib.request

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRAPED_DIR = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "Training_Data_Sources" / "scraped_articles"
TRANSCRIPTS_DIR = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "Training_Data_Transcripts"
NOTES_DIR = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "Training_Data_Notes"
PROGRESS_FILE = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "Training_Data_Sources" / ".batch_distillation_progress.json"

ENDPOINT = "http://127.0.0.1:11436/api/chat"
MODEL_ID = "kenn-notes-qwen3-4b-gpu1"

SYSTEM_PROMPT = (
    "You are KENN Knowledge Architect, an elite audio engineer and Ableton Live 12 specialist.\n"
    "Distill the supplied reference text into a dense, battle-tested, authoritative KENN Knowledge Note.\n\n"
    "GROUND RULES:\n"
    "1. TREAT SOURCE AS GROUND TRUTH: Extract real techniques, precise parameters, routing paths, and physics principles.\n"
    "2. CONCRETE VALUES ONLY: Always give exact frequency numbers (Hz), dB levels, attack/release times, and exact Ableton device names.\n"
    "3. ZERO FLUFF: No conversational intros or promotional text.\n\n"
    "OUTPUT FORMAT REQUIREMENTS:\n"
    "# {Descriptive, Actionable Title}\n\n"
    "Type: Production workflow\n"
    "Tags: {comma-separated lowercase tags including 'ableton', devices, and concepts}\n"
    "Status: Approved\n"
    "Source: Official Reference Documentation\n"
    "Reviewed: 2026-09-18\n\n"
    "Use these EXACT plain-text section headings:\n"
    "Short answer:\n"
    "Try this:\n"
    "Why it matters:\n"
    "Related questions:\n\n"
    "- 'Short answer:' must be 2-3 sentences explaining the core technique.\n"
    "- 'Try this:' must be a numbered step-by-step practical guide with exact parameter settings and device routing.\n"
    "- 'Why it matters:' must explain audio acoustics, psychoacoustics, or workflow impact.\n"
    "- 'Related questions:' must list 3-4 pertinent technical follow-up questions.\n"
    "Keep the note between 250 and 400 words."
)


def load_progress() -> set[str]:
    if PROGRESS_FILE.exists():
        try:
            data = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
            return set(data.get("completed_slugs", []))
        except Exception:
            pass
    return set()


def save_progress(completed: set[str]) -> None:
    data = {"completed_slugs": sorted(list(completed)), "last_updated": time.strftime("%Y-%m-%d %H:%M:%S")}
    PROGRESS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def generate_note_from_chunk(title: str, tags: str, text: str, focus: str) -> str:
    user_prompt = f"Topic: {title}\nFocus: {focus}\nTags: {tags}\n\nReference Material:\n{text[:14000]}"
    payload = {
        "model": MODEL_ID,
        "stream": False,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "options": {"num_predict": 750, "temperature": 0.2},
    }
    req = urllib.request.Request(ENDPOINT, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.load(resp)
        return result["message"]["content"].strip()


def validate_note(body: str) -> bool:
    required = ("Short answer:", "Try this:", "Why it matters:", "Related questions:")
    return all(h in body for h in required) and len(body) > 200


def build_work_items() -> list[dict]:
    items = []


    # 1. Scraped Ableton Live 12 Manual Chapters
    if SCRAPED_DIR.exists():
        for json_path in sorted(SCRAPED_DIR.glob("*.json")):
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                text = data.get("text", "")
                words = text.split()
                chunk_size = 2500
                overlap = 300
                step = chunk_size - overlap
                for i in range(0, len(words), step):
                    chunk_words = words[i : i + chunk_size]
                    if len(chunk_words) < 300:
                        continue
                    part = (i // step) + 1
                    base_slug = data.get("slug", json_path.stem)
                    slug = f"{base_slug}-pt{part}"
                    items.append({
                        "slug": slug,
                        "title": f"{data.get('title', json_path.stem)} (Part {part})",
                        "tags": data.get("tags", "ableton, live 12, reference"),
                        "focus": f"Key technical concepts, parameters, and workflows from {data.get('title', json_path.stem)} Part {part}",
                        "text": " ".join(chunk_words),
                    })
            except Exception as e:
                print(f"[!] Error reading {json_path}: {e}")

    # 2. Masterclass Transcripts
    if TRANSCRIPTS_DIR.exists():
        for txt_path in sorted(TRANSCRIPTS_DIR.glob("*.txt")):
            try:
                raw = txt_path.read_text(encoding="utf-8")
                words = raw.split()
                chunk_size = 2000
                overlap = 200
                step = chunk_size - overlap
                for i in range(0, len(words), step):
                    chunk_words = words[i : i + chunk_size]
                    if len(chunk_words) < 300:
                        continue
                    part = (i // step) + 1
                    base_slug = txt_path.stem
                    slug = f"{base_slug}-pt{part}"
                    items.append({
                        "slug": slug,
                        "title": f"{txt_path.stem.replace('-', ' ').title()} (Part {part})",
                        "tags": "ableton, masterclass, sound design, mixing, production",
                        "focus": f"Actionable music production techniques and engineering rules from {txt_path.stem} Part {part}",
                        "text": " ".join(chunk_words),
                    })
            except Exception as e:
                print(f"[!] Error reading {txt_path}: {e}")

    return items


def run_pipeline(max_notes: int = 1000):
    print("=" * 75)
    print("   KENN AUTONOMOUS GPU 1 BATCH DISTILLATION PIPELINE")
    print(f"   Target: {ENDPOINT} (GPU 1 only, 0 token burn)")
    print(f"   Output Directory: {NOTES_DIR}")
    print("=" * 75)

    completed = load_progress()
    work_items = build_work_items()
    pending = [w for w in work_items if w["slug"] not in completed and not (NOTES_DIR / f"{w['slug']}.md").exists()]


    print(f"Total Work Items Discovered: {len(work_items)}")
    print(f"Already Completed / Cached:  {len(completed)}")
    print(f"Pending Items in Queue:      {len(pending)}")


    limit = min(max_notes, len(pending))
    print(f"Processing up to {limit} items in this run...\n")

    success = 0
    t_start = time.time()

    for idx, item in enumerate(pending[:limit], start=1):
        slug = item["slug"]
        out_path = NOTES_DIR / f"{slug}.md"
        print(f"[{idx}/{limit}] Distilling: {item['title']}...")
        t0 = time.perf_counter()


        try:
            note_content = generate_note_from_chunk(
                title=item["title"],
                tags=item["tags"],
                text=item["text"],
                focus=item["focus"]
            )


            if not validate_note(note_content):
                raise ValueError("Generated note failed schema validation (missing required headings or too short).")


            out_path.write_text(note_content + "\n", encoding="utf-8")
            completed.add(slug)
            save_progress(completed)


            elapsed = round(time.perf_counter() - t0, 2)
            success += 1
            print(f"      -> SUCCESS ({elapsed}s, {len(note_content)} chars)")
            print(f"      -> Saved to: {out_path.name}")
        except Exception as exc:
            print(f"      [!] ERROR on {slug}: {exc}")


        # Brief pause between inference passes to keep GPU cool
        time.sleep(0.5)

    total_time = round(time.time() - t_start, 2)
    print("\n" + "=" * 75)
    print(f"Batch Run Finished: {success}/{limit} notes generated in {total_time}s.")
    print("Zero API tokens spent. 100% GPU 1 execution.")
    print("=" * 75)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KENN Batch Distiller on GPU 1")
    parser.add_argument("--max", type=int, default=100, help="Maximum number of notes to generate in this pass (default: 100)")
    args = parser.parse_args()
    run_pipeline(max_notes=args.max)

