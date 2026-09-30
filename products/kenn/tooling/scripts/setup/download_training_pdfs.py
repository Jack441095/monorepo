#!/usr/bin/env python3
"""Download cataloged training PDFs into Training_Data_PDF/.

`python main.py download-pdfs` has pointed at this path since 2026-09-01 while
the file did not exist (KNOWN_ISSUES: "deeper subcommands reference scripts
that don't exist"). This is the real one.

Honesty rules it enforces:
  * Only entries the catalog marks indexable (no index_policy, "index", or
    "local_opt_in") are fetched. A "reference_only" entry stays unfetched --
    making a licensed manual indexable is a deliberate catalog edit, never a
    side effect of running setup.
  * A file lands on its final name only after the server confirmed HTTP 200
    with an application/pdf body; anything else dies as a .part and is
    deleted. A saved HTML error page masquerading as a manual would poison
    the index for months.
  * The catalog records a license note per source; it is printed with every
    download because the manuals are personal-use licensed and must never
    enter git (Training_Data_PDF/ is gitignored).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PDF_DIR = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "Training_Data_PDF"
CATALOG_PATH = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "Training_Data_Sources" / "pdf_sources.json"

USER_AGENT = "kenn-training-fetch/1.0"
CHUNK = 1024 * 1024


def load_catalog(catalog_path: Path = CATALOG_PATH) -> list[dict]:
    return json.loads(catalog_path.read_text(encoding="utf-8"))


def is_indexable(entry: dict) -> bool:
    # An absent policy means "index" (the original catalog predated the flag).
    policy = str(entry.get("index_policy", "index")).strip().lower()
    return policy != "reference_only"


def select_entries(catalog: list[dict], *, essential_only: bool = False, category: str | None = None) -> list[dict]:
    entries = [e for e in catalog if is_indexable(e)]
    if essential_only:
        entries = [e for e in entries if str(e.get("priority", "")).lower() == "essential"]
    if category:
        entries = [e for e in entries if str(e.get("category", "")).lower() == category.lower()]
    return entries


def fetch_pdf(entry: dict, dest: Path) -> Path:
    """Stream entry's download_url to dest. Raises RuntimeError on any doubt."""
    url = str(entry.get("download_url") or "").strip()
    if not url:
        raise RuntimeError(f"{entry.get('title')}: catalog records no download_url -- {entry.get('how_to_obtain', 'obtain manually')}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp = dest.with_suffix(dest.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            if response.status != 200:
                raise RuntimeError(f"{entry.get('title')}: server returned HTTP {response.status}")
            content_type = response.headers.get("Content-Type", "")
            if "application/pdf" not in content_type.lower():
                # CDNs happily serve 200 + text/html for soft 404s; refuse it.
                raise RuntimeError(f"{entry.get('title')}: response is {content_type!r}, not a PDF")
            written = 0
            with temp.open("wb") as handle:
                while True:
                    block = response.read(CHUNK)
                    if not block:
                        break
                    handle.write(block)
                    written += len(block)
            if written == 0:
                raise RuntimeError(f"{entry.get('title')}: server sent an empty body")
        temp.rename(dest)
    except (RuntimeError, urllib.error.URLError, OSError):
        if temp.exists():
            temp.unlink()
        raise
    dest.chmod(0o644)
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download indexable training PDFs into Training_Data_PDF/.")
    parser.add_argument("--essential", action="store_true", help="only catalog entries with priority=essential")
    parser.add_argument("--category", type=str, default=None, help="restrict to one catalog category")
    parser.add_argument("--force", action="store_true", help="re-download files that already exist")
    parser.add_argument("--list", action="store_true", dest="list_only", help="show the plan and exit")
    args = parser.parse_args(argv)

    catalog = load_catalog()
    entries = select_entries(catalog, essential_only=args.essential, category=args.category)
    skipped = len(catalog) - len(entries)
    failures = 0
    for entry in entries:
        dest = PDF_DIR / str(entry.get("filename", ""))
        if not entry.get("download_url"):
            print(f"[manual] {entry.get('title')}: {entry.get('how_to_obtain', 'no instructions in catalog')}")
            continue
        if dest.exists() and not args.force:
            print(f"[exists] {dest.name} ({dest.stat().st_size:,} bytes) -- use --force to re-download")
            continue
        if args.list_only:
            print(f"[fetch]  {entry.get('title')} <- {entry['download_url']}")
            continue
        print(f"[fetch]  {entry.get('title')} <- {entry['download_url']}")
        print(f"         license: {entry.get('license', 'unspecified')}")
        try:
            saved = fetch_pdf(entry, dest)
            print(f"[ok]     {saved.name} ({saved.stat().st_size:,} bytes)")
        except (RuntimeError, urllib.error.URLError) as exc:
            print(f"[fail]   {exc}")
            failures += 1
    if skipped:
        print(f"{skipped} catalog entr{'y' if skipped == 1 else 'ies'} withheld (index_policy=reference_only).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
