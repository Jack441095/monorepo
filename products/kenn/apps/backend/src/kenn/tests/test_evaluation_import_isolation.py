"""Collecting offline evidence tests must leave another test's model policy alone."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


KENN_ROOT = Path(__file__).resolve().parents[5]
IMPORT_TARGETS = (
    "apps/backend/src/kenn/tests/test_evidence_budget_alignment.py",
    "apps/backend/src/kenn/tests/test_measure_capture_evidence.py",
    "apps/backend/src/kenn/tests/test_rescore_capture_evidence.py",
    "tooling/scripts/rescore_captured_answers.py",
)


@pytest.mark.parametrize("relative_path", IMPORT_TARGETS)
@pytest.mark.parametrize("enabled", [None, "1"])
def test_evidence_import_preserves_the_callers_llm_switch(relative_path, enabled) -> None:
    # Collection once disabled the command-repair test before its fixture could run.
    env = os.environ.copy()
    env.pop("KENN_LLM_ENABLED", None)
    if enabled is not None:
        env["KENN_LLM_ENABLED"] = enabled
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json, os, runpy, sys; runpy.run_path(sys.argv[1]); "
            "print(json.dumps(os.environ.get('KENN_LLM_ENABLED')))",
            str(KENN_ROOT / relative_path),
        ],
        cwd=KENN_ROOT / "apps/backend/src",
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert json.loads(completed.stdout.splitlines()[-1]) == enabled
