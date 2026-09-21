#!/usr/bin/env python3
"""Synthesize Ableton Live 12 Reference Manual workflows into KENN knowledge notes.

Runs on the remote GPU server targeting GPU 1 loopback endpoint:
    http://127.0.0.1:11436/api/chat (running kenn-notes-qwen3-4b-gpu1 on GPU 1).
Extracts text directly from live12-manual-en.pdf using pypdf.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request

import pypdf

ROOT = Path("/mnt/data/kenn-notes-gpu1")
OUT_DIR = ROOT / "manual_notes"
MODEL_PID_FILE = ROOT / "model.pid"
PDF_PATH = Path("/mnt/data/kenn-GPU/apps/backend/src/kenn/Training_Data_PDF/live12-manual-en.pdf")
ENDPOINT = "http://127.0.0.1:11436/api/chat"
MODEL_ID = "kenn-notes-qwen3-4b-gpu1"
REQUIRED_HEADINGS = ("Short answer:", "Try this:", "Why it matters:", "Related questions:")

TOPICS = [
    {
        "slug": "ableton-stem-separation",
        "title": "Ableton Live 12 Stem Separation",
        "start": 430,
        "end": 437,
        "focus": "Live 12 machine-learning stem separation for isolating vocals, drums, bass, and other elements from audio clips and files.",
    },
    {
        "slug": "ableton-comping-and-take-lanes",
        "title": "Ableton Live Comping and Take Lanes",
        "start": 424,
        "end": 429,
        "focus": "Take lanes, recording loop takes, auditioning take lanes, creating comped tracks, and source highlights.",
    },
    {
        "slug": "ableton-bounce-to-audio-workflow",
        "title": "Ableton Live 12 Bounce to Audio Workflow",
        "start": 418,
        "end": 423,
        "focus": "Bouncing individual tracks, bouncing group tracks, pasting bounced audio, and replacing vs retaining original tracks.",
    },
    {
        "slug": "ableton-device-delay-compensation",
        "title": "Ableton Live Plugin Delay Compensation (PDC)",
        "start": 469,
        "end": 470,
        "focus": "Device Delay Compensation (PDC), handling plug-in latency, sidechain latency considerations, and Low Latency When Monitoring mode.",
    },
    {
        "slug": "ableton-midi-tools-transformations-generators",
        "title": "Ableton Live 12 MIDI Transformations and Generators",
        "start": 288,
        "end": 305,
        "focus": "Live 12 MIDI Tools in Clip View: Transformations (Arpeggiate, Connect, Slice, Strum, Time Warp) and Generators (Rhythm, Seed, Shape, Stacks).",
    },
    {
        "slug": "ableton-editing-mpe",
        "title": "Ableton Live MPE Editing and Expression Control",
        "start": 325,
        "end": 334,
        "focus": "MIDI Polyphonic Expression (MPE) tab, editing per-note pitch bend, slide, and pressure curves, and MPE-enabled instruments.",
    },
    {
        "slug": "ableton-converting-audio-to-midi",
        "title": "Ableton Live Converting Audio to MIDI",
        "start": 335,
        "end": 339,
        "focus": "Converting audio drums to MIDI, melody to MIDI, and harmony to MIDI; best source material and transient handling.",
    },
    {
        "slug": "ableton-using-grooves",
        "title": "Ableton Live Groove Pool and Swing",
        "start": 340,
        "end": 345,
        "focus": "Groove Pool, extracting grooves from audio/MIDI clips, timing, velocity, and random parameters, and non-destructive groove commitment.",
    },
    {
        "slug": "ableton-launching-clips-and-follow-actions",
        "title": "Ableton Live Clip Launch Modes and Follow Actions",
        "start": 355,
        "end": 366,
        "focus": "Launch Modes (Trigger, Gate, Toggle, Repeat), Quantization, Follow Actions (chance ratios, A/B probability, Linked vs Unlinked follow action lengths).",
    },
    {
        "slug": "ableton-routing-and-submixing",
        "title": "Ableton Live Audio and MIDI Routing Architecture",
        "start": 367,
        "end": 380,
        "focus": "Routing architecture: Audio From / Audio To, internal routing, submixing with Group Tracks, tap points (Pre FX, Post FX, Post Mixer), and Resampling.",
    },
    {
        "slug": "ableton-mixing-and-gain-staging",
        "title": "Ableton Live Mixing and Gain Staging",
        "start": 389,
        "end": 404,
        "focus": "Mixer section, peak vs RMS metering, 60 dB fader range, solo in place vs cueing, crossfader curves, and group track volume relationships.",
    },
    {
        "slug": "ableton-drum-racks-and-internal-routing",
        "title": "Ableton Live Drum Racks and Internal Routing",
        "start": 481,
        "end": 490,
        "focus": "Drum Racks: pad routing, choke groups, internal send/return chains, sub-mixer, and routing individual drum pads to external DAW tracks.",
    },
    {
        "slug": "ableton-clip-envelopes-and-modulation",
        "title": "Ableton Live Clip Envelopes and Modulation",
        "start": 504,
        "end": 516,
        "focus": "Clip Envelopes: difference between absolute track automation and relative clip modulation, unlinking clip envelopes for polymetric modulation, and MIDI CC envelopes.",
    },
    {
        "slug": "ableton-tempo-follower-and-sync",
        "title": "Ableton Live Tempo Follower and Synchronization",
        "start": 944,
        "end": 952,
        "focus": "Ableton Link peer-to-peer sync, Tempo Follower listening to real-time audio input, and MIDI clock master/slave sync.",
    },
    {
        "slug": "ableton-cpu-management-and-freezing",
        "title": "Ableton Live CPU Management and Track Freezing",
        "start": 953,
        "end": 958,
        "focus": "Managing CPU load: CPU meter interpretations (current vs average), audio buffer size trade-offs, freezing and flattening tracks, and disabling unused devices.",
    },
    {
        "slug": "ableton-audio-fact-sheet-neutral-operations",
        "title": "Ableton Live Audio Fact Sheet and Summing Engine",
        "start": 959,
        "end": 966,
        "focus": "Live audio engine neutrality: 32-bit floating point summing, 0 dB fader transparency, pan law compensation, when warping is neutral vs non-neutral, and triangular vs rectangular dither.",
    },
    {
        "slug": "ableton-midi-fact-sheet-timing-jitter",
        "title": "Ableton Live MIDI Fact Sheet and Timing",
        "start": 967,
        "end": 972,
        "focus": "MIDI timing accuracy: hardware MIDI interface jitter, plugin delay compensation for MIDI tracks, timestamped MIDI events, and driver buffer configurations.",
    },
    {
        "slug": "ableton-accessibility-and-navigation",
        "title": "Ableton Live 12 Accessibility and Keyboard Navigation",
        "start": 973,
        "end": 983,
        "focus": "Live 12 keyboard navigation system: landmark navigation, screen reader support, full keyboard control over clips, mixer, and device parameters.",
    },
]


def verify_gpu_binding() -> int:
    pid = int(MODEL_PID_FILE.read_text().strip())
    environ = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
    assert b"CUDA_VISIBLE_DEVICES=1" in environ, "Model process is not restricted to GPU 1"
    print(f"Verified process {pid} bound to GPU 1 (CUDA_VISIBLE_DEVICES=1).")
    return pid


def generate_note(title: str, text: str, focus: str) -> str:
    system_prompt = (
        "Write an authoritative, highly practical KENN knowledge note for Ableton Live 12 using ONLY "
        "the supplied official manual excerpt. Treat the excerpt as ground truth data. Do not invent "
        "controls, shortcuts, or behaviors. Ensure all parameter names, menu locations, and steps are "
        "100% accurate to the manual text.\n\n"
        "Format requirements:\n"
        f"Title: {title}\n"
        "Status: Approved\n\n"
        "Use these exact section headings:\n"
        "Short answer: (2-3 sentences direct summary)\n"
        "Try this: (Numbered, step-by-step actionable guide with exact parameter names and paths)\n"
        "Why it matters: (Engineering explanation of audio engine, workflow impact, or edge cases)\n"
        "Related questions: (3-4 relevant follow-up questions for Ableton users)\n\n"
        "Keep the total note under 350 words."
    )
    payload = {
        "model": MODEL_ID,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"Focus topic: {focus}\n\nManual Excerpt:\n{text[:18000]}",
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
    reader = pypdf.PdfReader(str(PDF_PATH))
    print(f"Loaded manual PDF from {PDF_PATH} ({len(reader.pages)} pages).")

    for i, topic in enumerate(TOPICS, 1):
        slug = topic["slug"]
        title = topic["title"]
        start_p = topic["start"]
        end_p = topic["end"]
        focus = topic["focus"]
        out_file = OUT_DIR / f"{slug}.md"

        print(f"[{i}/{len(TOPICS)}] Processing {slug} (pages {start_p}-{end_p})...", flush=True)
        text = "\n".join(reader.pages[p - 1].extract_text() or "" for p in range(start_p, end_p + 1))
        words = len(text.split())
        print(f"  Extracted {words} words. Querying GPU 1 model...", flush=True)

        note_body = generate_note(title, text, focus)
        # Ensure Title and Status header
        if not note_body.startswith("Title:"):
            full_note = f"Title: {title}\nStatus: Approved\n\n{note_body}\n"
        else:
            full_note = f"{note_body}\n"
        if "Status: Approved" not in full_note:
            lines = full_note.splitlines()
            full_note = f"{lines[0]}\nStatus: Approved\n" + "\n".join(lines[1:]) + "\n"

        out_file.write_text(full_note, encoding="utf-8")
        print(f"  Successfully wrote {out_file.name} ({len(full_note)} chars).", flush=True)

    print(f"\nAll {len(TOPICS)} notes successfully generated on GPU 1!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
