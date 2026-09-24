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
import io
import json
import math
import os
import shutil
import socket
import struct
import subprocess
import tarfile
import tempfile
import time
import urllib.request
import wave
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
    "packages/mix-review/core",  # KENN's own Mix Review engine (loaded by core/local_mix_review_service.py)
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


# Installed but never imported by the app: pip, Hugging Face download tooling (pulled in by
# tokenizers) and uvicorn's optional speedups (the app serves HTTP with the standard library).
PRUNE_PACKAGES = ("pip", "huggingface_hub", "hf_xet", "uvloop", "httptools", "watchfiles", "websockets")


def prune_python(resources: Path) -> int:
    """Remove unused packages and test suites from site-packages; returns bytes saved."""
    site = next((resources / "python" / "lib").glob("python3.*")) / "site-packages"
    doomed = [site / name for name in PRUNE_PACKAGES if (site / name).is_dir()]
    doomed += [p for name in PRUNE_PACKAGES for p in site.glob(f"{name}-*.dist-info")]
    doomed += [p for p in site.rglob("*") if p.is_dir() and p.name in {"tests", "test"}]
    saved = 0
    for path in doomed:
        if path.exists():
            saved += sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
            shutil.rmtree(path)
    return saved


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _sine_wav(seconds: float = 2.0, rate: int = 44100) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        frames = bytearray()
        for n in range(int(seconds * rate)):
            value = int(8000 * math.sin(2 * math.pi * 110 * n / rate))
            frames += struct.pack("<hh", value, value)
        handle.writeframes(bytes(frames))
    return buffer.getvalue()


def smoke_test(app: Path) -> dict[str, str]:
    """Start the bundled KENN with an empty environment and exercise its main paths."""
    resources = app / "Contents" / "Resources"
    port = _free_port()
    with tempfile.TemporaryDirectory(prefix="kenn-app-smoke-") as data:
        environment = {
            "HOME": os.environ.get("HOME", "/tmp"), "PATH": "/usr/bin:/bin", "PYTHONNOUSERSITE": "1",
            "PYTHONPATH": f"{resources}/kenn/apps/backend/src:{resources}/kenn/packages/chat",
            "KENN_DATA_ROOT": data, "KENN_PORT": str(port),
        }
        server = subprocess.Popen(
            [str(resources / "python" / "bin" / "python3"), str(resources / "kenn/apps/backend/src/kenn/app_entry.py")],
            env=environment, cwd=data, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        base = f"http://127.0.0.1:{port}"
        try:
            for _ in range(120):
                try:
                    health = json.load(urllib.request.urlopen(f"{base}/api/health", timeout=2))
                    break
                except OSError:
                    if server.poll() is not None:
                        raise SystemExit("Smoke test: KENN exited during start-up:\n" + server.stderr.read().decode()[-2000:])
                    time.sleep(1)
            else:
                raise SystemExit("Smoke test: KENN did not answer /api/health within 120 s.")
            mode = health.get("subsystems", {}).get("knowledge_index", {}).get("active_mode")
            setup = json.load(urllib.request.urlopen(f"{base}/api/setup/status", timeout=10))
            ask = urllib.request.Request(f"{base}/kenn/api/ask", method="POST", headers={"Content-Type": "application/json"},
                                         data=json.dumps({"session_id": "smoke", "question": "What does Note Echo do?",
                                                          "stream": False}).encode())
            answer = json.load(urllib.request.urlopen(ask, timeout=120))
            boundary = "kennsmoke"
            body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"smoke.wav\"\r\n"
                    f"Content-Type: audio/wav\r\n\r\n").encode() + _sine_wav() + f"\r\n--{boundary}--\r\n".encode()
            review_request = urllib.request.Request(f"{base}/api/mix-review", method="POST", data=body,
                                                    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
            review = json.load(urllib.request.urlopen(review_request, timeout=120))
        finally:
            server.terminate()
            server.wait(timeout=30)
    checks = {
        "health": bool(health.get("ok")),
        "hybrid_retrieval": mode == "hybrid",
        "setup_status": setup.get("schema") == "kenn.setup_status.v1",
        "cited_answer": bool(answer.get("answer")) and bool(answer.get("sources")),
        "mix_review": review.get("ok") is True,
    }
    if not all(checks.values()):
        raise SystemExit(f"Smoke test failed: {checks}")
    return {"smoke_test": "passed: " + ", ".join(checks)}


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


def build_dmg(app: Path, output: Path, manifest: dict) -> dict[str, str]:
    """KENN.app plus an Applications link, as a compressed read-only disk image."""
    version = manifest.get("source_git_commit", "")[:7] or "dev"
    staging = output / "dmg-staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    _run(["ditto", str(app), str(staging / app.name)])  # ditto keeps the signature and extended attributes
    (staging / "Applications").symlink_to("/Applications")
    dmg = output / f"KENN-beta-{version}.dmg"
    if dmg.exists():
        dmg.unlink()
    _run(["hdiutil", "create", "-volname", "KENN", "-srcfolder", str(staging), "-ov", "-format", "UDZO", str(dmg)],
         stdout=subprocess.DEVNULL)
    shutil.rmtree(staging)
    return {"dmg": str(dmg), "dmg_mb": str(round(dmg.stat().st_size / 1e6, 1)), "dmg_sha256": _sha256(dmg)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runtime", type=Path, required=True, help=f"path to {RUNTIME_NAME}")
    parser.add_argument("--data-root", type=Path, required=True, help="KENN checkout holding the built index, notes, models and UI")
    parser.add_argument("--code-root", type=Path, default=KENN_ROOT)
    parser.add_argument("--output", type=Path, required=True, help="folder to write KENN.app into")
    parser.add_argument("--dmg", action="store_true", help="also write a compressed drag-to-Applications disk image")
    args = parser.parse_args()

    app = args.output / "KENN.app"
    if app.exists():
        shutil.rmtree(app)
    resources, kenn = app / "Contents" / "Resources", app / "Contents" / "Resources" / "kenn"
    build_launcher(app)
    resources.mkdir(parents=True, exist_ok=True)
    python = install_python(resources, args.runtime)
    pruned = prune_python(resources)
    copy_code(kenn, args.code_root)
    data = copy_data(kenn, args.data_root)
    data.update(smoke_test(app))
    data["pruned_mb"] = str(round(pruned / 1e6, 1))
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=args.code_root, capture_output=True, text=True).stdout.strip()
    size = sum(p.stat().st_size for p in app.rglob("*") if p.is_file())
    manifest = {
        "schema": "kenn.app_build.v1", "built_at": datetime.now(timezone.utc).isoformat(),
        "source_git_commit": commit, "python": RUNTIME_NAME, "python_sha256": RUNTIME_SHA256,
        **data, "size_bytes": size, "signing": "ad-hoc (not notarized)",
    }
    (resources / "build_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    _run(["codesign", "--force", "--deep", "--sign", "-", str(app)], stdout=subprocess.DEVNULL)
    result = {"app": str(app), "python": str(python), "size_mb": round(size / 1e6, 1), **data}
    if args.dmg:
        result.update(build_dmg(app, args.output, manifest))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
