"""Batch paraphrase KENN training notes through the LLM.

Rewrites notes into KENN's own voice using Qwen, keeping only the factual
content. Use this on any note sourced from copyrighted material to ensure
the expression is entirely yours.

Usage:
    # Paraphrase specific files
    python scripts/paraphrase_notes.py Training_Data_Notes/wwise-spatial-audio-rooms-portals.md

    # Paraphrase all notes modified today
    python scripts/paraphrase_notes.py --today

    # Dry run — show what would be paraphrased without writing
    python scripts/paraphrase_notes.py --today --dry-run

Output: overwrites the note in-place (original backed up to .bak)
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOTES_DIR = ROOT / "studio" / "kenn" / "kenn" / "Training_Data_Notes"
sys.path.insert(0, str(ROOT / "studio" / "kenn"))
sys.path.insert(0, str(ROOT))

# Load .env
_env_file = ROOT / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())


def paraphrase_note(path: Path, dry_run: bool = False) -> bool:
    """Paraphrase a single note file. Returns True on success."""
    from kenn.llm.llm_rewrite import enhance_paraphrase_note, is_enabled

    if not is_enabled("paraphrase"):
        print("  ✗ LLM not enabled — check AUDIO_TOO_LLM_ENABLED in .env")
        return False

    content = path.read_text(encoding="utf-8")
    title = path.stem.replace("-", " ").title()

    # Extract source excerpt hint from Source title metadata if present
    transcript_excerpt = ""
    for line in content.splitlines():
        if line.lower().startswith("source title:"):
            transcript_excerpt = line.split(":", 1)[1].strip()
            break

    if dry_run:
        print(f"  [dry-run] would paraphrase: {path.name}")
        return True

    result = enhance_paraphrase_note(
        content,
        title=title,
        transcript_excerpt=transcript_excerpt,
    )

    if result is None:
        print(f"  ✗ LLM returned nothing — skipping {path.name}")
        return False

    # Preserve metadata header lines from original
    original_lines = content.splitlines()
    result_lines = result.splitlines()

    # Keep original metadata (Type, Tags, Status, Source *, Reviewed)
    meta_keys = ("type:", "tags:", "status:", "source ", "reviewed:")
    original_meta = [
        ln for ln in original_lines
        if any(ln.lower().startswith(k) for k in meta_keys)
    ]
    result_body = [
        ln for ln in result_lines
        if not any(ln.lower().startswith(k) for k in meta_keys)
    ]

    final = "\n".join(original_meta + [""] + result_body).strip() + "\n"

    # Back up original
    backup = path.with_suffix(".md.bak")
    backup.write_text(content, encoding="utf-8")

    # Write paraphrased version
    path.write_text(final, encoding="utf-8")
    print(f"  ✓ {path.name}  (backup → {backup.name})")
    return True


def _has_external_source(path: Path) -> bool:
    """Return True if the note has a Source title from a third-party (not Audio_Too)."""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lower().startswith("source title:"):
            src = line.split(":", 1)[1].strip()
            return bool(src) and "audio_too" not in src.lower()
    return False


def notes_modified_today(sourced_only: bool = False) -> list[Path]:
    import datetime
    today = datetime.date.today()
    results = []
    for p in NOTES_DIR.glob("*.md"):
        mtime = datetime.date.fromtimestamp(p.stat().st_mtime)
        if mtime == today:
            if not sourced_only or _has_external_source(p):
                results.append(p)
    return sorted(results)


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch paraphrase KENN training notes")
    parser.add_argument("files", nargs="*", help="Note files to paraphrase (relative to Training_Data_Notes/)")
    parser.add_argument("--today", action="store_true", help="Paraphrase all notes modified today")
    parser.add_argument("--sourced-only", action="store_true", help="With --today, skip original notes (no external Source title)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be changed, don't write")
    args = parser.parse_args()

    targets: list[Path] = []

    if args.today:
        targets = notes_modified_today(sourced_only=args.sourced_only)
        if not targets:
            print("No notes modified today.")
            return
        label = " (external sources only)" if args.sourced_only else ""
        print(f"Found {len(targets)} note(s) modified today{label}:\n")
        for t in targets:
            print(f"  {t.name}")
        print()
    elif args.files:
        for f in args.files:
            p = Path(f)
            if not p.is_absolute():
                p = NOTES_DIR / p
            if not p.exists():
                print(f"Not found: {p}")
                continue
            targets.append(p)
    else:
        parser.print_help()
        return

    if not targets:
        print("Nothing to paraphrase.")
        return

    print(f"Paraphrasing {len(targets)} note(s) via Qwen...\n")
    ok = 0
    for path in targets:
        print(f"→ {path.name}")
        success = paraphrase_note(path, dry_run=args.dry_run)
        if success:
            ok += 1
        time.sleep(1)  # avoid hammering Ollama

    print(f"\nDone: {ok}/{len(targets)} paraphrased.")
    if ok < len(targets):
        print("Check Ollama is running: ollama serve")


if __name__ == "__main__":
    main()
