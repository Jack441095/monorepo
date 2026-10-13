#!/usr/bin/env python3
"""Build a validation manifest from locally reviewed, hash-pinned QA documents.

Source PDFs and review values stay in the ignored corpus. This tool checks the
review record and file identity; it never supplies answers from Submit's output.
"""

import argparse
import json
from pathlib import Path

from restore_public_corpus import LICENSES, PRODUCT_DIR, digest, source_path


FIELDS = {"student_name", "student_id", "university", "module_code", "project_title"}
REVIEW_METHODS = {"independent_cover_review", "controlled_fixture_truth"}


def build_cases(documents, corpus):
    """Reject incomplete reviews or changed files before emitting any cases."""
    cases = []
    identifiers = set()
    paths = set()
    for row in documents:
        identifier = row["document_id"]
        target = source_path(row, corpus)
        if identifier in identifiers or target.resolve() in paths:
            # Repeated inputs would inflate the apparent validation coverage.
            raise ValueError("Duplicate case ID or PDF path")
        identifiers.add(identifier)
        paths.add(target.resolve())
        licence = row.get("licence_status") or row.get("licence_class")
        controlled = licence == "CONTROLLED_GENERATED_TEST_DATA"
        if (licence not in LICENSES and not controlled) or row.get("qualification_eligible") is False:
            raise ValueError("Unqualified document cannot enter the reviewed corpus")
        if digest(target) != row["sha256"]:
            # Truth belongs to these exact bytes, never to a newer replacement.
            raise ValueError("Reviewed PDF differs from recorded hash")
        mode = row.get("evaluation_mode", "accuracy")
        truth = row["truth"]
        if not isinstance(truth, dict) or set(truth) - FIELDS:
            raise ValueError("Truth must contain only supported validation fields")
        if mode == "layout_only":
            if truth:
                # Sample names in guidance cannot become submission accuracy claims.
                raise ValueError("Layout-only documents must not carry accuracy truth")
        elif mode == "accuracy":
            if row.get("review_method") not in REVIEW_METHODS or not truth:
                raise ValueError("Accuracy cases need independent review and truth")
            if controlled != (row["review_method"] == "controlled_fixture_truth"):
                raise ValueError("Controlled truth cannot qualify a public document")
            if any(not isinstance(value, str) or not value.strip() or
                   value.upper() in {"UNREVIEWED", "REVIEW"} for value in truth.values()):
                # Unknown fields should be omitted, not counted as reviewed coverage.
                raise ValueError("Accuracy truth contains an unreviewed value")
        else:
            raise ValueError("Unknown evaluation mode")
        cases.append({"id": identifier, "pdf": str(target),
                      "category": row["category"], "evaluation_mode": mode, "truth": truth})
    if not cases:
        # An empty report is not evidence that the corpus is ready.
        raise ValueError("Reviewed corpus has no cases")
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review", type=Path, help="Ignored JSON with reviewed documents")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    corpus = PRODUCT_DIR / "real_validation_corpus"
    if not args.out.resolve().is_relative_to((corpus / "manifests").resolve()):
        # Absolute paths and public bylines stay in the ignored local workspace.
        parser.error("Output must be inside real_validation_corpus/manifests")
    review = json.loads(args.review.read_text())
    cases = build_cases(review["documents"], corpus)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"corpus_id": review["corpus_id"], "cases": cases}, indent=2) + "\n")
    scored = sum(case["evaluation_mode"] == "accuracy" for case in cases)
    print(f"cases={len(cases)} accuracy={scored} layout_only={len(cases) - scored}")


if __name__ == "__main__":
    main()
