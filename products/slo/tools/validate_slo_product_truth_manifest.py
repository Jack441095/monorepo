#!/usr/bin/env python3
"""Validate the fail-closed SLO product truth manifest."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "SLO_PRODUCT_TRUTH_MANIFEST_V1.json"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main() -> int:
    data = json.loads(MANIFEST.read_text())
    assert data["product_id"] == "slo"
    assert data["display_name"] == "SLO"
    assert data["identity"]["product_version"] is None
    assert data["identity"]["version_status"] == "not_defined"
    assert data["source"]["shared_canonical_candidate"]["dirty_entries"] == 49
    assert git("merge-base", "--is-ancestor", data["source"]["product_code_checkpoint_sha"], "HEAD") == ""
    assert git("merge-base", "--is-ancestor", data["source"]["estate_registry_commit"], "HEAD") == ""
    assert git("status", "--porcelain") == ""
    assert "WAV" in data["supported_scope"]["enabled_input_formats"]
    assert data["supported_scope"]["not_enabled_input_formats"] == ["AIFF", "FLAC", "MP3"]
    assert data["supported_scope"]["read_only_default"] is True
    assert data["release_authority"]["authority"] == "platform"
    assert data["release_authority"]["release_ready"] is False
    assert data["release_authority"]["notarised"] is False
    assert data["truth_controls"]["owner_approved"] is False
    assert data["truth_controls"]["protected_data_accessed"] is False
    assert (ROOT / "SLO_V1_WORKING_PRODUCT_DEFINITION.md").is_file()
    assert "ssm_qual_full" in (ROOT / "SmartSampleManager/CMakeLists.txt").read_text()
    print("slo_product_truth_manifest=valid")
    print("product=slo")
    print("version_status=not_defined")
    print("enabled_formats=WAV")
    print("release_ready=false")
    print("owner_approved=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
