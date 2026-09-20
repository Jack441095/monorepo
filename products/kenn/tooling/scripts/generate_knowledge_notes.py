#!/usr/bin/env python3
"""
KENN Knowledge Note Generator
Generates knowledge base notes using OpenAI-compatible API (Ollama, OpenAI, etc.) for uncovered topics.

Usage:
    python3 tooling/scripts/generate_knowledge_notes.py [--dry-run] [--topic "specific topic"]

Reads TOPICS list below, skips existing notes, generates new ones in the KENN format.
"""

import os
import re
import sys
import time
import argparse
from pathlib import Path

# Add project root to path for kenn imports
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "apps" / "backend" / "src"))

try:
    from kenn.llm.llm_rewrite import is_enabled, config, _chat_completion
except ImportError as e:
    print(f"Import error: {e}")
    print("Run from project root or ensure PYTHONPATH includes source/")
    sys.exit(1)

NOTES_DIR = PROJECT_ROOT / "apps/backend/src/kenn/Training_Data_Notes"

SYSTEM_PROMPT = """You are a professional music producer and Ableton Live expert writing knowledge base notes for KENN, an AI mix assistant.

Write each note in EXACTLY this plain text format — no markdown, no headers with ##:

# Title In Title Case

Type: Sound design
Tags: ableton, tag1, tag2, tag3, tag4, tag5, tag6
Status: Approved

Short answer:
2-3 sentences. Direct answer. Professional tone. Specific device names and parameter values.

Try this:
1. First actionable step with specific parameter values.
2. Second step with concrete details.
3. Continue with 6-12 numbered steps covering the topic thoroughly.
...

Why it matters:
1-2 sentences on why this matters in real production.

Related questions:
- Question 1
- Question 2
- Question 3
- Question 4
- Question 5

Rules:
- NO markdown formatting (no ##, no **, no ---, no ###, no bold)
- Type/Tags/Status on single lines with colon and space (Type: Sound design)
- Tags: lowercase, comma-separated, 6-10 tags including "ableton"
- Numbered steps: 1. 2. 3. (not 1) or **1.**)
- Each step unique, 1-2 sentences max
- Accurate device knowledge
- Start with # Title exactly as shown
- Section headers: Short answer:, Try this:, Why it matters:, Related questions:
"""

# Topics to generate — add more to expand coverage
TOPICS = [
    # Ableton Devices
    ("ableton-clip-envelopes", "Using clip envelopes and clip automation in Ableton"),
    ("ableton-drift-synth", "Ableton Drift synthesizer — sound design and synthesis"),
    ("ableton-spectral-resonator", "Ableton Spectral Resonator effect"),
    ("ableton-spectral-time", "Ableton Spectral Time effect"),
    ("ableton-meld-synth", "Ableton Meld synthesizer"),
    ("ableton-roar-effect", "Ableton Roar saturation and distortion effect"),
    ("ableton-granulator-ii", "Ableton Granulator II Max for Live device"),
    ("ableton-analog-synth", "Ableton Analog synthesizer — sound design"),
    ("ableton-electric-instrument", "Ableton Electric — electric piano simulation"),
    ("ableton-tension-synth", "Ableton Tension physical modeling string synthesizer"),
    ("ableton-pressor-compressor", "Ableton Pressor compressor — sidechain and modes"),
    ("ableton-erosion-effect", "Ableton Erosion audio degradation effect"),
    ("ableton-vinyl-distortion", "Ableton Vinyl Distortion effect"),
    ("ableton-multiband-dynamics", "Ableton Multiband Dynamics compressor and expander"),
    ("ableton-gate-effect", "Ableton Gate noise gate — settings and use cases"),

    # Production Techniques
    ("recording-with-click-track", "Recording to a click track and metronome in Ableton"),
    ("pad-sound-design", "Making a pad sound from scratch in Ableton"),
    ("spectral-effects-music-production", "Using spectral effects in music production"),
    ("bouncing-in-place-ableton", "Bouncing in place vs freeze and flatten in Ableton"),
    ("time-signature-changes", "Time signature changes in an Ableton arrangement"),
    ("mixing-to-reference-track", "Mixing to a reference track in Ableton"),
    ("sample-flipping-hip-hop", "Sample flipping and chopping for hip-hop production"),
    ("making-a-pad-sound", "Making ambient and atmospheric pad sounds"),
    ("neuro-bass-sound-design", "Neuro bass sound design — growl, movement, modulation"),
    ("making-pluck-lead-synth", "Making a pluck or lead synth sound in Ableton"),
    ("foley-and-sound-design", "Using foley and field recordings in music production"),
    ("limiter-use-mastering", "Using a limiter at mastering for loudness and protection"),
    ("ableton-live-set-organisation", "Organising a complex Ableton Live set — tracks, colors, groups"),
    ("recording-audio-in-ableton", "Recording audio in Ableton — input monitoring, arm, buffer"),
    ("mixing-brass-and-strings", "Mixing brass and string instruments in a mix"),
    ("mixing-synth-bass-electronic", "Mixing synth bass in electronic music — layering and clarity"),
    ("saturation-vs-distortion", "Saturation vs distortion — differences and when to use each"),
    ("mono-vs-stereo-in-mixes", "When to use mono vs stereo on instruments"),
    ("delay-vs-reverb-differences", "Delay vs reverb — how to choose between them"),
    ("ableton-follow-actions-advanced", "Advanced Follow Actions in Ableton — probability, length, linked"),
    ("pitch-correction-vocals", "Pitch correction for vocals — manual tuning and auto-tune approaches"),
    ("making-ambient-music-ableton", "Making ambient music in Ableton — drones, texture, space"),
    ("live-djing-ableton", "DJing and live performance with Ableton — decks, cue points, crossfade"),
    ("ableton-max-for-live-basics", "Max for Live basics — what it is and best devices to use"),
    ("bouncing-stems-for-collaboration", "Bouncing and exporting stems for collaboration"),
    ("noise-gate-recording", "Using a noise gate on recordings — threshold, attack, hold, release"),
    ("using-reference-tracks-eq", "EQ matching and referencing in the low end"),
    ("glitch-effects-production", "Glitch effects in production — stutter, bit crush, buffer repeat"),
    ("making-a-kick-drum", "Designing a kick drum from scratch in Ableton"),
    ("making-a-snare-drum", "Designing a snare drum from scratch in Ableton"),
    ("making-hi-hats-from-scratch", "Designing hi-hats from scratch — synthesis and layering"),
    ("mixdown-checklist", "Mixdown checklist — steps before exporting a final mix"),
    ("ableton-midi-remote-control", "Using MIDI controllers with Ableton — mapping and setup"),
]


def slug_to_filename(slug: str) -> Path:
    return NOTES_DIR / f"{slug}.md"


def already_exists(slug: str) -> bool:
    return slug_to_filename(slug).exists()


def generate_note(topic_description: str) -> str | None:
    """Generate a note using the configured LLM (Ollama/OpenAI-compatible)."""
    if not is_enabled("rewrite"):
        print("  ✗ LLM not enabled — check AUDIO_TOO_LLM_ENABLED in .env")
        return None

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Write a KENN knowledge note about: {topic_description}"},
    ]

    try:
        content, usage = _chat_completion(messages, "rewrite")
        print(f"  ✓ Generated ({usage.total_tokens} tokens, {usage.latency_ms}ms)")
        return content
    except Exception as e:
        print(f"  ✗ Generation failed: {e}")
        return None


def save_note(slug: str, content: str) -> None:
    path = slug_to_filename(slug)
    path.write_text(content + "\n", encoding="utf-8")
    print(f"  Saved: {path.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate KENN knowledge base notes")
    parser.add_argument("--dry-run", action="store_true", help="List topics without generating")
    parser.add_argument("--topic", help="Generate a single note for this description (slug auto-derived)")
    parser.add_argument("--slug", help="Slug for --topic output filename")
    parser.add_argument("--limit", type=int, default=0, help="Max notes to generate (0 = all)")
    args = parser.parse_args()

    if args.topic:
        topics = [(args.slug or re.sub(r"[^a-z0-9]+", "-", args.topic.lower()).strip("-"), args.topic)]
    else:
        topics = TOPICS

    pending = [(slug, desc) for slug, desc in topics if not already_exists(slug)]

    if args.dry_run:
        print(f"Topics to generate ({len(pending)} pending, {len(topics) - len(pending)} already exist):")
        for slug, desc in pending:
            print(f"  [{slug}] {desc}")
        return

    if args.limit:
        pending = pending[: args.limit]

    if not is_enabled("rewrite"):
        print("LLM not enabled. Set in .env:")
        print("  AUDIO_TOO_LLM_ENABLED=1")
        print("  AUDIO_TOO_LLM_PROVIDER=ollama")
        print("  AUDIO_TOO_LLM_MODEL=qwen2.5:1.5b")
        print("And run: ollama serve")
        sys.exit(1)

    print(f"Generating {len(pending)} notes via {config()['model']}...")

    for i, (slug, desc) in enumerate(pending, 1):
        print(f"\n[{i}/{len(pending)}] {desc}")
        content = generate_note(desc)
        if content:
            save_note(slug, content)
            if i < len(pending):
                time.sleep(1)  # gentle rate limiting for local models

    print(f"\nDone. Generated {len(pending)} notes into {NOTES_DIR}")
    print("\nNext steps:")
    print("  1. Review generated notes in Training_Data_Notes/")
    print("  2. Bump SEMANTIC_CACHE_LOGIC_VERSION in session_memory.py")
    print("  3. Run: PYTHONPATH=apps/backend/src python3 -m kenn.retrieval.build_index --include-local-manuals")
    print("  4. Commit and push")


if __name__ == "__main__":
    main()