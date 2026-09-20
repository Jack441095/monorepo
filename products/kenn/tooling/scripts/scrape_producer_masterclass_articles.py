#!/usr/bin/env python3
"""Scrape high-yield technical masterclass articles for KENN knowledge corpus.

Target Sources:
- FabFilter Official Audio Engineering Masterclasses (Linear Phase, Dynamics, Reverb, Acoustics, Synthesis)
- iZotope Audio Engineering & Mixing Masterclasses (Masking, Spectral Carving, Dynamic EQ, Repair)
- Bob Katz K-System & Mastering Standards
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import urllib.request

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "Training_Data_Sources" / "scraped_articles"
OUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Curated FabFilter Masterclass Guides (Official Audio Engineering Library)
FABFILTER_ARTICLES = [
    ("/learn/equalization/linear-phase-eq/", "FabFilter: Linear Phase vs Minimum Phase EQ", "dsp, eq, linear phase, minimum phase, pre-ringing, phase shift, latency, mastering"),
    ("/learn/equalization/frequency-range-characteristics/", "FabFilter: Frequency Range Characteristics & Low-End Management", "eq, frequency spectrum, sub bass, kick, muddiness, presence, air band"),
    ("/learn/equalization/introduction-to-eq/", "FabFilter: Introduction to Equalization & Filter Types", "eq, filters, bell, shelf, notch, high pass, resonance, q factor"),
    ("/learn/compression/introduction-to-compression/", "FabFilter: Introduction to Dynamic Range Compression", "compression, dynamic range, threshold, ratio, attack, release, knee"),
    ("/learn/compression/basic-compressor-controls/", "FabFilter: Mastering Compressor Controls & Envelopes", "compression, transient shaping, attack time, release time, peak detection, rms"),
    ("/learn/compression/compression-techniques-bus-parallel-and-mix-bus/", "FabFilter: Bus, Parallel, and Mix Bus Compression Techniques", "compression, bus compression, parallel compression, mix bus, new york compression, glue"),
    ("/learn/compression/side-chain-compression/", "FabFilter: Side-Chain Compression & Frequency Filtering", "compression, sidechain, kick ducking, external trigger, high pass filter"),
    ("/learn/reverb/introduction-to-reverb/", "FabFilter: Introduction to Reverb Acoustics & Spatial Simulation", "reverb, acoustics, early reflections, late decay, room simulation, predelay"),
    ("/learn/reverb/basic-reverb-controls/", "FabFilter: Reverb Controls & Decay Characteristics", "reverb, decay time, damping, diffusion, pre-delay, size, stereo width"),
    ("/learn/reverb/how-to-use-reverb/", "FabFilter: Creative & Corrective Reverb Mixing Workflows", "reverb, mixing, sends, aux returns, 3d space, depth, eq on reverb"),
    ("/learn/mixing/mixing-a-song-where-to-start/", "FabFilter: Mixing Workflow - Balance, Gain Staging & Foundation", "mixing, gain staging, headroom, balance, panning, fader balance"),
    ("/learn/mixing/creating-a-sound-stage/", "FabFilter: Creating a 3D Sound Stage - Depth, Width & Height", "mixing, stereo width, sound stage, depth, psychoacoustics, phantom center"),
    ("/learn/mixing/how-to-use-automation/", "FabFilter: Dynamic Automation & Mix Arrangement Movement", "mixing, automation, volume riding, vocal balance, energy modulation, arrangement"),
    ("/learn/science-of-sound/wave-theory/", "FabFilter: Sound Wave Theory - Frequency, Amplitude & Harmonics", "acoustics, wave theory, sine waves, complex waves, harmonics, fundamental frequency"),
    ("/learn/science-of-sound/phase-what-is-it-and-why-does-it-matter/", "FabFilter: Phase Physics - Cancellation, Polarity & Alignment", "acoustics, phase, polarity, constructive interference, destructive cancellation, drum alignment"),
    ("/learn/science-of-sound/perception-of-frequency-and-loudness/", "FabFilter: Psychoacoustics - Fletcher-Munson & Loudness Perception", "psychoacoustics, fletcher munson, equal loudness, phon, lufs, ear sensitivity"),
    ("/learn/science-of-sound/sound-localization/", "FabFilter: Sound Localization & Binaural Psychoacoustics", "psychoacoustics, ITD, ILD, interaural time difference, head shadow, binaural, panning"),
    ("/learn/science-of-sound/timbre-understanding-and-crafting-complex-sounds/", "FabFilter: Timbre & Harmonic Series Architecture", "sound design, timbre, harmonics, overtone series, saturation, formant"),
    ("/learn/synthesis-and-sound-design/basics-oscillators/", "FabFilter: Oscillator Types, Waveforms & Frequency Ratios", "synthesis, oscillators, saw, square, pulse width, triangle, fm, wavefolding"),
    ("/learn/synthesis-and-sound-design/basics-filters/", "FabFilter: Filter Topologies, Resonance & Cutoff Slopes", "synthesis, filters, low pass, high pass, 12db, 24db, resonance, self oscillation"),
    ("/learn/synthesis-and-sound-design/basics-subtractive-synthesis/", "FabFilter: Subtractive Synthesis Signal Path & Architecture", "synthesis, subtractive, patch design, bass design, lead design, envelopes"),
    ("/learn/synthesis-and-sound-design/modulation-envelopes/", "FabFilter: ADSR Envelopes & Dynamic Modulation Curves", "synthesis, envelopes, adsr, exponential decay, linear curve, transient design"),
    ("/learn/synthesis-and-sound-design/modulation-lfos/", "FabFilter: Low Frequency Oscillators (LFOs) & Modulation Rhythms", "synthesis, lfo, vibrato, tremolo, filter sweep, tempo sync, wobble"),
]

# Curated iZotope Masterclass Blog Guides
IZOTOPE_ARTICLES = [
    ("/community/blog/digital-audio-basics-sample-rate-and-bit-depth", "iZotope: Digital Audio Basics - Sample Rate, Bit Depth & Aliasing", "digital audio, sample rate, bit depth, nyquist, aliasing, quantization, dither"),
    ("/community/blog/how-to-mix-music", "iZotope: Step-by-Step Modern Music Mixing Workflow", "mixing, workflow, gain staging, bus routing, static mix, vocal balance"),
    ("/community/blog/how-to-eq-vocals", "iZotope: Vocal EQ Guide - Carving Sibilance, Resonance & Air", "vocal mixing, eq, high pass, de-essing, presence, dynamic eq, boxiness"),
    ("/community/blog/mastering-for-streaming-platforms", "iZotope: Mastering for Streaming Services - LUFS, True Peak & Headroom", "mastering, streaming, lufs, true peak, -14 lufs, inter-sample peaks, normalization"),
    ("/community/blog/understanding-spectrograms", "iZotope: Reading & Interpreting Spectrograms for Audio Repair", "spectrogram, fft, spectral editing, noise reduction, audio repair, harmonics"),
    ("/community/blog/repairing-a-distorted-audio-track", "iZotope: Audio Repair - De-Clipping, De-Humming & Restoration", "audio repair, declip, dehum, spectral repair, harmonic distortion restoration"),
    ("/community/blog/a-glossary-of-common-and-confusing-mixing-terms", "iZotope: Comprehensive Audio Engineering & Mixing Glossary", "glossary, audio terminology, headroom, crest factor, phase, transients, mud"),
    ("/community/blog/4-popular-mixing-reference-tracks-and-why-they-work", "iZotope: Reference Track Analysis - Frequency Curve & Dynamic Range", "reference tracks, mix balance, low end reference, dynamic range, crest factor"),
]


def clean_html_to_text(html: str) -> str:
    html = re.sub(r'<(script|style|nav|header|footer|aside|noscript)[^>]*>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&quot;', '"', text)
    text = re.sub(r'&#039;', "'", text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n\n".join(lines)


def scrape_all():
    print("=" * 75)
    print("   KENN MASTERCLASS & TECHNICAL ARTICLE HARVESTER")
    print(f"   Target Directory: {OUT_DIR}")
    print("=" * 75)

    downloaded = 0
    skipped = 0

    # 1. Harvest FabFilter Masterclasses
    print("\n--- Harvesting FabFilter Audio Engineering Masterclasses ---")
    for path, title, tags in FABFILTER_ARTICLES:
        slug = "fabfilter-" + path.strip("/").replace("/", "-")
        out_file = OUT_DIR / f"{slug}.json"
        if out_file.exists() and out_file.stat().st_size > 2000:
            skipped += 1
            continue

        url = f"https://www.fabfilter.com{path}"
        print(f"[*] Scraping: {title}...")
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=12) as resp:
                raw_html = resp.read().decode("utf-8", errors="replace")

            cleaned = clean_html_to_text(raw_html)
            words = cleaned.split()
            if len(words) < 250:
                print(f"    [!] Short content ({len(words)} words), skipping.")
                continue

            doc = {
                "title": title,
                "slug": slug,
                "url": url,
                "tags": tags,
                "source": "FabFilter Audio Engineering Guide",
                "word_count": len(words),
                "char_count": len(cleaned),
                "text": cleaned[:35000],
            }
            out_file.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"    -> SUCCESS: {len(words):,} words saved to {out_file.name}")
            downloaded += 1
        except Exception as e:
            print(f"    [!] Failed to scrape {url}: {e}")

    # 2. Harvest iZotope Masterclasses
    print("\n--- Harvesting iZotope Audio Engineering Masterclasses ---")
    for path, title, tags in IZOTOPE_ARTICLES:
        slug = "izotope-" + path.strip("/").split("/")[-1]
        out_file = OUT_DIR / f"{slug}.json"
        if out_file.exists() and out_file.stat().st_size > 2000:
            skipped += 1
            continue

        url = f"https://www.izotope.com{path}"
        print(f"[*] Scraping: {title}...")
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=12) as resp:
                raw_html = resp.read().decode("utf-8", errors="replace")

            cleaned = clean_html_to_text(raw_html)
            words = cleaned.split()
            if len(words) < 250:
                print(f"    [!] Short content ({len(words)} words), skipping.")
                continue

            doc = {
                "title": title,
                "slug": slug,
                "url": url,
                "tags": tags,
                "source": "iZotope Audio Engineering Guide",
                "word_count": len(words),
                "char_count": len(cleaned),
                "text": cleaned[:35000],
            }
            out_file.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"    -> SUCCESS: {len(words):,} words saved to {out_file.name}")
            downloaded += 1
        except Exception as e:
            print(f"    [!] Failed to scrape {url}: {e}")

    print("\n" + "=" * 75)
    print(f"Scrape Complete: {downloaded} downloaded, {skipped} already cached.")
    print(f"Total Scraped Masterclasses: {len(list(OUT_DIR.glob('*.json')))}")
    print("=" * 75)


if __name__ == "__main__":
    scrape_all()
