import json
from pathlib import Path

import pytest

from scripts.upload_release import _canonical_storage_key, main


def test_release_cli_uses_platform_and_architecture_in_default_key(tmp_path: Path):
    source = tmp_path / "Submit-0.2.0-macOS.zip"

    assert _canonical_storage_key(
        "nite-submit", "0.2.0", "macos", "arm64", source
    ) == "releases/nite-submit/0.2.0/macos/arm64/Submit-0.2.0-macOS.zip"


def test_release_cli_rejects_noncanonical_identity_components(tmp_path: Path):
    with pytest.raises(ValueError):
        _canonical_storage_key("nite-submit", "0.2.0", "..", "arm64", tmp_path / "Submit.zip")


def test_release_cli_dry_run_never_requires_credentials_or_upload(tmp_path: Path, capsys):
    source = tmp_path / "Submit.zip"
    source.write_bytes(b"release bytes")

    assert main(
        ["nite-submit", "0.2.0", "macos", "arm64", str(source), "--dry-run"]
    ) == 0

    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "dry-run"
    assert result["size_bytes"] == len(b"release bytes")
    assert result["storage_key"] == "releases/nite-submit/0.2.0/macos/arm64/Submit.zip"
    assert len(result["checksum_sha256"]) == 64
