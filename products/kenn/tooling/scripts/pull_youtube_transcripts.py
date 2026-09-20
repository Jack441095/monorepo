#!/usr/bin/env python3
"""Pull high-value masterclass & tutorial transcripts for KENN training.

Extracts verbatim transcripts for Dan Worrall, Baphometrix (Clip to Zero),
and Mr. Bill, writing clean text files into apps/backend/src/kenn/Training_Data_Transcripts/.
"""

from __future__ import annotations

from pathlib import Path
import time
from youtube_transcript_api import YouTubeTranscriptApi

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "Training_Data_Transcripts"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TARGET_VIDEOS = [
    {
        "id": "efKabAQQsPQ",
        "slug": "dan-worrall-linear-phase-vs-minimum-phase",
        "title": "Dan Worrall: Linear Phase vs Minimum Phase EQ",
        "creator": "Dan Worrall",
        "tags": "dan worrall, eq, linear phase, minimum phase, pre-ringing, phase shift, latency, mixing",
    },
    {
        "id": "m255y4W6_Zg",
        "slug": "dan-worrall-fabfilter-pro-c2-compression-masterclass",
        "title": "Dan Worrall: Dynamics, Compression Styles and Knee Shaping",
        "creator": "Dan Worrall",
        "tags": "dan worrall, compression, pro-c2, attack, release, opto, vocal, bus, clean, knee, sidechain",
    },
    {
        "id": "dTFAceVmAWg",
        "slug": "baphometrix-clip-to-zero-production-strategy",
        "title": "Baphometrix: The Clip-To-Zero Production Strategy (Full Masterclass)",
        "creator": "Baphometrix",
        "tags": "baphometrix, clip to zero, ctz, soft clipping, headroom, crest factor, loudness, mastering, gain staging",
    },
    {
        "id": "EBAglKYTOe0",
        "slug": "mr-bill-granular-synthesis-ableton",
        "title": "Mr. Bill: Ableton Tutorial 68 - Granular Synthesis",
        "creator": "Mr. Bill",
        "tags": "mr bill, ableton, granulator, sound design, texture, ambient, pads, sampling",
    },
    {
        "id": "wXh8aD5D_W0",
        "slug": "mr-bill-automatic-hocket-machine",
        "title": "Mr. Bill: Ableton Tutorial 73 - Automatic Hocket Machine & Modulation",
        "creator": "Mr. Bill",
        "tags": "mr bill, ableton, racks, chains, modulation, hocket, sound design, glitch",
    },
    {
        "id": "gT8g01z4h5g",
        "slug": "mr-bill-delay-time-tricks-ableton",
        "title": "Mr. Bill: Ableton Tutorial 1 - Delay Time Tricks & Comb Filtering",
        "creator": "Mr. Bill",
        "tags": "mr bill, ableton, delay, comb filter, modulation, sound design, stereo width",
    },
]


def pull_transcripts():
    print(f"Pulling transcripts for {len(TARGET_VIDEOS)} masterclasses...")
    api = YouTubeTranscriptApi()
    success = 0

    for idx, item in enumerate(TARGET_VIDEOS, start=1):
        slug = item["slug"]
        out_file = OUT_DIR / f"{slug}.txt"
        if out_file.exists() and out_file.stat().st_size > 500:
            print(f"[{idx}/{len(TARGET_VIDEOS)}] Already exists: {slug}.txt")
            success += 1
            continue

        print(f"[{idx}/{len(TARGET_VIDEOS)}] Fetching {item['title']} (ID: {item['id']})...")
        try:
            ts = api.fetch(item["id"])
            full_text = " ".join([snippet.text for snippet in ts])
            full_text = full_text.replace("\n", " ").replace("  ", " ")


            header = (
                f"Title: {item['title']}\n"
                f"Creator: {item['creator']}\n"
                f"Tags: {item['tags']}\n"
                f"Video ID: {item['id']}\n"
                f"{'=' * 60}\n\n"
            )
            out_file.write_text(header + full_text, encoding="utf-8")
            print(f"       -> Saved {len(full_text)} characters to {slug}.txt")
            success += 1
            time.sleep(1.0)
        except Exception as exc:
            print(f"       [!] Could not fetch {item['id']} ({exc})")

    print(f"\n[+] Transcript fetch complete: {success}/{len(TARGET_VIDEOS)} files ready in {OUT_DIR}")


if __name__ == "__main__":
    pull_transcripts()

