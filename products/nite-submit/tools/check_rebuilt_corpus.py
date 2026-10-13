#!/usr/bin/env python3
"""Verify the rebuilt local corpus against a supplied Submit CLI."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

from build_reviewed_corpus import FIELDS, build_cases
from restore_public_corpus import PRODUCT_DIR


PROFILES = (
    ("rebuilt_public", "review_rebuilt_public_v1.json", 35,
     {"student_name": 7, "project_title": 9, "university": 9}),
    ("field_policy_rebuilt", "review_rebuilt_field_policy_v1.json", 12,
     {"student_id": 12, "module_code": 10}),
)


def qualification_record(row):
    """Fingerprint a reviewed input without copying its values or source URL."""
    truth = json.dumps(row["truth"], sort_keys=True, separators=(",", ":")).encode()
    return {"id": row["document_id"], "pdf": row["local_filename"],
            "sha256": row["sha256"], "evaluation_mode": row.get("evaluation_mode", "accuracy"),
            "reviewed_fields": sorted(row["truth"]),
            "truth_sha256": hashlib.sha256(truth).hexdigest()}


def check_qualification(review, expected):
    """Reject replacement cases or edited truth even if counts still agree."""
    actual = [qualification_record(row) for row in review["documents"]]
    if review["corpus_id"] != expected["corpus_id"] or actual != expected["documents"]:
        # Requalification is an explicit reviewed migration, never directory discovery.
        raise ValueError("Approved rebuilt inputs or review fingerprints changed")


def qualified_profiles(corpus):
    """Load the fixed public/controlled profiles and verify their exact bytes."""
    pinned = json.loads((PRODUCT_DIR / "tools/Fixtures/rebuilt_qualification_v1.json").read_text())
    expected = {profile["profile"]: profile for profile in pinned["profiles"]}
    profiles = []
    for name, review_name, count, coverage in PROFILES:
        review = json.loads((corpus / "manifests" / review_name).read_text())
        check_qualification(review, expected[name])
        cases = build_cases(review["documents"], corpus)
        check_coverage(cases, count, coverage)
        profiles.append((name, review["corpus_id"], cases, coverage))
    return profiles


def check_coverage(cases, count, coverage):
    """Reject lost cases or reduced review coverage before running Submit."""
    actual = Counter(field for case in cases for field in case["truth"])
    if len(cases) != count or dict(actual) != coverage:
        # Layout PDFs count as extraction inputs, never as reviewed field values.
        raise ValueError("Rebuilt corpus case count or reviewed coverage changed")


def check_report(report, cases):
    """Require every input and every independently reviewed value to pass."""
    if report["processed"] != len(cases):
        raise ValueError("Submit did not process every rebuilt corpus input")
    for key in ("failed_missing_files", "encrypted_or_unreadable", "wrong_high_confidence_total"):
        if report[key] != 0:
            raise ValueError(f"Rebuilt corpus report failed: {key}")
    failed_fields = []
    for field in sorted(FIELDS):
        values = [case["truth"][field] for case in cases if field in case["truth"]]
        absent = sum(value == "ABSENT" for value in values)
        metrics = report["fields"][field]
        expected = {"true_positives": len(values) - absent,
                    "absent_correctly_ignored": absent,
                    "false_positives": 0, "false_negatives": 0}
        if any(int(metrics[key]) != value for key, value in expected.items()):
            # Exit status alone does not certify extraction accuracy.
            failed_fields.append(field)
    if failed_fields:
        raise ValueError(f"Rebuilt corpus field checks failed: {', '.join(failed_fields)}")


def run_validation(cli, manifest, report_path):
    """Read only a new report from a successfully completed CLI invocation."""
    report_path.unlink(missing_ok=True)
    subprocess.run([str(cli), "validate", "--manifest", str(manifest),
                    "--out", str(report_path)], cwd=PRODUCT_DIR, check=True)
    return json.loads(report_path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", type=Path, required=True)
    args = parser.parse_args()
    cli = args.cli.resolve(strict=True)
    corpus = PRODUCT_DIR / "real_validation_corpus"
    manifests = corpus / "manifests"
    failed = False
    for name, corpus_id, cases, coverage in qualified_profiles(corpus):
        manifest = manifests / f"{name}_manifest_v1.json"
        manifest.write_text(json.dumps({"corpus_id": corpus_id, "cases": cases}, indent=2) + "\n")
        report_path = manifests / f"{name}_results_v1.json"
        report = run_validation(cli, manifest, report_path)
        try:
            if report["corpus_id"] != corpus_id:
                raise ValueError("CLI report belongs to another corpus")
            check_report(report, cases)
        except ValueError as error:
            # Finish the independent field-policy suite even if public OCR fails.
            failed = True
            print(f"{name}: FAILED: {error}", flush=True)
        else:
            print(f"{name}: {len(cases)} inputs passed; reviewed fields={sum(coverage.values())}", flush=True)
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
