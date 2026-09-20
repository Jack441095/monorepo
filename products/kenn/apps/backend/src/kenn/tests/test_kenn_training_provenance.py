"""Checks for non-secret reproducibility metadata in command-model runs."""

from __future__ import annotations

import pytest

from scripts.train_kenn_command_lora import _provenance, _select_device, _training_dtype


def test_training_provenance_contains_revision_and_runtime_without_credentials() -> None:
    provenance = _provenance()

    assert provenance["git_revision"]
    assert provenance["python"]
    assert provenance["platform"]
    assert "password" not in str(provenance).lower()
    assert "token" not in str(provenance).lower()


def test_training_device_selector_supports_explicit_cpu() -> None:
    torch = pytest.importorskip("torch", reason="optional command-model training dependency")
    assert str(_select_device(torch, "cpu")) == "cpu"


def test_training_dtype_follows_selected_accelerator() -> None:
    torch = pytest.importorskip("torch", reason="optional command-model training dependency")
    assert _training_dtype(torch, torch.device("cpu")) == torch.float32
    assert _training_dtype(torch, type("Device", (), {"type": "cuda"})()) == torch.float16
    assert _training_dtype(torch, type("Device", (), {"type": "mps"})()) == torch.float16
