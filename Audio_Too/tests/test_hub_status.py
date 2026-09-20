"""Tests for umbrella hub status API."""

from __future__ import annotations

import sys
from pathlib import Path

WEBSITE = Path(__file__).resolve().parent.parent / "server" / "app"
sys.path.insert(0, str(WEBSITE))

from hub_status import hub_snapshot, site_url  # noqa: E402


def test_site_url() -> None:
    assert site_url("/hub").endswith("/hub")


def test_hub_modules_include_core_apps() -> None:
    data = hub_snapshot()
    ids = {m["id"] for m in data["modules"]}
    assert {"public", "faq", "dashboard", "creative_lab", "tips_web", "audiogen"}.issubset(ids)
    assert data["website_port"] == 8080
    assert data["kenn"]["app"] == "KENN"
    assert data["kenn"]["answer_mode"] in {"retrieval", "retrieval+rewrite"}
    assert "audiogen" in data
    creative = next(module for module in data["modules"] if module["id"] == "creative_lab")
    assert creative["url"].endswith("/creative-lab")
    assert creative["requires_auth"] is True
