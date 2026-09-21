#!/usr/bin/env python3
"""Synthesize pro producer YouTube transcripts into KENN knowledge notes.

Runs on the remote GPU server targeting GPU 1 loopback endpoint:
    http://127.0.0.1:11436/api/chat (running kenn-notes-qwen3-4b-gpu1 on GPU 1).
Extracts text directly from apps/backend/src/kenn/Training_Data_Transcripts/.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request

ROOT = Path("/mnt/data/kenn-notes-gpu1")
OUT_DIR = ROOT / "transcript_notes"
MODEL_PID_FILE = ROOT / "model.pid"
TRANSCRIPTS_DIR = Path("/mnt/data/kenn-GPU/apps/backend/src/kenn/Training_Data_Transcripts")
ENDPOINT = "http://127.0.0.1:11436/api/chat"
MODEL_ID = "kenn-notes-qwen3-4b-gpu1"
REQUIRED_HEADINGS = ("Short answer:", "Try this:", "Why it matters:", "Related questions:")

MODULES = [
    {
        "slug": "virtual-riot-fat-rack-architecture",
        "title": "Virtual Riot Fat Rack Modular Preset Architecture",
        "file": "virtual-riot-SLAM-academy-workshop.txt",
        "start_word": 7500,
        "end_word": 10500,
        "focus": "Virtual Riot Fat Rack concept: building modular instrument and FX racks that bundle synth presets, processing chains, and MIDI loops into reusable Ableton rack files for instant recall across projects.",
        "tags": "ableton, virtual riot, racks, macros, sound design, workflow",
    },
    {
        "slug": "virtual-riot-multi-macro-modulation",
        "title": "Virtual Riot Multi-Macro Depth and Offset Mapping",
        "file": "virtual-riot-SLAM-academy-workshop.txt",
        "start_word": 11500,
        "end_word": 14500,
        "focus": "Virtual Riot technique for mapping a single macro knob to multiple device parameters with custom depth and offset ranges, allowing expressive filter sweeps, saturation boosts, and stereo changes simultaneously.",
        "tags": "ableton, virtual riot, macros, rack modulation, sound design",
    },
    {
        "slug": "virtual-riot-granular-foley-synthesis",
        "title": "Virtual Riot Granular Foley Synthesis for Pads and Risers",
        "file": "virtual-riot-SLAM-academy-workshop.txt",
        "start_word": 16000,
        "end_word": 19000,
        "focus": "Using everyday sounds, computer OS sounds, foley, and clicks in granular samplers (Granulator/Sampler) to create cinematic atmospheres, evolving pads, and tension-building risers.",
        "tags": "ableton, virtual riot, granular, foley, sound design, pads",
    },
    {
        "slug": "virtual-riot-anthem-drums-transient-layering",
        "title": "Virtual Riot Anthem Drums: Transient Layering and Phase Alignment",
        "file": "virtual-riot-how-to-fine-dat-anthem-drums.txt",
        "start_word": 0,
        "end_word": 2609,
        "focus": "Virtual Riot drum layering masterclass: separating top transient clicks from tonal bodies, aligning phase relationships between layered kicks and snares, and using transient shapers to avoid limiter clipping.",
        "tags": "ableton, virtual riot, drums, layering, transient shaping, phase alignment",
    },
    {
        "slug": "virtual-riot-chaos-racks-random-lfos",
        "title": "Virtual Riot Chaos Racks and Voice-Independent LFOs",
        "file": "virtual-riot-transformers.txt",
        "start_word": 0,
        "end_word": 2500,
        "focus": "Building Ableton Chaos Racks: using smoothed random LFOs in voice-independent mode, modulating delay times, comb filters, and wavetable indices to generate organic, robotic transformer sounds.",
        "tags": "ableton, virtual riot, lfo, chaos, sound design, transformers, dubstep",
    },
    {
        "slug": "virtual-riot-sound-design-resampling-workflow",
        "title": "Virtual Riot Improvised Sound Design Resampling",
        "file": "virtual-riot-transformers.txt",
        "start_word": 3200,
        "end_word": 5997,
        "focus": "Virtual Riot long-pass sound design session workflow: recording continuous audio modulation passes, then chopping, sorting, and exporting into dedicated sample folders (sweeps, lasers, impacts, morphs).",
        "tags": "ableton, virtual riot, resampling, sample packs, sound design, workflow",
    },
    {
        "slug": "noisia-stem-mixing-headroom-allocation",
        "title": "Noisia Stem Mixing and Headroom Allocation",
        "file": "noisia-creative-mixing.txt",
        "start_word": 0,
        "end_word": 1830,
        "focus": "Noisia mixing principles: allocating sub headroom, aggressive high-passing of non-bass elements, parallel saturation for loudness without squashing, and balancing kick and sub dominance in Drum & Bass.",
        "tags": "mixing, noisia, drum and bass, headroom, sub bass, parallel processing",
    },
    {
        "slug": "feed-me-bass-resampling-distortion-stack",
        "title": "Feed Me Bass Resampling and Distortion Stacking",
        "file": "feed-me-bass-resampling.txt",
        "start_word": 0,
        "end_word": 865,
        "focus": "Feed Me bass sound design: iterating audio bounces through multiple distortion, tape saturation, and moving notch filter passes, re-pitching and re-warping audio for complex neuro bass textures.",
        "tags": "sound design, feed me, bass, resampling, distortion, neurofunk",
    },
]


def verify_gpu_binding() -> int:
    pid = int(MODEL_PID_FILE.read_text().strip())
    environ = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
    assert b"CUDA_VISIBLE_DEVICES=1" in environ, "Model process is not restricted to GPU 1"
    print(f"Verified process {pid} bound to GPU 1 (CUDA_VISIBLE_DEVICES=1).")
    return pid


def generate_note(title: str, text: str, focus: str, tags: str) -> str:
    system_prompt = (
        "Write an authoritative, highly practical KENN knowledge note for music producers using ONLY "
        "the supplied tutorial/masterclass transcript excerpt. Treat the excerpt as ground truth data. "
        "Extract concrete production techniques, routing steps, plugin configurations, and engineering principles.\n\n"
        "Format requirements:\n"
        f"# {title}\n\n"
        "Type: Production workflow\n"
        f"Tags: {tags}\n"
        "Status: Approved\n"
        "Source: Artist Masterclass Transcript\n"
        "Reviewed: 2026-07-06\n\n"
        "Use these exact section headings:\n"
        "Short answer: (2-3 sentences direct summary of the technique)\n"
        "Try this: (Numbered, step-by-step actionable guide with exact parameter settings, device names, and routing)\n"
        "Why it matters: (Engineering explanation of audio dynamics, acoustics, or workflow impact)\n"
        "Related questions: (3-4 relevant follow-up questions for music producers)\n\n"
        "Keep the total note under 350 words."
    )
    payload = {
        "model": MODEL_ID,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"Focus topic: {focus}\n\nTranscript Excerpt:\n{text[:16000]}",
            },
        ],
        "options": {"num_predict": 750, "temperature": 0.2},
    }
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.load(resp)
                content = data["message"]["content"].strip()
                if all(h in content for h in REQUIRED_HEADINGS):
                    return content
                print(f"Missing headings on attempt {attempt + 1}, retrying...")
        except urllib.error.HTTPError as exc:
            print(f"HTTP error {exc.code}, retrying...")
            time.sleep(5 * (attempt + 1))
        except Exception as exc:
            print(f"Error {exc}, retrying...")
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Failed to generate note for {title}")


def main() -> int:
    verify_gpu_binding()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for i, mod in enumerate(MODULES, 1):
        slug = mod["slug"]
        title = mod["title"]
        file_name = mod["file"]
        s_idx = mod["start_word"]
        e_idx = mod["end_word"]
        focus = mod["focus"]
        tags = mod["tags"]
        out_file = OUT_DIR / f"{slug}.md"

        print(f"[{i}/{len(MODULES)}] Processing {slug} from {file_name} (words {s_idx}-{e_idx})...", flush=True)
        full_text = (TRANSCRIPTS_DIR / file_name).read_text(encoding="utf-8")
        words = full_text.split()
        excerpt = " ".join(words[s_idx:e_idx])
        print(f"  Extracted {len(excerpt.split())} words. Querying GPU 1 model...", flush=True)

        note_body = generate_note(title, excerpt, focus, tags)
        if not note_body.startswith(f"# {title}"):
            full_note = (
                f"# {title}\n\n"
                f"Type: Production workflow\n"
                f"Tags: {tags}\n"
                f"Status: Approved\n"
                f"Source: Artist Masterclass Transcript ({file_name})\n"
                f"Reviewed: 2026-07-06\n\n"
                f"{note_body}\n"
            )
        else:
            full_note = f"{note_body}\n"

        out_file.write_text(full_note, encoding="utf-8")
        print(f"  Successfully wrote {out_file.name} ({len(full_note)} chars).", flush=True)

    print(f"\nAll {len(MODULES)} transcript notes successfully generated on GPU 1!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
