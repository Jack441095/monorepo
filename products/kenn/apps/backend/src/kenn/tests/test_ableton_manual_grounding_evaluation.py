from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[5] / "tooling" / "scripts" / "evaluate_ableton_manual_grounding.py"
module = importlib.util.module_from_spec(
    spec := importlib.util.spec_from_file_location("manual_grounding_evaluation", SCRIPT)
)
assert spec.loader
spec.loader.exec_module(module)


def test_manual_grounding_passes_only_for_official_manual_selection() -> None:
    manual = {"source": "live12-manual-en.pdf", "evidence_class": "official_ableton_manual"}
    note = {"source": "workflow.md", "evidence_class": "curated_kenn_note"}

    report = module.evaluate_cases(
        module.REFERENCE_CASES,
        search_fn=lambda _query: [(5.0, manual), (4.0, note)],
        display_fn=lambda _query, results: results[:1],
    )

    assert report["all_cases_passed"] is True
    assert report["passed_case_count"] == len(module.REFERENCE_CASES)
    assert report["coverage"]["category_count"] == 9
    assert all(item["all_cases_passed"] for item in report["coverage"]["categories"].values())
    assert all(row["selected_evidence_class"] == "official_ableton_manual" for row in report["rows"])


def test_manual_grounding_reports_selection_failure() -> None:
    note = {"source": "workflow.md", "evidence_class": "curated_kenn_note"}

    report = module.evaluate_cases(
        module.REFERENCE_CASES,
        search_fn=lambda _query: [(5.0, note)],
        display_fn=lambda _query, results: results[:1],
    )

    assert report["all_cases_passed"] is False
    assert report["passed_case_count"] == 0
    assert all(item["all_cases_passed"] is False for item in report["coverage"]["categories"].values())
