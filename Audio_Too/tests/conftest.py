import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEST_STATE_ROOT = Path(tempfile.mkdtemp(prefix="audio-too-pytest-"))

# These variables are set during conftest import, before test modules import
# KENN. This prevents chat/eval tests from writing generated sessions into the
# developer's live KENN database and JSON session file.
os.environ.setdefault("KENN_CHATS_DIR", str(TEST_STATE_ROOT / "kenn-chats"))
os.environ.setdefault("KENN_DB_PATH", str(TEST_STATE_ROOT / "kenn-chats" / "kenn.db"))
os.environ.setdefault(
    "KENN_SESSION_FILE", str(TEST_STATE_ROOT / "kenn-chats" / "session.json")
)
os.environ.setdefault("THURSDAY_PROFILE_DIR", str(TEST_STATE_ROOT / "thursday" / "profiles"))
os.environ.setdefault("THURSDAY_DATA_DIR", str(TEST_STATE_ROOT / "thursday" / "user_data"))
os.environ.setdefault("THURSDAY_ANALYTICS_DIR", str(TEST_STATE_ROOT / "thursday" / "analytics"))
os.environ.setdefault("THURSDAY_CALENDAR_DIR", str(TEST_STATE_ROOT / "thursday" / "calendar"))
os.environ.setdefault("THURSDAY_ALERTS_DIR", str(TEST_STATE_ROOT / "thursday" / "alerts"))
os.environ.setdefault("THURSDAY_SESSION_DIR", str(TEST_STATE_ROOT / "thursday" / "sessions"))
os.environ.setdefault("AUDIO_TOO_MIX_REVIEW_DATA_ROOT", str(TEST_STATE_ROOT / "mix_reviews"))

# Same ambient-leak class as the vars above, found 2026-07-27: Thursday's
# brain is gated behind THURSDAY_BRAIN_ENABLED/AUDIO_TOO_LLM_ENABLED, which
# now live in the developer's real .env for live use. studio/kenn's
# llm_rewrite.load_env() applies .env into os.environ (via plain assignment,
# not setdefault) the first time anything in the suite imports KENN, and
# from that point on every test in the process sees the real env value --
# not just the tests that explicitly opted into brain-enabled behavior.
# That silently broke deterministic-routing tests that never touch Thursday's
# brain at all (routing-quality assertions, automix status round-trips,
# followup-intent inheritance) once a real ambiguous-looking message in
# their flow got intercepted by the brain instead of the regex router they
# were actually testing. setdefault (not assignment) so any test that
# explicitly monkeypatch.setenv()s these itself is unaffected.
os.environ.setdefault("THURSDAY_BRAIN_ENABLED", "0")
os.environ.setdefault("AUDIO_TOO_LLM_ENABLED", "0")

analysis_tool_path = str(ROOT / "studio" / "audio_analysis")
if analysis_tool_path not in sys.path:
    sys.path.insert(0, analysis_tool_path)


def pytest_runtest_setup(item) -> None:
    """Undo tests/audiogen's ``main`` module hijack for tests outside that directory.

    ``studio/audiogen/audiogen/main.py`` and the repo-root ``main.py`` are both
    importable as bare ``main``. Once an audiogen test caches the former in
    ``sys.modules``, any later test doing ``import main`` expecting the real
    root entry point gets the wrong module. Evict the mismatch so it gets
    re-imported correctly.
    """
    nodeid = getattr(item, "nodeid", "") or ""
    if nodeid.startswith("tests/audiogen/"):
        return
    loaded = sys.modules.get("main")
    loaded_file = Path(getattr(loaded, "__file__", "")).resolve() if loaded else None
    real_main = (ROOT / "main.py").resolve()
    if loaded_file and loaded_file != real_main:
        sys.modules.pop("main", None)


def pytest_sessionfinish(session, exitstatus) -> None:
    shutil.rmtree(TEST_STATE_ROOT, ignore_errors=True)


@pytest.fixture(autouse=True)
def _clear_semantic_cache_between_tests():
    """Prevent one test's answer_payload()/answer_payload_stream() call from
    contaminating another test via KENN's semantic cache (session_memory.py).

    Found 2026-08-04: KENN_DB_PATH already points tests at an isolated,
    per-session temp DB (see the env vars above), so this isn't cross-run
    leakage from a developer's real database -- it's leakage *within* one
    pytest run. Any test that calls into the real chat/answer pipeline with
    a high-confidence result caches it; a later, unrelated test asking an
    embedding-similar question (0.95 cosine threshold -- easy to cross
    without meaning to) silently gets that cached answer back instead of
    exercising its own mocks/patches. Concretely broke
    test_stream_and_voice_buffer_then_reject_unsupported_generation, which
    expects `generation_validation` in the metadata but got a cached
    response from an earlier, unrelated test instead. Same class of bug as
    the "no TTL" issue in production -- just surfacing inside the test
    suite instead.
    """
    try:
        from kenn.core.session_memory import _get_db

        conn = _get_db()
        conn.execute("DELETE FROM semantic_cache")
        conn.commit()
    except Exception:
        pass
    yield
    try:
        from kenn.core.session_memory import _get_db

        conn = _get_db()
        conn.execute("DELETE FROM semantic_cache")
        conn.commit()
    except Exception:
        pass


