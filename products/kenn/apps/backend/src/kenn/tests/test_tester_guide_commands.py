"""Every change command in docs/BETA_TESTER_GUIDE.md's "Things to try" works end to end on the demo set.

Proposal → nothing written before Apply → apply → readback verified → undo → set restored exactly, through the same
gateway the app uses, on the demo backend (which, like real Live, leaves fader values out of topology reads).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

KENN_ROOT = Path(__file__).resolve().parents[5]
COMMANDS = [json.loads(line) for line in (KENN_ROOT / "tooling" / "data" / "tester_guide_commands.jsonl")
            .read_text(encoding="utf-8").splitlines() if line.strip()]
_SPEC = importlib.util.spec_from_file_location("e2e_demo_commands", KENN_ROOT / "tooling" / "scripts" / "e2e_demo_commands.py")
e2e = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(e2e)


def test_the_guide_lists_these_commands() -> None:
    guide = (KENN_ROOT / "docs" / "BETA_TESTER_GUIDE.md").read_text(encoding="utf-8")
    assert all(f"`{case['query']}`" in guide for case in COMMANDS)


@pytest.mark.parametrize("case", COMMANDS, ids=[case["query"] for case in COMMANDS])
def test_guide_command_applies_verifies_and_undoes(case, monkeypatch, tmp_path: Path) -> None:
    from kenn.core import live_receipt_journal

    monkeypatch.setattr(live_receipt_journal, "JOURNAL_PATH", tmp_path / "receipts.jsonl")
    monkeypatch.setenv("KENN_ALLOW_DAW_CONTROL", "1")
    for name in ("KENN_LIVE_LLM_ENABLED", "KENN_LLM_ENABLED", "KENN_LLM_ENABLED_COMMAND"):
        monkeypatch.delenv(name, raising=False)

    row = e2e.run_one(case["query"], 1)

    assert row["action"] == case["expected_action"]
    assert row["outcome"] == "pass", row
