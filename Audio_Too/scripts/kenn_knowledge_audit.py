#!/usr/bin/env python3
"""Audit KENN notes for structure, provenance, coverage, and training readiness."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
NOTES_DIR = ROOT / "studio" / "kenn" / "kenn" / "Training_Data_Notes"
REQUIRED_SECTIONS = ("Short answer", "Try this", "Why it matters", "Related questions")
COVERAGE_AREAS: dict[str, tuple[str, ...]] = {
    "ableton": ("ableton", "operator", "eq eight", "drum rack", "warp", "clip automation"),
    "recording": ("recording", "microphone", "preamp", "room tone", "comping"),
    "mixing": ("mixing", "mix", "eq", "compression", "reverb", "delay", "stereo", "phase"),
    "mastering": ("mastering", "loudness", "true peak", "limiter", "dither", "streaming"),
    "vocals": ("vocal", "de-ess", "sibilance", "tuning", "adlib"),
    "sound_design": ("sound design", "synthesis", "operator", "resampling", "bass", "kick", "snare"),
    "game_audio": ("wwise", "game audio", "soundbank", "rtpc", "unity", "unreal"),
    "studio_business": ("client", "pricing", "quote", "revision", "delivery", "handoff"),
    "acoustics_monitoring": ("acoustic", "monitor", "room mode", "translation", "reference track"),
    "editing_delivery": ("editing", "noise cleanup", "export", "stem", "wav", "podcast"),
}


def _field(text: str, name: str) -> str:
    match = re.search(rf"^{re.escape(name)}:\s*(.*?)\s*$", text, re.MULTILINE | re.IGNORECASE)
    return match.group(1).strip() if match else ""


_KNOWN_HEADINGS = (
    "short answer",
    "try this",
    "why it matters",
    "common mistakes",
    "when this does not apply",
    "related questions",
)


def _section(text: str, name: str) -> str:
    # Prefix match, not exact match: e.g. automix-reverb-and-delay-sends.md's
    # real "Try this" heading is "Try this -- default reverb sends by
    # instrument:", not bare "Try this:". kenn/core/chat_formatting.py's
    # section_lines() (the version this same regex was duplicated from) was
    # already loosened to a prefix match for exactly this case (2026-08-03);
    # this copy in kenn_knowledge_audit.py -- and its duplicate in
    # studio/kenn/kenn/training/note_quality.py, fixed the same way -- had
    # drifted back to the stricter exact-line pattern, so this audit was
    # flagging dozens of genuinely well-formed, already-approved notes
    # (including automix-compression-ratios.md) as missing sections they
    # actually have. Found running `python main.py knowledge-audit` 2026-08-06.
    #
    # The stop-boundary also previously matched ANY line of just
    # letters/spaces ending in a colon -- including ordinary body prose that
    # ends a sentence with a colon before a list (e.g. "...depending on the
    # client type:"), truncating the body to empty at the first such
    # sentence. Found the same day on jack-export-specs.md, a real note
    # wrongly flagged as having no Short answer despite visibly having one.
    # Restricted the stop-boundary to only the known heading names, matching
    # chat_formatting.py's section_lines(), which already enumerates them.
    headings = "|".join(re.escape(h) for h in _KNOWN_HEADINGS)
    match = re.search(
        rf"^{re.escape(name)}\b[^\n]*:\s*\n(?P<body>.*?)"
        rf"(?=^(?:{headings})\b[^\n]*:\s*(?:\n|$)|\Z)",
        text,
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    return match.group("body").strip() if match else ""


def inspect_note(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    title_match = re.search(r"^#\s+(.+?)\s*$", text, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else ""
    status = _field(text, "Status") or "Missing"
    tags = [item.strip().lower() for item in _field(text, "Tags").split(",") if item.strip()]
    errors: list[str] = []
    warnings: list[str] = []
    if not title:
        errors.append("missing H1 title")
    for field in ("Type", "Tags", "Status"):
        if not _field(text, field):
            errors.append(f"missing {field} field")
    sections = {name: _section(text, name) for name in REQUIRED_SECTIONS}
    if status.lower() == "approved":
        for name, body in sections.items():
            if not body:
                errors.append(f"approved note missing {name} section")
    related = re.findall(r"^\s*-\s+(.+?)\s*$", sections["Related questions"], re.MULTILINE)
    if status.lower() == "approved" and len(related) < 2:
        warnings.append("approved note has fewer than two related questions")
    if len(tags) < 3:
        warnings.append("fewer than three tags")
    source_values = [_field(text, key) for key in ("Source", "Source title", "Source URL", "Source ID")]
    if status.lower() == "approved" and not any(source_values):
        warnings.append("no provenance field (Source, Source title, Source URL, or Source ID)")
    if status.lower() == "approved" and not _field(text, "Reviewed"):
        warnings.append("no Reviewed date")
    searchable = f"{title} {' '.join(tags)} {text}".lower()
    areas = sorted(area for area, terms in COVERAGE_AREAS.items() if any(term in searchable for term in terms))
    if status.lower() == "approved" and not areas:
        warnings.append("not mapped to a coverage area")
    score = max(0, 100 - 25 * len(errors) - 5 * len(warnings))
    return {
        "file": path.name,
        "title": title,
        "status": status,
        "tags": tags,
        "coverage_areas": areas,
        "related_questions": related,
        "errors": errors,
        "warnings": warnings,
        "quality_score": score,
    }


def build_report(notes_dir: Path = NOTES_DIR) -> dict[str, Any]:
    notes = [inspect_note(path) for path in sorted(notes_dir.glob("*.md"))]
    approved = [note for note in notes if note["status"].lower() == "approved"]
    coverage = Counter(area for note in approved for area in note["coverage_areas"])
    question_files: dict[str, list[str]] = defaultdict(list)
    for note in approved:
        for question in note["related_questions"]:
            normalized = re.sub(r"\W+", " ", question.lower()).strip()
            question_files[normalized].append(note["file"])
    duplicates = [
        {"question": question, "files": files}
        for question, files in sorted(question_files.items())
        if len(files) > 1
    ]
    missing_areas = sorted(area for area in COVERAGE_AREAS if not coverage.get(area))
    errors = sum(len(note["errors"]) for note in notes)
    warnings = sum(len(note["warnings"]) for note in notes)
    title_questions = len(approved)
    related_questions = len(question_files)
    return {
        "schema": "kenn.knowledge_audit.v1",
        "notes_dir": str(notes_dir),
        "summary": {
            "notes": len(notes),
            "approved": len(approved),
            "draft": sum(1 for note in notes if note["status"].lower() == "draft"),
            "errors": errors,
            "warnings": warnings,
            "unique_related_questions": related_questions,
            "note_training_prompts": title_questions + related_questions,
            "duplicate_related_questions": len(duplicates),
        },
        "coverage": {area: coverage.get(area, 0) for area in COVERAGE_AREAS},
        "missing_coverage_areas": missing_areas,
        "duplicates": duplicates,
        "notes": notes,
    }


def print_report(report: dict[str, Any]) -> None:
    summary = report["summary"]
    print(
        f"KENN knowledge: {summary['approved']}/{summary['notes']} approved notes; "
        f"{summary['note_training_prompts']} note-derived prompts"
    )
    print(f"Quality: {summary['errors']} errors, {summary['warnings']} warnings")
    print("Coverage: " + ", ".join(f"{key}={value}" for key, value in report["coverage"].items()))
    if report["missing_coverage_areas"]:
        print("Missing coverage: " + ", ".join(report["missing_coverage_areas"]))
    for note in report["notes"]:
        if note["errors"]:
            print(f"ERROR {note['file']}: " + "; ".join(note["errors"]))
    print(f"Duplicate related questions: {summary['duplicate_related_questions']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit KENN knowledge-note quality and coverage.")
    parser.add_argument("--notes-dir", type=Path, default=NOTES_DIR)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--strict", action="store_true", help="Fail when structural errors are present.")
    args = parser.parse_args(argv)
    report = build_report(args.notes_dir)
    body = json.dumps(report, indent=2, ensure_ascii=False) if args.json else ""
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.json:
        print(body)
    else:
        print_report(report)
    return 1 if args.strict and report["summary"]["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
