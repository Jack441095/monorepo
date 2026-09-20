"""Pytest configuration: ensure repo root is on sys.path when tests are collected."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_ROOT = REPO_ROOT / "studio" / "audiogen" / "audiogen"
root_str = str(_ROOT)
sys.path[:] = [entry for entry in sys.path if entry != root_str]
sys.path.insert(0, root_str)

for mod_name in ("training", "core", "composition"):
    loaded = sys.modules.get(mod_name)
    loaded_file = Path(getattr(loaded, "__file__", "") or "").resolve() if loaded else None
    if loaded and (not loaded_file or not str(loaded_file).startswith(root_str)):
        sys.modules.pop(mod_name, None)

# Realtime / audio-thread tests: run in a fresh interpreter to avoid numba/sounddevice
# teardown races and segfaults when mixed with composition tests in one process.
_ISOLATED_SUBSTRINGS = (
    "test_realtime_smoke",
    "test_player_runtime",
    "test_rt_performance_health",
    "test_system_performance_benchmark",
    "test_chorus_kick_sidechain",
    "test_sample_loader_dc",
)


def pytest_sessionstart(session):
    """Production defaults favor quality mode; tests reset to balanced for speed/CI."""
    from audiogen_core.config import CONFIG

    CONFIG.set_performance_mode("balanced")


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Keep local ``import main`` pointed at LLM_AudioGen/main.py for subproject tests."""
    nodeid = getattr(item, "nodeid", "") or ""
    if not nodeid.startswith("tests/audiogen/"):
        return
    root_str = str(_ROOT)
    sys.path[:] = [entry for entry in sys.path if entry != root_str]
    sys.path.insert(0, root_str)
    loaded = sys.modules.get("main")
    loaded_file = Path(getattr(loaded, "__file__", "")).resolve() if loaded else None
    local_main = (_ROOT / "main.py").resolve()
    if loaded_file and loaded_file != local_main:
        sys.modules.pop("main", None)


def pytest_collection_modifyitems(config, items):
    # Heavy / IO / realtime — run via `pytest -m slow` or full suite; default CI uses `-m "not slow"`.
    slow_substrings = _ISOLATED_SUBSTRINGS
    for item in items:
        nodeid = getattr(item, "nodeid", str(item)) or ""
        if any(s in nodeid for s in slow_substrings):
            item.add_marker(pytest.mark.slow)
            item.add_marker(pytest.mark.isolated)


def _isolation_disabled() -> bool:
    return bool(os.environ.get("AUDIOGEN_TEST_SUBPROCESS")) or bool(
        os.environ.get("AUDIOGEN_TEST_NO_ISOLATE")
    )


def _run_isolated_subprocess(item: pytest.Item) -> None:
    """Execute a single marked test in a child process (same repo, no re-isolation)."""
    env = os.environ.copy()
    env["AUDIOGEN_TEST_SUBPROCESS"] = "1"
    nodeid = str(item.nodeid)
    if any(
        name in nodeid
        for name in ("test_realtime_smoke.py", "test_rt_performance_health.py")
    ):
        # CI validates the realtime scheduler without opening CoreAudio. Hardware
        # device lifecycle is covered by the separate manual/native acceptance run.
        env["AUDIOGEN_HEADLESS"] = "1"
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        nodeid,
        "-q",
        "--tb=short",
        "-o",
        "addopts=",
    ]
    # Forward -m / -k from parent when present so selective runs still work in the child.
    try:
        markexpr = str(getattr(item.config.option, "markexpr", "") or "").strip()
        if markexpr:
            cmd.extend(["-m", markexpr])
        keyword = str(getattr(item.config.option, "keyword", "") or "").strip()
        if keyword:
            cmd.extend(["-k", keyword])
    except Exception:
        pass

    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.stdout:
        sys.stdout.write(proc.stdout)
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        raise pytest.fail(
            f"isolated subprocess failed for {item.nodeid} (exit {proc.returncode})",
            pytrace=False,
        )


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_protocol(item: pytest.Item, nextitem):
    """Run ``isolated`` tests in a subprocess; all other tests use the default protocol."""
    if _isolation_disabled():
        return None
    if item.get_closest_marker("isolated") is None:
        return None
    _run_isolated_subprocess(item)
    return True
