"""The chat tests that need the local knowledge index skip on a clean checkout, like the backend's."""

from pathlib import Path

import pytest

# The index is local-only (see apps/backend/src/kenn/tests/conftest.py). On a fresh kenn-app clone, 5 Oct 2026, these
# eight failed with found=False because retrieval had nothing to search, which said nothing about the code.
INDEX_POINTER = Path(__file__).resolve().parents[3] / "apps" / "backend" / "src" / "kenn" / "data" / "index" / "CURRENT"
NEEDS_INDEX = {
    "test_app.py::test_specialist_keyword_stays_retrieval_only",
    "test_app.py::test_specific_reverb_setting_is_kept_visible_in_advice",
    "test_app.py::test_specific_eq_eight_insertion_keeps_ableton_track_workflow_visible",
    "test_app.py::test_specific_pink_noise_measurement_is_interpreted_as_bounded_advice",
    "test_chat_hard_case_benchmark.py::test_real_engine_hard_case_benchmark_passes_without_storing_content",
    "test_eval_chat_coverage.py::test_full_chat_coverage_receipt_passes",
    "test_eval_runner.py::test_full_evaluation_receipt_passes",
    "test_golden_knowledge_eval.py::TestGoldenKnowledgeEval::test_golden_benchmark_cases",
}


def pytest_collection_modifyitems(config, items):
    if INDEX_POINTER.exists():
        return
    marker = pytest.mark.skip(reason="requires the local KENN corpus/index, excluded from public CI")
    for item in items:
        if item.nodeid.split("tests/", 1)[-1] in NEEDS_INDEX:
            item.add_marker(marker)
