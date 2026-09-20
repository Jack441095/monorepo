#!/usr/bin/env python3
"""Batch scraper for the complete Ableton Live 12 reference manual technical chapters.

Extracts all core technical sections into clean structured JSON in
apps/backend/src/kenn/Training_Data_Sources/scraped_articles/.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import time
import urllib.request
from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "Training_Data_Sources" / "scraped_articles"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CHAPTERS = [
    {"slug": "ableton12-audio-fact-sheet", "url": "https://www.ableton.com/en/live-manual/12/audio-fact-sheet/", "title": "Ableton Live 12 Audio Fact Sheet", "tags": "ableton, live 12, audio fact sheet, neutral operations, 32-bit float, summing, dither, sample rate conversion"},
    {"slug": "ableton12-midi-fact-sheet", "url": "https://www.ableton.com/en/live-manual/12/midi-fact-sheet/", "title": "Ableton Live 12 MIDI Fact Sheet", "tags": "ableton, live 12, midi, jitter, timing, latency, quantization, hardware"},
    {"slug": "ableton12-live-audio-effects-ref", "url": "https://www.ableton.com/en/live-manual/12/live-audio-effect-reference/", "title": "Ableton Live 12 Audio Effects Reference", "tags": "ableton, live 12, eq eight, compressor, glue compressor, roar, saturator, limiter, utility, delay, reverb"},
    {"slug": "ableton12-live-midi-effects-ref", "url": "https://www.ableton.com/en/live-manual/12/live-midi-effect-reference/", "title": "Ableton Live 12 MIDI Effects Reference", "tags": "ableton, live 12, arpeggiator, chord, scale, velocity, pitch, random, note length, expression control"},
    {"slug": "ableton12-live-instruments-ref", "url": "https://www.ableton.com/en/live-manual/12/live-instrument-reference/", "title": "Ableton Live 12 Instrument Reference", "tags": "ableton, live 12, wavetable, operator, drift, meld, analog, collision, tension, sampler, simpler, drum sampler"},
    {"slug": "ableton12-comping", "url": "https://www.ableton.com/en/live-manual/12/comping/", "title": "Ableton Live 12 Comping and Take Lanes", "tags": "ableton, live 12, comping, take lanes, vocal comping, crossfades, editing"},
    {"slug": "ableton12-stem-separation", "url": "https://www.ableton.com/en/live-manual/12/stem-separation/", "title": "Ableton Live 12 Stem Separation", "tags": "ableton, live 12, stem separation, vocals, drums, bass, instruments, machine learning"},
    {"slug": "ableton12-using-grooves", "url": "https://www.ableton.com/en/live-manual/12/using-grooves/", "title": "Ableton Live 12 Using Grooves and Groove Pool", "tags": "ableton, live 12, grooves, groove pool, swing, timing, velocity, extract groove"},
    {"slug": "ableton12-using-tuning-systems", "url": "https://www.ableton.com/en/live-manual/12/using-tuning-systems/", "title": "Ableton Live 12 Tuning Systems and Microtuning", "tags": "ableton, live 12, microtuning, scl files, asdf, tuning systems, just intonation, pythagorean"},
    {"slug": "ableton12-launching-clips", "url": "https://www.ableton.com/en/live-manual/12/launching-clips/", "title": "Ableton Live 12 Launching Clips and Follow Actions", "tags": "ableton, live 12, follow actions, clip launching, legato, quantization, random jump"},
    {"slug": "ableton12-midi-tools", "url": "https://www.ableton.com/en/live-manual/12/midi-tools/", "title": "Ableton Live 12 MIDI Transformations and Generators", "tags": "ableton, live 12, midi tools, generators, arpeggiate, rhythm, seed, strum, ornament, time warp"},
    {"slug": "ableton12-editing-mpe", "url": "https://www.ableton.com/en/live-manual/12/editing-mpe/", "title": "Ableton Live 12 Editing MPE Expressive Modulation", "tags": "ableton, live 12, mpe, pressure, slide, pitch bend, per note expression"},
    {"slug": "ableton12-converting-audio-to-midi", "url": "https://www.ableton.com/en/live-manual/12/converting-audio-to-midi/", "title": "Ableton Live 12 Converting Audio to MIDI", "tags": "ableton, live 12, audio to midi, drums, harmony, melody, transient detection"},
    {"slug": "ableton12-max-for-live-devices", "url": "https://www.ableton.com/en/live-manual/12/max-for-live-devices/", "title": "Ableton Live 12 Max for Live Essentials", "tags": "ableton, live 12, max for live, lfo, shaper, envelope follower, expression control"},
    {"slug": "ableton12-arrangement-view", "url": "https://www.ableton.com/en/live-manual/12/arrangement-view/", "title": "Ableton Live 12 Arrangement View Architecture", "tags": "ableton, live 12, arrangement, timeline, locators, loop brace, tracks, editing"},
    {"slug": "ableton12-session-view", "url": "https://www.ableton.com/en/live-manual/12/session-view/", "title": "Ableton Live 12 Session View Architecture", "tags": "ableton, live 12, session view, clips, scenes, scene launch, stop buttons"},
    {"slug": "ableton12-clip-envelopes", "url": "https://www.ableton.com/en/live-manual/12/clip-envelopes/", "title": "Ableton Live 12 Clip Envelopes and Modulation", "tags": "ableton, live 12, clip envelopes, modulation, unlinked envelopes, loop lengths, automation"},
    {"slug": "ableton12-automation-and-editing-envelopes", "url": "https://www.ableton.com/en/live-manual/12/automation-and-editing-envelopes/", "title": "Ableton Live 12 Automation and Envelope Editing", "tags": "ableton, live 12, automation, curves, breakpoints, draw mode, thin automation"},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}


def clean_page(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body
    if not main:
        return ""
    text = main.get_text(separator="\n", strip=True)
    lines = [line.strip() for line in text.splitlines() if len(line.strip()) > 0]
    return "\n\n".join(lines)


def run_batch():
    print(f"Starting batch scrape of {len(CHAPTERS)} major Ableton Live 12 chapters...")
    success = 0
    for idx, chap in enumerate(CHAPTERS, start=1):
        slug = chap["slug"]
        out_file = OUTPUT_DIR / f"{slug}.json"
        if out_file.exists() and out_file.stat().st_size > 1000:
            print(f"[{idx}/{len(CHAPTERS)}] Already cached: {slug}")
            success += 1
            continue
        print(f"[{idx}/{len(CHAPTERS)}] Fetching {chap['title']}...")
        try:
            req = urllib.request.Request(chap["url"], headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as resp:
                html = resp.read().decode("utf-8")
            text = clean_page(html)
            record = {
                "slug": slug,
                "title": chap["title"],
                "url": chap["url"],
                "tags": chap["tags"],
                "char_count": len(text),
                "text": text,
            }
            out_file.write_text(json.dumps(record, indent=2), encoding="utf-8")
            print(f"       -> Saved {len(text)} characters to {slug}.json")
            success += 1
            time.sleep(1.0)
        except Exception as e:
            print(f"       [!] Error fetching {slug}: {e}")
    print(f"\n[+] Finished scraping: {success}/{len(CHAPTERS)} chapters successfully saved.")


if __name__ == "__main__":
    run_batch()

