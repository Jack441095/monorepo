from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[5] / "tooling" / "scripts" / "kenn_mcp_server.py"
SPEC = importlib.util.spec_from_file_location("kenn_mcp_server", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


def test_planner_is_disabled_by_default() -> None:
    assert server.planner_identity({}) == ("disabled", "disabled")


def test_planner_provider_is_explicitly_preserved() -> None:
    assert server.planner_identity({
        "KENN_DELIBERATIVE_MODEL": "Qwen3-4B-input-bound-v6",
        "KENN_DELIBERATIVE_PROVIDER": "transformers",
    }) == ("Qwen3-4B-input-bound-v6", "transformers")


def test_unknown_planner_provider_fails_closed() -> None:
    with pytest.raises(ValueError, match="PROVIDER"):
        server.planner_identity({
            "KENN_DELIBERATIVE_MODEL": "model",
            "KENN_DELIBERATIVE_PROVIDER": "remote-mystery",
        })
