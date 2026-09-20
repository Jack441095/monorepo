"""Tests for thursday/engineering_ops.py (Thursday Ops upgrade, phase 7).

Deliberately not a code-quality judgment -- these tests confirm the
report is a faithful, real pass-through of shadow_adapters.get_git_state()
for every registered repo, never a guess, and that it counts clean/dirty/
unreachable correctly against whatever real state those repos are in
right now (not a fixed expectation, since that state changes as work
continues on this exact session).
"""

from __future__ import annotations

import thursday.ops.engineering_ops as eng
import thursday.shadow_adapters as sa
from thursday.registry.handlers import _handle_release_hygiene


def test_release_hygiene_reports_every_registered_adapter():
    out = eng.release_hygiene_check()
    for name in sa.ADAPTERS:
        assert name in out


def test_release_hygiene_totals_match_real_adapter_states():
    out = eng.release_hygiene_check()
    dirty = 0
    unknown = 0
    for adapter in sa.ADAPTERS.values():
        state = adapter.get_git_state()
        if state.get("branch") in ("UNKNOWN", "ERROR"):
            unknown += 1
        elif not state.get("clean", True):
            dirty += 1
    total = len(sa.ADAPTERS)
    assert f"{total - dirty - unknown}/{total} clean" in out
    assert f"{dirty} with uncommitted changes" in out
    assert f"{unknown} unreachable" in out


def test_release_hygiene_never_claims_a_code_review():
    out = eng.release_hygiene_check()
    assert "not a code review" in out
    assert "not a claim about what the uncommitted changes actually are" in out


def test_release_hygiene_unreachable_repo_reported_honestly(monkeypatch):
    # "real" is whatever this machine actually has: on a dev checkout
    # Audio_Too resolves (1 unreachable: ghost); on the purpose-built
    # server deploy it doesn't (2 unreachable). The test pins the honest
    # behavior (UNKNOWN named + count math), not a fixed count.
    real_state = sa.ADAPTERS["audio_too"].get_git_state()
    real_unreachable = real_state.get("branch") in ("UNKNOWN", "ERROR")
    fake_adapters = {
        "ghost": sa.ShadowAdapter("ghost", "/nonexistent/path/xyz"),
        "real": sa.ADAPTERS["audio_too"],
    }
    monkeypatch.setattr(sa, "ADAPTERS", fake_adapters)
    out = eng.release_hygiene_check()
    assert "ghost: UNKNOWN" in out
    assert f"{1 + int(real_unreachable)} unreachable" in out


def test_handler_end_to_end():
    out = _handle_release_hygiene()
    assert "RELEASE HYGIENE CHECK" in out
