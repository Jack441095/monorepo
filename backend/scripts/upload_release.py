#!/usr/bin/env python3
"""Upload one immutable release artifact and register its verified row.

Usage is intentionally explicit about product/version/platform/architecture.
The command uploads bytes to the configured release storage first, then calls
the authenticated admin endpoint to recompute and register the checksum.  It
never accepts customer documents and never prints storage credentials.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

import httpx

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.storage import StorageError, object_storage_key, get_storage  # noqa: E402


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _default_storage_key(product: str, version: str, source: Path) -> str:
    return object_storage_key(f"releases/{product}/{version}/{source.name}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("product", help="internal product slug, e.g. nite-submit")
    parser.add_argument("version", help="version, e.g. 0.2.0")
    parser.add_argument("platform", choices=("macos", "windows", "linux"))
    parser.add_argument("architecture", help="release architecture, e.g. arm64 or x64")
    parser.add_argument("artifact", type=Path, help="local ZIP/artifact path")
    parser.add_argument("--channel", choices=("dev", "beta", "private-beta", "stable"), default="stable")
    parser.add_argument("--storage-key", help="override the immutable object key")
    parser.add_argument("--release-notes", default=None)
    parser.add_argument("--api-url", default=os.getenv("NITE_DSP_API_URL", "http://localhost:8000"))
    parser.add_argument("--admin-key", default=os.getenv("ADMIN_API_KEY", ""))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source = args.artifact.expanduser().resolve()
    if not source.is_file():
        print(f"artifact not found: {source}", file=sys.stderr)
        return 2
    if not args.admin_key:
        print("ADMIN_API_KEY or --admin-key is required; no upload attempted", file=sys.stderr)
        return 2

    try:
        storage_key = object_storage_key(args.storage_key or _default_storage_key(args.product, args.version, source))
    except ValueError as exc:
        print(f"invalid storage key: {exc}", file=sys.stderr)
        return 2

    checksum = sha256_file(source)
    try:
        get_storage().put_file(source, storage_key, checksum)
    except StorageError as exc:
        print(f"release upload failed: {exc}", file=sys.stderr)
        return 1

    endpoint = (
        f"{args.api_url.rstrip('/')}/admin/releases/"
        f"{quote(args.product, safe='')}/{quote(args.version, safe='')}/"
        f"{quote(args.platform, safe='')}/{quote(args.architecture, safe='')}"
    )
    payload = {
        "product_id": args.product,
        "version": args.version,
        "platform": args.platform,
        "architecture": args.architecture,
        "channel": args.channel,
        "checksum_sha256": checksum,
        "storage_key": storage_key,
        "release_notes": args.release_notes,
    }
    try:
        response = httpx.put(
            endpoint,
            headers={"X-Admin-Key": args.admin_key, "Content-Type": "application/json"},
            json=payload,
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        print(f"release registration failed: {exc}", file=sys.stderr)
        return 1
    if not response.is_success:
        print(f"release registration failed ({response.status_code}): {response.text}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "status": "registered",
                "product_id": args.product,
                "version": args.version,
                "platform": args.platform,
                "architecture": args.architecture,
                "channel": args.channel,
                "checksum_sha256": checksum,
                "storage_key": storage_key,
                "registration": response.json(),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
