from pathlib import Path

import pytest

from scripts.upload_release import _canonical_storage_key


def test_release_cli_uses_platform_and_architecture_in_default_key(tmp_path: Path):
    source = tmp_path / "Submit-0.2.0-macOS.zip"

    assert _canonical_storage_key(
        "nite-submit", "0.2.0", "macos", "arm64", source
    ) == "releases/nite-submit/0.2.0/macos/arm64/Submit-0.2.0-macOS.zip"


def test_release_cli_rejects_noncanonical_identity_components(tmp_path: Path):
    with pytest.raises(ValueError):
        _canonical_storage_key("nite-submit", "0.2.0", "..", "arm64", tmp_path / "Submit.zip")
