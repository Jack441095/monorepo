#!/usr/bin/env python3
"""Securely fetch the pinned ONNX model used by KENN hybrid retrieval."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import urllib.request
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "artifacts" / "models" / "minilm"

# Pin the revision and content digests so a mutable upstream branch cannot
# silently change the model that KENN indexes and executes.
MODEL_REVISION = "751bff37182d3f1213fa05d7196b954e230abad9"
BASE_URL = f"https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/{MODEL_REVISION}"
MODEL_URL = f"{BASE_URL}/onnx/model.onnx"
TOKENIZER_URL = f"{BASE_URL}/tokenizer.json"
MODEL_SHA256 = "759c3cd2b7fe7e93933ad23c4c9181b7396442a2ed746ec7c1d46192c469c46e"
TOKENIZER_SHA256 = "da0e79933b9ed51798a3ae27893d3c5fa4a201126cef75586296df9b4d2c62a0"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download_file(url: str, dest_path: Path, *, expected_sha256: str | None = None) -> bool:
    """Download one file over verified TLS and optionally verify its digest."""
    print(f"Downloading: {url}")
    print(f"Destination: {dest_path}")
    temp_path = dest_path.with_name(f".{dest_path.name}.download")
    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.unlink(missing_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "KENN-Fetcher/1.0"})
        # Use urllib's default verified TLS context. Model artifacts are code-like
        # inputs and must never be fetched with certificate checks disabled.
        with urllib.request.urlopen(req, timeout=60) as response, temp_path.open("wb") as out_file:
            total_size = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            block_size = 64 * 1024
            while True:
                buffer = response.read(block_size)
                if not buffer:
                    break
                downloaded += len(buffer)
                out_file.write(buffer)
                if total_size > 0:
                    percent = (downloaded / total_size) * 100
                    sys.stdout.write(
                        f"\rProgress: {downloaded / (1024 * 1024):.1f} MB / "
                        f"{total_size / (1024 * 1024):.1f} MB ({percent:.1f}%)"
                    )
                    sys.stdout.flush()

        print()
        if expected_sha256:
            actual_sha256 = _sha256(temp_path)
            if actual_sha256 != expected_sha256:
                raise ValueError(
                    "SHA-256 mismatch: "
                    f"expected {expected_sha256}, downloaded {actual_sha256}"
                )
        temp_path.replace(dest_path)
        print(f"Successfully saved to {dest_path}")
        return True
    except Exception as exc:
        temp_path.unlink(missing_ok=True)
        print(f"Failed to download {url}: {exc}")
        return False


def _installed_files_are_valid(model_path: Path, tokenizer_path: Path) -> bool:
    return (
        model_path.is_file()
        and tokenizer_path.is_file()
        and _sha256(model_path) == MODEL_SHA256
        and _sha256(tokenizer_path) == TOKENIZER_SHA256
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch pinned ONNX weights for KENN retrieval.")
    parser.add_argument("--force", action="store_true", help="Replace valid existing model files")
    args = parser.parse_args()

    print("=========================================================")
    print(" KENN ONNX Embedding Model Fetcher (all-MiniLM-L6-v2)")
    print("=========================================================\n")

    model_path = MODEL_DIR / "model.onnx"
    tokenizer_path = MODEL_DIR / "tokenizer.json"

    if _installed_files_are_valid(model_path, tokenizer_path) and not args.force:
        print(f"Verified model files already exist at {MODEL_DIR}. Use --force to re-download.")
        return 0

    MODEL_DIR.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="kenn-minilm-", dir=MODEL_DIR.parent) as staging:
        staging_dir = Path(staging)
        staged_tokenizer = staging_dir / "tokenizer.json"
        staged_model = staging_dir / "model.onnx"
        if not download_file(TOKENIZER_URL, staged_tokenizer, expected_sha256=TOKENIZER_SHA256):
            return 1
        if not download_file(MODEL_URL, staged_model, expected_sha256=MODEL_SHA256):
            return 1

        try:
            json.loads(staged_tokenizer.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            print(f"Downloaded tokenizer is invalid: {exc}")
            return 1

        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        staged_tokenizer.replace(tokenizer_path)
        staged_model.replace(model_path)

    print("\n---------------------------------------------------------")
    print(" ONNX Embedding Model Download Complete and Verified!")
    print(" Run `python3 apps/backend/src/kenn/main.py build` to build the hybrid index.")
    print("---------------------------------------------------------\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
