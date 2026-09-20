#!/usr/bin/env python3
"""Read-only inventory of real-world sound hints in filenames.

Filename matches are discovery hints only. This tool never treats a match as a
label, never decodes audio, and never changes the classifier or source tree.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


AUDIO_EXTENSIONS = {".wav", ".aif", ".aiff", ".flac", ".mp3", ".ogg", ".m4a"}

# Deliberately conservative tokens. Broad words such as "hit" and "noise" are
# excluded because they have too many music-sample meanings to be useful hints.
HINTS = {
    "animal": (
        "animal", "bird", "birds", "dog", "bark", "cat", "meow", "horse",
        "neigh", "cow", "moo", "goat", "sheep", "pig", "insect", "bee",
        "cricket", "frog", "owl", "rooster", "crow", "wildlife", "whale",
        "dolphin",
    ),
    "environment": (
        "rain", "rainfall", "thunder", "storm", "wind", "water", "river",
        "ocean", "sea", "wave", "fire", "flame", "forest", "jungle",
        "nature", "leaves", "leaf", "birds", "ambience", "ambient",
    ),
    "human": (
        "voice", "speech", "laugh", "laughter", "cough", "sneeze", "breath",
        "footstep", "footsteps", "whisper", "shout", "cry",
    ),
    "mechanical": (
        "engine", "motor", "car", "vehicle", "train", "machine", "gear",
        "clock", "robot", "mechanical", "door", "drawer",
    ),
    "material": (
        "metal", "metallic", "glass", "wood", "wooden", "paper", "stone",
        "bubble", "rubber", "plastic", "ceramic", "coin", "chain",
    ),
}


def _token_pattern(token: str) -> re.Pattern[str]:
    return re.compile(r"(?<![a-z0-9])" + re.escape(token) + r"(?![a-z0-9])")


PATTERNS = {
    domain: [(token, _token_pattern(token)) for token in tokens]
    for domain, tokens in HINTS.items()
}


def scan(root: Path, example_limit: int = 20) -> dict:
    counts: Counter[str] = Counter()
    token_counts: Counter[str] = Counter()
    examples: dict[str, list[str]] = defaultdict(list)
    matched_paths: dict[str, set[str]] = defaultdict(set)
    audio_files = 0

    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        audio_files += 1
        haystack = str(path.relative_to(root)).lower()
        for domain, patterns in PATTERNS.items():
            domain_tokens = []
            for token, pattern in patterns:
                if pattern.search(haystack):
                    domain_tokens.append(token)
                    token_counts[f"{domain}:{token}"] += 1
            if domain_tokens:
                rel = str(path.relative_to(root))
                matched_paths[domain].add(rel)
                counts[domain] += 1
                if len(examples[domain]) < example_limit:
                    examples[domain].append(rel)

    return {
        "record_type": "slo_real_world_filename_hint_audit",
        "schema_version": "1.0.0",
        "safety": {
            "read_only": True,
            "audio_decoded": False,
            "labels_created": False,
            "production_taxonomy_changed": False,
            "rename_plan_applied": False,
            "interpretation": "filename_hint_only; every match requires audio and human validation",
        },
        "source_root": str(root.resolve()),
        "audio_files_scanned_by_metadata": audio_files,
        "domain_summary": {
            domain: {
                "matched_files": counts[domain],
                "fraction_of_audio_files": (counts[domain] / audio_files if audio_files else 0.0),
                "examples": examples[domain],
            }
            for domain in sorted(HINTS)
        },
        "token_counts": dict(sorted(token_counts.items())),
        "next_gate": "sample matched files for human-by-ear labels before any taxonomy activation",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not args.root.is_dir():
        raise SystemExit(f"source root does not exist: {args.root}")
    report = scan(args.root)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["domain_summary"], indent=2))


if __name__ == "__main__":
    main()
