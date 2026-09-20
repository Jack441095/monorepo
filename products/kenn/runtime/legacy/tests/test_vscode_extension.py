"""Tests for KENN Audio Dev Agent VS Code extension & /api/audio-dev HTTP endpoint."""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EXT_DIR = REPO_ROOT / "studio" / "kenn" / "kenn" / "vscode_extension"


def test_vscode_extension_manifest_and_entrypoint_exist():
    """Assert package.json and extension.js are present and valid."""
    assert (EXT_DIR / "package.json").exists()
    assert (EXT_DIR / "extension.js").exists()

    manifest = json.loads((EXT_DIR / "package.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "kenn-audio-dev"
    assert manifest["main"] == "./extension.js"
    assert "onCommand:kenn.askAudioDev" in manifest["activationEvents"]
    assert "onCommand:kenn.insertDspSnippet" in manifest["activationEvents"]

    commands = [c["command"] for c in manifest["contributes"]["commands"]]
    assert "kenn.askAudioDev" in commands
    assert "kenn.insertDspSnippet" in commands

