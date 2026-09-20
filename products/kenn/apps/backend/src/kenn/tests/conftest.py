"""Pytest configuration for apps/backend/src/kenn/tests to ensure source is in sys.path."""

import sys
from pathlib import Path

import pytest

SOURCE_DIR = Path(__file__).resolve().parents[2]
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))


# The reviewed knowledge corpus, generated retrieval index, and qualification
# receipts are intentionally local-only. Keep those integration tests active
# on developer machines, but skip them in a clean public checkout where the
# inputs are not present. Core routing, SLO, API-contract, and unit tests still
# run normally in public CI.
INDEX_POINTER = SOURCE_DIR / "kenn" / "data" / "index" / "CURRENT"
LOCAL_INDEX_TEST_MODULES = {
    "test_chat_ableton_chain_selector_routing.py",
    "test_chat_max_for_live_routing.py",
    "test_fastapi_routes.py",
    "test_human_review_packet_provenance.py",
    "test_internal_beta_gate.py",
    "test_kenn_command_training.py",
    "test_session_grounded_advice_evaluation.py",
    "test_start_server_script.py",
    "test_support_diagnostics.py",
}


def pytest_collection_modifyitems(config, items):
    if INDEX_POINTER.exists():
        return
    reason = "requires the local KENN corpus/index, excluded from public CI"
    marker = pytest.mark.skip(reason=reason)
    for item in items:
        if Path(str(item.fspath)).name in LOCAL_INDEX_TEST_MODULES:
            item.add_marker(marker)
