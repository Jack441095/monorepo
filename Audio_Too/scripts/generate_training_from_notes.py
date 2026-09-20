#!/usr/bin/env python3
"""Generate LoRA training pairs from the 'Related questions' sections in KENN notes.

Reads every approved note, extracts each Related question, asks KENN's retrieval
pipeline (no LLM), and records question + context + answer as a training pair.
Skips questions already present in the output file.

Usage:
    python scripts/generate_training_from_notes.py
    python scripts/generate_training_from_notes.py --dry-run       # count only, no writes
    python scripts/generate_training_from_notes.py --limit 50      # first N questions
    python scripts/generate_training_from_notes.py --min-conf medium  # skip low-conf answers
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KENN_DIR = ROOT / "studio" / "kenn" / "kenn"
NOTES_DIR = KENN_DIR / "Training_Data_Notes"
OUT_PATH = KENN_DIR / "artifacts" / "training" / "kenn_session_training.jsonl"

for p in (ROOT / "studio" / "kenn", ROOT):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)

# Load .env
_env = ROOT / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())


def _extract_related_questions(path: Path) -> list[str]:
    """Return all questions listed under 'Related questions:' in a note."""
    questions: list[str] = []
    in_section = False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.lower() == "related questions:":
            in_section = True
            continue
        if in_section:
            if stripped.startswith("- "):
                q = stripped[2:].strip()
                if q:
                    questions.append(q)
            elif stripped and not stripped.startswith("-"):
                in_section = False
    return questions


def _load_existing(path: Path) -> set[str]:
    """Return normalised questions already in the output file."""
    if not path.exists():
        return set()
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            seen.add(json.loads(line)["question"].lower().strip())
        except Exception:
            pass
    return seen


def _context_from_sources(sources: list[dict]) -> str:
    parts: list[str] = []
    for src in sources[:5]:
        title = src.get("title", src.get("label", ""))
        text = src.get("text", "")
        if title and text:
            parts.append(f"# {title}\n{text.strip()}")
    return "\n\n".join(parts)


CONF_ORDER = {"low": 0, "medium": 1, "high": 2}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate training pairs from note Related questions")
    parser.add_argument("--dry-run", action="store_true", help="Count pairs without writing")
    parser.add_argument("--limit", type=int, default=0, help="Max questions to process (0 = all)")
    parser.add_argument("--min-conf", choices=["low", "medium", "high"], default="low", help="Skip answers below this confidence")
    parser.add_argument("--output", type=Path, default=OUT_PATH, help="Output JSONL path")
    args = parser.parse_args(argv)

    from kenn.core.chat import answer_payload, warm_index

    warm_index()

    # Collect all questions from notes
    all_pairs: list[tuple[str, str]] = []  # (note_stem, question)
    for note in sorted(NOTES_DIR.glob("*.md")):
        content = note.read_text(encoding="utf-8")
        # Skip unapproved drafts
        if "status: approved" not in content.lower():
            continue
        for q in _extract_related_questions(note):
            all_pairs.append((note.stem, q))

    existing = _load_existing(args.output)
    new_pairs = [(stem, q) for stem, q in all_pairs if q.lower().strip() not in existing]

    print("\nKENN training generator")
    print(f"  Notes scanned:       {len(set(s for s, _ in all_pairs))}")
    print(f"  Total related Qs:    {len(all_pairs)}")
    print(f"  Already in output:   {len(existing)}")
    print(f"  New to generate:     {len(new_pairs)}")

    if args.limit:
        new_pairs = new_pairs[: args.limit]
        print(f"  Capped at:           {args.limit}")

    if args.dry_run:
        print("\n  [dry-run] No files written.\n")
        for stem, q in new_pairs[:20]:
            print(f"  {stem}: {q[:70]}")
        if len(new_pairs) > 20:
            print(f"  ... and {len(new_pairs) - 20} more")
        return 0

    print()

    min_conf_level = CONF_ORDER[args.min_conf]
    written = skipped_conf = skipped_no_source = 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("a", encoding="utf-8") as fh:
        for i, (stem, question) in enumerate(new_pairs, 1):
            try:
                payload = answer_payload(question, limit=6, allow_llm=False)
            except Exception as e:
                print(f"  [{i}/{len(new_pairs)}] ERROR: {e}")
                continue

            conf = str(payload.get("confidence", "low")).lower()
            sources = payload.get("sources", [])

            if not sources:
                skipped_no_source += 1
                print(f"  [{i}/{len(new_pairs)}] skip (no sources)  {question[:60]}")
                continue

            if CONF_ORDER.get(conf, 0) < min_conf_level:
                skipped_conf += 1
                print(f"  [{i}/{len(new_pairs)}] skip ({conf})  {question[:60]}")
                continue

            record = {
                "question": question,
                "context": _context_from_sources(sources),
                "answer": payload.get("answer", ""),
                "route": payload.get("route", ""),
                "confidence": conf,
                "source_note": stem,
            }
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            fh.flush()
            written += 1
            print(f"  [{i}/{len(new_pairs)}] ✓ [{conf}] {question[:65]}")

            time.sleep(0.05)  # avoid hammering index

    total_now = len(existing) + written
    print("\nDone.")
    print(f"  Written:      {written}")
    print(f"  Skipped (no source): {skipped_no_source}")
    print(f"  Skipped (conf):      {skipped_conf}")
    print(f"  Total pairs now:     {total_now}")
    if total_now >= 500:
        print("\n  ✅ 500+ pairs — LoRA training data target reached!")
    else:
        print(f"\n  {500 - total_now} more needed to reach 500.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
