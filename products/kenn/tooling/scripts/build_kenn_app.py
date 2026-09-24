#!/usr/bin/env python3
"""Build the self-contained KENN beta app (KENN.app) for Apple Silicon Macs.

The app needs no terminal, no repository and no system Python:

    KENN.app/Contents/MacOS/KENN               Swift launcher (window + starts the server)
    KENN.app/Contents/Resources/python/        standalone CPython with KENN's runtime packages
    KENN.app/Contents/Resources/kenn/          KENN in its repository layout (so paths.py needs no changes)

Code comes from this checkout (``--code-root``). Git-ignored data (the active
knowledge index, notes, the embedding model, the built UI, the native DSP
module) comes from ``--data-root``, normally the main checkout where they were
built. Everything the app writes at runtime goes to
``~/Library/Application Support/KENN`` (``kenn/app_entry.py``).

The result is ad-hoc signed only; Developer ID signing and notarization are a
separate, credentialed step.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path

KENN_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_SHA256 = "d3904bd6a072246e07aa0bdadee9a14e80521e42a943c0848059feb16a2816dc"
RUNTIME_NAME = "cpython-3.13.15+20260901-aarch64-apple-darwin-install_only_stripped.tar.gz"
# Runtime packages: requirements.txt minus test tools and the optional heavy librosa.
EXCLUDED_REQUIREMENTS = ("pytest", "librosa")
CODE_TREES = (
    "apps/backend/src/kenn",
    "packages/chat",
    "integrations/ableton-osc",
)
CODE_IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", "tests", "data", "artifacts", "Training_Data_Notes", ".runtime", "*.so",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _run(command: list[str], **kwargs) -> None:
    print("+", " ".join(command[:6]), "..." if len(command) > 6 else "")
    subprocess.run(command, check=True, **kwargs)


def build_launcher(app: Path) -> None:
    source = KENN_ROOT / "apps" / "desktop" / "macos"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    plist = (source / "Info.plist").read_text(encoding="utf-8")
    plist = (plist.replace("<string>KENNDesktopCompanion</string>", "<string>KENN</string>")
                  .replace("<string>KENN Desktop Companion</string>", "<string>KENN</string>")
                  .replace("com.shenrendao.kenn.desktop-companion", "com.nitedsp.kenn"))
    (app / "Contents" / "Info.plist").write_text(plist, encoding="utf-8")
    _run(["swiftc", str(source / "KENNDesktopCompanion.swift"), "-o", str(app / "Contents" / "MacOS" / "KENN"),
          "-framework", "Cocoa", "-framework", "WebKit"])


def install_python(resources: Path, runtime: Path) -> Path:
    if _sha256(runtime) != RUNTIME_SHA256:
        raise SystemExit(f"{runtime.name} does not match the pinned SHA-256; refusing to bundle it.")
    with tarfile.open(runtime) as archive:
        archive.extractall(resources, filter="data")  # extracts to resources/python
    python = resources / "python" / "bin" / "python3"
    requirements = [
        line for line in (KENN_ROOT / "apps" / "backend" / "requirements.txt").read_text().splitlines()
        if line.strip() and not line.startswith("#") and not line.split(">")[0].split("[")[0].strip() in EXCLUDED_REQUIREMENTS
    ]
    requirements_file = resources / "requirements-runtime.txt"
    requirements_file.write_text("\n".join(requirements) + "\n", encoding="utf-8")
    _run([str(python), "-m", "pip", "install", "--no-cache-dir", "--disable-pip-version-check", "-q",
          "-r", str(requirements_file)])
    return python


# Helper modules the server imports from tooling/scripts at runtime (server.py puts that folder on sys.path).
RUNTIME_SCRIPTS = ("log_setup.py", "repo_python.py", "abletonosc_bundle.py")


def copy_code(kenn: Path, code_root: Path) -> None:
    for relative in CODE_TREES:
        shutil.copytree(code_root / relative, kenn / relative, ignore=CODE_IGNORE)
    (kenn / "tooling" / "scripts").mkdir(parents=True)
    for name in RUNTIME_SCRIPTS:
        shutil.copy2(code_root / "tooling" / "scripts" / name, kenn / "tooling" / "scripts" / name)


def copy_data(kenn: Path, data_root: Path) -> dict[str, str]:
    """The git-ignored runtime data, taken from the checkout where it was built."""
    source_pkg, target_pkg = data_root / "apps/backend/src/kenn", kenn / "apps/backend/src/kenn"
    index = source_pkg / "data" / "index"
    version = (index / "CURRENT").read_text(encoding="utf-8").strip()
    (target_pkg / "data" / "index" / "versions").mkdir(parents=True)
    shutil.copytree(index / "versions" / version, target_pkg / "data" / "index" / "versions" / version)
    (target_pkg / "data" / "index" / "CURRENT").write_text(version, encoding="utf-8")
    shutil.copytree(source_pkg / "Training_Data_Notes", target_pkg / "Training_Data_Notes")
    shutil.copytree(source_pkg / "artifacts" / "models" / "minilm", target_pkg / "artifacts" / "models" / "minilm")
    for native in (source_pkg / "core").glob("_kenn_dsp_native*.so"):
        shutil.copy2(native, target_pkg / "core" / native.name)
    shutil.copytree(data_root / "apps/frontend/dist", kenn / "apps/frontend/dist")
    return {"index_version": version}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runtime", type=Path, required=True, help=f"path to {RUNTIME_NAME}")
    parser.add_argument("--data-root", type=Path, required=True, help="KENN checkout holding the built index, notes, models and UI")
    parser.add_argument("--code-root", type=Path, default=KENN_ROOT)
    parser.add_argument("--output", type=Path, required=True, help="folder to write KENN.app into")
    args = parser.parse_args()

    app = args.output / "KENN.app"
    if app.exists():
        shutil.rmtree(app)
    resources, kenn = app / "Contents" / "Resources", app / "Contents" / "Resources" / "kenn"
    build_launcher(app)
    resources.mkdir(parents=True, exist_ok=True)
    python = install_python(resources, args.runtime)
    copy_code(kenn, args.code_root)
    data = copy_data(kenn, args.data_root)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=args.code_root, capture_output=True, text=True).stdout.strip()
    size = sum(p.stat().st_size for p in app.rglob("*") if p.is_file())
    manifest = {
        "schema": "kenn.app_build.v1", "built_at": datetime.now(timezone.utc).isoformat(),
        "source_git_commit": commit, "python": RUNTIME_NAME, "python_sha256": RUNTIME_SHA256,
        **data, "size_bytes": size, "signing": "ad-hoc (not notarized)",
    }
    (resources / "build_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    _run(["codesign", "--force", "--deep", "--sign", "-", str(app)], stdout=subprocess.DEVNULL)
    print(json.dumps({"app": str(app), "python": str(python), "size_mb": round(size / 1e6, 1), **data}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
