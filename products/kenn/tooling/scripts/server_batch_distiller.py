#!/usr/bin/env python3
"""Autonomous Batch Distiller running natively on the remote GPU server.

Operates directly on loopback http://127.0.0.1:11436 (GPU 1).
Completely independent of the local Mac; runs 24/7 inside tmux.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import time
import urllib.request

ROOT = Path("/mnt/data/kenn-notes-gpu1")
SCRAPED_DIR = ROOT / "scraped_articles"
TRANSCRIPTS_DIR = ROOT / "transcripts"
NOTES_DIR = ROOT / "generated_notes"
NOTES_DIR.mkdir(parents=True, exist_ok=True)
PROGRESS_FILE = ROOT / ".batch_distillation_progress.json"

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
    data = {
        "completed_slugs": sorted(list(completed)),
        "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
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
    for attempt in range(15):
        try:
            req = urllib.request.Request(
                ENDPOINT,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.load(resp)
                return result["message"]["content"].strip()
        except urllib.error.HTTPError as err:
            if err.code == 429:
                time.sleep(2.5)
                continue
            raise
    raise TimeoutError("Exceeded max retries waiting for GPU generation slot.")


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


def run_pipeline():
    print("=" * 75)
    print("   KENN AUTONOMOUS SERVER-SIDE GPU 1 BATCH DISTILLER")
    print(f"   Target: {ENDPOINT} (GPU 1 native loopback)")
    print(f"   Notes Output: {NOTES_DIR}")
    print("=" * 75)

    while True:
        completed = load_progress()
        work_items = build_work_items()
        pending = [w for w in work_items if w["slug"] not in completed and not (NOTES_DIR / f"{w['slug']}.md").exists()]


        print(f"\n[Status {time.strftime('%Y-%m-%d %H:%M:%S')}] Total: {len(work_items)} | Completed: {len(completed)} | Pending Queue: {len(pending)}")


        if not pending:
            print("[*] Queue empty. Sleeping 30s waiting for new transcripts/articles...")
            time.sleep(30)
            continue

        for idx, item in enumerate(pending, start=1):
            slug = item["slug"]
            out_path = NOTES_DIR / f"{slug}.md"
            print(f"[{idx}/{len(pending)}] [{time.strftime('%H:%M:%S')}] Distilling: {item['title']}...")
            t0 = time.perf_counter()


            try:
                note_content = generate_note_from_chunk(
                    title=item["title"],
                    tags=item["tags"],
                    text=item["text"],
                    focus=item["focus"]
                )


                if not validate_note(note_content):
                    raise ValueError("Generated note failed schema validation.")


                out_path.write_text(note_content + "\n", encoding="utf-8")
                completed.add(slug)
                save_progress(completed)


                elapsed = round(time.perf_counter() - t0, 2)
                print(f"      -> SUCCESS ({elapsed}s, {len(note_content)} chars)")
            except Exception as exc:
                print(f"      [!] ERROR on {slug}: {exc}")


            time.sleep(0.5)


if __name__ == "__main__":
    run_pipeline()
