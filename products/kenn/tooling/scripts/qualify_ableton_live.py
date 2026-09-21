#!/usr/bin/env python3
"""Capture a provenance-labelled, read-only Ableton qualification snapshot.

The default mode reads the local KENN companion's session endpoint and exits
non-zero unless a usable Live snapshot is returned. The companion owns the
selected Live transport, so this probe does not open a competing connection.
``--mode mock`` is deterministic harness coverage only; its output is
explicitly marked as mock and cannot be used as real-Live evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


SCHEMA = "kenn.ableton_qualification.v1"


def _mock_snapshot() -> dict[str, Any]:
    return {
        "status": "connected",
        "backend": "mock",
        "host": "mock",
        "port": 0,
        "tempo": 120.0,
        "is_playing": False,
        "tracks": [
            {"index": 0, "name": "Vocal", "volume": 0.5, "pan": 0.0, "muted": False, "soloed": False, "armed": False, "devices": []},
            {"index": 1, "name": "Drum Bus", "volume": 0.7, "pan": 0.0, "muted": False, "soloed": False, "armed": False, "devices": []},
        ],
        "scenes": [],
    }


def _real_snapshot(endpoint: str) -> dict[str, Any]:
    url = endpoint.rstrip("/") + "/api/ableton/osc/session"
    with urllib.request.urlopen(url, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload if isinstance(payload, dict) else {"status": "offline", "tracks": []}


def qualify(
    mode: str = "real",
    endpoint: str = "http://127.0.0.1:8090",
    required_backend: str = "",
) -> dict[str, Any]:
    is_mock = mode == "mock"
    started = time.perf_counter()
    try:
        snapshot = _mock_snapshot() if is_mock else _real_snapshot(endpoint)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        snapshot = {"status": "offline", "tracks": [], "error": f"{type(exc).__name__}: {exc}"}
    usable = snapshot.get("status") == "connected" and isinstance(snapshot.get("tracks"), list)
    tracks = snapshot.get("tracks", []) if isinstance(snapshot.get("tracks"), list) else []
    identity_ok = all(
        isinstance(track, dict) and "index" in track and "name" in track
        for track in tracks
    )
    observed_backend = str(snapshot.get("backend", "unknown"))
    backend_match = not required_backend or observed_backend == required_backend
    checks = {
        "connected": usable,
        "track_identity_fields": identity_ok,
        "read_only_probe": True,
        "backend_match": backend_match,
    }
    canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=str).encode()
    return {
        "schema": SCHEMA,
        "status": "passed" if usable and identity_ok and backend_match else "blocked",
        "evidence_kind": "deterministic_mock" if is_mock else "real_live",
        "captured_at": time.time(),
        "host_os": platform.platform(),
        "mode": mode,
        "backend": observed_backend,
        "required_backend": required_backend or None,
        "session_version": hashlib.sha256(canonical).hexdigest(),
        "checks": checks,
        "snapshot": snapshot,
        "runtime_ms": round((time.perf_counter() - started) * 1000.0, 3),
        "limitations": [
            "This probe is read-only and does not qualify mutation, readback, native undo, or crash recovery.",
            "A deterministic_mock result is harness evidence only and is never real-Live evidence.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("real", "mock"), default="real")
    parser.add_argument("--endpoint", default="http://127.0.0.1:8090", help="KENN companion URL")
    parser.add_argument(
        "--require-backend",
        default="",
        help="Fail unless the snapshot reports this exact backend identifier",
    )
    parser.add_argument("--output", type=Path, help="Optional JSON output path")
    args = parser.parse_args()
    result = qualify(args.mode, args.endpoint, args.require_backend)
    rendered = json.dumps(result, indent=2, sort_keys=True, default=str)
    if args.output:
        args.output.expanduser().resolve().write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
