"""Tests for thursday/infrastructure_ops.py (Thursday Ops upgrade, phase
8). Uses curl via subprocess rather than urllib -- this environment's
Python lacks a working local CA bundle (confirmed against google.com,
not just the target site). Most tests mock subprocess.run for
determinism; one real live check against the actual production site is
included and verified honestly (it can legitimately fail if the site is
ever actually down, which is correct behavior, not a test bug).
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import thursday.ops.infrastructure_ops as infra


def _fake_completed(stdout="200", returncode=0, stderr=""):
    return MagicMock(stdout=stdout, returncode=returncode, stderr=stderr)


def test_check_url_reports_reachable_on_200():
    with patch("subprocess.run", return_value=_fake_completed("200")):
        result = infra.check_url("https://example.com")
    assert result == {"reachable": True, "status_code": 200, "error": None}


def test_check_url_reports_reachable_non_2xx():
    with patch("subprocess.run", return_value=_fake_completed("503")):
        result = infra.check_url("https://example.com")
    assert result["reachable"] is True
    assert result["status_code"] == 503


def test_check_url_reports_unreachable_on_curl_failure():
    with patch("subprocess.run", return_value=_fake_completed("000", returncode=6, stderr="Could not resolve host")):
        result = infra.check_url("https://example.com")
    assert result["reachable"] is False
    assert "Could not resolve host" in result["error"]


def test_check_url_reports_unreachable_on_timeout():
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="curl", timeout=5)):
        result = infra.check_url("https://example.com")
    assert result["reachable"] is False
    assert "timed out" in result["error"]


def test_check_url_never_raises_on_unexpected_output():
    with patch("subprocess.run", return_value=_fake_completed("not-a-status-code")):
        result = infra.check_url("https://example.com")
    assert result["reachable"] is False
    assert "unexpected curl output" in result["error"]


def test_check_url_handles_missing_curl_gracefully():
    with patch("subprocess.run", side_effect=FileNotFoundError()):
        result = infra.check_url("https://example.com")
    assert result["reachable"] is False
    assert "curl not found" in result["error"]


# ── deployment_health_check ──────────────────────────────────────────────


def test_health_check_all_reachable(monkeypatch):
    monkeypatch.setattr(infra, "check_url", lambda url, **kw: {"reachable": True, "status_code": 200, "error": None})
    out = infra.deployment_health_check()
    assert f"{len(infra.TARGETS)}/{len(infra.TARGETS)} endpoints reachable" in out
    assert "UNREACHABLE" not in out


def test_health_check_partial_outage_reported_honestly(monkeypatch):
    def fake_check(url, **kw):
        if "api" in url:
            return {"reachable": False, "status_code": None, "error": "connection refused"}
        return {"reachable": True, "status_code": 200, "error": None}

    monkeypatch.setattr(infra, "check_url", fake_check)
    out = infra.deployment_health_check()
    assert "UNREACHABLE — connection refused" in out
    assert "1/3 endpoints reachable" in out


def test_health_check_never_claims_full_readiness_audit(monkeypatch):
    monkeypatch.setattr(infra, "check_url", lambda url, **kw: {"reachable": True, "status_code": 200, "error": None})
    out = infra.deployment_health_check()
    assert "not a full readiness audit" in out
    assert "not that the product is ready to sell" in out


# ── one real, live check (not mocked) ────────────────────────────────────


def test_real_live_check_against_production_website():
    # No mocking: a genuine outbound curl. This can fail if the real site
    # is actually down -- that would be correct, honest behavior, not a
    # test bug. Confirms the module's actual curl invocation is valid.
    result = infra.check_url("https://www.nitedsp.co.uk")
    assert result["reachable"] is True
    assert result["status_code"] == 200
