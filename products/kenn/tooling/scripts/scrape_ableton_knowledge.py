#!/usr/bin/env python3
"""Scrape official Ableton Live 12 technical documentation for KENN knowledge base.

Extracts clean textual sections from Ableton's online reference manual
into structured JSON chunks for GPU distillation.
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

TARGET_PAGES = [
    {
        "slug": "ableton12-mixing-manual",
        "title": "Ableton Live 12 Mixing Reference Manual",
        "url": "https://www.ableton.com/en/live-manual/12/mixing/",
        "tags": "ableton, live 12, mixing, gain staging, headroom, return tracks, master, solo, crossfader",
    },
    {
        "slug": "ableton12-routing-and-io",
        "title": "Ableton Live 12 Routing and I/O Reference Manual",
        "url": "https://www.ableton.com/en/live-manual/12/routing-and-i-o/",
        "tags": "ableton, live 12, routing, sidechaining, submixing, groups, internal audio routing, monitoring",
    },
    {
        "slug": "ableton12-audio-effect-racks",
        "title": "Ableton Live 12 Instrument, Drum and Effect Racks",
        "url": "https://www.ableton.com/en/live-manual/12/instrument-drum-and-effect-racks/",
        "tags": "ableton, live 12, audio effect racks, macro mapping, macro variations, parallel chains, zone editor",
    },
    {
        "slug": "ableton12-computer-audio-latency",
        "title": "Ableton Live 12 Computer Audio Resources and Delay Compensation",
        "url": "https://www.ableton.com/en/live-manual/12/computer-audio-resources-and-strategies/",
        "tags": "ableton, live 12, delay compensation, latency, cpu optimization, buffer size, track freeze",
    },
    {
        "slug": "ableton12-audio-clips-warping",
        "title": "Ableton Live 12 Audio Clips, Tempo, and Warping",
        "url": "https://www.ableton.com/en/live-manual/12/audio-clips-tempo-and-warping/",
        "tags": "ableton, live 12, warping, complex pro, beats mode, transient preservation, tempo follower",
    },
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}


def clean_text(soup: BeautifulSoup) -> str:
    """Extract clean text without navigation, headers, and footers."""
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()


    main = soup.find("main") or soup.find("article") or soup.body
    if not main:
        return ""


    raw = main.get_text(separator="\n", strip=True)
    # Remove excessive blank lines
    lines = [line.strip() for line in raw.splitlines() if len(line.strip()) > 0]
    return "\n\n".join(lines)


def scrape_all():
    print(f"Scraping {len(TARGET_PAGES)} Ableton Live 12 documentation modules...")
    results = []

    for item in TARGET_PAGES:
        print(f"[*] Fetching: {item['title']} ({item['url']})...")
        try:
            req = urllib.request.Request(item["url"], headers=HEADERS)
            with urllib.request.urlopen(req, timeout=25) as resp:
                html = resp.read().decode("utf-8")


            soup = BeautifulSoup(html, "html.parser")
            text = clean_text(soup)
            print(f"    -> Extracted {len(text)} characters.")


            out_file = OUTPUT_DIR / f"{item['slug']}.json"
            record = {
                "slug": item["slug"],
                "title": item["title"],
                "url": item["url"],
                "tags": item["tags"],
                "char_count": len(text),
                "text": text,
            }
            out_file.write_text(json.dumps(record, indent=2), encoding="utf-8")
            results.append(record)
            time.sleep(1.0)
        except Exception as exc:
            print(f"    [!] Error scraping {item['url']}: {exc}")

    print(f"[+] Scraped {len(results)}/{len(TARGET_PAGES)} pages to {OUTPUT_DIR}")
    return results


if __name__ == "__main__":
    scrape_all()

