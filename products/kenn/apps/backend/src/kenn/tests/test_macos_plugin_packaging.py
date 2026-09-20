"""The macOS beta packager must fail closed without release credentials."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[5]
PACKAGER = REPO_ROOT / "tooling" / "scripts" / "package_macos_plugins.sh"


def _fake_command(directory: Path, name: str, body: str = "exit 0") -> None:
    path = directory / name
    path.write_text(f"#!/usr/bin/env bash\n{body}\n", encoding="utf-8")
    path.chmod(0o755)


def test_plugin_packaging_preflight_does_not_make_adhoc_release(tmp_path: Path) -> None:
    env = dict(os.environ)
    env.pop("KENN_CODESIGN_IDENTITY", None)
    env.pop("KENN_NOTARY_PROFILE", None)
    env["KENN_PLUGIN_OUTPUT_DIR"] = str(tmp_path)

    result = subprocess.run(
        ["bash", str(PACKAGER), "--preflight"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "no release archive was created" in result.stderr
    assert not list(tmp_path.iterdir())


def test_plugin_packager_publishes_only_after_all_release_gates(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _fake_command(fake_bin, "cmake")
    _fake_command(fake_bin, "codesign")
    _fake_command(fake_bin, "spctl")
    _fake_command(
        fake_bin,
        "security",
        'echo "1) ABC123 Developer ID Application: KENN Test (TESTTEAM)"',
    )
    _fake_command(fake_bin, "xcrun")
    _fake_command(
        fake_bin,
        "ditto",
        """destination=\"${@: -1}\"
source=\"$1\"
if [[ \"$1\" == \"-c\" ]]; then
    printf 'validated-test-archive' > \"${destination}\"
else
    cp -R \"${source}\" \"${destination}\"
fi""",
    )
    build_root = tmp_path / "build"
    (build_root / "VST3" / "KENN Mix Assistant.vst3").mkdir(parents=True)
    (build_root / "AU" / "KENN Mix Assistant.component").mkdir(parents=True)
    output_dir = tmp_path / "release"
    env = dict(os.environ)
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["KENN_PLUGIN_OUTPUT_DIR"] = str(output_dir)
    env["KENN_PLUGIN_BUILD_ROOT"] = str(build_root)
    env["KENN_CODESIGN_IDENTITY"] = "Developer ID Application: KENN Test (TESTTEAM)"
    env["KENN_NOTARY_PROFILE"] = "kenn-test-notary"

    result = subprocess.run(
        ["bash", str(PACKAGER), "--version", "test"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    archive = output_dir / "KENN-Mix-Assistant-test-macOS.zip"
    checksum = output_dir / "KENN-Mix-Assistant-test-macOS.zip.sha256"
    assert result.returncode == 0, result.stderr
    assert archive.read_bytes() == b"validated-test-archive"
    assert checksum.read_text(encoding="utf-8").strip().endswith(str(archive))

    original_digest = checksum.read_text(encoding="utf-8")
    repeated = subprocess.run(
        ["bash", str(PACKAGER), "--version", "test"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert repeated.returncode == 2
    assert "Refusing to overwrite" in repeated.stderr
    assert checksum.read_text(encoding="utf-8") == original_digest
