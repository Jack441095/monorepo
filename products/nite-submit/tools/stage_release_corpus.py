#!/usr/bin/env python3
"""Stage only hash-verified rebuilt QA records, never discovered directory PDFs."""

import argparse
from pathlib import Path

from check_rebuilt_corpus import qualified_profiles
from restore_public_corpus import PRODUCT_DIR


def select_cases(profiles, selection):
    """Select by recorded source location; outputs and intake cannot qualify."""
    cases = [case for _, _, rows, _ in profiles for case in rows]
    if selection == "all":
        return cases
    roots = {"submissions": {"dissertations", "project_reports"},
             "guidance": {"university_templates"}}[selection]
    corpus = PRODUCT_DIR / "real_validation_corpus"
    return [case for case in cases if Path(case["pdf"]).relative_to(corpus).parts[0] in roots]


def stage_cases(cases, destination):
    """Create symlinks in an empty disposable folder after checking all names."""
    names = [Path(case["pdf"]).name for case in cases]
    if not cases or len(set(names)) != len(names):
        # Flattening two source paths onto one name would silently lose coverage.
        raise ValueError("Staging requires nonempty inputs with unique filenames")
    if destination.is_symlink() or (destination.exists() and any(destination.iterdir())):
        # Never reuse yesterday's output or modify an existing source directory.
        raise ValueError("Staging destination must be an empty nonsymlink directory")
    destination.mkdir(parents=True, exist_ok=True)
    for case, name in zip(cases, names):
        (destination / name).symlink_to(Path(case["pdf"]).resolve(strict=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--selection", choices=("all", "submissions", "guidance"), default="all")
    args = parser.parse_args()
    corpus = PRODUCT_DIR / "real_validation_corpus"
    if args.destination.resolve().is_relative_to(corpus.resolve()):
        parser.error("Release staging must be outside the corpus")
    cases = select_cases(qualified_profiles(corpus), args.selection)
    stage_cases(cases, args.destination)
    print(f"qualified_inputs={len(cases)} selection={args.selection}")


if __name__ == "__main__":
    main()
