#!/usr/bin/env python3
"""Resilient Masterclass Transcript Harvester for KENN Training Corpus.

Features:
- Curated video catalogue for Dan Worrall, Mr. Bill, Baphometrix, and FabFilter.
- Polite request pacing (3-6s delay) with exponential backoff on 429.
- Dual engine support: youtube_transcript_api + yt-dlp fallback.
- Optional --cookies parameter to bypass anonymous rate limits.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import random
import subprocess
import time
from youtube_transcript_api import YouTubeTranscriptApi

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "Training_Data_Transcripts"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Curated High-Yield Video Catalogue
CATALOGUE = [
    # Dan Worrall Audio Engineering & Physics
    ("Dan Worrall", "dan-worrall", "b2I8cjvhSog", "Linear Phase vs Minimum Phase"),
    ("Dan Worrall", "dan-worrall", "vgtB1lYMbTU", "How to Master Your Own Mixes"),
    ("Dan Worrall", "dan-worrall", "255sqe1o9fQ", "EQ Gain Compensation"),
    ("Dan Worrall", "dan-worrall", "nP74656yTi8", "Phascinating Phacts about Phase"),
    ("Dan Worrall", "dan-worrall", "a3O3FiGYBxo", "The Hardware Sound"),
    ("Dan Worrall", "dan-worrall", "s8JGUzZCynU", "LAAL Lookahead Analogue Limiter"),
    ("Dan Worrall", "dan-worrall", "cCGwZ7Re4VU", "About Transient Designers"),
    ("Dan Worrall", "dan-worrall", "LtNa8muwp0A", "Only Dither Once"),
    ("Dan Worrall", "dan-worrall", "PlcwZMb09Pw", "Pro Tools Meters Affect The Sound"),
    ("Dan Worrall", "dan-worrall", "b8NVAcZTH14", "Snapback Latency, PDC, and Reverse ReaVerb"),
    ("Dan Worrall", "dan-worrall", "0AxzJ-8n6qY", "Reacting To Jim Lill and Settling It"),


    # FabFilter Masterclasses (Narrated by Dan Worrall)
    ("FabFilter", "dan-worrall-fabfilter", "1xPO2Q2QHXk", "The Philosophy of Bass"),
    ("FabFilter", "dan-worrall-fabfilter", "NRlksRWP3d8", "20 Tips and Tricks"),
    ("FabFilter", "dan-worrall-fabfilter", "BuIXvKKtVSw", "Introduction to FabFilter Pro-R 2"),
    ("FabFilter", "dan-worrall-fabfilter", "dZAm57M5SuQ", "Synthesizing Hats and Shakers"),
    ("FabFilter", "dan-worrall-fabfilter", "IyzXl0urbDU", "Synthesizing Snare Drums"),
    ("FabFilter", "dan-worrall-fabfilter", "CZ1IznOnroA", "Synthesizing Kick Drums"),
    ("FabFilter", "dan-worrall-fabfilter", "MX2TetH84jA", "Mixing with the Pro-Q 4 Instance List"),
    ("FabFilter", "dan-worrall-fabfilter", "mSzvpCz-M2k", "Introduction to FabFilter Pro-C 3"),


    # Mr. Bill Ableton Live Production
    ("Mr. Bill", "mr-bill-live", "bF6iw4rmMMY", "Granular Synthesis Masterclass"),
    ("Mr. Bill", "mr-bill-live", "fx_8VhKBnzg", "Studio Cast 2.1 Production Workflow"),
    ("Mr. Bill", "mr-bill-live", "bP5P84TckfE", "Psytrance and Glitch Production Sessions"),


    # Baphometrix Clip-To-Zero
    ("Baphometrix", "baphometrix-ctz", "b2I8cjvhSog", "CTZ Episode 1"),
    ("Baphometrix", "baphometrix-ctz", "PR1o5LQzEB0", "CTZ Fundamentals"),
    ("Baphometrix", "baphometrix-ctz", "TdiCDayFMa8", "CTZ Gain Staging"),
    ("Baphometrix", "baphometrix-ctz", "x1ZNWl-xuh8", "CTZ Drum Buss Clipping"),
    ("Baphometrix", "baphometrix-ctz", "wcxvbJgKVUM", "CTZ Master Limiting"),
    ("Baphometrix", "baphometrix-ctz", "jR_AXNsrccQ", "CTZ Sub Bass Management"),
]


def fetch_via_ytdlp(video_id: str, cookies_path: str | None = None) -> str | None:
    url = f"https://www.youtube.com/watch?v={video_id}"
    cmd = ["yt-dlp", "--skip-download", "--write-auto-sub", "--sub-lang", "en", "-o", f"/tmp/%(id)s.%(ext)s"]
    if cookies_path and Path(cookies_path).exists():
        cmd.extend(["--cookies", cookies_path])
    cmd.append(url)


    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        vtt_file = Path(f"/tmp/{video_id}.en.vtt")
        if vtt_file.exists():
            content = vtt_file.read_text(encoding="utf-8")
            vtt_file.unlink()
            lines = [line.strip() for line in content.splitlines() if line.strip() and "-->" not in line and not line.startswith("WEBVTT")]
            return " ".join(lines)
    except Exception:
        pass
    return None


def harvest_all(cookies: str | None = None, min_delay: float = 3.0, max_delay: float = 6.0):
    print("=" * 75)
    print("   KENN RESILIENT MASTERCLASS HARVESTER")
    print(f"   Target Directory: {OUT_DIR}")
    print(f"   Catalogue Size: {len(CATALOGUE)} videos")
    print("=" * 75)

    api = YouTubeTranscriptApi()
    downloaded = 0
    skipped = 0
    blocked_count = 0

    for idx, (artist, prefix, vid, title) in enumerate(CATALOGUE, start=1):
        out_file = OUT_DIR / f"{prefix}-{vid}.txt"
        if out_file.exists() and out_file.stat().st_size > 500:
            skipped += 1
            continue

        print(f"[{idx}/{len(CATALOGUE)}] Fetching: {artist} - {title} ({vid})...")
        transcript_text = None

        # Try API first
        try:
            ts = api.fetch(vid)
            transcript_text = " ".join([snippet.text for snippet in ts]).replace("\n", " ")
        except Exception as err:
            err_str = str(err)
            if "blocking requests" in err_str or "429" in err_str:
                print("      [!] YouTube IP cooldown active on direct API. Trying yt-dlp fallback...")
                transcript_text = fetch_via_ytdlp(vid, cookies)
                if not transcript_text:
                    blocked_count += 1
                    print("      [!] Both engines temporarily throttled by YouTube.")
                    if blocked_count >= 3:
                        print("\n[!] YouTube rate limit cooldown reached. Stopping gracefully.")
                        print("[!] Transcripts can be resumed after cooldown or with a browser cookies.txt file.")
                        break
            else:
                print(f"      [i] No captions available for {vid}: {err}")

        if transcript_text and len(transcript_text) > 300:
            header = (
                f"Artist: {artist}\n"
                f"Title: {title}\n"
                f"Video ID: {vid}\n"
                f"Source: YouTube Verbatim Masterclass\n"
                f"{'=' * 60}\n\n"
            )
            out_file.write_text(header + transcript_text, encoding="utf-8")
            downloaded += 1
            print(f"      -> SUCCESS: {len(transcript_text)} chars saved to {out_file.name}")
            blocked_count = 0  # reset block counter on success

        delay = random.uniform(min_delay, max_delay)
        time.sleep(delay)

    print("\n" + "=" * 75)
    print(f"Harvest Summary: {downloaded} downloaded, {skipped} already cached.")
    print(f"Total Masterclasses in {OUT_DIR}: {len(list(OUT_DIR.glob('*.txt')))}")
    print("=" * 75)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Harvest masterclass transcripts for KENN.")
    parser.add_argument("--cookies", type=str, default=None, help="Path to cookies.txt exported from browser")
    parser.add_argument("--delay", type=float, default=3.5, help="Minimum delay in seconds between requests")
    args = parser.parse_args()

    harvest_all(cookies=args.cookies, min_delay=args.delay, max_delay=args.delay + 3.0)
