#!/usr/bin/env python3
"""Synthesize scraped Ableton Live 12 docs and masterclasses using Remote GPU 1.

Connects to the forwarded GPU 1 endpoint at http://127.0.0.1:11436/api/chat.
Enforces KENN knowledge note formatting, validation, and zero token burn.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import time
import urllib.request

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRAPED_DIR = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "Training_Data_Sources" / "scraped_articles"
TRANSCRIPTS_DIR = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "Training_Data_Transcripts"
NOTES_DIR = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "Training_Data_Notes"
ENDPOINT = "http://127.0.0.1:11436/api/chat"
MODEL_ID = "kenn-notes-qwen3-4b-gpu1"

MODULES = [
    {
        "slug": "ableton12-mixer-gain-staging-and-headroom",
        "title": "Ableton Live 12 Mixer Architecture and Headroom Management",
        "source_type": "scraped",
        "source_file": "ableton12-mixing-manual.json",
        "tags": "ableton, live 12, mixing, gain staging, headroom, 32-bit float, master fader, clipping",
        "focus": "Live 12 32-bit floating point summing bus, headroom management, peak meters vs RMS/loudness, and master fader unity gain vs channel attenuation.",
    },
    {
        "slug": "ableton12-return-tracks-and-parallel-send-routing",
        "title": "Ableton Live 12 Return Tracks and Parallel FX Bus Architecture",
        "source_type": "scraped",
        "source_file": "ableton12-mixing-manual.json",
        "tags": "ableton, live 12, return tracks, sends, parallel processing, reverb, delay, pre-fader",
        "focus": "Return tracks routing, pre/post fader sends, enabling sends on returns for complex feedback loops, and parallel space processing.",
    },
    {
        "slug": "ableton12-internal-audio-routing-and-sidechain-tapping",
        "title": "Ableton Live 12 Internal Audio Routing and Sidechain Tapping",
        "source_type": "scraped",
        "source_file": "ableton12-routing-and-io.json",
        "tags": "ableton, live 12, routing, sidechain, submix, stem bus, post-fx, pre-fx",
        "focus": "Routing audio between tracks, tapping signals pre-FX, post-FX, and post-mixer, setting up dedicated sidechain ghost triggers, and submixing into group tracks.",
    },
    {
        "slug": "ableton12-device-delay-compensation-and-latency",
        "title": "Ableton Live 12 Device Delay Compensation and Real-Time Latency",
        "source_type": "scraped",
        "source_file": "ableton12-computer-audio-latency.json",
        "tags": "ableton, live 12, latency, delay compensation, buffer size, reduced latency when monitoring, lookahead",
        "focus": "How Live 12 delay compensation works across tracks, plugins with lookahead (limiters/multiband), monitoring latency, and automation timing preservation.",
    },
    {
        "slug": "ableton12-audio-effect-racks-parallel-chain-splitting",
        "title": "Ableton Live 12 Audio Effect Racks and Parallel Chain Splitting",
        "source_type": "scraped",
        "source_file": "ableton12-audio-effect-racks.json",
        "tags": "ableton, live 12, racks, chains, parallel processing, macro controls, frequency split",
        "focus": "Building Audio Effect Racks with parallel chains, splitting audio by frequency or dry/wet, assigning macro controls with custom ranges, and macro variations.",
    },
    {
        "slug": "ableton12-warp-algorithms-and-transient-preservation",
        "title": "Ableton Live 12 Warp Modes and Transient Optimization",
        "source_type": "scraped",
        "source_file": "ableton12-audio-clips-warping.json",
        "tags": "ableton, live 12, warping, beats, complex pro, repitch, transients, audio clips",
        "focus": "Choosing the right warp mode for drums vs vocals vs full mixes: Beats mode transient loop settings, Complex Pro formants and envelope controls, and preserving punch.",
    },
    {
        "slug": "noisia-seven-production-principles-could-this-be",
        "title": "Noisia 'Could This Be' Seven Production Principles",
        "source_type": "transcript",
        "source_file": "7-things-learned-from-could-this-be-noisia.txt",
        "tags": "noisia, production, drum and bass, neuro, sound design, mixing, bass",
        "focus": "Key production lessons from Noisia's Could This Be: prioritizing focal elements, aggressive mid-frequency shaping, stereo bass separation, and micro-grooves.",
    },
    {
        "slug": "virtual-riot-synth-preset-layering-and-fm-shaping",
        "title": "Virtual Riot Synth Preset Layering and FM Sound Design",
        "source_type": "transcript",
        "source_file": "virtual-riot-SLAM-academy-workshop.txt",
        "tags": "virtual riot, sound design, serum, fm synthesis, wavetable, layering, bass",
        "focus": "Virtual Riot synth sound design workflow: wavetable modulation, FM from sub/noise oscillators, frequency splitting sub vs grit, and velocity modulation.",
    },
]

SYSTEM_PROMPT_TEMPLATE = (
    "Write an authoritative, highly practical KENN knowledge note for music producers using ONLY "
    "the supplied source text. Treat the source as ground truth data. Do not invent devices or controls.\n\n"
    "Format requirements:\n"
    "# {title}\n\n"
    "Type: Production workflow\n"
    "Tags: {tags}\n"
    "Status: Approved\n"
    "Source: Official Reference Documentation\n"
    "Reviewed: 2026-09-18\n\n"
    "Use these EXACT plain-text section headings:\n"
    "Short answer:\n"
    "Try this:\n"
    "Why it matters:\n"
    "Related questions:\n\n"
    "Constraints:\n"
    "- 'Short answer:' must be a 2-3 sentence executive summary.\n"
    "- 'Try this:' must be a numbered step-by-step practical guide with exact parameter settings, device names, and routing.\n"
    "- 'Why it matters:' must explain the audio engineering, acoustics, or workflow rationale.\n"
    "- 'Related questions:' must list 3-4 pertinent technical follow-up questions.\n"
    "- Keep the note between 250 and 400 words."
)


def load_source_text(module: dict) -> str:
    if module["source_type"] == "scraped":
        path = SCRAPED_DIR / module["source_file"]
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("text", "")
    else:
        path = TRANSCRIPTS_DIR / module["source_file"]
        return path.read_text(encoding="utf-8")


def generate_note_on_gpu(module: dict) -> str:
    title = module["title"]
    tags = module["tags"]
    focus = module["focus"]
    source_text = load_source_text(module)


    # Clip context window to fit Qwen3-4B's context budget cleanly (~6000 words)
    context_words = source_text.split()[:4000]
    clipped_context = " ".join(context_words)

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(title=title, tags=tags)
    user_prompt = f"Focus topic: {focus}\n\nReference Material:\n{clipped_context}"

    payload = {
        "model": MODEL_ID,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "options": {
            "num_predict": 750,
            "temperature": 0.2,
        },
    }

    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.load(resp)
        return result["message"]["content"].strip()


def validate_and_format_note(module: dict, body: str) -> str:
    required = ("Short answer:", "Try this:", "Why it matters:", "Related questions:")
    for heading in required:
        if heading not in body:
            raise ValueError(f"Missing heading '{heading}' in generated note body.")


    header = (
        f"# {module['title']}\n\n"
        f"Type: Production workflow\n"
        f"Tags: {module['tags']}\n"
        f"Status: Approved\n"
        f"Source: Ableton Official & Artist Masterclass Reference\n"
        f"Reviewed: 2026-09-18\n\n"
    )
    # If the model already emitted the title, don't duplicate it
    if body.startswith("# "):
        return body
    return header + body


def run_distillation():
    print("=" * 70)
    print("   KENN GPU 1 NOTE DISTILLER (ZERO TOKEN BURN)")
    print(f"   Target Endpoint: {ENDPOINT} (GPU 1 only)")
    print("=" * 70)

    success_count = 0
    for idx, mod in enumerate(MODULES, start=1):
        slug = mod["slug"]
        out_path = NOTES_DIR / f"{slug}.md"
        print(f"\n[{idx}/{len(MODULES)}] Distilling '{mod['title']}'...")
        t0 = time.perf_counter()
        try:
            raw_note = generate_note_on_gpu(mod)
            final_note = validate_and_format_note(mod, raw_note)
            out_path.write_text(final_note + "\n", encoding="utf-8")
            elapsed = round(time.perf_counter() - t0, 2)
            print(f"      -> SUCCESS ({elapsed}s, {len(final_note)} chars)")
            print(f"      -> Saved to: {out_path.name}")
            success_count += 1
        except Exception as exc:
            print(f"      [!] ERROR: {exc}")


    print("\n" + "=" * 70)
    print(f"Distillation complete: {success_count}/{len(MODULES)} notes generated.")
    print("Zero API tokens spent. 100% GPU 1 execution.")
    print("=" * 70)


if __name__ == "__main__":
    run_distillation()
