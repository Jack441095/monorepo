"""Tests for thursday/shadow_adapters.py -- read-only git-state inspection
across the NITE DSP monorepo's sibling repos.

Found 2026-09-02 while building the Engineering release-hygiene check:
this module's paths were still hardcoded to a pre-NITE_DSP directory
layout (Audio_Engineering_Company/SmartSampleManager/SLO_V5C/KENN/
NiteSubmit) that no longer exists at all -- get_git_state() silently
returned "UNKNOWN" for every registered adapter, always, because
os.path.exists() failed for all of them. Fixed alongside these tests.
"""

from __future__ import annotations

import os
import subprocess

import pytest

import thursday.shadow_adapters as sa

# The two live-checkout tests below assert dev-machine reality (full
# monorepo with Audio_Too). On the purpose-built server deploy
# (THURSDAY_DEPLOY_PROFILE=server), which intentionally ships only the
# business corpus, they skip honestly instead of faking a 12G checkout.
_server_deploy = pytest.mark.skipif(
    os.environ.get("THURSDAY_DEPLOY_PROFILE") == "server",
    reason="needs full monorepo checkout with Audio_Too (dev machine only)",
)


def test_nite_dsp_root_uses_env_var_override(monkeypatch):
    monkeypatch.setenv("NITE_DSP_ROOT", "/tmp/fake-nite-dsp")
    assert sa._nite_dsp_root() == "/tmp/fake-nite-dsp"


def test_nite_dsp_root_search_finds_real_directory_containing_audio_too_and_products(monkeypatch, tmp_path):
    monkeypatch.delenv("NITE_DSP_ROOT", raising=False)
    fake_root = tmp_path / "nite_dsp_root"
    (fake_root / "Audio_Too").mkdir(parents=True)
    (fake_root / "products").mkdir()
    fake_thursday_dir = fake_root / "Audio_Too" / "thursday"
    fake_thursday_dir.mkdir()
    fake_module = fake_thursday_dir / "shadow_adapters.py"
    fake_module.write_text("x = 1\n")

    monkeypatch.setattr(sa, "__file__", str(fake_module))
    assert sa._nite_dsp_root() == str(fake_root)


def test_adapters_registered_for_all_real_current_products():
    assert set(sa.ADAPTERS) == {
        "nite_submit", "slo", "kenn", "audio_too",
        "thursday_extraction", "platform_support", "layer_alignment",
    }
    for adapter in sa.ADAPTERS.values():
        assert adapter.read_only is True
        assert adapter.forbidden_writes == ["*"]


@_server_deploy
def test_registered_adapter_paths_actually_exist_on_this_machine():
    # A live, non-mocked check: confirms the fix, not just the logic.
    # If this ever fails, either a product moved or the search broke.
    for name, adapter in sa.ADAPTERS.items():
        assert sa.os.path.isdir(adapter.workspace_path), f"{name}: {adapter.workspace_path} does not exist"


@_server_deploy
def test_get_git_state_on_real_audio_too_returns_real_fields():
    state = sa.ADAPTERS["audio_too"].get_git_state()
    assert state["head_sha"] != "UNKNOWN"
    assert state["head_sha"] != "ERROR"
    assert len(state["head_sha"]) == 40
    assert isinstance(state["clean"], bool)


def test_get_git_state_on_nonexistent_path_reports_unknown_not_a_crash():
    adapter = sa.ShadowAdapter("ghost", "/nonexistent/path/does/not/exist")
    assert adapter.get_git_state() == {"head_sha": "UNKNOWN", "clean": True, "branch": "UNKNOWN"}
