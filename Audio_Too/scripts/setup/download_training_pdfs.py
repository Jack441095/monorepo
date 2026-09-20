#!/usr/bin/env python3
"""Download curated PDFs listed in pdf_sources.json (official URLs only)."""

from __future__ import annotations

import json
import ssl
import sys
import time
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest


def ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()

ROOT = Path(__file__).resolve().parent.parent.parent
CATALOG = ROOT / "studio" / "kenn" / "kenn" / "Training_Data_Sources" / "pdf_sources.json"
PDF_DIR = ROOT / "studio" / "kenn" / "kenn" / "Training_Data_PDF"
USER_AGENT = "Audio_Too-TrainingPDF/1.0 (local research; +https://github.com/Jack441095/Audio_Too)"


def load_catalog() -> list[dict]:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def download_file(url: str, dest: Path, *, force: bool = False) -> str:
    if dest.exists() and not force:
        size_mb = dest.stat().st_size / (1024 * 1024)
        return f"skip (exists, {size_mb:.1f} MB)"
    req = urlrequest.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlrequest.urlopen(req, timeout=120, context=ssl_context()) as response:
            data = response.read()
    except urlerror.URLError as exc:
        return f"fail ({exc})"
    if not data.startswith(b"%PDF"):
        return "fail (not a PDF response)"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    size_mb = len(data) / (1024 * 1024)
    return f"ok ({size_mb:.1f} MB)"


def parse_category(argv: list[str]) -> str:
    for index, item in enumerate(argv):
        if item == "--category" and index + 1 < len(argv):
            return argv[index + 1].strip().lower()
    return ""


def main() -> int:
    argv = sys.argv[1:]
    force = "--force" in argv
    essential_only = "--essential" in argv
    category = parse_category(argv)
    entries = load_catalog()
    if not entries:
        print("No catalog entries.")
        return 1

    print(f"PDF folder: {PDF_DIR}\n")
    failures = 0
    for entry in entries:
        url = (entry.get("download_url") or "").strip()
        filename = (entry.get("filename") or "").strip()
        if not url or not filename:
            continue
        if essential_only and entry.get("priority") != "essential":
            continue
        if category and entry.get("category", "").lower() != category:
            continue
        dest = PDF_DIR / filename
        print(f"{entry.get('title', filename)}")
        print(f"  -> {filename}")
        result = download_file(url, dest, force=force)
        print(f"  {result}")
        if result.startswith("fail"):
            failures += 1
        time.sleep(0.4)

    print("\nCategories: ableton | standards | game_audio | workflow | theory")
    print("Example: ./ableton download-pdfs --category standards\n")

    print("Manual steps (no auto-download):")
    for entry in entries:
        if category and entry.get("category", "").lower() != category:
            continue
        if entry.get("download_url"):
            continue
        if not entry.get("filename"):
            title = entry.get("title", "item")
            print(f"  - {title}: {entry.get('how_to_obtain', '')}")
            continue
        filename = entry["filename"]
        dest = PDF_DIR / filename
        if not dest.exists():
            print(f"  - Create {filename}: {entry.get('how_to_obtain', '')}")

    if failures:
        print(f"\n{failures} download(s) failed.")
        return 1
    print("\nDone. Run: python3 scripts/build_audio_too_checklist.py && ./ableton build")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
