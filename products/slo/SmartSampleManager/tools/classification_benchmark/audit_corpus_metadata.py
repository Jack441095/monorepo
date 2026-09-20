#!/usr/bin/env python3
"""Metadata-only preflight for the SLO real-corpus classification set.

This deliberately does not decode, hash, copy, or modify audio.  It reuses the
trusted folder mapping from ``build_real_corpus_v2.py`` and checks whether the
result can support grouped 17-class evidence before a corpus build or native
scan is attempted.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys
from pathlib import Path

from build_real_corpus_v2 import (
    FILENAME_KEYWORD_SPLIT_FOLDERS,
    MAPPING,
    SOURCE_ROOT,
    find_audio_files,
)
from source_family import candidate_source_family, legacy_source_family


TAXONOMY_CLASSES = (
    "Kick", "Snare", "Hi-Hat", "Clap", "Percussion", "Bass One-Shot",
    "Bass Loop", "Synth", "Synth Loop", "Vocal Phrase", "Vocal Loop",
    "Impact", "Riser", "Foley", "FX", "Atmosphere", "Music Loop",
)


def summarize_basename_collisions(paths: list[str]) -> dict:
    """Summarize duplicate basenames without reading or modifying file data."""
    paths_by_name = collections.defaultdict(set)
    for path in paths:
        normalized = os.path.realpath(path)
        paths_by_name[os.path.basename(normalized)].add(normalized)

    collisions = {
        name: sorted(file_paths)
        for name, file_paths in paths_by_name.items()
        if len(file_paths) > 1
    }
    return {
        "duplicate_basename_count": len(collisions),
        "duplicate_basename_rows": sum(len(file_paths) for file_paths in collisions.values()),
        "duplicate_basename_examples": [
            {"basename": name, "paths": file_paths}
            for name, file_paths in sorted(collisions.items())[:20]
        ],
    }


def audit(source_root: str, minimum_families: int) -> dict:
    class_counts = collections.Counter()
    vendor_counts = collections.Counter()
    families_by_class = collections.defaultdict(set)
    labels_by_family = collections.defaultdict(set)
    candidate_families_by_class = collections.defaultdict(set)
    candidate_labels_by_family = collections.defaultdict(set)
    missing_folders = []
    unmatched_split_files = []
    seen_paths = set()
    mapped_paths = []

    def add_file(path: str, subcategory: str, vendor: str, relative_folder: str) -> None:
        normalized = os.path.realpath(path)
        if normalized in seen_paths:
            return
        seen_paths.add(normalized)
        mapped_paths.append(normalized)
        family = legacy_source_family(os.path.basename(path))
        candidate_family = candidate_source_family(
            vendor, relative_folder, os.path.basename(path)
        )
        class_counts[subcategory] += 1
        vendor_counts[vendor] += 1
        families_by_class[subcategory].add(family)
        labels_by_family[family].add(subcategory)
        candidate_families_by_class[subcategory].add(candidate_family)
        candidate_labels_by_family[candidate_family].add(subcategory)

    for vendor, folders in MAPPING.items():
        for relative_folder, subcategory in folders.items():
            folder = os.path.join(source_root, vendor, relative_folder)
            if not os.path.isdir(folder):
                missing_folders.append(folder)
                continue
            for path in find_audio_files(folder):
                add_file(path, subcategory, vendor, relative_folder)

    for (vendor, relative_folder), keyword_rules in FILENAME_KEYWORD_SPLIT_FOLDERS.items():
        folder = os.path.join(source_root, vendor, relative_folder)
        if not os.path.isdir(folder):
            missing_folders.append(folder)
            continue
        for path in find_audio_files(folder):
            filename = os.path.basename(path).lower()
            subcategory = next(
                (category for keyword, category in keyword_rules if keyword in filename),
                None,
            )
            if subcategory is None:
                unmatched_split_files.append(path)
                continue
            add_file(path, subcategory, vendor, relative_folder)

    missing_classes = [name for name in TAXONOMY_CLASSES if not class_counts[name]]
    insufficient_classes = [
        (name, len(families_by_class[name]))
        for name in TAXONOMY_CLASSES
        if len(families_by_class[name]) < minimum_families
    ]
    mixed_families = sorted(
        (family, sorted(labels))
        for family, labels in labels_by_family.items()
        if len(labels) > 1
    )
    candidate_insufficient_classes = [
        (name, len(candidate_families_by_class[name]))
        for name in TAXONOMY_CLASSES
        if len(candidate_families_by_class[name]) < minimum_families
    ]
    candidate_mixed_families = sorted(
        (family, sorted(labels))
        for family, labels in candidate_labels_by_family.items()
        if len(labels) > 1
    )

    basename_collision_summary = summarize_basename_collisions(mapped_paths)

    return {
        "source_root": os.path.realpath(source_root),
        "files": sum(class_counts.values()),
        "vendors": len(vendor_counts),
        "classes": len([name for name in TAXONOMY_CLASSES if class_counts[name]]),
        "class_counts": dict(sorted(class_counts.items())),
        "vendor_counts": dict(sorted(vendor_counts.items())),
        "legacy_class_family_counts": {
            name: len(families_by_class[name]) for name in TAXONOMY_CLASSES
        },
        "candidate_class_family_counts": {
            name: len(candidate_families_by_class[name]) for name in TAXONOMY_CLASSES
        },
        "source_families": sum(len(values) for values in families_by_class.values()),
        **basename_collision_summary,
        "missing_classes": missing_classes,
        "insufficient_class_family_support": insufficient_classes,
        "mixed_source_families": mixed_families,
        "legacy_boundary": {
            "definition": "first 3 underscore-delimited filename tokens",
            "insufficient_class_family_support": insufficient_classes,
            "mixed_source_families": mixed_families,
            "status": "PASS" if not (insufficient_classes or mixed_families) else "BLOCKED",
        },
        "candidate_boundary": {
            "definition": "vendor + mapped source folder + first 5 underscore-delimited filename tokens",
            "insufficient_class_family_support": candidate_insufficient_classes,
            "mixed_source_families": candidate_mixed_families,
            "status": "PASS" if not (candidate_insufficient_classes or candidate_mixed_families) else "BLOCKED",
        },
        "missing_folders": missing_folders,
        "unmatched_split_files": len(unmatched_split_files),
        "status": "PASS" if not (
            missing_classes or insufficient_classes or mixed_families
        ) else "BLOCKED",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", default=SOURCE_ROOT)
    parser.add_argument("--minimum-families", type=int, default=5)
    args = parser.parse_args()
    result = audit(args.source_root, args.minimum_families)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
