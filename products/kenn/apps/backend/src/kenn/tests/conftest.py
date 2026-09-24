"""Pytest configuration for apps/backend/src/kenn/tests to ensure source is in sys.path."""

import os
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


@pytest.fixture(scope="session", autouse=True)
def isolate_live_shadow_evidence(tmp_path_factory: pytest.TempPathFactory):
    """Never let model-shadow tests count as real promotion evidence.

    Some command tests intentionally cap a requested active mode back to
    shadow.  That exercises the production recorder, so an unisolated suite
    used to append synthetic commands to ``kenn/data/live_llm_shadow.jsonl``.
    Point both this process and any spawned test server at a session-scoped
    temporary log, then restore the caller's environment on teardown.
    """
    from kenn.core import live_shadow_log

    path = tmp_path_factory.mktemp("kenn-shadow-evidence") / "live_llm_shadow.jsonl"
    old_path = live_shadow_log.SHADOW_LOG_PATH
    old_env = os.environ.get("KENN_LIVE_LLM_SHADOW_LOG")
    os.environ["KENN_LIVE_LLM_SHADOW_LOG"] = str(path)
    # Audio analyses in tests stay out of the real on-disk analysis cache too.
    old_cache = os.environ.get("KENN_ANALYSIS_CACHE_DIR")
    os.environ["KENN_ANALYSIS_CACHE_DIR"] = str(tmp_path_factory.mktemp("kenn-analysis-cache"))
    live_shadow_log.SHADOW_LOG_PATH = path
    try:
        yield
    finally:
        live_shadow_log.SHADOW_LOG_PATH = old_path
        if old_env is None:
            os.environ.pop("KENN_LIVE_LLM_SHADOW_LOG", None)
        else:
            os.environ["KENN_LIVE_LLM_SHADOW_LOG"] = old_env
        if old_cache is None:
            os.environ.pop("KENN_ANALYSIS_CACHE_DIR", None)
        else:
            os.environ["KENN_ANALYSIS_CACHE_DIR"] = old_cache


def pytest_collection_modifyitems(config, items):
    if INDEX_POINTER.exists():
        return
    reason = "requires the local KENN corpus/index, excluded from public CI"
    marker = pytest.mark.skip(reason=reason)
    for item in items:
        if Path(str(item.fspath)).name in LOCAL_INDEX_TEST_MODULES:
            item.add_marker(marker)
