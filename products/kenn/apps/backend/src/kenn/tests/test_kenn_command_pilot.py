"""Checks for the safe command-model pilot orchestrator."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.run_kenn_command_pilot import _model_contract_gate, run_pilot


def test_model_contract_gate_fails_closed_after_training() -> None:
    passed = _model_contract_gate({
        "counts": {
            "total": 3,
            "accepted_schema": 3,
            "comparison_match": 3,
            "deterministic_contract_failures": 0,
        }
    })
    assert passed["model_contract_passed"] is True
    assert passed["live_activation_allowed"] is False

    failed = _model_contract_gate({
        "adapter_result": {
            "counts": {
                "total": 3,
                "accepted_schema": 1,
                "comparison_match": 1,
                "deterministic_contract_failures": 0,
            }
        }
    })
    assert failed["model_contract_passed"] is False
    assert failed["live_activation_allowed"] is False
    assert len(failed["blockers"]) == 2


def test_pilot_default_is_preflight_only_and_preserves_artifacts(tmp_path: Path) -> None:
    result = run_pilot(
        workdir=tmp_path / "pilot",
        variants=2,
        scenarios=2,
        base_model="Qwen/Qwen2.5-1.5B-Instruct",
        epochs=1,
        batch_size=1,
        max_length=2048,
        learning_rate=2e-4,
        seed=42,
        device="cpu",
        allow_download=False,
        run_training=False,
    )

    assert result["status"] in {"preflight_ready", "preflight_blocked"}
    assert result["training_run"] is False
    # The seed corpus currently contains 48 reviewed records; two scenarios
    # with two variants therefore produce 192 preflight rows.
    assert result["records"] == 192
    assert (tmp_path / "pilot" / "corpus.jsonl").is_file()
    assert (tmp_path / "pilot" / "corpus-audit.json").is_file()
    assert (tmp_path / "pilot" / "dry-run.json").is_file()
    assert not (tmp_path / "pilot" / "adapter").exists()
    dry_run = json.loads((tmp_path / "pilot" / "dry-run.json").read_text())
    assert dry_run["status"] == ("ready" if result["status"] == "preflight_ready" else "blocked")
    if result["status"] == "preflight_blocked":
        assert "unavailable" in (dry_run["base_model_status"] + dry_run["device_status"]).lower()


def test_pilot_refuses_to_overwrite_existing_artifacts(tmp_path: Path) -> None:
    workdir = tmp_path / "pilot"
    workdir.mkdir()
    (workdir / "corpus.jsonl").write_text("sentinel\n")

    try:
        run_pilot(
            workdir=workdir,
            variants=1,
            scenarios=1,
            base_model="Qwen/Qwen2.5-1.5B-Instruct",
            epochs=1,
            batch_size=1,
            max_length=2048,
            learning_rate=2e-4,
            seed=42,
            device="cpu",
            allow_download=False,
            run_training=False,
        )
    except FileExistsError:
        pass
    else:
        raise AssertionError("pilot must refuse to overwrite an existing corpus")
