"""Checks for the pre-training command corpus audit."""

from __future__ import annotations

from scripts.audit_kenn_command_corpus import audit_rows
from scripts.build_kenn_command_corpus import build_rows


def test_audit_reports_synthetic_size_and_mechanical_expansion() -> None:
    report = audit_rows(build_rows(variants=64, scenarios=2))

    assert report["status"] == "review_required"
    # The seed corpus currently contains 48 reviewed records; two scenarios
    # with 64 variants therefore produce 6,144 audited rows.
    assert report["records"] == 6144
    assert report["unique_labels"] == 73
    assert report["mechanical_variant_rows"] > 0
    assert report["holdout_protection"] == "passed"
    assert report["validation_errors"] == []
    assert report["parser_contract"]["eligible"] > 0
