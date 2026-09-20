#!/usr/bin/env python3
"""Extract all chapters from the official 1,009-page Ableton Live 12 Manual PDF.

Produces clean, structured JSON documents in apps/backend/src/kenn/Training_Data_Sources/scraped_articles/
to feed KENN's autonomous GPU 1 distillation pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from pypdf import PdfReader

REPO_ROOT = Path(__file__).resolve().parents[2]
PDF_PATH = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "Training_Data_PDF" / "live12-manual-en.pdf"
OUT_DIR = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "Training_Data_Sources" / "scraped_articles"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def slugify(text: str) -> str:
    cleaned = re.sub(r'^\d+\.\s*', '', text)  # remove leading chapter numbers
    slug = re.sub(r'[^a-zA-Z0-9]+', '-', cleaned.strip().lower()).strip('-')
    return f"ableton12-{slug}"


def extract_all():
    print("=" * 75)
    print("   EXTRACTING OFFICIAL ABLETON LIVE 12 MANUAL (1,009 PAGES)")
    print(f"   Source PDF: {PDF_PATH}")
    print(f"   Output Dir: {OUT_DIR}")
    print("=" * 75)

    if not PDF_PATH.exists():
        print(f"[!] PDF not found: {PDF_PATH}")
        sys.exit(1)

    reader = PdfReader(str(PDF_PATH))
    total_pages = len(reader.pages)
    print(f"[+] Loaded PDF: {total_pages} total pages.")

    # Build chapter boundaries from outline
    chapters = []
    for item in reader.outline:
        if hasattr(item, 'title'):
            title = str(item.title).strip()
            # We want chapters 1 through 41
            if re.match(r'^\d+\.', title):
                try:
                    start_page = reader.get_destination_page_number(item)
                    chapters.append((title, start_page))
                except Exception as e:
                    print(f"[!] Could not resolve page for {title}: {e}")

    print(f"[+] Found {len(chapters)} numbered chapters in outline.")

    for i, (title, start_p) in enumerate(chapters):
        end_p = chapters[i + 1][1] if i + 1 < len(chapters) else total_pages - 3
        page_count = end_p - start_p
        slug = slugify(title)
        out_file = OUT_DIR / f"{slug}.json"

        # Check if already scraped from web or previous extract
        if out_file.exists() and out_file.stat().st_size > 10000:
            print(f"    [SKIP] Chapter {title} already exists ({out_file.name}, {out_file.stat().st_size // 1024} KB)")
            continue

        print(f"    [*] Extracting Chapter {title} (Pages {start_p}–{end_p}, {page_count} pages)...")
        chapter_pages_text = []
        for p in range(start_p, end_p):
            try:
                page_text = reader.pages[p].extract_text() or ""
                # Strip headers/footers
                cleaned_page = re.sub(r'Ableton Live 12 Manual\s*\d*', '', page_text)
                chapter_pages_text.append(cleaned_page.strip())
            except Exception as e:
                print(f"        [!] Error on page {p}: {e}")

        full_text = "\n\n".join(chapter_pages_text).strip()
        word_count = len(full_text.split())

        if word_count < 100:
            print(f"        [!] Insufficient text ({word_count} words), skipping.")
            continue

        doc = {
            "title": f"Ableton Live 12 - {title}",
            "slug": slug,
            "source_type": "official_manual_pdf",
            "page_start": start_p,
            "page_end": end_p,
            "tags": f"ableton, live 12, reference, {slug.replace('ableton12-', '').replace('-', ', ')}",
            "text": full_text,
            "word_count": word_count,
            "char_count": len(full_text),
        }

        out_file.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"        -> Saved: {out_file.name} ({word_count:,} words, {len(full_text):,} chars)")

    print("\n" + "=" * 75)
    print(f"[+] Extraction complete. Total JSON files in {OUT_DIR}: {len(list(OUT_DIR.glob('*.json')))}")
    print("=" * 75)


if __name__ == "__main__":
    extract_all()
