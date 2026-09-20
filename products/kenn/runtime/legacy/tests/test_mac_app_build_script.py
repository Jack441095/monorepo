"""Tests for scripts/build_mac_app.py macOS desktop app packaging helper."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_mac_app.py"


def test_build_mac_app_creates_app_structure(tmp_path, monkeypatch):
    """Verify scripts/build_mac_app.py creates AudioToo.app structure."""
    monkeypatch.setattr("scripts.build_mac_app.BUILD_DIR", tmp_path / "dist")
    monkeypatch.setattr("scripts.build_mac_app.APP_DIR", tmp_path / "dist" / "AudioToo.app")

    from scripts.build_mac_app import prepare_app_bundle

    app_path = prepare_app_bundle()

    assert app_path.exists()
    assert (app_path / "Contents" / "Info.plist").exists()
    assert (app_path / "Contents" / "MacOS" / "AudioToo").exists()
